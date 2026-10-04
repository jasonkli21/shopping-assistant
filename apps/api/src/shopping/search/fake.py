from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from shopping.search.provider import SearchProviderError, SearchQuery, SearchResponse, SearchResult


@dataclass(frozen=True)
class FakeSearchFailure:
    code: str


class FakeSearchProvider:
    """Keyed deterministic search responses for offline development and tests."""

    name = "fake"

    def __init__(
        self,
        responses: Mapping[str, list[SearchResult] | SearchResponse | FakeSearchFailure]
        | None = None,
        *,
        delay_seconds: float = 0,
    ) -> None:
        self.responses = dict(responses or {})
        self.delay_seconds = delay_seconds
        self.calls: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> SearchResponse:
        self.calls.append(query)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        response = self.responses.get(query.text, [])
        if isinstance(response, FakeSearchFailure):
            raise SearchProviderError(response.code)
        if isinstance(response, SearchResponse):
            return SearchResponse(
                results=list(response.results[: query.max_results]),
                provider_request_id=response.provider_request_id,
                usage_units=response.usage_units,
            )
        return SearchResponse(results=list(response[: query.max_results]))
