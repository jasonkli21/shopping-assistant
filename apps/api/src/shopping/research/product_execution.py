from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from shopping.evidence import claim_task
from shopping.evidence.classification import classify_source, page_metadata
from shopping.evidence.service import extraction_input, persist_extraction
from shopping.extraction.http_retriever import MAX_PAGE_BYTES, html_to_text
from shopping.extraction.retriever import PageRetrievalError, PageRetriever
from shopping.integrations.personal_ai.client import AIProviderError, PersonalAIClient
from shopping.research import service
from shopping.research.common import (
    normalize_candidate_url,
)
from shopping.research.models import (
    SearchQueryRecord,
    SearchResult,
)
from shopping.research.product_persistence import (
    fail_product_research,
    finish_product_research,
    finish_source_attempt,
    finish_stage_attempt,
    list_target_results,
    save_product_plan,
    start_source_attempt,
    start_stage_attempt,
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
                        bytes_read=(
                            min(error.bytes_read, MAX_PAGE_BYTES)
                            if error.bytes_read > 0
                            else min(MAX_PAGE_BYTES, remaining_bytes)
                        ),
                    )
                )
            except TimeoutError:
                await with_session(
                    partial(
                        finish_source_attempt,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        source_attempt_id=source_attempt_id,
                        status="timeout",
                        reason="timeout",
                        bytes_read=min(MAX_PAGE_BYTES, remaining_bytes),
                    )
                )
            except Exception as error:
                logger.info("Source retrieval failed for %s (%s)", result.url, type(error).__name__)
                await with_session(
                    partial(
                        finish_source_attempt,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        source_attempt_id=source_attempt_id,
                        status="failed",
                        reason="retrieval_failed",
                        bytes_read=min(MAX_PAGE_BYTES, remaining_bytes),
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
                project_id=project_id,
                target_id=target_id,
                source_attempt_id=source_attempt_id,
                stage_attempt_id=stage.id,
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
        lambda session: fail_product_research(
            session,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            error_code=code,
            summary=summary,
        )
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
