from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from shopping.projects.errors import ProjectError
from shopping.projects.models import ShoppingProject
from shopping.research.models import (
    CandidateSearchResult,
    DiscoveryCandidate,
    ResearchRun,
    SearchAttempt,
    SearchQueryRecord,
    SearchResult,
)
from shopping.research.schemas import (
    CandidatePage,
    CandidateRead,
    CandidateResultRead,
    ResearchBudgets,
    ResearchCreate,
    ResearchRunPage,
    ResearchRunRead,
    SearchAttemptRead,
    SearchQueryRead,
)
from shopping.search.provider import SearchResponse
from shopping.search.provider import SearchResult as ProviderResult

ACTIVE_STATES = {"queued", "running"}
TERMINAL_STATES = {"succeeded", "partial", "failed", "canceled", "interrupted"}


def exact_replay(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    command: ResearchCreate,
) -> ResearchRunRead | None:
    project = _live_project(session, owner_id, project_id)
    del project
    run = session.scalar(
        select(ResearchRun)
        .options(selectinload(ResearchRun.queries).selectinload(SearchQueryRecord.attempts))
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.request_key == command.request_key,
        )
    )
    if run is None:
        return None
    if run.request_hash != _request_hash(command):
        raise _conflict("request_key_conflict", "This request key was used for another command")
    return _run_read(run, replayed=True)


def create_run(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    command: ResearchCreate,
    settings: Any,
    ai_provider_name: str,
    search_provider_name: str,
) -> tuple[ResearchRunRead, bool]:
    project = _live_project(session, owner_id, project_id, lock=True)
    existing = session.scalar(
        select(ResearchRun)
        .options(selectinload(ResearchRun.queries).selectinload(SearchQueryRecord.attempts))
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.request_key == command.request_key,
        )
    )
    if existing is not None:
        if existing.request_hash != _request_hash(command):
            raise _conflict("request_key_conflict", "This request key was used for another command")
        return _run_read(existing, replayed=True), False
    if project.revision != command.expected_version:
        raise _conflict(
            "revision_conflict",
            "The project changed before discovery started",
            {"current_version": project.revision},
        )
    active = session.scalar(
        select(ResearchRun.id).where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.status.in_(ACTIVE_STATES),
        )
    )
    if active is not None:
        raise _conflict("research_active", "A discovery run is already active for this project")

    snapshot = _snapshot(project, command)
    budgets = effective_budgets(command.budgets, settings)
    if command.manual_queries and len(command.manual_queries) > budgets["max_queries"]:
        raise _invalid("The supplied query list exceeds the effective query budget")
    run = ResearchRun(
        project_id=project.id,
        owner_id=owner_id,
        objective=command.objective,
        run_type=command.type,
        status="queued",
        request_key=command.request_key,
        request_hash=_request_hash(command),
        snapshot_revision=project.revision,
        input_snapshot=snapshot,
        effective_budgets=budgets,
        task_name="plan_discovery.v1",
        prompt_version="shopping-discovery-1",
        schema_version=1,
        ai_provider=ai_provider_name,
        search_provider=search_provider_name,
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _conflict(
            "research_active", "A discovery run is already active for this project"
        ) from error
    session.refresh(run)
    return _run_read(run), True


def effective_budgets(requested: ResearchBudgets, settings: Any) -> dict[str, int]:
    def cap(name: str, server: int) -> int:
        selected = getattr(requested, name)
        return min(server, selected) if selected is not None else server

    return {
        "max_queries": cap("max_queries", settings.research_max_queries),
        "max_candidates": cap("max_candidates", settings.research_max_candidates),
        "max_results": cap("max_results", settings.research_max_results),
        "max_results_per_query": cap(
            "max_results_per_query", settings.research_max_results_per_query
        ),
        "max_attempts": cap("max_attempts", settings.research_max_attempts),
        "deadline_seconds": cap("deadline_seconds", settings.research_deadline_seconds),
        "max_concurrent": cap("max_concurrent", settings.research_max_concurrent_searches),
    }


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
    run.error_code = error_code
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
    if len(response.results) > 20:
        raise ValueError("search response exceeded the provider result limit")
    usage_units = response.usage_units
    if usage_units is not None and (
        isinstance(usage_units, bool)
        or not isinstance(usage_units, int)
        or not 0 <= usage_units <= 100_000
    ):
        raise ValueError("search provider returned invalid usage metadata")
    cleaned = [_clean_provider_result(item) for item in response.results]
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
    attempt.status = "failed"
    attempt.error_code = error_code
    attempt.finished_at = now
    query.state = "failed"
    query.error_code = error_code
    query.completed_at = now
    run.queries_failed += 1
    run.error_code = run.error_code or error_code
    session.commit()
    return True


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
    run.error_code = error_code
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


def list_runs(
    session: Session, owner_id: UUID, project_id: UUID, limit: int = 20
) -> ResearchRunPage:
    _live_project(session, owner_id, project_id)
    runs = list(
        session.scalars(
            select(ResearchRun)
            .options(selectinload(ResearchRun.queries).selectinload(SearchQueryRecord.attempts))
            .where(ResearchRun.owner_id == owner_id, ResearchRun.project_id == project_id)
            .order_by(ResearchRun.queued_at.desc(), ResearchRun.id.desc())
            .limit(limit)
        ).all()
    )
    return ResearchRunPage(items=[_run_read(run) for run in runs])


def get_run(session: Session, owner_id: UUID, project_id: UUID, run_id: UUID) -> ResearchRunRead:
    _live_project(session, owner_id, project_id)
    run = session.scalar(
        select(ResearchRun)
        .options(selectinload(ResearchRun.queries).selectinload(SearchQueryRecord.attempts))
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.id == run_id,
        )
    )
    if run is None:
        raise _not_found("Research run not found")
    return _run_read(run)


