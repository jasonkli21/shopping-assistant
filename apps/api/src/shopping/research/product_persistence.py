"""Transactional persistence for selected-product research runs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shopping.catalog.models import RetailOffer
from shopping.catalog.resolution import match_existing_variant
from shopping.evidence.assessment import record_assessment
from shopping.evidence.claim_task import PROMPT_VERSION
from shopping.evidence.classification import classify_source
from shopping.evidence.models import Claim, ResearchRunSource, Source, SourceSnapshot
from shopping.extraction.http_retriever import MAX_PAGE_BYTES
from shopping.extraction.retriever import RetrievedDocument
from shopping.extraction.schemas import CatalogExtraction
from shopping.research import service
from shopping.research.common import (
    _live_project,
    _lock_live_run,
    _not_found,
    _safe_error_code,
    normalize_candidate_url,
)
from shopping.research.models import (
    ResearchRun,
    ResearchRunTarget,
    ResearchStageAttempt,
    SearchAttempt,
    SearchQueryRecord,
    SearchResult,
)


def _work_allowed(run: ResearchRun) -> bool:
    if run.status != "running" or run.started_at is None:
        return False

    return datetime.now(UTC) < run.started_at + timedelta(
        seconds=run.effective_budgets["deadline_seconds"]
    )


def save_product_plan(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    queries: list[dict[str, Any]],
    summary: str | None,
    stage_attempt_id: UUID | None = None,
    provider_request_id: str | None = None,
    output_chars: int = 0,
) -> bool:
    project, run = _lock_live_run(session, owner_id, project_id, run_id)
    del project
    if run.status != "running" or run.run_type != "product_research":
        return False
    if not _work_allowed(run):
        return fail_product_research(
            session,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            error_code="deadline_exceeded",
            summary="The product research deadline expired before its plan could be saved.",
        )
    if run.queries_planned:
        _finish_planning_stage(
            session,
            run_id=run.id,
            owner_id=owner_id,
            attempt_id=stage_attempt_id,
            provider_request_id=provider_request_id,
            output_chars=output_chars,
        )
        session.commit()
        return True
    budget = run.effective_budgets
    now = datetime.now(UTC)
    for ordinal, query in enumerate(queries):
        target_id = UUID(query["project_product_id"])
        target = session.scalar(
            select(ResearchRunTarget).where(
                ResearchRunTarget.research_run_id == run.id,
                ResearchRunTarget.project_product_id == target_id,
                ResearchRunTarget.owner_id == owner_id,
            )
        )
        if target is None:
            raise _not_found("The research plan referenced an unavailable target")
        target.status = "running"
        target.updated_at = now
        session.add(
            SearchQueryRecord(
                run_id=run.id,
                target_project_product_id=target_id,
                ordinal=ordinal,
                text=query["text"],
                purpose=f"{query['source_class']}: {query['purpose']}",
                max_results=budget["max_results_per_query"],
                state="queued",
            )
        )
    run.queries_planned = len(queries)
    run.summary = summary[:1000] if summary else None
    _finish_planning_stage(
        session,
        run_id=run.id,
        owner_id=owner_id,
        attempt_id=stage_attempt_id,
        provider_request_id=provider_request_id,
        output_chars=output_chars,
    )
    if not queries:
        targets = list(
            session.scalars(
                select(ResearchRunTarget).where(ResearchRunTarget.research_run_id == run.id)
            ).all()
        )
        for target in targets:
            target.status = "failed"
            target.error_code = "no_sources_retrieved"
            target.updated_at = now
            record_assessment(session, run, target)
        run.status = "failed"
        run.error_code = "no_sources_retrieved"
        run.finished_at = now
        run.summary = "No sources were identified for the selected products."
    session.commit()
    return True


def start_stage_attempt(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    target_project_product_id: UUID | None,
    stage: str,
    task_name: str,
    prompt_version: str,
    input_chars: int,
    source_snapshot_id: UUID | None = None,
) -> ResearchStageAttempt | None:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.status != "running":
        return None
    target = None
    if target_project_product_id is not None:
        target = session.scalar(
            select(ResearchRunTarget).where(
                ResearchRunTarget.research_run_id == run.id,
                ResearchRunTarget.project_product_id == target_project_product_id,
                ResearchRunTarget.owner_id == owner_id,
            )
        )
        if target is None:
            raise _not_found("Research target not found")
    used = (
        session.scalar(
            select(func.count(ResearchStageAttempt.id)).where(
                ResearchStageAttempt.research_run_id == run.id,
                ResearchStageAttempt.status != "skipped",
            )
        )
        or 0
    )
    previous = (
        session.scalar(
            select(func.max(ResearchStageAttempt.attempt_number)).where(
                ResearchStageAttempt.research_run_id == run.id,
                ResearchStageAttempt.target_project_product_id == target_project_product_id,
                ResearchStageAttempt.stage == stage,
                ResearchStageAttempt.source_snapshot_id == source_snapshot_id,
            )
        )
        or 0
    )
    number = previous + 1
    reason = None
    if not _work_allowed(run):
        reason = "deadline_exceeded"
    elif input_chars > 24_000:
        reason = "input_budget_exhausted"
    elif used >= run.effective_budgets["max_ai_calls"]:
        reason = "ai_call_budget_exhausted"
    elif number > 2:
        reason = "stage_attempt_budget_exhausted"
    if reason is not None:
        if number <= 3:
            session.add(
                ResearchStageAttempt(
                    owner_id=owner_id,
                    research_run_id=run.id,
                    target_project_product_id=target_project_product_id,
                    source_snapshot_id=source_snapshot_id,
                    stage=stage,
                    attempt_number=number,
                    status="skipped",
                    task_name=task_name,
                    prompt_version=prompt_version,
                    input_chars=min(max(input_chars, 0), 24_000),
                    error_code=reason,
                    finished_at=datetime.now(UTC),
                )
            )
        if target is not None:
            target.error_code = target.error_code or reason
            target.updated_at = datetime.now(UTC)
        session.commit()
        return None
    attempt = ResearchStageAttempt(
        owner_id=owner_id,
        research_run_id=run.id,
        target_project_product_id=target_project_product_id,
        source_snapshot_id=source_snapshot_id,
        stage=stage,
        attempt_number=number,
        status="running",
        task_name=task_name,
        prompt_version=prompt_version,
        input_chars=input_chars,
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def finish_stage_attempt(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    attempt_id: UUID,
    status: str,
    error_code: str | None = None,
    provider_request_id: str | None = None,
    output_chars: int = 0,
    validation_warnings: list[dict[str, Any]] | None = None,
) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    attempt = session.scalar(
        select(ResearchStageAttempt)
        .where(
            ResearchStageAttempt.id == attempt_id,
            ResearchStageAttempt.owner_id == owner_id,
            ResearchStageAttempt.research_run_id == run.id,
        )
        .with_for_update()
    )
    if run.status != "running" or attempt is None or attempt.status != "running":
        return False
    allowed = _work_allowed(run)
    attempt.status = status if allowed else "failed"
    attempt.error_code = (
        _safe_error_code(error_code)
        if error_code and allowed
        else ("deadline_exceeded" if not allowed else None)
    )
    attempt.provider_request_id = (
        provider_request_id[:200] if isinstance(provider_request_id, str) else None
    )
    attempt.output_chars = min(max(output_chars, 0), 16_000)
    attempt.validation_warnings = (validation_warnings or [])[:20]
    attempt.finished_at = datetime.now(UTC)
    session.commit()
    return True


def planning_attempt_uncertain(
    session: Session, *, owner_id: UUID, project_id: UUID, run_id: UUID
) -> bool:
    _live_project(session, owner_id, project_id)
    return (
        session.scalar(
            select(ResearchStageAttempt.id)
            .where(
                ResearchStageAttempt.owner_id == owner_id,
                ResearchStageAttempt.research_run_id == run_id,
                ResearchStageAttempt.stage == "planning",
                ResearchStageAttempt.error_code == "uncertain_completion",
            )
            .limit(1)
        )
        is not None
    )


def _finish_planning_stage(
    session: Session,
    *,
    run_id: UUID,
    owner_id: UUID,
    attempt_id: UUID | None,
    provider_request_id: str | None,
    output_chars: int,
) -> None:
    if attempt_id is None:
        return
    attempt = session.scalar(
        select(ResearchStageAttempt)
        .where(
            ResearchStageAttempt.id == attempt_id,
            ResearchStageAttempt.owner_id == owner_id,
            ResearchStageAttempt.research_run_id == run_id,
            ResearchStageAttempt.stage == "planning",
        )
        .with_for_update()
    )
    if attempt is None or attempt.status != "running":
        return
    attempt.status = "succeeded"
    attempt.error_code = None
    attempt.provider_request_id = (
        provider_request_id[:200] if isinstance(provider_request_id, str) else None
    )
    attempt.output_chars = min(max(output_chars, 0), 16_000)
    attempt.finished_at = datetime.now(UTC)


def list_target_results(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
) -> dict[UUID, list[tuple[SearchResult, SearchQueryRecord]]]:
    _live_project(session, owner_id, project_id)
    run = session.scalar(
        select(ResearchRun).where(
            ResearchRun.id == run_id,
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
        )
    )
    if run is None:
        raise _not_found("Research run not found")
    rows = session.execute(
        select(SearchResult, SearchQueryRecord)
        .join(SearchQueryRecord, SearchQueryRecord.id == SearchResult.query_id)
        .where(
            SearchQueryRecord.run_id == run.id,
            SearchQueryRecord.target_project_product_id.is_not(None),
        )
        .order_by(SearchQueryRecord.ordinal, SearchResult.result_rank)
    ).all()
    grouped: dict[UUID, list[tuple[SearchResult, SearchQueryRecord]]] = {}
    for result, query in rows:
        grouped.setdefault(query.target_project_product_id, []).append((result, query))
    return grouped


def start_offer_refresh_targets(
    session: Session, *, owner_id: UUID, project_id: UUID, run_id: UUID
) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.status != "running" or run.run_type != "product_research":
        return False
    targets = list(
        session.scalars(
            select(ResearchRunTarget)
            .where(ResearchRunTarget.research_run_id == run.id)
            .with_for_update()
        ).all()
    )
    now = datetime.now(UTC)
    for target in targets:
        if target.status == "queued":
            target.status = "running"
            target.updated_at = now
    session.commit()
    return True


def processed_offer_refresh_urls(
    session: Session, *, owner_id: UUID, project_id: UUID, run_id: UUID, target_id: UUID
) -> set[str]:
    _live_project(session, owner_id, project_id)
    run = session.scalar(
        select(ResearchRun).where(
            ResearchRun.id == run_id,
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
        )
    )
    if run is None:
        return set()
    urls = session.scalars(
        select(ResearchRunSource.requested_url).where(
            ResearchRunSource.owner_id == owner_id,
            ResearchRunSource.research_run_id == run.id,
            ResearchRunSource.project_product_id == target_id,
            ResearchRunSource.offer_status.in_(
                ["succeeded", "no_offer", "identity_mismatch", "unsupported"]
            ),
        )
    ).all()
    normalized: set[str] = set()
    for url in urls:
        try:
            normalized.add(normalize_candidate_url(url))
        except ValueError:
            continue
    return normalized


def prior_source_attempts_by_result(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    target_id: UUID,
) -> dict[UUID, dict[str, Any]]:
    """Latest persisted retrieval outcome for each search result in this run."""
    _live_project(session, owner_id, project_id)
    rows = (
        session.execute(
            select(ResearchRunSource)
            .where(
                ResearchRunSource.owner_id == owner_id,
                ResearchRunSource.research_run_id == run_id,
                ResearchRunSource.project_product_id == target_id,
                ResearchRunSource.search_result_id.is_not(None),
            )
            .order_by(ResearchRunSource.retrieved_at.desc(), ResearchRunSource.id.desc())
        )
        .scalars()
        .all()
    )
    outcomes: dict[UUID, dict[str, Any]] = {}
    for attempt in rows:
        if attempt.search_result_id in outcomes:
            continue
        outcomes[attempt.search_result_id] = {
            "attempt_id": attempt.id,
            "snapshot_id": attempt.snapshot_id,
            "status": attempt.status,
        }
    return outcomes


def _source_for_url(
    session: Session,
    *,
    owner_id: UUID,
    url: str,
    title: str | None,
    brand: str | None,
) -> Source:
    normalized = normalize_candidate_url(url)
    source = session.scalar(
        select(Source)
        .where(Source.owner_id == owner_id, Source.normalized_url == normalized)
        .with_for_update()
    )
    if source is None:
        host = (urlsplit(normalized).hostname or "unknown").casefold()[:253]
        classification = classify_source(normalized, title=title, brand=brand)
        session.execute(
            pg_insert(Source)
            .values(
                owner_id=owner_id,
                normalized_url=normalized,
                title=(title or "")[:300] or None,
                publisher=host[:200],
                domain=host,
                classification=classification.classification,
                classification_basis=classification.basis[:500],
                classification_actor="system",
                classification_version="source-classifier.v1",
            )
            .on_conflict_do_nothing(index_elements=["owner_id", "normalized_url"])
        )
        source = session.scalar(
            select(Source)
            .where(Source.owner_id == owner_id, Source.normalized_url == normalized)
            .with_for_update()
        )
    elif title and not source.title:
        source.title = title[:300]
    return source


def start_source_attempt(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    project_product_id: UUID,
    search_result_id: UUID | None,
    url: str,
    title: str | None,
    brand: str | None,
) -> tuple[UUID, str | None, int] | None:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.status != "running" or run.run_type != "product_research":
        return None
    target = session.scalar(
        select(ResearchRunTarget)
        .where(
            ResearchRunTarget.research_run_id == run.id,
            ResearchRunTarget.project_product_id == project_product_id,
            ResearchRunTarget.owner_id == owner_id,
        )
        .with_for_update()
    )
    if target is None:
        raise _not_found("Research target not found")
    source = _source_for_url(session, owner_id=owner_id, url=url, title=title, brand=brand)
    prior_attempts = (
        session.scalar(
            select(func.count(ResearchRunSource.id)).where(
                ResearchRunSource.research_run_id == run.id,
                ResearchRunSource.project_product_id == project_product_id,
                ResearchRunSource.source_id == source.id,
            )
        )
        or 0
    )
    attempt_number = prior_attempts + 1
    current_pages = (
        session.scalar(
            select(func.count(ResearchRunSource.id)).where(
                ResearchRunSource.research_run_id == run.id,
                ResearchRunSource.status != "skipped",
            )
        )
        or 0
    )
    bytes_used = (
        session.scalar(
            select(func.coalesce(func.sum(ResearchRunSource.bytes_read), 0)).where(
                ResearchRunSource.research_run_id == run.id
            )
        )
        or 0
    )
    reason = None if _work_allowed(run) else "deadline_exceeded"
    if (
        reason is None
        and target.sources_attempted >= run.effective_budgets["max_sources_per_product"]
    ):
        reason = "source_budget_exhausted"
    elif reason is None and current_pages >= run.effective_budgets["max_pages"]:
        reason = "page_budget_exhausted"
    elif reason is None and bytes_used >= run.effective_budgets["max_total_bytes"]:
        reason = "byte_budget_exhausted"
    row = ResearchRunSource(
        owner_id=owner_id,
        research_run_id=run.id,
        project_product_id=project_product_id,
        search_result_id=search_result_id,
        source_id=source.id,
        requested_url=url[:2048],
        final_url=url[:2048],
        retrieved_at=datetime.now(UTC),
        status="skipped" if reason else "running",
        reason=reason,
        attempt_number=attempt_number,
    )
    session.add(row)
    if reason is None:
        target.sources_attempted += 1
    target.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(row)
    remaining_bytes = max(0, run.effective_budgets["max_total_bytes"] - int(bytes_used))
    return row.id, reason, remaining_bytes


def finish_source_attempt(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    source_attempt_id: UUID,
    status: str,
    reason: str | None,
    document: RetrievedDocument | None = None,
    title: str | None = None,
    published_at: datetime | None = None,
    relevant_text: str | None = None,
    classification: str | None = None,
    classification_basis: str | None = None,
    bytes_read: int | None = None,
    offer_refresh: bool = False,
    offer_extraction: CatalogExtraction | None = None,
    offer_error_code: str | None = None,
) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    attempt = session.scalar(
        select(ResearchRunSource)
        .where(
            ResearchRunSource.id == source_attempt_id,
            ResearchRunSource.owner_id == owner_id,
            ResearchRunSource.research_run_id == run.id,
        )
        .with_for_update()
    )
    if run.status != "running" or attempt is None or attempt.status != "running":
        return False
    allowed = _work_allowed(run)
    now = document.retrieved_at if document else datetime.now(UTC)
    attempt.status = status if allowed else "failed"
    attempt.reason = ((reason or "") if allowed else "deadline_exceeded")[:80] or None
    attempt.retrieved_at = now
    if bytes_read is not None:
        attempt.bytes_read = min(max(bytes_read, 0), 20_000_000)
    if document is not None and not allowed:
        attempt.bytes_read = min(
            max(document.decoded_bytes or 0, len(document.body.encode("utf-8"))),
            20_000_000,
        )
        attempt.final_url = document.final_url[:2048]
    if document is not None and allowed:
        attempt.final_url = document.final_url[:2048]
        actual_bytes = max(document.decoded_bytes or 0, len(document.body.encode("utf-8")))
        used = (
            session.scalar(
                select(func.coalesce(func.sum(ResearchRunSource.bytes_read), 0)).where(
                    ResearchRunSource.research_run_id == run.id
                )
            )
            or 0
        )
        if (
            actual_bytes > MAX_PAGE_BYTES
            or used + actual_bytes > run.effective_budgets["max_total_bytes"]
        ):
            attempt.status = "failed"
            attempt.reason = "byte_budget_exceeded"
            attempt.bytes_read = min(actual_bytes, 20_000_000)
            session.commit()
            return False
        attempt.bytes_read = actual_bytes
        snapshot = session.scalar(
            select(SourceSnapshot).where(
                SourceSnapshot.source_id == attempt.source_id,
                SourceSnapshot.content_hash == document.content_hash,
            )
        )
        if snapshot is None:
            snapshot = SourceSnapshot(
                owner_id=owner_id,
                source_id=attempt.source_id,
                content_hash=document.content_hash,
                media_type=(document.content_type or "")[:200] or None,
                title=(title or "")[:300] or None,
                published_at=published_at,
                retrieved_at=document.retrieved_at,
                relevant_text=relevant_text or "",
                excerpts=[],
                extractor_version="httpx-page-retriever.v1",
            )
            session.add(snapshot)
            session.flush()
        attempt.snapshot_id = snapshot.id
        target = session.scalar(
            select(ResearchRunTarget)
            .where(
                ResearchRunTarget.research_run_id == run.id,
                ResearchRunTarget.project_product_id == attempt.project_product_id,
            )
            .with_for_update()
        )
        if target is not None:
            target.sources_retrieved += 1
            target.updated_at = now
        source = session.scalar(
            select(Source).where(Source.id == attempt.source_id, Source.owner_id == owner_id)
        )
        if source is not None:
            if title and source.classification_actor != "user":
                source.title = title[:300]
            if published_at is not None and source.classification_actor != "user":
                source.updated_at = now
            if classification and source.classification_actor == "system":
                source.classification = classification
                source.classification_basis = (classification_basis or "")[:500] or None
                source.classification_version = "source-classifier.v1"
                source.updated_at = now
        if offer_refresh:
            _save_offer_observation(
                session,
                run=run,
                attempt=attempt,
                target=target,
                document=document,
                extraction=offer_extraction,
                error_code=offer_error_code,
            )
    elif offer_refresh:
        attempt.offer_status = "failed"
        attempt.offer_error_code = _safe_error_code(offer_error_code or reason or status)
        attempt.offer_observation = {}
    session.commit()
    return allowed


def _save_offer_observation(
    session: Session,
    *,
    run: ResearchRun,
    attempt: ResearchRunSource,
    target: ResearchRunTarget | None,
    document: RetrievedDocument,
    extraction: CatalogExtraction | None,
    error_code: str | None,
) -> None:
    if error_code:
        attempt.offer_status = "unsupported"
        attempt.offer_error_code = _safe_error_code(error_code)
        attempt.offer_observation = {}
        return
    if extraction is None or extraction.offer is None:
        attempt.offer_status = "no_offer"
        attempt.offer_error_code = None
        attempt.offer_observation = {}
        return
    if target is None:
        attempt.offer_status = "identity_mismatch"
        attempt.offer_error_code = "target_missing"
        attempt.offer_observation = {}
        return
    decision = match_existing_variant(session, run.owner_id, extraction)
    if (
        decision.product is None
        or decision.variant is None
        or decision.product.id != target.product_id
        or decision.variant.id != target.variant_id
    ):
        attempt.offer_status = "identity_mismatch"
        attempt.offer_error_code = "variant_identity_mismatch"
        attempt.offer_observation = {}
        return
    offer = extraction.offer
    parsed = urlsplit(document.final_url)
    if parsed.hostname is None or parsed.username is not None or parsed.password is not None:
        attempt.offer_status = "unsupported"
        attempt.offer_error_code = "invalid_offer_origin"
        attempt.offer_observation = {}
        return
    retailer_domain = parsed.hostname.casefold().removeprefix("www.")[:253]
    attempt.offer_status = "succeeded"
    attempt.offer_error_code = None
    attempt.offer_observation = {
        "retailer_name": offer.retailer_name[:200],
        "retailer_domain": retailer_domain,
        "amount": format(offer.amount, ".2f") if offer.amount is not None else None,
        "currency": offer.currency,
        "availability": offer.availability,
        "condition": offer.condition,
    }
    session.add(
        RetailOffer(
            owner_id=run.owner_id,
            variant_id=target.variant_id,
            observation_id=None,
            research_source_attempt_id=attempt.id,
            idempotency_key=f"research-source:{attempt.id}",
            retailer_name=offer.retailer_name,
            retailer_domain=retailer_domain,
            url=offer.url,
            amount=offer.amount,
            currency=offer.currency,
            availability=offer.availability,
            condition=offer.condition,
            observed_at=document.retrieved_at,
        )
    )


def finish_product_research(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.status != "running" or run.run_type != "product_research":
        return False
    expired = not _work_allowed(run)
    if expired:
        now = datetime.now(UTC)
        open_queries = list(
            session.scalars(
                select(SearchQueryRecord)
                .where(
                    SearchQueryRecord.run_id == run.id,
                    SearchQueryRecord.state.in_(["queued", "running"]),
                )
                .with_for_update()
            ).all()
        )
        for query in open_queries:
            query.state = "skipped" if query.state == "queued" else "failed"
            query.error_code = "deadline_exceeded"
            query.retry_not_before = None
            query.completed_at = now
            if query.state == "skipped":
                run.skipped_count += 1
            else:
                run.queries_failed += 1
                for attempt in session.scalars(
                    select(SearchAttempt)
                    .where(SearchAttempt.query_id == query.id, SearchAttempt.status == "running")
                    .with_for_update()
                ).all():
                    attempt.status = "failed"
                    attempt.error_code = "deadline_exceeded"
                    attempt.finished_at = now
        for attempt in session.scalars(
            select(ResearchRunSource)
            .where(
                ResearchRunSource.research_run_id == run.id,
                ResearchRunSource.status == "running",
            )
            .with_for_update()
        ).all():
            attempt.status = "failed"
            attempt.reason = "deadline_exceeded"
        for stage in session.scalars(
            select(ResearchStageAttempt)
            .where(
                ResearchStageAttempt.research_run_id == run.id,
                ResearchStageAttempt.status == "running",
            )
            .with_for_update()
        ).all():
            stage.status = "failed"
            stage.error_code = "deadline_exceeded"
            stage.finished_at = now
    targets = list(
        session.scalars(
            select(ResearchRunTarget)
            .where(ResearchRunTarget.research_run_id == run.id)
            .with_for_update()
        ).all()
    )
    for target in targets:
        if expired and target.status not in {"failed", "skipped"}:
            target.error_code = target.error_code or "deadline_exceeded"
        record_assessment(session, run, target)
        if target.status in {"failed", "skipped"}:
            continue
        failed_sources = (
            session.scalar(
                select(func.count(ResearchRunSource.id)).where(
                    ResearchRunSource.research_run_id == run.id,
                    ResearchRunSource.project_product_id == target.project_product_id,
                    ResearchRunSource.status.in_(
                        ["blocked", "timeout", "unsupported", "failed", "skipped"]
                    ),
                )
            )
            or 0
        )
        failed_stages = (
            session.scalar(
                select(func.count(ResearchStageAttempt.id)).where(
                    ResearchStageAttempt.research_run_id == run.id,
                    ResearchStageAttempt.target_project_product_id == target.project_product_id,
                    ResearchStageAttempt.status == "failed",
                )
            )
            or 0
        )
        refresh_targets = run.input_snapshot.get("refresh_targets", [])
        claims_requested = not refresh_targets or "claims" in refresh_targets
        offers_requested = "offers" in refresh_targets
        usable_claims = (
            session.scalar(
                select(func.count(Claim.id)).where(
                    Claim.owner_id == owner_id,
                    Claim.subject_product_id == target.product_id,
                    Claim.subject_variant_id == target.variant_id,
                    Claim.prompt_version == PROMPT_VERSION,
                )
            )
            or 0
        )
        offer_rows = list(
            session.scalars(
                select(ResearchRunSource).where(
                    ResearchRunSource.research_run_id == run.id,
                    ResearchRunSource.project_product_id == target.project_product_id,
                    ResearchRunSource.offer_status.is_not(None),
                )
            ).all()
        )
        failed_offers = sum(item.offer_status != "succeeded" for item in offer_rows)
        succeeded_offers = sum(item.offer_status == "succeeded" for item in offer_rows)
        offer_problem = offers_requested and (succeeded_offers == 0 or failed_offers > 0)
        if target.sources_retrieved > 0:
            if claims_requested and usable_claims == 0 and not target.error_code:
                target.error_code = "no_grounded_claims"
            if offers_requested and offer_problem and not target.error_code:
                target.error_code = "offer_refresh_unavailable"
            target.status = (
                "partial"
                if failed_sources or failed_stages or target.error_code or offer_problem
                else "succeeded"
            )
        else:
            target.status = "failed"
            target.error_code = target.error_code or (
                "offer_refresh_unavailable" if offers_requested else "no_sources_retrieved"
            )
        target.updated_at = datetime.now(UTC)
    succeeded = sum(target.status == "succeeded" for target in targets)
    partial = sum(target.status == "partial" for target in targets)
    failed = sum(target.status in {"failed", "skipped"} for target in targets)
    now = datetime.now(UTC)
    if succeeded + partial == 0:
        run.status = "failed"
        run.summary = "No selected product source pages could be retrieved."
        run.error_code = "deadline_exceeded" if expired else "no_sources_retrieved"
    elif partial or failed or run.queries_failed or run.skipped_count:
        run.status = "partial"
        run.summary = (
            "The research deadline expired after some evidence was saved."
            if expired
            else "Research retrieved some source pages; some planned work failed or was skipped."
        )
        if expired:
            run.error_code = "deadline_exceeded"
    else:
        run.status = "succeeded"
        run.summary = "Research retrieved source snapshots for each selected product."
    run.finished_at = now
    session.commit()
    return True


def fail_product_research(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    error_code: str,
    summary: str,
) -> bool:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
    if run.run_type != "product_research" or run.status != "running":
        return False
    expired = not _work_allowed(run)
    code = "deadline_exceeded" if expired else _safe_error_code(error_code)
    if expired:
        summary = "The product research deadline expired before this work could finish."
    if not service.fail_run(session, owner_id, project_id, run_id, code, summary):
        return False
    targets = list(
        session.scalars(
            select(ResearchRunTarget)
            .where(ResearchRunTarget.research_run_id == run_id)
            .with_for_update()
        ).all()
    )
    for target in targets:
        if target.status not in {"failed", "skipped"}:
            target.status = "failed"
            target.error_code = code
            target.updated_at = datetime.now(UTC)
        record_assessment(session, run, target)
    session.commit()
    return True
