from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shopping.evidence import claim_task
from shopping.evidence.assessment import record_assessment
from shopping.evidence.classification import classify_source, page_metadata
from shopping.evidence.models import ResearchRunSource, Source, SourceSnapshot
from shopping.evidence.service import extraction_input, persist_extraction
from shopping.extraction.http_retriever import MAX_PAGE_BYTES, html_to_text
from shopping.extraction.retriever import PageRetrievalError, PageRetriever, RetrievedDocument
from shopping.integrations.personal_ai.client import AIProviderError, PersonalAIClient
from shopping.research import service
from shopping.research.common import (
    _live_project,
    _lock_live_run,
    _not_found,
    normalize_candidate_url,
)
from shopping.research.models import (
    ResearchRun,
    ResearchRunTarget,
    ResearchStageAttempt,
    SearchQueryRecord,
    SearchResult,
)
from shopping.research.product_task import (
    PROMPT_VERSION,
    TASK_NAME,
    build_request,
    validate_output,
)
from shopping.search.provider import SearchProvider, SearchProviderError, SearchQuery

logger = logging.getLogger(__name__)
WithSession = Callable[[Callable[[Session], Any]], Awaitable[Any]]
RemainingSeconds = Callable[[], Awaitable[float]]


def save_product_plan(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    queries: list[dict[str, Any]],
    summary: str | None,
) -> bool:
    project, run = _lock_live_run(session, owner_id, project_id, run_id)
    del project
    if run.status != "running" or run.run_type != "product_research":
        return False
    if run.queries_planned:
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
    if not queries:
        run.status = "succeeded"
        run.finished_at = now
        run.summary = run.summary or "No sources were identified for the selected products."
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
    if run.status != "running" or input_chars > 24_000:
        return None
    used = (
        session.scalar(
            select(func.count(ResearchStageAttempt.id)).where(
                ResearchStageAttempt.research_run_id == run.id
            )
        )
        or 0
    )
    if used >= run.effective_budgets["max_ai_calls"]:
        return None
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
    if number > 2:
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
    attempt.status = status
    attempt.error_code = error_code
    attempt.provider_request_id = (
        provider_request_id[:200] if isinstance(provider_request_id, str) else None
    )
    attempt.output_chars = min(max(output_chars, 0), 16_000)
    attempt.validation_warnings = (validation_warnings or [])[:20]
    attempt.finished_at = datetime.now(UTC)
    session.commit()
    return True


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
    search_result_id: UUID,
    url: str,
    title: str | None,
    brand: str | None,
) -> tuple[UUID, str | None, int] | None:
    _project, run = _lock_live_run(session, owner_id, project_id, run_id)
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
    reason = None
    if target.sources_attempted >= run.effective_budgets["max_sources_per_product"]:
        reason = "source_budget_exhausted"
    elif current_pages >= run.effective_budgets["max_pages"]:
        reason = "page_budget_exhausted"
    elif bytes_used >= run.effective_budgets["max_total_bytes"]:
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
    now = document.retrieved_at if document else datetime.now(UTC)
    attempt.status = status
    attempt.reason = (reason or "")[:80] or None
    attempt.retrieved_at = now
    if bytes_read is not None:
        attempt.bytes_read = max(bytes_read, 0)
    if document is not None:
        attempt.final_url = document.final_url[:2048]
        attempt.bytes_read = document.decoded_bytes or len(document.body.encode("utf-8"))
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
    session.commit()
    return True


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
    targets = list(
        session.scalars(
            select(ResearchRunTarget)
            .where(ResearchRunTarget.research_run_id == run.id)
            .with_for_update()
        ).all()
    )
    for target in targets:
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
        if target.sources_retrieved > 0:
            target.status = "partial" if failed_sources or failed_stages else "succeeded"
        else:
            target.status = "failed"
            target.error_code = target.error_code or "no_sources_retrieved"
        target.updated_at = datetime.now(UTC)
    succeeded = sum(target.status == "succeeded" for target in targets)
    partial = sum(target.status == "partial" for target in targets)
    failed = sum(target.status in {"failed", "skipped"} for target in targets)
    now = datetime.now(UTC)
    if succeeded + partial == 0:
        run.status = "failed"
        run.summary = "No selected product source pages could be retrieved."
        run.error_code = "no_sources_retrieved"
    elif partial or failed or run.queries_failed or run.skipped_count:
        run.status = "partial"
        run.summary = (
            "Research retrieved some source pages; some planned work failed or was skipped."
        )
    else:
        run.status = "succeeded"
        run.summary = "Research retrieved source snapshots for each selected product."
    run.finished_at = now
    session.commit()
    return True


