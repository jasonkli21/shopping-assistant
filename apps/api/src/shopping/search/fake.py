from shopping.search.provider import SearchProvider, SearchQuery, SearchResult


class FakeSearchProvider(SearchProvider):
    """Deterministic provider used by tests and offline development."""

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        return []
