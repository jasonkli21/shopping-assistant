from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.projects.models import ShoppingProject
from shopping.research.common import (
    ACTIVE_STATES,
    _clean_text,
    _live_project,
    _lock_live_run,
    _not_found,
    _owned_run,
    _safe_error_code,
    _safe_http_url,
    normalize_candidate_url,
)
from shopping.research.models import (
    CandidateSearchResult,
    DiscoveryCandidate,
    ResearchRun,
    SearchAttempt,
    SearchQueryRecord,
    SearchResult,
)
from shopping.research.reads import _run_read_with_queries
from shopping.research.schemas import ResearchRunRead
from shopping.search.provider import SearchResponse
from shopping.search.provider import SearchResult as ProviderResult


def load_execution_input(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID
) -> tuple[dict[str, Any], dict[str, int]] | None:
    _live_project(session, owner_id, project_id)
    run = _owned_run(session, owner_id, project_id, run_id)
    if run is None or run.status not in ACTIVE_STATES:
        return None
    return run.input_snapshot, run.effective_budgets


def list_run_queries(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID
) -> list[tuple[UUID, int]]:
    _live_project(session, owner_id, project_id)
    if _owned_run(session, owner_id, project_id, run_id) is None:
        return []
    rows = session.execute(
        select(SearchQueryRecord.id, SearchQueryRecord.max_results)
        .join(ResearchRun, ResearchRun.id == SearchQueryRecord.run_id)
        .where(
            SearchQueryRecord.run_id == run_id,
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
        )
        .order_by(SearchQueryRecord.ordinal)
    ).all()
    return [(row.id, row.max_results) for row in rows]


def run_started_at(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID
) -> datetime | None:
    _live_project(session, owner_id, project_id)
    run = _owned_run(session, owner_id, project_id, run_id)
    return run.started_at if run is not None else None


def interrupt_run(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID, error_code: str
) -> bool:
    project = session.scalar(
        select(ShoppingProject)
        .where(ShoppingProject.id == project_id, ShoppingProject.owner_id == owner_id)
        .with_for_update()
    )
    if project is None or project.deleted_at is not None:
        return False
    run = _owned_run(session, owner_id, project_id, run_id, lock=True)
    if run is None or run.status not in ACTIVE_STATES:
        return False
    run.status = "interrupted"
    run.error_code = _safe_error_code(error_code)
    run.summary = (
        "The local discovery worker stopped before finishing. Start a new run to continue."
    )
    run.finished_at = datetime.now(UTC)
    _cancel_open_work(session, run, "canceled")
    session.commit()
    return True


def mark_running(session: Session, owner_id: UUID, project_id: UUID, run_id: UUID) -> bool:
    project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.status != "queued":
        return False
    run.status = "running"
    run.started_at = datetime.now(UTC)
    session.commit()
    return True


def save_plan(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    queries: list[dict[str, str]],
    summary: str | None,
) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.status != "running":
        return False
    if run.queries_planned:
        return True
    budget = run.effective_budgets
    now = datetime.now(UTC)
    for ordinal, query in enumerate(queries):
        session.add(
            SearchQueryRecord(
                run_id=run.id,
                ordinal=ordinal,
                text=query["text"],
                purpose=query["purpose"],
                max_results=budget["max_results_per_query"],
                state="queued",
            )
        )
    run.queries_planned = len(queries)
    run.summary = _clean_text(summary, 1000) if summary else None
    if not queries:
        run.status = "succeeded"
        run.finished_at = now
        run.summary = (
            run.summary or "No search was started because the planner requested clarification."
        )
    session.commit()
    return True


def start_attempt(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    query_id: UUID,
) -> tuple[SearchQueryRecord, UUID, int] | None:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    query = session.scalar(
        select(SearchQueryRecord)
        .where(SearchQueryRecord.id == query_id, SearchQueryRecord.run_id == run.id)
        .with_for_update()
    )
    if run.status != "running" or query is None or query.state != "queued":
        return None
    budget = run.effective_budgets
    if run.started_at is None or _deadline_expired(run, budget):
        _skip_query(run, query, "deadline_exceeded")
        session.commit()
        return None
    if run.attempts_used >= budget["max_attempts"]:
        _skip_query(run, query, "attempt_budget_exhausted")
        session.commit()
        return None
    remaining_results = budget["max_results"] - run.results_found
    remaining_candidates = budget["max_candidates"] - run.candidates_found
    allowance = min(query.max_results, remaining_results, remaining_candidates)
    if allowance < 1:
        _skip_query(run, query, "result_budget_exhausted")
        session.commit()
        return None

    now = datetime.now(UTC)
    query.max_results = allowance
    query.state = "running"
    query.started_at = now
    attempt = SearchAttempt(
        query_id=query.id,
        attempt_number=1,
        provider=run.search_provider,
        status="running",
        started_at=now,
    )
    run.attempts_used += 1
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return query, attempt.id, allowance


