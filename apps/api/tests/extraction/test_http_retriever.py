from __future__ import annotations

import asyncio
import gzip
import hashlib

import httpx
import pytest
from httpcore import ConnectError
from httpcore._backends.anyio import AnyIOBackend

from shopping.extraction.http_retriever import (
    HTTPPageRetriever,
    _is_public_address,
    _PinnedHTTPXTransport,
    _PinnedNetworkBackend,
    html_to_text,
)
from shopping.extraction.retriever import PageRetrievalError


def _resolver_for(addresses: dict[str, list[str]]):
    def resolve(host: str, _port: int):
        return addresses[host]

    return resolve


class BytesStream(httpx.AsyncByteStream):
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def __aiter__(self):
        yield self.payload


@pytest.mark.asyncio
async def test_retriever_returns_requested_and_final_url_hash_and_utc_time():
    factories: list[dict[str, str]] = []

    def transport_factory(pinned: dict[str, str]):
        factories.append(pinned)
        return httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                stream=BytesStream(b"<h1>Product</h1>"),
                request=request,
            )
        )

    result = await HTTPPageRetriever(
        resolver=_resolver_for({"retailer.example": ["93.184.216.34"]}),
        transport_factory=transport_factory,
    ).retrieve("https://retailer.example/item")

    assert result.requested_url == "https://retailer.example/item"
    assert result.final_url == result.requested_url
    assert result.content_hash == hashlib.sha256(b"<h1>Product</h1>").hexdigest()
    assert result.content_type == "text/html; charset=utf-8"
    assert result.retrieved_at.tzinfo is not None
    assert factories == [{"retailer.example": "93.184.216.34"}]


@pytest.mark.asyncio
async def test_retriever_validates_every_redirect_before_opening_it():
    requested: list[str] = []
    pins: list[dict[str, str]] = []

    def factory(pinned):
        pins.append(pinned)

        def handle(request):
            requested.append(str(request.url))
            return httpx.Response(
                302,
                headers={"location": "https://private.example/latest"},
                request=request,
            )

        return httpx.MockTransport(handle)

    retriever = HTTPPageRetriever(
        resolver=_resolver_for(
            {
                "retailer.example": ["93.184.216.34"],
                "private.example": ["10.0.0.8"],
            }
        ),
        transport_factory=factory,
    )
    with pytest.raises(PageRetrievalError, match="restricted address") as error:
        await retriever.retrieve("https://retailer.example/item")

    assert error.value.code == "blocked_address"
    assert requested == ["https://retailer.example/item"]
    assert pins == [{"retailer.example": "93.184.216.34"}]


@pytest.mark.asyncio
async def test_retriever_blocks_private_ip_and_mixed_public_private_dns():
    opened = False

    def factory(_pins):
        nonlocal opened
        opened = True
        return httpx.MockTransport(lambda request: httpx.Response(200, request=request))

    retriever = HTTPPageRetriever(
        resolver=_resolver_for(
            {
                "mixed.example": ["93.184.216.34", "192.168.1.10"],
                "public.example": ["93.184.216.34"],
            }
        ),
        transport_factory=factory,
    )
    with pytest.raises(PageRetrievalError) as literal:
        await retriever.retrieve("http://127.0.0.1/private")
    with pytest.raises(PageRetrievalError) as mixed:
        await retriever.retrieve("https://mixed.example/item")
    assert literal.value.code == "blocked_address"
    assert mixed.value.code == "blocked_address"
    assert opened is False


@pytest.mark.asyncio
async def test_network_backend_connects_to_pinned_ip_and_rejects_unpinned_host(monkeypatch):
    connected = []

    async def connect_tcp(_self, host, port, timeout=None, local_address=None, socket_options=None):
        connected.append((host, port))
        return object()

    monkeypatch.setattr(AnyIOBackend, "connect_tcp", connect_tcp)
    transport = _PinnedHTTPXTransport({"retailer.example": "93.184.216.34"})
    backend = transport._pool._network_backend
    assert isinstance(backend, _PinnedNetworkBackend)
    await backend.connect_tcp("retailer.example", 443)
    assert connected == [("93.184.216.34", 443)]

    with pytest.raises(ConnectError):
        await backend.connect_tcp("other.example", 443)
    assert _is_public_address("93.184.216.34")
    assert not _is_public_address("169.254.169.254")
    assert transport._pool._ssl_context.verify_mode
    assert transport._pool._ssl_context.check_hostname
    await transport.aclose()


@pytest.mark.asyncio
async def test_retriever_caps_decoded_content_and_rejects_unsupported_mime():
    compressed = gzip.compress(b"x" * 5_000_000)

    def transport_factory(_pins):
        def handle(request):
            return httpx.Response(
                200,
                headers={"content-type": "text/html", "content-encoding": "gzip"},
                stream=BytesStream(compressed),
                request=request,
            )

        return httpx.MockTransport(handle)

    retriever = HTTPPageRetriever(
        max_decoded_bytes=100_000,
        resolver=_resolver_for({"retailer.example": ["93.184.216.34"]}),
        transport_factory=transport_factory,
    )
    with pytest.raises(PageRetrievalError) as too_large:
        await retriever.retrieve("https://retailer.example/item")
    assert too_large.value.code == "page_too_large"

    unsupported = HTTPPageRetriever(
        resolver=_resolver_for({"retailer.example": ["93.184.216.34"]}),
        transport_factory=lambda _pins: httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "application/pdf"}, content=b"%PDF", request=request
            )
        ),
    )
    with pytest.raises(PageRetrievalError) as mime:
        await unsupported.retrieve("https://retailer.example/file")
    assert mime.value.code == "unsupported_content_type"


