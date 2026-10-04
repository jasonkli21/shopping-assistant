from __future__ import annotations

import json

import httpx
import pytest

from shopping.search.provider import SearchProviderError, SearchQuery
from shopping.search.tavily import TavilySearchProvider


@pytest.mark.asyncio
async def test_tavily_contract_sends_bearer_and_result_budget_and_decodes_neutral_fields():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "request_id": "tavily-request-1",
                "results": [
                    {
                        "title": "Cordless vacuum guide",
                        "url": "https://example.com/vacuum",
                        "content": "A guide to cordless designs.",
                        "score": 0.98,
                        "raw_content": "ignored",
                    }
                ],
                "usage": {"credits": 1},
            },
        )

    provider = TavilySearchProvider("test-secret", transport=httpx.MockTransport(handler))
    response = await provider.search(SearchQuery("cordless vacuum", max_results=3))

    assert seen["url"] == "https://api.tavily.com/search"
    assert seen["authorization"] == "Bearer test-secret"
    assert seen["payload"]["max_results"] == 3
    assert seen["payload"]["include_answer"] is False
    assert seen["payload"]["include_raw_content"] is False
    assert seen["payload"]["include_usage"] is True
    assert response.provider_request_id == "tavily-request-1"
    assert response.results[0].title == "Cordless vacuum guide"
    assert response.results[0].snippet == "A guide to cordless designs."
    assert response.usage_units == 1
    assert not hasattr(response.results[0], "score")


@pytest.mark.asyncio
async def test_tavily_bounds_max_results_and_accepts_empty_results():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["max_results"] == 20
        return httpx.Response(200, json={"results": []})

    provider = TavilySearchProvider("test-secret", transport=httpx.MockTransport(handler))
    response = await provider.search(SearchQuery("vacuum", max_results=40))
    assert response.results == []


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "provider_auth"),
        (403, "provider_rejected"),
        (429, "rate_limited"),
        (432, "quota_exceeded"),
        (433, "quota_exceeded"),
        (503, "provider_unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_tavily_maps_http_status_to_sanitized_error(status, code):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="provider body contains secret diagnostic")

    provider = TavilySearchProvider("test-secret", transport=httpx.MockTransport(handler))
    with pytest.raises(SearchProviderError) as captured:
        await provider.search(SearchQuery("vacuum", max_results=2))
    assert captured.value.code == code
    assert "secret" not in str(captured.value)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"results": {}},
        {"results": [None]},
        {"results": [{"title": 5, "url": "https://x.com"}]},
        {"results": [{"title": "x", "url": "https://x.com", "content": {}}]},
    ],
)
@pytest.mark.asyncio
async def test_tavily_rejects_malformed_payloads(payload):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = TavilySearchProvider("test-secret", transport=httpx.MockTransport(handler))
    with pytest.raises(SearchProviderError, match="malformed_response"):
        await provider.search(SearchQuery("vacuum", max_results=2))


@pytest.mark.asyncio
async def test_tavily_rejects_unbounded_or_malformed_usage_metadata():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [], "usage": {"credits": True}})

    provider = TavilySearchProvider("test-secret", transport=httpx.MockTransport(handler))
    with pytest.raises(SearchProviderError, match="malformed_response"):
        await provider.search(SearchQuery("vacuum", max_results=2))


@pytest.mark.asyncio
async def test_tavily_maps_timeout_without_leaking_transport_details():
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("request url and key test-secret")

    provider = TavilySearchProvider("test-secret", transport=httpx.MockTransport(handler))
    with pytest.raises(SearchProviderError, match="provider_timeout") as captured:
        await provider.search(SearchQuery("vacuum", max_results=2))
    assert "test-secret" not in str(captured.value)


def test_tavily_requires_explicit_server_side_credential():
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        TavilySearchProvider(None)
