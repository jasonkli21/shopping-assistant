"""Deterministic provider wiring for the real API used by Playwright."""

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated

from fastapi import Query

from shopping.extraction.fake import FakePageRetriever
from shopping.extraction.retriever import RetrievedDocument
from shopping.extraction.schemas import CatalogExtraction
from shopping.extraction.task import FakeCatalogExtractionTask
from shopping.integrations.personal_ai.client import AIProviderError, AIRequest
from shopping.integrations.personal_ai.fake import FakePersonalAIClient
from shopping.main import app
from shopping.search.provider import SearchProviderError, SearchQuery, SearchResponse, SearchResult

RUN_AT = datetime(2026, 10, 7, 12, tzinfo=UTC)

PRODUCTS = (
    {
        "key": "ax4",
        "brand": "Acme",
        "name": "CleanVac",
        "model": "AX-4",
        "color": "Graphite",
        "runtime": 60,
        "url": "https://acme.example/cleanvac-ax4/specifications",
    },
    {
        "key": "bp2",
        "brand": "Breez",
        "name": "CleanPet",
        "model": "BP-2",
        "color": "Ocean",
        "runtime": 48,
        "url": "https://breez.example/cleanpet-bp2/specifications",
    },
)


def _document(product: dict) -> RetrievedDocument:
    brand = product["brand"]
    name = product["name"]
    model = product["model"]
    color = product["color"]
    runtime = product["runtime"]
    body = (
        "<!doctype html><html><head><title>"
        f"{brand} {name} {model} specifications</title></head><body>"
        f"<h1>{brand} {name} {model}</h1>"
        "<p>Vacuum specifications.</p>"
        f"<p>{brand} {name} {model} Color {color}: measured "
        f"{runtime} minutes runtime in normal mode.</p>"
        "</body></html>"
    )
    encoded = body.encode("utf-8")
    return RetrievedDocument(
        requested_url=product["url"],
        final_url=product["url"],
        content_type="text/html; charset=utf-8",
        body=body,
        content_hash=sha256(encoded).hexdigest(),
        retrieved_at=RUN_AT,
        decoded_bytes=len(encoded),
    )


def _catalog_output(product: dict) -> CatalogExtraction:
    brand = product["brand"]
    name = product["name"]
    model = product["model"]
    color = product["color"]
    return CatalogExtraction.model_validate(
        {
            "product_name": name,
            "product_name_excerpt": name,
            "brand": brand,
            "brand_excerpt": brand,
            "category": "Vacuum",
            "category_excerpt": "Vacuum",
            "model_family": model,
            "model_family_excerpt": model,
            "variant_attributes": {"color": color},
            "variant_attribute_excerpts": {"color": color},
            "identifiers": [
                {
                    "scheme": "manufacturer_model",
                    "namespace": f"brand:{brand.casefold()}|category:vacuum",
                    "value": model,
                    "excerpt": model,
                }
            ],
        }
    )


class DeterministicSearchProvider:
    """Returns two fixed discovery candidates and one source per selected variant."""

    name = "e2e-fake"

    async def search(self, query: SearchQuery) -> SearchResponse:
        lowered = query.text.casefold()
        if "e2e_trigger_research_failure" in lowered:
            raise SearchProviderError("provider_auth")
        matching = next(
            (product for product in PRODUCTS if product["model"].casefold() in lowered),
            None,
        )
        selected = [matching] if matching else list(PRODUCTS)
        return SearchResponse(
            results=[
                SearchResult(
                    title=(
                        f"{product['brand']} {product['name']} {product['model']} "
                        f"{product['color']}"
                    ),
                    url=product["url"],
                    snippet=(
                        f"{product['name']} vacuum specifications; "
                        f"measured runtime {product['runtime']} minutes."
                    ),
                )
                for product in selected
            ][: query.max_results],
            provider_request_id="shopping-e2e-search",
        )


class DeterministicPersonalAIClient(FakePersonalAIClient):
    def __init__(self) -> None:
        self.intent_calls_by_marker: dict[str, int] = {}
        fixtures = {
            "extract_claims.v1": {
                product["url"]: {
                    "claims": [
                        {
                            "attribute_key": "runtime",
                            "quote": (
                                f"measured {product['runtime']} minutes runtime in normal mode."
                            ),
                            "context_quote": (
                                f"{product['brand']} {product['name']} {product['model']} "
                                f"Color {product['color']}: measured {product['runtime']} "
                                "minutes runtime in normal mode."
                            ),
                            "normalized_value": product["runtime"],
                            "unit": "min",
                            "qualifiers": {"mode": "normal"},
                            "measurement_details": {},
                            "extraction_confidence": "high",
                        }
                    ],
                    "explanation": "Fixed, source-grounded E2E runtime claim.",
                }
                for product in PRODUCTS
            }
        }
        super().__init__(task_fixtures=fixtures)

    async def generate(self, request: AIRequest):
        context = request.input.get("context", {})
        message = context.get("new_user_message", "") if isinstance(context, dict) else ""
        marker = next(
            (
                part.rstrip(":")
                for part in str(message).split()
                if part.startswith("E2E_DELAYED_GENERATION_")
            ),
            None,
        )
        if marker is not None and request.task.startswith("interpret_shopping_intent"):
            self.intent_calls_by_marker[marker] = self.intent_calls_by_marker.get(marker, 0) + 1
            await asyncio.sleep(3)
        if request.task.startswith("interpret_shopping_intent") and (
            "e2e_trigger_generation_failure" in str(message).casefold()
        ):
            raise AIProviderError("provider_unavailable")
        return await super().generate(request)

    def intent_calls_for_marker(self, marker: str) -> int:
        return self.intent_calls_by_marker.get(marker, 0)


_documents = {product["url"]: _document(product) for product in PRODUCTS}
_extractions = {product["url"]: _catalog_output(product) for product in PRODUCTS}
_client = DeterministicPersonalAIClient()

app.state.conversation_ai_client = _client
app.state.discovery_ai_client = _client
app.state.research_search_provider = DeterministicSearchProvider()
app.state.catalog_page_retriever = FakePageRetriever(_documents)
app.state.catalog_extraction_task = FakeCatalogExtractionTask(_extractions)


@app.get("/__e2e__/intent-call-count", include_in_schema=False)
def e2e_intent_call_count(marker: Annotated[str, Query(min_length=1, max_length=80)]):
    """Expose deterministic provider call counts only in the local browser harness."""
    return {"count": _client.intent_calls_for_marker(marker)}