def list_candidates(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    limit: int,
    cursor: str | None,
) -> CandidatePage:
    _live_project(session, owner_id, project_id)
    statement = (
        select(DiscoveryCandidate)
        .join(ResearchRun, ResearchRun.id == DiscoveryCandidate.run_id)
        .where(
            DiscoveryCandidate.project_id == project_id,
            ResearchRun.owner_id == owner_id,
        )
    )
    if cursor:
        created_at, candidate_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                DiscoveryCandidate.created_at < created_at,
                (DiscoveryCandidate.created_at == created_at)
                & (DiscoveryCandidate.id < candidate_id),
            )
        )
    candidates = list(
        session.scalars(
            statement.order_by(
                DiscoveryCandidate.created_at.desc(), DiscoveryCandidate.id.desc()
            ).limit(limit + 1)
        ).all()
    )
    has_more = len(candidates) > limit
    selected = candidates[:limit]
    output = [_candidate_read(session, candidate) for candidate in selected]
    next_cursor = _encode_cursor(selected[-1].created_at, selected[-1].id) if has_more else None
    return CandidatePage(items=output, next_cursor=next_cursor)


def _candidate_read(session: Session, candidate: DiscoveryCandidate) -> CandidateRead:
    rows = session.execute(
        select(SearchResult, SearchQueryRecord)
        .join(CandidateSearchResult, CandidateSearchResult.search_result_id == SearchResult.id)
        .join(SearchQueryRecord, SearchQueryRecord.id == SearchResult.query_id)
        .where(CandidateSearchResult.candidate_id == candidate.id)
        .order_by(SearchResult.received_at, SearchResult.id)
    ).all()
    results = [
        CandidateResultRead(
            search_result_id=result.id,
            query_id=query.id,
            query_text=query.text,
            purpose=query.purpose,
            title=result.title,
            url=result.url,
            snippet=result.snippet,
            result_rank=result.result_rank,
            received_at=result.received_at,
        )
        for result, query in rows
    ]
    return CandidateRead(
        id=candidate.id,
        project_id=candidate.project_id,
        research_run_id=candidate.run_id,
        provisional_name=candidate.provisional_name,
        brand_clue=candidate.brand_clue,
        model_clue=candidate.model_clue,
        category_clue=candidate.category_clue,
        discovery_reason=candidate.discovery_reason,
        indicative_price_text=candidate.indicative_price_text,
        observed_at=min((item.received_at for item in results), default=candidate.created_at),
        search_results=results,
    )


def _snapshot(project: ShoppingProject, command: ResearchCreate) -> dict[str, Any]:
    requirements = list(
        sorted(project.requirements, key=lambda item: (item.position, str(item.id)))
    )[:100]
    snapshot = {
        "objective": command.objective,
        "manual_queries": command.manual_queries,
        "project": {
            "id": str(project.id),
            "revision": project.revision,
            "title": project.title,
            "goal": project.goal,
            "category": project.category,
            "budget_target": _money(project.budget_target),
            "budget_maximum": _money(project.budget_maximum),
            "budget_currency": project.budget_currency,
        },
        "requirements": [
            {
                "id": str(item.id),
                "kind": item.kind,
                "label": item.label,
                "detail": item.detail,
                "attribute_key": item.attribute_key,
                "operator": item.operator,
                "value": item.value,
                "unit": item.unit,
            }
            for item in requirements
        ],
    }
    encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded) > 24_000:
        raise _invalid("Project discovery context exceeds its configured size limit")
    return snapshot