def complete_attempt(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    query_id: UUID,
    attempt_id: UUID,
    response: SearchResponse,
) -> bool:
    if not isinstance(response, SearchResponse) or not isinstance(response.results, list):
        raise ValueError("search provider returned an invalid response")
    usage_units = response.usage_units
    if usage_units is not None and (
        isinstance(usage_units, bool)
        or not isinstance(usage_units, int)
        or not 0 <= usage_units <= 100_000
    ):
        raise ValueError("search provider returned invalid usage metadata")
    if response.provider_request_id is not None and not isinstance(
        response.provider_request_id, str
    ):
        raise ValueError("search provider returned invalid request metadata")
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    query = session.scalar(
        select(SearchQueryRecord)
        .where(SearchQueryRecord.id == query_id, SearchQueryRecord.run_id == run.id)
        .with_for_update()
    )
    attempt = session.scalar(
        select(SearchAttempt)
        .where(SearchAttempt.id == attempt_id, SearchAttempt.query_id == query_id)
        .with_for_update()
    )
    if (
        run.status != "running"
        or query is None
        or query.state != "running"
        or attempt is None
        or attempt.status != "running"
    ):
        return False

    now = datetime.now(UTC)
    if _deadline_expired(run, run.effective_budgets):
        _fail_locked_attempt(run, query, attempt, "deadline_exceeded", now)
        session.commit()
        return True

    allowance = min(
        query.max_results,
        run.effective_budgets["max_results"] - run.results_found,
        run.effective_budgets["max_candidates"] - run.candidates_found,
    )
    if allowance < 1:
        _fail_locked_attempt(run, query, attempt, "result_budget_exhausted", now)
        session.commit()
        return True

    # Providers are expected to honor max_results, but persistence enforces the run's
    # reserved allowance independently. Retained rows keep their original order and lineage.
    cleaned = [_clean_provider_result(item) for item in response.results[:allowance]]
    new_candidates = 0
    for result_rank, result in enumerate(cleaned, start=1):
        search_result = SearchResult(
            query_id=query.id,
            attempt_id=attempt.id,
            result_rank=result_rank,
            title=result.title,
            url=result.url,
            snippet=result.snippet,
            received_at=now,
            provider_metadata={},
        )
        session.add(search_result)
        session.flush()
        normalized_url = normalize_candidate_url(result.url)
        candidate = session.scalar(
            select(DiscoveryCandidate)
            .where(
                DiscoveryCandidate.run_id == run.id,
                DiscoveryCandidate.normalized_url == normalized_url,
            )
            .with_for_update()
        )
        if candidate is None:
            candidate = DiscoveryCandidate(
                project_id=project_id,
                run_id=run.id,
                provisional_name=result.title or "Unlabelled search result",
                discovery_reason=f"Found for query: {query.text}"[:300],
                normalized_url=normalized_url,
            )
            session.add(candidate)
            session.flush()
            new_candidates += 1
        session.add(
            CandidateSearchResult(candidate_id=candidate.id, search_result_id=search_result.id)
        )

    attempt.status = "succeeded"
    attempt.error_code = None
    attempt.provider_request_id = _clean_text(response.provider_request_id, 200)
    attempt.results_count = len(cleaned)
    attempt.usage_units = usage_units
    attempt.finished_at = now
    query.state = "succeeded"
    query.results_count = len(cleaned)
    query.candidates_count = new_candidates
    query.completed_at = now
    run.queries_completed += 1
    run.results_found += len(cleaned)
    run.candidates_found += new_candidates
    session.commit()
    return True


def fail_attempt(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    query_id: UUID,
    attempt_id: UUID,
    error_code: str,
) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    query = session.scalar(
        select(SearchQueryRecord)
        .where(SearchQueryRecord.id == query_id, SearchQueryRecord.run_id == run.id)
        .with_for_update()
    )
    attempt = session.scalar(
        select(SearchAttempt)
        .where(SearchAttempt.id == attempt_id, SearchAttempt.query_id == query_id)
        .with_for_update()
    )
    if (
        run.status != "running"
        or query is None
        or query.state != "running"
        or attempt is None
        or attempt.status != "running"
    ):
        return False
    now = datetime.now(UTC)
    _fail_locked_attempt(run, query, attempt, error_code, now)
    session.commit()
    return True


def _fail_locked_attempt(
    run: ResearchRun,
    query: SearchQueryRecord,
    attempt: SearchAttempt,
    error_code: str,
    now: datetime,
) -> None:
    code = _safe_error_code(error_code)
    attempt.status = "failed"
    attempt.error_code = code
    attempt.finished_at = now
    query.state = "failed"
    query.error_code = code
    query.completed_at = now
    run.queries_failed += 1
    run.error_code = run.error_code or code


