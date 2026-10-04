from shopping.extraction.retriever import PageRetriever, RetrievedDocument


class FakePageRetriever(PageRetriever):
    """In-memory retriever suitable for deterministic tests."""

    def __init__(self, documents: dict[str, RetrievedDocument] | None = None) -> None:
        self._documents = documents or {}

    async def retrieve(self, url: str) -> RetrievedDocument:
        try:
            return self._documents[url]
        except KeyError as exc:
            raise LookupError(f"No fake document registered for {url}") from exc