def _request_hash(command: ResearchCreate) -> str:
    encoded = json.dumps(
        command.model_dump(mode="json", exclude_none=False),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _live_project(
    session: Session, owner_id: UUID, project_id: UUID, *, lock: bool = False
) -> ShoppingProject:
    statement = select(ShoppingProject).where(
        ShoppingProject.id == project_id,
        ShoppingProject.owner_id == owner_id,
        ShoppingProject.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    project = session.scalar(statement)
    if project is None:
        raise _not_found("Project not found")
    return project


def _lock_live_run(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID
) -> tuple[ShoppingProject, ResearchRun]:
    project = _live_project(session, owner_id, project_id, lock=True)
    run = _owned_run(session, owner_id, project_id, run_id, lock=True)
    if run is None:
        raise _not_found("Research run not found")
    return project, run


def _owned_run(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID, *, lock: bool = False
) -> ResearchRun | None:
    statement = select(ResearchRun).where(
        ResearchRun.owner_id == owner_id,
        ResearchRun.project_id == project_id,
        ResearchRun.id == run_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _run_read_with_queries(
    session: Session, run: ResearchRun, *, replayed: bool
) -> ResearchRunRead:
    loaded = session.scalar(
        select(ResearchRun)
        .options(selectinload(ResearchRun.queries).selectinload(SearchQueryRecord.attempts))
        .where(ResearchRun.id == run.id)
    )
    return _run_read(loaded or run, replayed=replayed)


def _run_read(run: ResearchRun, *, replayed: bool = False) -> ResearchRunRead:
    queries = [
        SearchQueryRead(
            id=query.id,
            ordinal=query.ordinal,
            text=query.text,
            purpose=query.purpose,
            max_results=query.max_results,
            state=query.state,
            results_count=query.results_count,
            candidates_count=query.candidates_count,
            error_code=query.error_code,
            created_at=query.created_at,
            started_at=query.started_at,
            completed_at=query.completed_at,
            attempts=[
                SearchAttemptRead(
                    id=attempt.id,
                    attempt_number=attempt.attempt_number,
                    provider=attempt.provider,
                    status=attempt.status,
                    error_code=attempt.error_code,
                    provider_request_id=attempt.provider_request_id,
                    results_count=attempt.results_count,
                    usage_units=attempt.usage_units,
                    started_at=attempt.started_at,
                    finished_at=attempt.finished_at,
                )
                for attempt in query.attempts
            ],
        )
        for query in run.queries
    ]
    return ResearchRunRead(
        id=run.id,
        project_id=run.project_id,
        objective=run.objective,
        type="discovery",
        status=run.status,
        snapshot_revision=run.snapshot_revision,
        effective_budgets=run.effective_budgets,
        queries_planned=run.queries_planned,
        queries_completed=run.queries_completed,
        queries_failed=run.queries_failed,
        attempts_used=run.attempts_used,
        results_found=run.results_found,
        candidates_found=run.candidates_found,
        skipped_count=run.skipped_count,
        summary=run.summary,
        error_code=run.error_code,
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        replayed=replayed,
        queries=queries,
    )


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


def _safe_http_url(value: str) -> str | None:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not host
            or parsed.username
            or parsed.password
        ):
            return None
        port = parsed.port
        if port is not None and not (1 <= port <= 65535):
            return None
        lowered = host.lower().rstrip(".")
        if lowered == "localhost" or lowered.endswith((".localhost", ".local")):
            return None
        try:
            address = ipaddress.ip_address(lowered)
            if not address.is_global:
                return None
        except ValueError:
            if not re.fullmatch(r"[a-z0-9.-]+", lowered) or "." not in lowered:
                return None
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc,
                parsed.path or "/",
                parsed.query,
                parsed.fragment,
            )
        )
    except ValueError:
        return None


def normalize_candidate_url(url: str) -> str:
    safe = _safe_http_url(url)
    if safe is None:
        raise ValueError("search result URL is not safe HTTP/S")
    parsed = urlsplit(safe)
    host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
    port = parsed.port
    netloc = (
        host
        if port is None
        or (parsed.scheme == "http" and port == 80)
        or (parsed.scheme == "https" and port == 443)
        else f"{host}:{port}"
    )
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/") or "/", parsed.query, ""))


def _clean_text(value: str | None, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = "".join(char for char in value[:limit] if char in "\n\t" or ord(char) >= 32)
    return cleaned.strip()[:limit]


def _money(value: Any) -> str | None:
    return None if value is None else format(value, "f")


def _encode_cursor(created_at: datetime, candidate_id: UUID) -> str:
    value = json.dumps([created_at.isoformat(), str(candidate_id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return datetime.fromisoformat(value[0]), UUID(value[1])
    except (ValueError, TypeError, IndexError, json.JSONDecodeError) as error:
        raise _invalid("Candidate cursor is invalid") from error


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _invalid(message: str) -> ProjectError:
    return ProjectError(422, "validation_error", message)


def _conflict(code: str, message: str, details: dict | None = None) -> ProjectError:
    return ProjectError(409, code, message, details)