async def run_product_research(
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    snapshot: dict[str, Any],
    budgets: dict[str, int],
    client: PersonalAIClient,
    search_provider: SearchProvider,
    with_session: WithSession,
    remaining_seconds: RemainingSeconds,
    provider_timeout_seconds: int,
    page_retriever: PageRetriever | None = None,
) -> None:
    request = build_request(snapshot, budgets["max_queries"])
    input_chars = len(json.dumps(request.input, ensure_ascii=False, separators=(",", ":")))
    stage_attempt = await with_session(
        lambda session: start_stage_attempt(
            session,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            target_project_product_id=None,
            stage="planning",
            task_name=TASK_NAME,
            prompt_version=PROMPT_VERSION,
            input_chars=input_chars,
        )
    )
    if stage_attempt is None:
        await _fail_product_run(
            with_session,
            owner_id,
            project_id,
            run_id,
            "ai_call_budget_exhausted",
            "The product research planner could not start within the saved AI call budget.",
        )
        return
    try:
        timeout = min(provider_timeout_seconds, await remaining_seconds())
        if timeout <= 0:
            raise TimeoutError
        async with asyncio.timeout(timeout):
            response = await client.generate(request)
        if response.refused:
            raise AIProviderError("provider_refused")
        output = validate_output(
            response.output,
            snapshot,
            max_queries=budgets["max_queries"],
            max_output_chars=budgets["max_output_chars"],
        )
        output_chars = len(json.dumps(response.output, ensure_ascii=False, separators=(",", ":")))
        await with_session(
            lambda session: finish_stage_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                attempt_id=stage_attempt.id,
                status="succeeded",
                provider_request_id=response.provider_request_id,
                output_chars=output_chars,
            )
        )
    except (TimeoutError, AIProviderError, ValueError) as error:
        code = (
            "provider_timeout"
            if isinstance(error, TimeoutError)
            else (error.code if isinstance(error, AIProviderError) else "malformed_response")
        )
        await with_session(
            lambda session: finish_stage_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                attempt_id=stage_attempt.id,
                status="failed",
                error_code=code,
            )
        )

        await _fail_product_run(
            with_session,
            owner_id,
            project_id,
            run_id,
            code,
            "The product research planner could not produce a valid bounded source plan.",
        )
        return
    except Exception as error:
        logger.warning("Product research planning failed for %s (%s)", run_id, type(error).__name__)
        await with_session(
            lambda session: finish_stage_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                attempt_id=stage_attempt.id,
                status="failed",
                error_code="provider_error",
            )
        )
        await _fail_product_run(
            with_session,
            owner_id,
            project_id,
            run_id,
            "provider_error",
            "The product research planner could not finish.",
        )
        return

    saved = await with_session(
        lambda session: save_product_plan(
            session,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            queries=[item.model_dump(mode="json") for item in output.queries],
            summary=output.explanation,
        )
    )
    if not saved:
        return
    query_rows = await with_session(
        lambda session: service.list_run_queries(session, owner_id, project_id, run_id)
    )
    for query_id, max_results in query_rows:
        attempt = await with_session(
            lambda session, current_id=query_id: service.start_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                query_id=current_id,
            )
        )
        if attempt is None:
            continue
        query, attempt_id, allowance = attempt
        timeout = min(provider_timeout_seconds, await remaining_seconds())
        if timeout <= 0:
            await service_attempt_failure(
                with_session,
                owner_id,
                project_id,
                run_id,
                query_id,
                attempt_id,
                "deadline_exceeded",
            )
            continue
        try:
            async with asyncio.timeout(timeout):
                result = await search_provider.search(
                    SearchQuery(text=query.text, max_results=min(max_results, allowance))
                )
            completed = await with_session(
                partial(
                    service.complete_attempt,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    query_id=query_id,
                    attempt_id=attempt_id,
                    response=result,
                )
            )
            if not completed:
                return
        except TimeoutError:
            await service_attempt_failure(
                with_session, owner_id, project_id, run_id, query_id, attempt_id, "provider_timeout"
            )
        except SearchProviderError as error:
            await service_attempt_failure(
                with_session, owner_id, project_id, run_id, query_id, attempt_id, error.code
            )
        except ValueError:
            await service_attempt_failure(
                with_session,
                owner_id,
                project_id,
                run_id,
                query_id,
                attempt_id,
                "malformed_response",
            )
        except Exception as error:
            logger.info("Product search attempt failed for %s (%s)", run_id, type(error).__name__)
            await service_attempt_failure(
                with_session, owner_id, project_id, run_id, query_id, attempt_id, "provider_error"
            )

    by_target = await with_session(
        lambda session: list_target_results(
            session, owner_id=owner_id, project_id=project_id, run_id=run_id
        )
    )
    targets = snapshot.get("selected_products", [])
    for target in targets:
        target_id = UUID(target["project_product_id"])
        results = by_target.get(target_id, [])
        seen: set[str] = set()
        selected: list[tuple[SearchResult, SearchQueryRecord]] = []
        for result, query in results:
            try:
                normalized = normalize_candidate_url(result.url)
            except ValueError:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            if len(selected) >= budgets["max_sources_per_product"]:
                break
            selected.append((result, query))
        for result, _query in selected:
            if await remaining_seconds() <= 0:
                break
            started = await with_session(
                partial(
                    start_source_attempt,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    project_product_id=target_id,
                    search_result_id=result.id,
                    url=result.url,
                    title=result.title,
                    brand=target.get("brand"),
                )
            )
            if started is None:
                continue
            source_attempt_id, skip_reason, remaining_bytes = started
            if skip_reason:
                continue
            try:
                retriever = page_retriever
                if retriever is None:
                    raise RuntimeError("The research page retriever was not configured")
                timeout = min(provider_timeout_seconds, await remaining_seconds())
                if timeout <= 0:
                    raise PageRetrievalError("timeout", "The run deadline expired.")
                async with asyncio.timeout(timeout):
                    retrieve_with_limit = getattr(retriever, "retrieve_with_limit", None)
                    if retrieve_with_limit is None:
                        document = await retriever.retrieve(result.url)
                    else:
                        document = await retrieve_with_limit(
                            result.url, min(MAX_PAGE_BYTES, remaining_bytes)
                        )
                actual_bytes = document.decoded_bytes or len(document.body.encode("utf-8"))
                if actual_bytes > remaining_bytes:
                    await with_session(
                        partial(
                            finish_source_attempt,
                            owner_id=owner_id,
                            project_id=project_id,
                            run_id=run_id,
                            source_attempt_id=source_attempt_id,
                            status="failed",
                            reason="byte_budget_exceeded",
                            bytes_read=actual_bytes,
                        )
                    )
                    continue
                text_content = html_to_text(document.body)
                metadata = page_metadata(document.body)
                source_title = metadata.title or result.title
                classification = classify_source(
                    document.final_url,
                    title=source_title,
                    text=text_content,
                    brand=target.get("brand"),
                )
                bounded_text = _bounded_utf8(text_content, 12_000)
                stored = await with_session(
                    partial(
                        finish_source_attempt,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        source_attempt_id=source_attempt_id,
                        status="retrieved",
                        reason=None,
                        document=document,
                        title=source_title,
                        published_at=metadata.published_at,
                        relevant_text=bounded_text,
                        classification=classification.classification,
                        classification_basis=classification.basis,
                    )
                )
                if stored:
                    await _extract_source_claims(
                        with_session=with_session,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        target=target,
                        source_attempt_id=source_attempt_id,
                        client=client,
                        remaining_seconds=remaining_seconds,
                        provider_timeout_seconds=provider_timeout_seconds,
                        max_output_chars=budgets["max_output_chars"],
                    )
            except PageRetrievalError as error:
                status = _retrieval_status(error.code)
                await with_session(
                    partial(
                        finish_source_attempt,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        source_attempt_id=source_attempt_id,
                        status=status,
                        reason=error.code,
                    )
                )
            except TimeoutError:
                await with_session(
                    lambda session, current_attempt=source_attempt_id: finish_source_attempt(
                        session,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        source_attempt_id=current_attempt,
                        status="timeout",
                        reason="timeout",
                    )
                )
            except Exception as error:
                logger.info("Source retrieval failed for %s (%s)", result.url, type(error).__name__)
                await with_session(
                    lambda session, current_attempt=source_attempt_id: finish_source_attempt(
                        session,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        source_attempt_id=current_attempt,
                        status="failed",
                        reason="retrieval_failed",
                    )
                )
    await with_session(
        lambda session: finish_product_research(
            session, owner_id=owner_id, project_id=project_id, run_id=run_id
        )
    )


