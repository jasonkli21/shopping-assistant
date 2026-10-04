from __future__ import annotations

import json
import os

import pytest

from shopping.search.provider import SearchQuery
from shopping.search.tavily import TavilySearchProvider


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_tavily_search_smoke(record_property):
    api_key = os.getenv("TAVILY_LIVE_API_KEY")
    if not api_key:
        pytest.skip("set the dedicated TAVILY_LIVE_API_KEY to run the paid-provider smoke")
    if os.getenv("TAVILY_LIVE_ACK") != "I_ACCEPT_TAVILY_BILLABLE_CALL":
        pytest.fail("set TAVILY_LIVE_ACK=I_ACCEPT_TAVILY_BILLABLE_CALL for an explicit live call")

    query = "cordless vacuum pet hair under 400 USD"
    response = await TavilySearchProvider(api_key).search(SearchQuery(query, max_results=3))
    record_property("query_count", 1)
    record_property("query", query)
    record_property("result_count", len(response.results))
    record_property("candidate_examples", json.dumps([item.title for item in response.results]))
    record_property("provider_request_id", response.provider_request_id or "not reported")
    record_property(
        "reported_usage_units",
        "not reported" if response.usage_units is None else response.usage_units,
    )
    assert len(response.results) <= 3
