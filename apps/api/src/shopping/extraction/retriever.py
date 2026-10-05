from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RetrievedDocument:
    requested_url: str
    final_url: str
    content_type: str | None
    body: str
    content_hash: str
    retrieved_at: datetime
    decoded_bytes: int | None = None

    @property
    def url(self) -> str:
        """Compatibility alias for earlier fake fixtures."""
        return self.final_url


class PageRetriever(Protocol):
    """Retrieves bounded source content without imposing domain logic."""

    async def retrieve(self, url: str) -> RetrievedDocument: ...


class PageRetrievalError(Exception):
    """A typed, sanitized retrieval failure suitable for durable observations."""

    def __init__(
        self, code: str, message: str, *, status_code: int | None = None, bytes_read: int = 0
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.bytes_read = max(0, bytes_read)
