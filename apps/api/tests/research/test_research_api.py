from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.integrations.personal_ai.fake import FakePersonalAIClient
from shopping.research.models import (
    CandidateSearchResult,
    DiscoveryCandidate,
    ResearchRun,
    SearchAttempt,
    SearchResult,
)
from shopping.search.fake import FakeSearchFailure, FakeSearchProvider
from shopping.search.provider import SearchResponse
from shopping.search.provider import SearchResult as ProviderResult

pytestmark = pytest.mark.db


def _create_project(client: TestClient) -> dict:
    response = client.post(
        "/projects",
        json={
            "title": "Apartment vacuum",
            "goal": "Find a vacuum for pet hair",
            "category": "Vacuum",
            "budget_maximum": "400.00",
            "budget_currency": "USD",
            "requirements": [{"kind": "must_have", "label": "Works well on pet hair"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _start(
    client: TestClient,
    project: dict,
    *,
    key: str = "discovery-request-0001",
    queries: list[str] | None = None,
    budgets: dict | None = None,
    objective: str = "Find pet-hair vacuum options",
) -> dict:
    payload = {
        "objective": objective,
        "request_key": key,
        "expected_version": project["revision"],
        "budgets": budgets or {},
    }
    if queries is not None:
        payload["manual_queries"] = queries
    response = client.post(f"/projects/{project['id']}/research", json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def _wait_for_run(client: TestClient, project_id: str, run_id: str, timeout: float = 5) -> dict:
    stop_at = time.monotonic() + timeout
    while time.monotonic() < stop_at:
        response = client.get(f"/projects/{project_id}/research/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"succeeded", "partial", "failed", "canceled", "interrupted"}:
            return run
        time.sleep(0.01)
    raise AssertionError("research run did not reach a terminal state")


def _wait_for_query_state(
    client: TestClient, project_id: str, run_id: str, state: str, timeout: float = 3
) -> dict:
    stop_at = time.monotonic() + timeout
    while time.monotonic() < stop_at:
        run = client.get(f"/projects/{project_id}/research/{run_id}").json()
        if any(query["state"] == state for query in run["queries"]):
            return run
        time.sleep(0.01)
    raise AssertionError(f"query did not reach {state}")


def _result(title: str, url: str, snippet: str = "") -> ProviderResult:
    return ProviderResult(title=title, url=url, snippet=snippet or None)


def test_manual_discovery_replays_before_revision_check_and_preserves_result_lineage(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    provider = FakeSearchProvider(
        {
            "vacuum query one": SearchResponse(
                results=[
                    _result(
                        "Compact vacuum", "https://Shop.example/item?sku=1#details", "For pet hair"
                    )
                ],
                provider_request_id="fake-usage-request",
                usage_units=1,
            ),
            "vacuum query two": [
                _result("Retailer listing", "https://shop.example/item?sku=1#buy", "$399 listing")
            ],
            "vacuum query three": FakeSearchFailure("rate_limited"),
        }
    )
    client.app.state.discovery_supervisor.search_provider = provider
    body = {
        "objective": "Find compact options that handle pet hair",
        "request_key": "phase3-lineage-request-1",
        "expected_version": project["revision"],
        "manual_queries": ["vacuum query one", "vacuum query two", "vacuum query three"],
        "budgets": {"max_attempts": 3, "max_results": 10, "max_candidates": 5},
    }
    accepted = client.post(f"/projects/{project['id']}/research", json=body)
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]
    run = _wait_for_run(client, project["id"], run_id)
    assert run["status"] == "partial"
    assert run["snapshot_revision"] == project["revision"]
    assert run["attempts_used"] == 3
    assert run["results_found"] == 2
    assert run["candidates_found"] == 1
    assert run["queries_failed"] == 1
    assert run["queries"][2]["attempts"][0]["error_code"] == "rate_limited"
    assert run["queries"][0]["attempts"][0]["usage_units"] == 1
    assert run["queries"][0]["attempts"][0]["provider_request_id"] == "fake-usage-request"
    assert client.get(f"/projects/{project['id']}").json()["revision"] == project["revision"]

    candidates = client.get(f"/projects/{project['id']}/candidates?limit=20")
    assert candidates.status_code == 200, candidates.text
    item = candidates.json()["items"][0]
    assert item["provisional_name"] == "Compact vacuum"
    assert item["category_clue"] is None
    assert item["indicative_price_text"] is None
    assert len(item["search_results"]) == 2
    assert [result["query_text"] for result in item["search_results"]] == [
        "vacuum query one",
        "vacuum query two",
    ]
    with Session(engine) as session:
        assert (
            session.scalar(select(ResearchRun).where(ResearchRun.id == UUID(run_id))).status
            == "partial"
        )
        assert session.scalar(
            select(DiscoveryCandidate).where(DiscoveryCandidate.run_id == UUID(run_id))
        )
        assert len(session.scalars(select(SearchResult)).all()) == 2
        assert len(session.scalars(select(CandidateSearchResult)).all()) == 2

    edited = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": project["revision"], "goal": "Another vacuum goal"},
    )
    assert edited.status_code == 200
    replay = client.post(f"/projects/{project['id']}/research", json=body)
    assert replay.status_code == 202
    assert replay.json() == {"run_id": run_id, "status": "partial", "replayed": True}
    changed_body = {**body, "objective": "Different objective"}
    mismatch = client.post(f"/projects/{project['id']}/research", json=changed_body)
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "request_key_conflict"


def test_candidate_normalization_preserves_trailing_path_slashes(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client)
    client.app.state.discovery_supervisor.search_provider = FakeSearchProvider(
        {
            "vacuum query": [
                _result("Product route", "https://catalog.example/product"),
                _result("Product directory", "https://catalog.example/product/"),
            ]
        }
    )
    accepted = _start(
        client,
        project,
        key="phase3-path-slash-001",
        queries=["vacuum query"],
    )
    run = _wait_for_run(client, project["id"], accepted["run_id"])
    assert run["candidates_found"] == 2
    candidates = client.get(
        f"/projects/{project['id']}/candidates?run_id={accepted['run_id']}&limit=20"
    ).json()["items"]
    assert {item["search_results"][0]["url"] for item in candidates} == {
        "https://catalog.example/product",
        "https://catalog.example/product/",
    }


def test_failed_attempt_consumes_attempt_budget_and_skips_remaining_query(project_api):
    client, _owner, engine = project_api
    project = _create_project(client)
    provider = FakeSearchProvider({"first failed query": FakeSearchFailure("provider_timeout")})
    client.app.state.discovery_supervisor.search_provider = provider
    accepted = _start(
        client,
        project,
        key="phase3-budget-request-1",
        queries=["first failed query", "second query"],
        budgets={"max_attempts": 1},
    )
    run = _wait_for_run(client, project["id"], accepted["run_id"])
    assert run["status"] == "failed"
    assert run["attempts_used"] == 1
    assert run["queries_failed"] == 1
    assert run["skipped_count"] == 1
    assert run["queries"][1]["state"] == "skipped"
    assert len(provider.calls) == 1
    with Session(engine) as session:
        attempts = list(session.scalars(select(SearchAttempt)).all())
        assert len(attempts) == 1
        assert attempts[0].status == "failed"


def test_task_planner_uses_snapshot_and_effective_query_and_concurrency_budgets(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client)
    accepted = _start(
        client,
        project,
        key="phase3-planner-request-0001",
        budgets={"max_queries": 2, "max_concurrent": 8},
    )
    run = _wait_for_run(client, project["id"], accepted["run_id"])
    assert run["status"] == "succeeded"
    assert run["snapshot_revision"] == project["revision"]
    assert run["effective_budgets"]["max_queries"] == 2
    assert run["effective_budgets"]["max_concurrent"] == 1
    assert run["queries_planned"] == 1
    assert "pet hair" in run["queries"][0]["text"].casefold()
    assert "400.00" in run["queries"][0]["text"]
    assert "USD" in run["queries"][0]["text"]
    assert client.get(f"/projects/{project['id']}").json()["revision"] == project["revision"]


def test_planner_unavailability_is_honest_and_manual_queries_still_work(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client)
    client.app.state.discovery_supervisor.client = FakePersonalAIClient(
        error_code="provider_unavailable"
    )
    unavailable = _start(
        client,
        project,
        key="phase3-ai-unavailable-0001",
    )
    failed = _wait_for_run(client, project["id"], unavailable["run_id"])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "provider_unavailable"
    assert "explicit search queries" in failed["summary"]

    manual = _start(
        client,
        project,
        key="phase3-manual-fallback-0001",
        queries=["cordless vacuum pet hair under 400 USD"],
    )
    completed = _wait_for_run(client, project["id"], manual["run_id"])
    assert completed["status"] == "succeeded"
    assert completed["queries"][0]["text"] == "cordless vacuum pet hair under 400 USD"


def test_slow_provider_obeys_run_deadline_and_counts_attempt(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client)
    provider = FakeSearchProvider(
        {"slow query": [_result("Late vacuum", "https://catalog.example/late")]},
        delay_seconds=2,
    )
    client.app.state.discovery_supervisor.search_provider = provider
    accepted = _start(
        client,
        project,
        key="phase3-deadline-request-001",
        queries=["slow query"],
        budgets={"deadline_seconds": 1},
    )
    run = _wait_for_run(client, project["id"], accepted["run_id"])
    assert run["status"] == "failed"
    assert run["attempts_used"] == 1
    assert run["queries_failed"] == 1
    assert run["queries"][0]["attempts"][0]["error_code"] == "provider_timeout"
    assert run["results_found"] == 0


def test_startup_recovery_interrupts_unfinished_run_before_late_result(project_api):
    from shopping.research import service

    client, _owner, engine = project_api
    project = _create_project(client)
    provider = FakeSearchProvider(
        {"slow query": [_result("Late vacuum", "https://catalog.example/late")]},
        delay_seconds=0.2,
    )
    client.app.state.discovery_supervisor.search_provider = provider
    accepted = _start(
        client,
        project,
        key="phase3-restart-request-001",
        queries=["slow query"],
    )
    run_id = accepted["run_id"]
    _wait_for_query_state(client, project["id"], run_id, "running")
    with Session(engine) as session:
        assert service.interrupt_all_unfinished(session) == 1

    time.sleep(0.25)
    with Session(engine) as session:
        stored = session.get(ResearchRun, UUID(run_id))
        assert stored.status == "interrupted"
        assert stored.error_code == "process_restarted"
        assert stored.attempts_used == 1
        assert stored.results_found == 0
        assert stored.candidates_found == 0


def test_candidate_budget_is_reserved_before_provider_io(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client)
    provider = FakeSearchProvider(
        {
            "first query": [
                _result("Vacuum A", "https://catalog.example/a"),
                _result("Vacuum B", "https://catalog.example/b"),
            ],
            "second query": [_result("Vacuum C", "https://catalog.example/c")],
        }
    )
    client.app.state.discovery_supervisor.search_provider = provider
    accepted = _start(
        client,
        project,
        key="phase3-candidate-cap-001",
        queries=["first query", "second query"],
        budgets={"max_candidates": 1, "max_results": 10},
    )
    run = _wait_for_run(client, project["id"], accepted["run_id"])
    assert run["status"] == "partial"
    assert run["attempts_used"] == 1
    assert run["candidates_found"] == 1
    assert run["results_found"] == 1
    assert run["skipped_count"] == 1
    assert [call.max_results for call in provider.calls] == [1]


def test_provider_response_is_truncated_to_remaining_run_budgets(project_api):
    client, _owner, engine = project_api
    project = _create_project(client)

    class IgnoresRequestedLimit:
        name = "fake"

        def __init__(self):
            self.calls = []

        async def search(self, query):
            self.calls.append(query)
            return SearchResponse(
                results=[
                    _result(f"Vacuum {index}", f"https://catalog.example/item-{index}")
                    for index in range(20)
                ]
            )

    provider = IgnoresRequestedLimit()
    client.app.state.discovery_supervisor.search_provider = provider
    accepted = _start(
        client,
        project,
        key="phase3-response-cap-001",
        queries=["first query", "second query"],
        budgets={"max_candidates": 1, "max_results": 1},
    )
    run = _wait_for_run(client, project["id"], accepted["run_id"])
    assert run["status"] == "partial"
    assert run["attempts_used"] == 1
    assert run["results_found"] == 1
    assert run["candidates_found"] == 1
    assert run["queries"][0]["results_count"] == 1
    assert run["queries"][0]["attempts"][0]["results_count"] == 1
    assert run["queries"][1]["state"] == "skipped"
    assert [call.max_results for call in provider.calls] == [1]
    with Session(engine) as session:
        rows = list(session.scalars(select(SearchResult)).all())
        links = list(session.scalars(select(CandidateSearchResult)).all())
        assert len(rows) == len(links) == 1
        assert rows[0].title == "Vacuum 0"


def test_db_wait_past_deadline_discards_late_success(project_api):
    client, _owner, engine = project_api
    project = _create_project(client)

    class HeldResponseProvider:
        name = "fake"

        def __init__(self):
            self.started = Event()
            self.release = Event()
            self.returned = Event()

        async def search(self, _query):
            self.started.set()
            await asyncio.to_thread(self.release.wait, 5)
            self.returned.set()
            return SearchResponse(results=[_result("Late vacuum", "https://catalog.example/late")])

    provider = HeldResponseProvider()
    client.app.state.discovery_supervisor.search_provider = provider
    accepted = _start(
        client,
        project,
        key="phase3-db-deadline-001",
        queries=["slow query"],
        budgets={"deadline_seconds": 1},
    )
    run_id = UUID(accepted["run_id"])
    assert provider.started.wait(2)
    with Session(engine) as locker:
        locker.begin()
        locker.execute(select(ResearchRun).where(ResearchRun.id == run_id).with_for_update()).one()
        provider.release.set()
        assert provider.returned.wait(2)
        time.sleep(1.1)
        locker.rollback()

    run = _wait_for_run(client, project["id"], str(run_id))
    assert run["status"] == "failed"
    assert run["queries"][0]["attempts"][0]["error_code"] == "deadline_exceeded"
    assert run["results_found"] == 0
    assert run["candidates_found"] == 0
    with Session(engine) as session:
        assert session.scalars(select(SearchResult)).all() == []
        assert session.scalars(select(DiscoveryCandidate)).all() == []


def test_unrecognized_provider_error_code_is_sanitized(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client)
    client.app.state.discovery_supervisor.search_provider = FakeSearchProvider(
        {"bad provider": FakeSearchFailure("sk-secret-token-123456789")}
    )
    accepted = _start(
        client,
        project,
        key="phase3-safe-error-001",
        queries=["bad provider"],
    )
    run = _wait_for_run(client, project["id"], accepted["run_id"])
    assert run["error_code"] == "provider_error"
    assert run["queries"][0]["error_code"] == "provider_error"
    assert run["queries"][0]["attempts"][0]["error_code"] == "provider_error"
    assert "secret" not in str(run)


def test_unexpected_search_response_shape_is_failed_as_malformed(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client)

    class WrongShapeProvider:
        name = "fake"

        async def search(self, _query):
            return {"results": [_result("Should not persist", "https://catalog.example/item")]}

    client.app.state.discovery_supervisor.search_provider = WrongShapeProvider()
    accepted = _start(
        client,
        project,
        key="phase3-malformed-response-001",
        queries=["malformed provider"],
    )
    run = _wait_for_run(client, project["id"], accepted["run_id"])
    assert run["status"] == "failed"
    assert run["error_code"] == "malformed_response"
    assert run["queries"][0]["attempts"][0]["error_code"] == "malformed_response"
    assert run["results_found"] == 0


def test_run_and_candidate_pagination_is_stable_and_run_scoped(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    base_time = datetime(2026, 10, 1, tzinfo=UTC)
    run_ids = [UUID(int=1000 + index) for index in range(21)]
    latest_id = run_ids[-1]
    older_id = run_ids[0]
    with Session(engine) as session:
        for index, run_id in enumerate(run_ids):
            session.add(
                ResearchRun(
                    id=run_id,
                    project_id=UUID(project["id"]),
                    owner_id=owner["id"],
                    objective=f"Saved run {index}",
                    run_type="discovery",
                    status="succeeded",
                    request_key=f"pagination-run-{index:02}",
                    request_hash="0" * 64,
                    snapshot_revision=1,
                    input_snapshot={},
                    effective_budgets={
                        "max_queries": 1,
                        "max_candidates": 100,
                        "max_results": 100,
                        "max_results_per_query": 20,
                        "max_attempts": 1,
                        "deadline_seconds": 10,
                        "max_concurrent": 1,
                    },
                    task_name="plan_discovery.v1",
                    prompt_version="shopping-discovery-1",
                    schema_version=1,
                    ai_provider="fake",
                    search_provider="fake",
                    queued_at=base_time,
                    started_at=base_time,
                    finished_at=base_time,
                )
            )
        session.flush()
        for index in range(55):
            session.add(
                DiscoveryCandidate(
                    id=UUID(int=2000 + index),
                    project_id=UUID(project["id"]),
                    run_id=latest_id,
                    provisional_name=f"Recent candidate {index}",
                    discovery_reason="Pagination fixture",
                    normalized_url=f"https://catalog.example/recent-{index}",
                    created_at=base_time,
                )
            )
        session.add(
            DiscoveryCandidate(
                id=UUID(int=1),
                project_id=UUID(project["id"]),
                run_id=older_id,
                provisional_name="Older selected-run candidate",
                discovery_reason="Pagination fixture",
                normalized_url="https://catalog.example/older",
                created_at=base_time,
            )
        )
        session.commit()

    first_runs = client.get(f"/projects/{project['id']}/research?limit=20").json()
    assert [item["id"] for item in first_runs["items"]] == [
        str(run_id) for run_id in reversed(run_ids[1:])
    ]
    assert first_runs["next_cursor"]
    last_runs = client.get(
        f"/projects/{project['id']}/research?limit=20&cursor={first_runs['next_cursor']}"
    ).json()
    assert [item["id"] for item in last_runs["items"]] == [str(older_id)]
    assert last_runs["next_cursor"] is None

    first_candidates = client.get(
        f"/projects/{project['id']}/candidates?run_id={latest_id}&limit=20"
    ).json()
    candidate_ids = [item["id"] for item in first_candidates["items"]]
    cursor = first_candidates["next_cursor"]
    while cursor:
        page = client.get(
            f"/projects/{project['id']}/candidates?run_id={latest_id}&limit=20&cursor={cursor}"
        ).json()
        candidate_ids.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
    assert len(candidate_ids) == len(set(candidate_ids)) == 55
    assert candidate_ids == [str(UUID(int=value)) for value in reversed(range(2000, 2055))]

    unscoped = client.get(f"/projects/{project['id']}/candidates?limit=50").json()
    assert str(UUID(int=1)) not in {item["id"] for item in unscoped["items"]}
    older_candidates = client.get(
        f"/projects/{project['id']}/candidates?run_id={older_id}&limit=20"
    )
    assert older_candidates.status_code == 200
    assert [item["provisional_name"] for item in older_candidates.json()["items"]] == [
        "Older selected-run candidate"
    ]
    assert (
        client.get(f"/projects/{project['id']}/candidates?run_id={uuid4()}&limit=20").status_code
        == 404
    )


def test_malformed_pagination_cursors_return_422(project_api):
    import base64
    import json

    from shopping.research.service import _decode_cursor

    client, _owner, _engine = project_api
    project = _create_project(client)

    def cursor(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    invalid = [
        "",
        cursor({}),
        cursor(["2026-10-01T00:00:00+00:00", str(uuid4()), "extra"]),
        cursor([123, str(uuid4())]),
        cursor(["2026-10-01T00:00:00", str(uuid4())]),
        "%%%not-base64%%%",
    ]
    for value in invalid:
        response = client.get(f"/projects/{project['id']}/candidates?cursor={value}")
        assert response.status_code == 422, response.text
        response = client.get(f"/projects/{project['id']}/research?cursor={value}")
        assert response.status_code == 422, response.text

    timestamp, identifier = _decode_cursor(cursor(["2026-10-01T12:00:00+02:00", str(uuid4())]))
    assert timestamp == datetime(2026, 10, 1, 10, tzinfo=UTC)
    assert timestamp.utcoffset() == timedelta(0)
    assert isinstance(identifier, UUID)


def test_cancellation_is_idempotent_and_late_provider_result_cannot_write(project_api):
    client, _owner, engine = project_api
    project = _create_project(client)
    provider = FakeSearchProvider(
        {"slow query": [_result("Late candidate", "https://catalog.example/late")]},
        delay_seconds=1,
    )
    client.app.state.discovery_supervisor.search_provider = provider
    accepted = _start(
        client,
        project,
        key="phase3-cancel-request-01",
        queries=["slow query"],
    )
    run_id = accepted["run_id"]
    active = _wait_for_query_state(client, project["id"], run_id, "running")
    assert active["attempts_used"] == 1

    canceled = client.post(f"/projects/{project['id']}/research/{run_id}/cancel")
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["run"]["status"] == "canceled"
    assert canceled.json()["replayed"] is False
    replay = client.post(f"/projects/{project['id']}/research/{run_id}/cancel")
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    with Session(engine) as session:
        run = session.get(ResearchRun, UUID(run_id))
        assert run.status == "canceled"
        assert run.attempts_used == 1
        assert run.results_found == 0
        assert run.candidates_found == 0
        assert (
            session.scalar(
                select(SearchAttempt).where(SearchAttempt.query_id == run.queries[0].id)
            ).status
            == "canceled"
        )


def test_project_deletion_interrupts_active_run_and_blocks_late_writes(project_api):
    client, _owner, engine = project_api
    project = _create_project(client)
    provider = FakeSearchProvider(
        {"slow query": [_result("Late candidate", "https://catalog.example/late")]},
        delay_seconds=0.4,
    )
    client.app.state.discovery_supervisor.search_provider = provider
    accepted = _start(
        client,
        project,
        key="phase3-delete-request-01",
        queries=["slow query"],
    )
    run_id = accepted["run_id"]
    _wait_for_query_state(client, project["id"], run_id, "running")
    deleted = client.delete(f"/projects/{project['id']}?expected_version={project['revision']}")
    assert deleted.status_code == 204
    time.sleep(0.5)
    with Session(engine) as session:
        run = session.get(ResearchRun, UUID(run_id))
        assert run.status == "interrupted"
        assert run.error_code == "project_deleted"
        assert run.results_found == 0
        assert run.candidates_found == 0
        assert session.scalars(select(SearchResult)).all() == []


def test_concurrent_exact_command_replays_once_and_competing_command_conflicts(project_api):
    client, _owner, engine = project_api
    project = _create_project(client)
    provider = FakeSearchProvider(
        {"slow query": [_result("Candidate", "https://catalog.example/candidate")]},
        delay_seconds=0.3,
    )
    client.app.state.discovery_supervisor.search_provider = provider
    body = {
        "objective": "Find a vacuum",
        "request_key": "phase3-concurrent-request-01",
        "expected_version": project["revision"],
        "manual_queries": ["slow query"],
    }
    barrier = Barrier(2)

    def submit():
        barrier.wait()
        return client.post(f"/projects/{project['id']}/research", json=body)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _index: submit(), range(2)))
    assert all(response.status_code == 202 for response in responses)
    assert len({response.json()["run_id"] for response in responses}) == 1
    assert sorted(response.json()["replayed"] for response in responses) == [False, True]
    assert (
        _wait_for_run(client, project["id"], responses[0].json()["run_id"])["status"] == "succeeded"
    )
    assert len(provider.calls) == 1
    with Session(engine) as session:
        assert len(session.scalars(select(ResearchRun)).all()) == 1

    provider = FakeSearchProvider(delay_seconds=0.3)
    client.app.state.discovery_supervisor.search_provider = provider
    active = _start(
        client,
        project,
        key="phase3-competing-request-01",
        queries=["another slow query"],
    )
    _wait_for_query_state(client, project["id"], active["run_id"], "running")
    competing = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Another search",
            "request_key": "phase3-competing-request-02",
            "expected_version": project["revision"],
            "manual_queries": ["second search"],
        },
    )
    assert competing.status_code == 409
    assert competing.json()["error"]["code"] == "research_active"
    canceled = client.post(f"/projects/{project['id']}/research/{active['run_id']}/cancel")
    assert canceled.status_code == 200


def test_stale_revision_foreign_owner_and_bounded_manual_query_validation(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client)
    stale = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Find a vacuum",
            "request_key": "phase3-stale-request-0001",
            "expected_version": 2,
            "manual_queries": ["vacuum"],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["current_version"] == 1
    invalid = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Find a vacuum",
            "request_key": "phase3-invalid-query-0001",
            "expected_version": 1,
            "manual_queries": ["  ", "same", "same"],
        },
    )
    assert invalid.status_code == 422
    oversized_query = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Find a vacuum",
            "request_key": "phase3-oversized-query-01",
            "expected_version": 1,
            "manual_queries": ["x" * 301],
        },
    )
    assert oversized_query.status_code == 422

    accepted = _start(
        client,
        project,
        key="phase3-owner-request-0001",
        queries=["vacuum"],
    )
    _wait_for_run(client, project["id"], accepted["run_id"])
    from shopping.projects.dependencies import get_owner_id

    client.app.dependency_overrides[get_owner_id] = lambda: uuid4()
    assert client.get(f"/projects/{project['id']}/research").status_code == 404