def finalize(session: Session, owner_id: UUID, project_id: UUID, run_id: UUID) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.status != "running":
        return False
    pending = list(
        session.scalars(
            select(SearchQueryRecord)
            .where(SearchQueryRecord.run_id == run.id, SearchQueryRecord.state == "queued")
            .with_for_update()
        ).all()
    )
    for query in pending:
        _skip_query(run, query, "discovery_stopped")
    now = datetime.now(UTC)
    if run.candidates_found > 0 and (run.queries_failed > 0 or run.skipped_count > 0):
        run.status = "partial"
        run.summary = (
            run.summary
            or "Discovery saved some candidates; other planned work failed or was skipped."
        )
    elif run.candidates_found > 0 or (run.queries_failed == 0 and run.skipped_count == 0):
        run.status = "succeeded"
        run.summary = run.summary or (
            "No candidates were found." if run.candidates_found == 0 else "Discovery completed."
        )
    else:
        run.status = "failed"
        run.summary = (
            run.summary
            or "Discovery did not produce candidates. Retry or provide a different query."
        )
    run.finished_at = now
    session.commit()
    return True


def fail_run(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    error_code: str,
    summary: str,
) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.status not in ACTIVE_STATES:
        return False
    now = datetime.now(UTC)
    run.status = "failed"
    run.error_code = _safe_error_code(error_code)
    run.summary = _clean_text(summary, 1000)
    run.finished_at = now
    _cancel_open_work(session, run, "canceled")
    session.commit()
    return True


def cancel_run(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID
) -> tuple[ResearchRunRead, bool]:
    _project = _live_project(session, owner_id, project_id, lock=True)
    run = _owned_run(session, owner_id, project_id, run_id, lock=True)
    if run is None:
        raise _not_found("Research run not found")
    changed = run.status in ACTIVE_STATES
    if changed:
        run.status = "canceled"
        run.error_code = "user_canceled"
        run.summary = "Discovery was canceled. Saved candidates remain available."
        run.finished_at = datetime.now(UTC)
        _cancel_open_work(session, run, "canceled")
        session.commit()
    return _run_read_with_queries(session, run, replayed=not changed), changed


def interrupt_project_runs(session: Session, owner_id: UUID, project_id: UUID) -> int:
    runs = list(
        session.scalars(
            select(ResearchRun)
            .where(
                ResearchRun.owner_id == owner_id,
                ResearchRun.project_id == project_id,
                ResearchRun.status.in_(ACTIVE_STATES),
            )
            .with_for_update()
        ).all()
    )
    for run in runs:
        run.status = "interrupted"
        run.error_code = "project_deleted"
        run.summary = "The project was deleted before discovery finished."
        run.finished_at = datetime.now(UTC)
        _cancel_open_work(session, run, "canceled")
    session.flush()
    return len(runs)


def interrupt_all_unfinished(session: Session) -> int:
    runs = list(
        session.scalars(
            select(ResearchRun).where(ResearchRun.status.in_(ACTIVE_STATES)).with_for_update()
        ).all()
    )
    for run in runs:
        run.status = "interrupted"
        run.error_code = "process_restarted"
        run.summary = (
            "The local API restarted while this discovery run was active. "
            "Start a new run to continue."
        )
        run.finished_at = datetime.now(UTC)
        _cancel_open_work(session, run, "canceled")
    session.commit()
    return len(runs)


def _skip_query(run: ResearchRun, query: SearchQueryRecord, reason: str) -> None:
    query.state = "skipped"
    query.error_code = reason
    query.completed_at = datetime.now(UTC)
    run.skipped_count += 1


def _cancel_open_work(session: Session, run: ResearchRun, state: str) -> None:
    now = datetime.now(UTC)
    queries = list(
        session.scalars(
            select(SearchQueryRecord)
            .where(
                SearchQueryRecord.run_id == run.id,
                SearchQueryRecord.state.in_(["queued", "running"]),
            )
            .with_for_update()
        ).all()
    )
    for query in queries:
        query.state = state
        query.error_code = run.error_code
        query.completed_at = now
        attempts = list(
            session.scalars(
                select(SearchAttempt)
                .where(SearchAttempt.query_id == query.id, SearchAttempt.status == "running")
                .with_for_update()
            ).all()
        )
        for attempt in attempts:
            attempt.status = "canceled"
            attempt.error_code = run.error_code
            attempt.finished_at = now


def _deadline_expired(run: ResearchRun, budgets: dict[str, int]) -> bool:
    return run.started_at is None or datetime.now(UTC) >= run.started_at + timedelta(
        seconds=budgets["deadline_seconds"]
    )


def _clean_provider_result(result: ProviderResult) -> ProviderResult:
    if not isinstance(result, ProviderResult):
        raise ValueError("search provider returned an invalid result")
    if not isinstance(result.title, str) or (
        result.snippet is not None and not isinstance(result.snippet, str)
    ):
        raise ValueError("search provider returned an invalid result")
    title = _clean_text(result.title, 300)
    snippet = _clean_text(result.snippet, 2000) if result.snippet is not None else None
    url = _safe_http_url(result.url)
    if not title or url is None:
        raise ValueError("search provider returned an invalid result")
    return ProviderResult(title=title, url=url, snippet=snippet)
