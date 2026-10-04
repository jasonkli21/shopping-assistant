from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RetrievedDocument:
    url: str
    content_type: str | None
    body: str


class PageRetriever(Protocol):
    """Retrieves source content without imposing extraction or domain logic."""

    async def retrieve(self, url: str) -> RetrievedDocument: ...
