from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from shopping.research.common import (
    _decode_cursor,
    _encode_cursor,
    _live_project,
    _not_found,
    _owned_run,
    _validate_page_limit,
)
from shopping.research.models import (
    CandidateSearchResult,
    DiscoveryCandidate,
    ResearchRun,
    SearchQueryRecord,
    SearchResult,
)
from shopping.research.schemas import (
    CandidatePage,
    CandidateRead,
    CandidateResultRead,
    ResearchRunPage,
    ResearchRunRead,
    SearchAttemptRead,
    SearchQueryRead,
)


def list_runs(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    limit: int = 20,
    *,
    cursor: str | None = None,
) -> ResearchRunPage:
    _live_project(session, owner_id, project_id)
    _validate_page_limit(limit)
    statement = (
        select(ResearchRun)
        .options(selectinload(ResearchRun.queries).selectinload(SearchQueryRecord.attempts))
        .where(ResearchRun.owner_id == owner_id, ResearchRun.project_id == project_id)
    )
    if cursor is not None:
        queued_at, run_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                ResearchRun.queued_at < queued_at,
                (ResearchRun.queued_at == queued_at) & (ResearchRun.id < run_id),
            )
        )
    runs = list(
        session.scalars(
            statement.order_by(ResearchRun.queued_at.desc(), ResearchRun.id.desc()).limit(limit + 1)
        ).all()
    )
    has_more = len(runs) > limit
    selected = runs[:limit]
    next_cursor = _encode_cursor(selected[-1].queued_at, selected[-1].id) if has_more else None
    return ResearchRunPage(items=[_run_read(run) for run in selected], next_cursor=next_cursor)


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
    run_id: UUID | None = None,
) -> CandidatePage:
    _live_project(session, owner_id, project_id)
    _validate_page_limit(limit)
    statement = (
        select(DiscoveryCandidate)
        .join(ResearchRun, ResearchRun.id == DiscoveryCandidate.run_id)
        .where(
            DiscoveryCandidate.project_id == project_id,
            ResearchRun.owner_id == owner_id,
        )
    )
    if run_id is not None:
        if _owned_run(session, owner_id, project_id, run_id) is None:
            raise _not_found("Research run not found")
        statement = statement.where(DiscoveryCandidate.run_id == run_id)
    if cursor is not None:
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
