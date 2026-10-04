from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchQuery:
    text: str
    max_results: int = 10


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str | None = None


@dataclass(frozen=True)
class SearchResponse:
    results: list[SearchResult]
    provider_request_id: str | None = None
    usage_units: int | None = None


class SearchProvider(Protocol):
    """Provider-neutral search boundary for product and evidence discovery."""

    async def search(self, query: SearchQuery) -> SearchResponse: ...


class SearchProviderError(Exception):
    """Sanitized, stable error categories from a configured search provider."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
