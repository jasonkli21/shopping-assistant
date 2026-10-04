from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import socket
import ssl
import zlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from email.message import Message
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx
from httpcore._backends.anyio import AnyIOBackend

from shopping.extraction.retriever import PageRetrievalError, RetrievedDocument

Resolver = Callable[[str, int], Sequence[str]]
TransportFactory = Callable[[dict[str, str]], httpx.AsyncBaseTransport]

MAX_PAGE_BYTES = 1_500_000
MAX_REDIRECTS = 5
MAX_URL_LENGTH = 2048
ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
REDIRECT_CODES = {301, 302, 303, 307, 308}


def _system_resolver(host: str, port: int) -> Sequence[str]:
    return tuple(
        dict.fromkeys(
            answer[4][0] for answer in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        )
    )


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return bool(address.is_global and not address.is_multicast and not address.is_unspecified)


def _host_and_port(url: str) -> tuple[str, int]:
    if len(url) > MAX_URL_LENGTH:
        raise PageRetrievalError("url_too_long", "The source URL exceeds the allowed length.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise PageRetrievalError("invalid_url", "The source URL is invalid.") from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise PageRetrievalError(
            "invalid_url", "Only credential-free HTTP or HTTPS URLs are allowed."
        )
    normalized_host = host.rstrip(".").lower()
    if (
        not normalized_host
        or normalized_host in {"localhost", "metadata", "instance-data"}
        or normalized_host.endswith((".localhost", ".local", ".internal"))
    ):
        raise PageRetrievalError("blocked_address", "The source host is not publicly reachable.")
    try:
        literal_address = ipaddress.ip_address(normalized_host)
    except ValueError:
        try:
            normalized_host = normalized_host.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise PageRetrievalError("invalid_url", "The source host is invalid.") from error
    else:
        if not _is_public_address(str(literal_address)):
            raise PageRetrievalError(
                "blocked_address", "The source host is not publicly reachable."
            )
        normalized_host = str(literal_address).casefold()

    actual_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    if actual_port not in {80, 443}:
        raise PageRetrievalError("blocked_port", "Only standard web ports are allowed.")
    return normalized_host, actual_port


class _PinnedNetworkBackend(AnyIOBackend):
    """Connect to the exact public IP validated before HTTPX begins the request."""

    def __init__(self, pinned_addresses: dict[str, str]) -> None:
        self._pinned_addresses = pinned_addresses

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        address = self._pinned_addresses.get(host.rstrip(".").lower())
        if address is None or not _is_public_address(address):
            raise httpcore.ConnectError("Destination was not validated for this request")
        return await super().connect_tcp(
            host=address,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class _PinnedHTTPXTransport(httpx.AsyncHTTPTransport):
    def __init__(self, pinned_addresses: dict[str, str]) -> None:
        super().__init__(verify=True, trust_env=False, limits=httpx.Limits(max_connections=1))
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=1,
            max_keepalive_connections=0,
            keepalive_expiry=0,
            retries=0,
            network_backend=_PinnedNetworkBackend(pinned_addresses),
        )