async def _extract_source_claims(
    *,
    with_session: WithSession,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    target: dict[str, Any],
    source_attempt_id: UUID,
    client: PersonalAIClient,
    remaining_seconds: RemainingSeconds,
    provider_timeout_seconds: int,
    max_output_chars: int,
) -> None:
    target_id = UUID(target["project_product_id"])
    source_input = await with_session(
        lambda session: extraction_input(
            session,
            owner_id=owner_id,
            run_id=run_id,
            target_id=target_id,
            attempt_id=source_attempt_id,
        )
    )
    if source_input is None:
        return
    _identity, source, text_content = source_input
    if not text_content:
        return
    request = claim_task.build_request(target=target, source=source, text=text_content)
    input_chars = len(json.dumps(request.input, ensure_ascii=False, separators=(",", ":")))
    stage = await with_session(
        lambda session: start_stage_attempt(
            session,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            target_project_product_id=target_id,
            source_snapshot_id=UUID(source["snapshot_id"]),
            stage="extraction",
            task_name=claim_task.TASK_NAME,
            prompt_version=claim_task.PROMPT_VERSION,
            input_chars=input_chars,
        )
    )
    if stage is None:
        return
    try:
        timeout = min(provider_timeout_seconds, await remaining_seconds())
        if timeout <= 0:
            raise TimeoutError
        async with asyncio.timeout(timeout):
            response = await client.generate(request)
        if response.refused:
            raise AIProviderError("provider_refused")
        extraction = claim_task.validate_output(
            response.output,
            target=target,
            source_text=text_content,
            max_output_chars=max_output_chars,
        )
        await with_session(
            lambda session: persist_extraction(
                session,
                owner_id=owner_id,
                run_id=run_id,
                target_id=target_id,
                source_attempt_id=source_attempt_id,
                extraction=extraction,
            )
        )
        await with_session(
            lambda session: finish_stage_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                attempt_id=stage.id,
                status="succeeded",
                provider_request_id=response.provider_request_id,
                output_chars=len(json.dumps(response.output, ensure_ascii=False)),
                validation_warnings=extraction.warnings,
            )
        )
    except (TimeoutError, AIProviderError, ValueError) as error:
        code = (
            "provider_timeout"
            if isinstance(error, TimeoutError)
            else (error.code if isinstance(error, AIProviderError) else "malformed_response")
        )
        await with_session(
            lambda session: finish_stage_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                attempt_id=stage.id,
                status="failed",
                error_code=code,
            )
        )
    except Exception as error:
        logger.warning("Claim extraction failed for %s (%s)", run_id, type(error).__name__)
        await with_session(
            lambda session: finish_stage_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                attempt_id=stage.id,
                status="failed",
                error_code="extraction_failed",
            )
        )


async def service_attempt_failure(
    with_session: WithSession,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    query_id: UUID,
    attempt_id: UUID,
    code: str,
) -> None:
    await with_session(
        lambda session: service.fail_attempt(
            session,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            query_id=query_id,
            attempt_id=attempt_id,
            error_code=code,
        )
    )


async def _fail_product_run(
    with_session: WithSession,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    code: str,
    summary: str,
) -> None:
    await with_session(
        lambda session: service.fail_run(session, owner_id, project_id, run_id, code, summary)
    )


def _retrieval_status(code: str) -> str:
    if code == "timeout":
        return "timeout"
    if code == "unsupported_content_type":
        return "unsupported"
    if code in {
        "invalid_url",
        "blocked_address",
        "blocked_port",
        "redirect_limit",
        "redirect_loop",
        "invalid_redirect",
    }:
        return "blocked"
    return "failed"


def _bounded_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")
