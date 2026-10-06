from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from shopping.evidence.freshness import offer_freshness
from shopping.extraction.retriever import PageRetrievalError, RetrievedDocument
from shopping.integrations.personal_ai.client import AIProviderError
from shopping.integrations.personal_ai.fake import FakePersonalAIClient
from shopping.research import product_execution
from shopping.research.product_execution import (
    _retrieve_with_retries,
    _select_source_results,
    _source_target_rejection,
)


def test_fake_product_plan_reserves_one_query_per_selected_target() -> None:
    targets = [
        {
            "project_product_id": str(uuid4()),
            "brand": "Acme",
            "product_name": f"Vacuum {index}",
        }
        for index in range(3)
    ]
    context = {
        "selected_products": targets,
        "source_targets": {"source_classes": ["manufacturer_specification", "retailer_listing"]},
        "limits": {"maximum_queries": 8},
    }

    plan = FakePersonalAIClient._plan_product_research(context)

    assert {query["project_product_id"] for query in plan["queries"]} == {
        target["project_product_id"] for target in targets
    }
    assert len(plan["queries"]) <= 8

    minimum_context = {**context, "limits": {"maximum_queries": 3}}
    minimum_plan = FakePersonalAIClient._plan_product_research(minimum_context)
    assert len(minimum_plan["queries"]) == 3
    assert {query["project_product_id"] for query in minimum_plan["queries"]} == {
        target["project_product_id"] for target in targets
    }


def test_source_selection_interleaves_classes_and_deduplicates_publishers() -> None:
    results = []
    for index in range(4):
        results.append(
            (
                SimpleNamespace(id=uuid4(), url=f"https://manufacturer{index}.example/item"),
                SimpleNamespace(purpose="manufacturer_specification: Find specifications"),
            )
        )
    results.extend(
        [
            (
                SimpleNamespace(id=uuid4(), url="https://tests.example/product"),
                SimpleNamespace(purpose="independent_measurement: Find measured tests"),
            ),
            (
                SimpleNamespace(id=uuid4(), url="https://reviews.example/product"),
                SimpleNamespace(purpose="editorial_assessment: Find reviews"),
            ),
        ]
    )

    selected = _select_source_results(
        results,
        allowed_classes=[
            "manufacturer_specification",
            "independent_measurement",
            "editorial_assessment",
        ],
        include_domains=[],
        exclude_domains=[],
        limit=3,
    )

    assert [_query.purpose.partition(":")[0] for _, _query in selected] == [
        "manufacturer_specification",
        "independent_measurement",
        "editorial_assessment",
    ]
    assert len({item.url.split("/")[2] for item, _ in selected}) == 3


@pytest.mark.parametrize(
    ("requested", "final", "actual_class", "expected"),
    [
        (
            "https://allowed.example/item",
            "https://excluded.example/item",
            "manufacturer_specification",
            "source_domain_excluded",
        ),
        (
            "https://allowed.example/item",
            "https://allowed.example/item",
            "retailer_listing",
            "source_class_mismatch",
        ),
        (
            "https://allowed.example/item",
            "https://sub.allowed.example/item",
            "manufacturer_specification",
            None,
        ),
    ],
)
def test_source_target_validation_checks_redirect_and_verified_class(
    requested: str, final: str, actual_class: str, expected: str | None
) -> None:
    assert (
        _source_target_rejection(
            requested_url=requested,
            final_url=final,
            actual_class=actual_class,
            requested_class="manufacturer_specification",
            allowed_classes=["manufacturer_specification"],
            include_domains=["allowed.example"],
            exclude_domains=["excluded.example"],
        )
        == expected
    )


def test_offer_freshness_uses_the_shared_24_hour_display_boundary() -> None:
    now = datetime.now(UTC)
    assert offer_freshness(now - timedelta(hours=24), now=now) == "current"
    assert offer_freshness(now - timedelta(hours=24, seconds=1), now=now) == "stale"


@pytest.mark.asyncio
async def test_retrieval_retries_one_explicit_rate_limit_without_exceeding_budget() -> None:
    now = datetime.now(UTC)
    document = RetrievedDocument(
        requested_url="https://allowed.example/item",
        final_url="https://allowed.example/item",
        content_type="text/html",
        body="<html>saved page</html>",
        content_hash="0" * 64,
        retrieved_at=now,
        decoded_bytes=24,
    )

    class FlakyRetriever:
        def __init__(self) -> None:
            self.calls = 0

        async def retrieve(self, _url: str) -> RetrievedDocument:
            self.calls += 1
            if self.calls == 1:
                raise PageRetrievalError(
                    "rate_limited", "try again", status_code=429, retry_after_seconds=0
                )
            return document

    retriever = FlakyRetriever()

    async def remaining_seconds() -> float:
        return 5

    returned = await _retrieve_with_retries(
        retriever,
        document.requested_url,
        1_000,
        include_domains=["allowed.example"],
        exclude_domains=[],
        remaining_seconds=remaining_seconds,
        provider_timeout_seconds=2,
    )

    assert returned == document
    assert retriever.calls == 2


@pytest.mark.asyncio
async def test_product_planning_retries_only_explicit_transient_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_ids = [uuid4(), uuid4()]
    started: list[object] = []
    finished: list[dict[str, object]] = []

    async def with_session(operation):
        return operation(object())

    monkeypatch.setattr(
        product_execution, "planning_attempt_uncertain", lambda *_args, **_kwargs: False
    )
    monkeypatch.setattr(
        product_execution,
        "start_stage_attempt",
        lambda *_args, **_kwargs: SimpleNamespace(id=attempt_ids[len(started)]),
    )
    monkeypatch.setattr(
        product_execution,
        "finish_stage_attempt",
        lambda _session, **values: finished.append(values) or True,
    )
    monkeypatch.setattr(
        product_execution,
        "build_request",
        lambda *_args, **_kwargs: SimpleNamespace(input={"objective": "runtime"}),
    )
    monkeypatch.setattr(
        product_execution,
        "validate_output",
        lambda *_args, **_kwargs: SimpleNamespace(
            queries=[SimpleNamespace(model_dump=lambda **_kwargs: {"text": "runtime test"})],
            explanation="Find grounded runtime evidence.",
        ),
    )

    original_start = product_execution.start_stage_attempt

    def record_start(*args, **kwargs):
        attempt = original_start(*args, **kwargs)
        started.append(attempt)
        return attempt

    monkeypatch.setattr(product_execution, "start_stage_attempt", record_start)

    class TransientClient:
        calls = 0

        async def generate(self, _request):
            self.calls += 1
            if self.calls == 1:
                raise AIProviderError("provider_unavailable")
            return SimpleNamespace(
                refused=False,
                output={"queries": [{"text": "runtime test"}]},
                provider_request_id="provider-request-2",
            )

    client = TransientClient()

    async def remaining_seconds() -> float:
        return 10

    async def unexpected_failure(*_args, **_kwargs):
        raise AssertionError("transient planner failure should recover")

    monkeypatch.setattr(product_execution, "_fail_product_run", unexpected_failure)
    result = await product_execution._generate_product_plan(
        owner_id=uuid4(),
        project_id=uuid4(),
        run_id=uuid4(),
        snapshot={},
        budgets={"max_queries": 2, "max_output_chars": 1_000},
        client=client,
        with_session=with_session,
        remaining_seconds=remaining_seconds,
        provider_timeout_seconds=5,
    )

    assert result is not None
    assert client.calls == 2
    assert len(started) == 2
    assert finished[0]["error_code"] == "provider_unavailable"
    assert result[2] == attempt_ids[1]
    assert result[3] == "provider-request-2"
