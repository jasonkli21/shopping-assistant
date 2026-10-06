from __future__ import annotations

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from shopping.search.provider import SearchProviderError, SearchQuery, SearchResponse, SearchResult

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
MAX_RESPONSE_BYTES = 2_000_000


class TavilySearchProvider:
    """Small Tavily adapter that exposes only the neutral search-result contract."""

    name = "tavily"

    def __init__(
        self,
        api_key: str | None,
        *,
        timeout_seconds: float = 12,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("Tavily provider requires TAVILY_API_KEY")
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def search(self, query: SearchQuery) -> SearchResponse:
        request_body = {
            "query": query.text,
            "search_depth": "basic",
            "max_results": min(max(query.max_results, 1), 20),
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_usage": True,
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(self._timeout_seconds),
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST",
                    TAVILY_SEARCH_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=request_body,
                ) as response:
                    if response.status_code == 401:
                        raise SearchProviderError("provider_auth")
                    if response.status_code == 403:
                        raise SearchProviderError("provider_rejected")
                    if response.status_code == 429:
                        raise SearchProviderError(
                            "rate_limited",
                            retry_after_seconds=_retry_after_seconds(
                                response.headers.get("Retry-After")
                            ),
                        )
                    if response.status_code in {432, 433}:
                        raise SearchProviderError("quota_exceeded")
                    if response.status_code >= 500:
                        raise SearchProviderError("provider_unavailable")
                    if not response.is_success:
                        raise SearchProviderError("provider_rejected")

                    chunks: list[bytes] = []
                    length = 0
                    async for chunk in response.aiter_bytes():
                        length += len(chunk)
                        if length > MAX_RESPONSE_BYTES:
                            raise SearchProviderError("malformed_response")
                        chunks.append(chunk)
                    body = b"".join(chunks)
        except httpx.TimeoutException as error:
            raise SearchProviderError("provider_timeout") from error
        except httpx.RequestError as error:
            raise SearchProviderError("provider_unavailable") from error

        try:
            decoded = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise SearchProviderError("malformed_response") from error
        request_id = decoded.get("request_id") if isinstance(decoded, dict) else None
        if request_id is not None and not isinstance(request_id, str):
            raise SearchProviderError("malformed_response")
        usage_units = _decode_usage_units(decoded)
        return SearchResponse(
            results=_decode_results(decoded, min(max(query.max_results, 1), 20)),
            provider_request_id=request_id[:200] if request_id else None,
            usage_units=usage_units,
        )


def _decode_results(payload: Any, max_results: int) -> list[SearchResult]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SearchProviderError("malformed_response")
    if len(payload["results"]) > 20:
        raise SearchProviderError("malformed_response")

    output: list[SearchResult] = []
    for item in payload["results"][:max_results]:
        if not isinstance(item, dict):
            raise SearchProviderError("malformed_response")
        title = item.get("title")
        url = item.get("url")
        snippet = item.get("content")
        if (
            not isinstance(title, str)
            or not isinstance(url, str)
            or (snippet is not None and not isinstance(snippet, str))
        ):
            raise SearchProviderError("malformed_response")
        output.append(SearchResult(title=title, url=url, snippet=snippet))
    return output


def _decode_usage_units(payload: Any) -> int | None:
    if not isinstance(payload, dict) or "usage" not in payload or payload["usage"] is None:
        return None
    usage = payload["usage"]
    units = usage.get("credits") if isinstance(usage, dict) else None
    if isinstance(units, bool) or not isinstance(units, int) or not 0 <= units <= 100_000:
        raise SearchProviderError("malformed_response")
    return units


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            seconds = (retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if not 0 <= seconds <= 60:
        return None
    return seconds