class HTTPPageRetriever:
    """Bounded HTTP retrieval with per-hop DNS validation and IP pinning."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 8,
        max_decoded_bytes: int = MAX_PAGE_BYTES,
        max_redirects: int = MAX_REDIRECTS,
        resolver: Resolver | None = None,
        transport_factory: TransportFactory | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_decoded_bytes <= 0 or max_redirects < 0:
            raise ValueError("retrieval limits must be positive")
        self._timeout_seconds = timeout_seconds
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 3))
        self._max_decoded_bytes = max_decoded_bytes
        self._max_redirects = max_redirects
        self._resolver = resolver or _system_resolver
        self._transport_factory = transport_factory or _PinnedHTTPXTransport

    async def retrieve(self, url: str) -> RetrievedDocument:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._retrieve_with_deadline(url)
        except TimeoutError as error:
            raise PageRetrievalError(
                "timeout", "The source page exceeded its retrieval deadline."
            ) from error

    async def _retrieve_with_deadline(self, url: str) -> RetrievedDocument:
        requested_url = url
        current_url = url
        seen = set()

        for redirect_number in range(self._max_redirects + 1):
            if current_url in seen:
                raise PageRetrievalError("redirect_loop", "The page redirected in a loop.")
            seen.add(current_url)
            host, port = _host_and_port(current_url)
            try:
                ipaddress.ip_address(host)
                resolved = (host,)
            except ValueError:
                try:
                    resolved = await asyncio.to_thread(self._resolver, host, port)
                except (OSError, UnicodeError) as error:
                    raise PageRetrievalError(
                        "dns_failed", "The source host could not be resolved."
                    ) from error
            unique_addresses = tuple(dict.fromkeys(resolved))
            if not unique_addresses or any(
                not _is_public_address(item) for item in unique_addresses
            ):
                raise PageRetrievalError(
                    "blocked_address", "The source host resolves to a restricted address."
                )

            transport = self._transport_factory({host: unique_addresses[0]})
            try:
                async with httpx.AsyncClient(
                    transport=transport,
                    timeout=self._timeout,
                    follow_redirects=False,
                    trust_env=False,
                    headers={
                        "User-Agent": "ShoppingAssistantResearch/1.0",
                        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                    },
                ) as client:
                    async with client.stream("GET", current_url) as response:
                        if response.status_code in REDIRECT_CODES:
                            if redirect_number >= self._max_redirects:
                                raise PageRetrievalError(
                                    "redirect_limit", "The page exceeded the redirect limit."
                                )
                            location = response.headers.get("location")
                            if not location:
                                raise PageRetrievalError(
                                    "invalid_redirect", "The page returned an incomplete redirect."
                                )
                            current_url = urljoin(current_url, location)
                            continue
                        if response.status_code >= 400:
                            raise PageRetrievalError(
                                "http_error",
                                "The source page could not be retrieved.",
                                status_code=response.status_code,
                            )
                        if response.status_code < 200 or response.status_code >= 300:
                            raise PageRetrievalError(
                                "http_error",
                                "The source page returned an unsupported response.",
                                status_code=response.status_code,
                            )

                        content_type = response.headers.get("content-type")
                        mime_type = _mime_type(content_type)
                        if mime_type not in ALLOWED_CONTENT_TYPES:
                            raise PageRetrievalError(
                                "unsupported_content_type",
                                "The source is not a supported text page.",
                            )
                        body = bytearray()
                        encoding = (
                            response.headers.get("content-encoding", "identity").strip().lower()
                        )
                        decoder = _content_decoder(encoding)
                        encoded_size = 0
                        async for chunk in response.aiter_raw():
                            encoded_size += len(chunk)
                            if encoded_size > self._max_decoded_bytes:
                                raise PageRetrievalError(
                                    "page_too_large", "The encoded page exceeds the allowed size."
                                )
                            if decoder is None:
                                _append_bounded(body, chunk, self._max_decoded_bytes)
                            else:
                                pending = chunk
                                while pending:
                                    remaining = self._max_decoded_bytes - len(body)
                                    try:
                                        decoded = decoder.decompress(pending, remaining + 1)
                                    except zlib.error as error:
                                        raise PageRetrievalError(
                                            "invalid_content_encoding",
                                            "The compressed page could not be decoded.",
                                        ) from error
                                    _append_bounded(body, decoded, self._max_decoded_bytes)
                                    pending = decoder.unconsumed_tail
                                    if not pending:
                                        break
                        if decoder is not None and (not decoder.eof or decoder.unused_data):
                            raise PageRetrievalError(
                                "invalid_content_encoding",
                                "The compressed page is invalid or incomplete.",
                            )
                        encoding = response.encoding or "utf-8"
                        decoded = bytes(body).decode(encoding, errors="replace")
                        return RetrievedDocument(
                            requested_url=requested_url,
                            final_url=str(response.url),
                            content_type=content_type,
                            body=decoded,
                            content_hash=hashlib.sha256(body).hexdigest(),
                            retrieved_at=datetime.now(UTC),
                        )
            except PageRetrievalError:
                raise
            except httpx.TimeoutException as error:
                raise PageRetrievalError("timeout", "The source page request timed out.") from error
            except httpx.HTTPError as error:
                raise PageRetrievalError(
                    "transport_error", "The source page request failed."
                ) from error

        raise PageRetrievalError("redirect_limit", "The page exceeded the redirect limit.")


def _content_decoder(encoding: str):
    if encoding in {"", "identity"}:
        return None
    if encoding in {"gzip", "x-gzip"}:
        return zlib.decompressobj(16 + zlib.MAX_WBITS)
    if encoding == "deflate":
        return zlib.decompressobj()
    raise PageRetrievalError(
        "unsupported_content_encoding", "The page uses an unsupported compression format."
    )


def _append_bounded(body: bytearray, chunk: bytes, maximum: int) -> None:
    if len(body) + len(chunk) > maximum:
        raise PageRetrievalError("page_too_large", "The decoded page exceeds the allowed size.")
    body.extend(chunk)


def _mime_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    message = Message()
    message["content-type"] = content_type
    return message.get_content_type().lower()


class _TextExtractor:
    """Small stdlib HTML text converter; never executes page scripts or markup."""

    def __init__(self) -> None:

        self._parts: list[str] = []

    def text(self, html: str) -> str:
        from html.parser import HTMLParser

        class Parser(HTMLParser):
            def __init__(self, outer: _TextExtractor) -> None:
                super().__init__(convert_charrefs=True)
                self.outer = outer
                self.ignored = 0

            def handle_starttag(self, tag: str, attrs) -> None:
                if tag in {"script", "style", "noscript", "svg", "iframe", "template"}:
                    self.ignored += 1
                elif not self.ignored and tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
                    self.outer._parts.append(" ")

            def handle_endtag(self, tag: str) -> None:
                if (
                    tag in {"script", "style", "noscript", "svg", "iframe", "template"}
                    and self.ignored
                ):
                    self.ignored -= 1
                elif not self.ignored and tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
                    self.outer._parts.append(" ")

            def handle_data(self, data: str) -> None:
                if not self.ignored:
                    self.outer._parts.append(data)

        self._parts.clear()
        Parser(self).feed(html)
        return " ".join(" ".join(self._parts).split())[:40_000]


def html_to_text(html: str) -> str:
    return _TextExtractor().text(html)