@pytest.mark.asyncio
async def test_retriever_increments_gzip_within_decoded_limit():
    payload = b"<h1>Product</h1>"
    compressed = gzip.compress(payload)
    retriever = HTTPPageRetriever(
        max_decoded_bytes=100,
        resolver=_resolver_for({"retailer.example": ["93.184.216.34"]}),
        transport_factory=lambda _pins: httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html", "content-encoding": "gzip"},
                stream=BytesStream(compressed),
                request=request,
            )
        ),
    )
    result = await retriever.retrieve("https://retailer.example/item")
    assert result.body == payload.decode()
    assert result.content_hash == hashlib.sha256(payload).hexdigest()


@pytest.mark.asyncio
async def test_retriever_returns_typed_timeout_and_redirect_limit_failures():
    timeout = HTTPPageRetriever(
        resolver=_resolver_for({"retailer.example": ["93.184.216.34"]}),
        transport_factory=lambda _pins: httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("delayed", request=request))
        ),
    )
    with pytest.raises(PageRetrievalError) as timeout_error:
        await timeout.retrieve("https://retailer.example/item")
    assert timeout_error.value.code == "timeout"

    redirects = []

    def loop_factory(_pins):
        return httpx.MockTransport(
            lambda request: (
                redirects.append(str(request.url))
                or httpx.Response(302, headers={"location": "/again"}, request=request)
            )
        )

    loop = HTTPPageRetriever(
        max_redirects=1,
        resolver=_resolver_for({"retailer.example": ["93.184.216.34"]}),
        transport_factory=loop_factory,
    )
    with pytest.raises(PageRetrievalError) as redirect_error:
        await loop.retrieve("https://retailer.example/item")
    assert redirect_error.value.code == "redirect_limit"
    assert len(redirects) == 2


@pytest.mark.asyncio
async def test_overall_deadline_includes_stalled_dns_and_slow_drip_body():
    def stalled_dns(_host, _port):
        import time

        time.sleep(0.1)
        return ["93.184.216.34"]

    stalled = HTTPPageRetriever(timeout_seconds=0.02, resolver=stalled_dns)
    with pytest.raises(PageRetrievalError) as dns_error:
        await stalled.retrieve("https://retailer.example/item")
    assert dns_error.value.code == "timeout"

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"<h1>"
            await asyncio.sleep(0.03)
            yield b"Product"
            await asyncio.sleep(0.03)
            yield b"</h1>"

    async def slow_response(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            stream=SlowStream(),
            request=request,
        )

    slow = HTTPPageRetriever(
        timeout_seconds=0.05,
        resolver=_resolver_for({"retailer.example": ["93.184.216.34"]}),
        transport_factory=lambda _pins: httpx.MockTransport(slow_response),
    )
    with pytest.raises(PageRetrievalError) as slow_error:
        await slow.retrieve("https://retailer.example/item")
    assert slow_error.value.code == "timeout"

    redirect_count = 0

    async def slow_redirect(request):
        nonlocal redirect_count
        redirect_count += 1
        await asyncio.sleep(0.03)
        return httpx.Response(
            302,
            headers={"location": "/step-" + str(redirect_count)},
            request=request,
        )

    redirecting = HTTPPageRetriever(
        timeout_seconds=0.05,
        max_redirects=3,
        resolver=_resolver_for({"retailer.example": ["93.184.216.34"]}),
        transport_factory=lambda _pins: httpx.MockTransport(slow_redirect),
    )
    with pytest.raises(PageRetrievalError) as redirect_error:
        await redirecting.retrieve("https://retailer.example/item")
    assert redirect_error.value.code == "timeout"
    assert redirect_count == 2


def test_html_to_text_omits_executable_and_nonvisible_content():
    text = html_to_text(
        "<h1>Vacuum</h1><script>ignore me</script><style>hidden</style>"
        "<p>Pet hair model</p><iframe>frame</iframe>"
    )
    assert text == "Vacuum Pet hair model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pass@shop.example/item",
        "http://shop.example:8080/item",
        "http://metadata.google.internal/latest/meta-data/",
        "https://shop.example/item#fragment",
    ],
)
async def test_retriever_rejects_unsafe_url_forms_without_dns(url):
    retriever = HTTPPageRetriever(
        resolver=lambda _host, _port: pytest.fail("unsafe URL must be rejected before DNS"),
        transport_factory=lambda _pins: pytest.fail("unsafe URL must not open transport"),
    )
    with pytest.raises(PageRetrievalError):
        await retriever.retrieve(url)
