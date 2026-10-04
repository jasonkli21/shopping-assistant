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


class SearchProvider(Protocol):
    """Provider-neutral search boundary for product and evidence discovery."""

    async def search(self, query: SearchQuery) -> list[SearchResult]: ...
