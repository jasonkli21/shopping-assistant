from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy.orm import Session

from shopping.evidence import claim_task
from shopping.evidence.classification import classify_source, page_metadata
from shopping.evidence.service import (
    extraction_input,
    has_validated_extraction,
    persist_extraction,
)
from shopping.extraction.http_retriever import MAX_PAGE_BYTES, HTTPPageRetriever, html_to_text
from shopping.extraction.retriever import PageRetrievalError, PageRetriever, RetrievedDocument
from shopping.extraction.task import CatalogExtractionError, StructuredDataCatalogExtractionTask
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
    planning_attempt_uncertain,
    prior_source_attempts_by_result,
    processed_offer_refresh_urls,
    save_product_plan,
    start_offer_refresh_targets,
    start_source_attempt,
    start_stage_attempt,
)
from shopping.research.product_task import (
    PROMPT_VERSION,
    TASK_NAME,
    build_request,
    validate_output,
)
from shopping.research.search_execution import execute_search_query
from shopping.search.provider import SearchProvider

logger = logging.getLogger(__name__)
WithSession = Callable[[Callable[[Session], Any]], Awaitable[Any]]
RemainingSeconds = Callable[[], Awaitable[float]]


async def _retrieve_with_retries(
    retriever: PageRetriever,
    url: str,
    max_bytes: int,
    *,
    include_domains: list[str],
    exclude_domains: list[str],
    remaining_seconds: RemainingSeconds,
    provider_timeout_seconds: int,
) -> RetrievedDocument:
    """One bounded retry for safe transient page retrieval errors."""
    retryable = {"rate_limited", "server_error", "timeout", "transport_error"}
    for retry_number in range(2):
        timeout = min(provider_timeout_seconds, await remaining_seconds())
        if timeout <= 0:
            raise PageRetrievalError("timeout", "The run deadline expired.")
        try:
            async with asyncio.timeout(timeout):
                retrieve_with_limit = getattr(retriever, "retrieve_with_limit", None)
                if isinstance(retriever, HTTPPageRetriever):
                    return await retriever.retrieve_with_limit(
                        url,
                        max_bytes,
                        allowed_domains=include_domains or None,
                        excluded_domains=exclude_domains,
                    )
                if retrieve_with_limit is None:
                    return await retriever.retrieve(url)
                return await retrieve_with_limit(url, max_bytes)
        except PageRetrievalError as error:
            if retry_number >= 1 or error.code not in retryable:
                raise
            delay = error.retry_after_seconds if error.retry_after_seconds is not None else 0.25
            remaining = await remaining_seconds()
            if delay > 5 or delay >= remaining:
                raise
            if delay > 0:
                await asyncio.sleep(delay)
    raise PageRetrievalError("timeout", "The source retrieval retry budget was exhausted.")


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
    refresh_targets = snapshot.get("refresh_targets", [])
    claims_requested = not refresh_targets or "claims" in refresh_targets
    offers_requested = "offers" in refresh_targets
    offer_extractor = StructuredDataCatalogExtractionTask() if offers_requested else None
    if claims_requested:
        saved_plan = await with_session(
            lambda session: service.load_saved_plan(session, owner_id, project_id, run_id)
        )
        if saved_plan is None:
            planned = await _generate_product_plan(
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                snapshot=snapshot,
                budgets=budgets,
                client=client,
                with_session=with_session,
                remaining_seconds=remaining_seconds,
                provider_timeout_seconds=provider_timeout_seconds,
            )
            if planned is None:
                return
            queries, summary, planning_stage_id, plan_request_id, plan_output_chars = planned
        else:
            queries, summary = saved_plan["queries"], saved_plan["summary"]
            planning_stage_id = None
            plan_request_id = None
            plan_output_chars = 0

        saved = await with_session(
            lambda session: save_product_plan(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                queries=queries,
                summary=summary,
                stage_attempt_id=planning_stage_id,
                provider_request_id=plan_request_id,
                output_chars=plan_output_chars,
            )
        )
        if not saved:
            return
    else:
        started = await with_session(
            lambda session: start_offer_refresh_targets(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
            )
        )
        if not started:
            return

    query_rows = (
        await with_session(
            lambda session: service.list_run_queries(session, owner_id, project_id, run_id)
        )
        if claims_requested
        else []
    )
    for query_id, max_results in query_rows:
        if not await execute_search_query(
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            query_id=query_id,
            max_results=max_results,
            search_provider=search_provider,
            with_session=with_session,
            remaining_seconds=remaining_seconds,
            provider_timeout_seconds=provider_timeout_seconds,
        ):
            return

    by_target = await with_session(
        lambda session: list_target_results(
            session, owner_id=owner_id, project_id=project_id, run_id=run_id
        )
    )
    targets = snapshot.get("selected_products", [])
    for target in targets:
        target_id = UUID(target["project_product_id"])
        results = by_target.get(target_id, [])
        source_targets = snapshot.get("source_targets", {})
        include_domains = source_targets.get("include_domains", [])
        exclude_domains = source_targets.get("exclude_domains", [])
        allowed_classes = source_targets.get("source_classes", [])
        offer_refresh_allowed = (
            offers_requested
            and bool(target.get("offer_observations"))
            and (not allowed_classes or "retailer_listing" in allowed_classes)
        )
        claim_source_limit = max(
            0,
            budgets["max_sources_per_product"] - (1 if offer_refresh_allowed else 0),
        )
        selected = _select_source_results(
            results,
            allowed_classes=allowed_classes,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            limit=claim_source_limit,
        )
        prior_attempts = await with_session(
            partial(
                prior_source_attempts_by_result,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                target_id=target_id,
            )
        )
        for result, _query in selected:
            prior = prior_attempts.get(result.id)
            if prior and prior["status"] == "retrieved" and prior["snapshot_id"] is not None:
                if claims_requested:
                    await _extract_source_claims(
                        with_session=with_session,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        target=target,
                        source_attempt_id=prior["attempt_id"],
                        client=client,
                        remaining_seconds=remaining_seconds,
                        provider_timeout_seconds=provider_timeout_seconds,
                        max_output_chars=budgets["max_output_chars"],
                    )
                continue
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
            requested_class = _query_source_class(_query)
            offer_refresh_for_source = offers_requested and requested_class == "retailer_listing"
            try:
                retriever = page_retriever
                if retriever is None:
                    raise RuntimeError("The research page retriever was not configured")
                document = await _retrieve_with_retries(
                    retriever,
                    result.url,
                    min(MAX_PAGE_BYTES, remaining_bytes),
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    remaining_seconds=remaining_seconds,
                    provider_timeout_seconds=provider_timeout_seconds,
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
                            offer_refresh=offer_refresh_for_source,
                            offer_error_code=(
                                "byte_budget_exceeded" if offer_refresh_for_source else None
                            ),
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
                rejected_reason = _source_target_rejection(
                    requested_url=result.url,
                    final_url=document.final_url,
                    actual_class=classification.classification,
                    requested_class=requested_class,
                    allowed_classes=allowed_classes,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                )
                if rejected_reason:
                    await with_session(
                        partial(
                            finish_source_attempt,
                            owner_id=owner_id,
                            project_id=project_id,
                            run_id=run_id,
                            source_attempt_id=source_attempt_id,
                            status="skipped",
                            reason=rejected_reason,
                            bytes_read=actual_bytes,
                            offer_refresh=offer_refresh_for_source,
                            offer_error_code=rejected_reason if offer_refresh_for_source else None,
                        )
                    )
                    continue
                bounded_text = _bounded_utf8(text_content, 12_000)
                offer_extraction = None
                offer_error_code = None
                if offer_extractor is not None and offer_refresh_for_source:
                    try:
                        offer_extraction = await offer_extractor.extract(document)
                    except CatalogExtractionError as error:
                        offer_error_code = error.code
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
                        offer_refresh=offer_refresh_for_source,
                        offer_extraction=offer_extraction,
                        offer_error_code=offer_error_code,
                    )
                )
                if stored and claims_requested:
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
                        offer_refresh=offer_refresh_for_source,
                        offer_error_code=error.code if offer_refresh_for_source else None,
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
                        offer_refresh=offer_refresh_for_source,
                        offer_error_code="timeout" if offer_refresh_for_source else None,
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
                        offer_refresh=offer_refresh_for_source,
                        offer_error_code="retrieval_failed" if offer_refresh_for_source else None,
                    )
                )
        if offers_requested:
            await _refresh_prior_offer_pages(
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                target=target,
                source_targets=source_targets,
                budgets=budgets,
                client=client,
                with_session=with_session,
                remaining_seconds=remaining_seconds,
                provider_timeout_seconds=provider_timeout_seconds,
                page_retriever=page_retriever,
                offer_extractor=offer_extractor,
                claims_requested=claims_requested,
            )
    await with_session(
        lambda session: finish_product_research(
            session, owner_id=owner_id, project_id=project_id, run_id=run_id
        )
    )


async def _refresh_prior_offer_pages(
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    target: dict[str, Any],
    source_targets: dict[str, Any],
    budgets: dict[str, int],
    client: PersonalAIClient,
    with_session: WithSession,
    remaining_seconds: RemainingSeconds,
    provider_timeout_seconds: int,
    page_retriever: PageRetriever | None,
    offer_extractor: StructuredDataCatalogExtractionTask | None,
    claims_requested: bool,
) -> None:
    if offer_extractor is None:
        return
    allowed_classes = source_targets.get("source_classes", [])
    if allowed_classes and "retailer_listing" not in allowed_classes:
        return
    target_id = UUID(target["project_product_id"])
    processed = await with_session(
        lambda session: processed_offer_refresh_urls(
            session,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            target_id=target_id,
        )
    )
    latest_by_url: dict[str, dict[str, Any]] = {}
    for offer in sorted(
        target.get("offer_observations", []),
        key=lambda item: item.get("observed_at", ""),
        reverse=True,
    ):
        url = offer.get("url")
        if not isinstance(url, str):
            continue
        try:
            normalized = normalize_candidate_url(url)
        except ValueError:
            continue
        latest_by_url.setdefault(normalized, offer)
    eligible: list[tuple[str, dict[str, Any]]] = []
    for normalized, offer in latest_by_url.items():
        if normalized in processed:
            continue
        host = (urlsplit(normalized).hostname or "").casefold().removeprefix("www.")
        if any(
            _domain_matches(host, domain) for domain in source_targets.get("exclude_domains", [])
        ):
            continue
        include_domains = source_targets.get("include_domains", [])
        if include_domains and not any(_domain_matches(host, domain) for domain in include_domains):
            continue
        eligible.append((normalized, offer))
    eligible.sort(
        key=lambda item: (
            0 if item[1].get("freshness") == "stale" else 1,
            item[1].get("observed_at", ""),
        )
    )
    for normalized, offer in eligible[: budgets["max_sources_per_product"]]:
        started = await with_session(
            partial(
                start_source_attempt,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                project_product_id=target_id,
                search_result_id=None,
                url=normalized,
                title=offer.get("retailer_name"),
                brand=target.get("brand"),
            )
        )
        if started is None:
            return
        source_attempt_id, skip_reason, remaining_bytes = started
        if skip_reason:
            continue
        try:
            if page_retriever is None:
                raise RuntimeError("The research page retriever was not configured")
            document = await _retrieve_with_retries(
                page_retriever,
                normalized,
                min(MAX_PAGE_BYTES, remaining_bytes),
                include_domains=source_targets.get("include_domains", []),
                exclude_domains=source_targets.get("exclude_domains", []),
                remaining_seconds=remaining_seconds,
                provider_timeout_seconds=provider_timeout_seconds,
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
                        offer_refresh=True,
                        offer_error_code="byte_budget_exceeded",
                    )
                )
                continue
            text_content = html_to_text(document.body)
            metadata = page_metadata(document.body)
            title = metadata.title or str(offer.get("retailer_name") or "Retailer listing")
            classification = classify_source(
                document.final_url,
                title=title,
                text=text_content,
                brand=target.get("brand"),
            )
            rejected_reason = _source_target_rejection(
                requested_url=normalized,
                final_url=document.final_url,
                actual_class=classification.classification,
                requested_class="retailer_listing",
                allowed_classes=allowed_classes,
                include_domains=source_targets.get("include_domains", []),
                exclude_domains=source_targets.get("exclude_domains", []),
            )
            if rejected_reason:
                await with_session(
                    partial(
                        finish_source_attempt,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        source_attempt_id=source_attempt_id,
                        status="skipped",
                        reason=rejected_reason,
                        bytes_read=actual_bytes,
                        offer_refresh=True,
                        offer_error_code=rejected_reason,
                    )
                )
                continue
            extraction = None
            error_code = None
            try:
                extraction = await offer_extractor.extract(document)
            except CatalogExtractionError as error:
                error_code = error.code
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
                    title=title,
                    published_at=metadata.published_at,
                    relevant_text=_bounded_utf8(text_content, 12_000),
                    classification=classification.classification,
                    classification_basis=classification.basis,
                    offer_refresh=True,
                    offer_extraction=extraction,
                    offer_error_code=error_code,
                )
            )
            if stored and claims_requested:
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
            await with_session(
                partial(
                    finish_source_attempt,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    source_attempt_id=source_attempt_id,
                    status=_retrieval_status(error.code),
                    reason=error.code,
                    bytes_read=min(error.bytes_read or remaining_bytes, MAX_PAGE_BYTES),
                    offer_refresh=True,
                    offer_error_code=error.code,
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
                    bytes_read=min(remaining_bytes, MAX_PAGE_BYTES),
                    offer_refresh=True,
                    offer_error_code="timeout",
                )
            )
        except Exception as error:
            logger.info("Offer refresh failed for %s (%s)", normalized, type(error).__name__)
            await with_session(
                partial(
                    finish_source_attempt,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    source_attempt_id=source_attempt_id,
                    status="failed",
                    reason="refresh_failed",
                    bytes_read=min(remaining_bytes, MAX_PAGE_BYTES),
                    offer_refresh=True,
                    offer_error_code="refresh_failed",
                )
            )


async def _generate_product_plan(
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    snapshot: dict[str, Any],
    budgets: dict[str, int],
    client: PersonalAIClient,
    with_session: WithSession,
    remaining_seconds: RemainingSeconds,
    provider_timeout_seconds: int,
) -> tuple[list[dict[str, Any]], str, UUID, str | None, int] | None:
    uncertain = await with_session(
        partial(
            planning_attempt_uncertain,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
        )
    )
    if uncertain:
        await _fail_product_run(
            with_session,
            owner_id,
            project_id,
            run_id,
            "uncertain_completion",
            "The product planning call ended without a saved result and was not repeated.",
        )
        return None
    request = build_request(snapshot, budgets["max_queries"])
    input_chars = len(json.dumps(request.input, ensure_ascii=False, separators=(",", ":")))
    for attempt_number in range(2):
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
            return None
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
            output_chars = len(
                json.dumps(response.output, ensure_ascii=False, separators=(",", ":"))
            )
            return (
                [item.model_dump(mode="json") for item in output.queries],
                output.explanation,
                stage_attempt.id,
                response.provider_request_id,
                output_chars,
            )
        except (TimeoutError, AIProviderError, ValueError) as error:
            code = (
                "provider_timeout"
                if isinstance(error, TimeoutError)
                else (error.code if isinstance(error, AIProviderError) else "malformed_response")
            )
            await with_session(
                partial(
                    finish_stage_attempt,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    attempt_id=stage_attempt.id,
                    status="failed",
                    error_code=code,
                )
            )
            if (
                attempt_number == 0
                and isinstance(error, AIProviderError)
                and error.code in {"provider_unavailable", "rate_limited"}
                and await remaining_seconds() > 0.5
            ):
                await asyncio.sleep(0.25)
                continue
            await _fail_product_run(
                with_session,
                owner_id,
                project_id,
                run_id,
                code,
                "The product research planner could not produce a valid bounded source plan.",
            )
            return None
        except Exception as error:
            logger.warning(
                "Product research planning failed for %s (%s)", run_id, type(error).__name__
            )
            await with_session(
                partial(
                    finish_stage_attempt,
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
            return None
    return None


def _domain_matches(host: str, domain: str) -> bool:
    host = host.casefold().removeprefix("www.")
    domain = domain.casefold().removeprefix("www.")
    return host == domain or host.endswith(f".{domain}")


def _query_source_class(query: SearchQueryRecord) -> str:
    return query.purpose.partition(":")[0].strip()


def _select_source_results(
    results: list[tuple[SearchResult, SearchQueryRecord]],
    *,
    allowed_classes: list[str],
    include_domains: list[str],
    exclude_domains: list[str],
    limit: int,
) -> list[tuple[SearchResult, SearchQueryRecord]]:
    """Interleave requested classes and select at most one result per publisher host."""
    if limit <= 0:
        return []
    buckets: dict[str, list[tuple[SearchResult, SearchQueryRecord]]] = {}
    seen_urls: set[str] = set()
    for result, query in results:
        source_class = _query_source_class(query)
        if allowed_classes and source_class not in allowed_classes:
            continue
        try:
            normalized = normalize_candidate_url(result.url)
        except ValueError:
            continue
        if normalized in seen_urls:
            continue
        host = (urlsplit(normalized).hostname or "").casefold().removeprefix("www.")
        if any(_domain_matches(host, domain) for domain in exclude_domains):
            continue
        if include_domains and not any(_domain_matches(host, domain) for domain in include_domains):
            continue
        seen_urls.add(normalized)
        buckets.setdefault(source_class, []).append((result, query))

    selected: list[tuple[SearchResult, SearchQueryRecord]] = []
    seen_hosts: set[str] = set()
    classes = list(buckets)
    while classes and len(selected) < limit:
        remaining_classes: list[str] = []
        for source_class in classes:
            bucket = buckets[source_class]
            choice = None
            while bucket:
                candidate = bucket.pop(0)
                host = (urlsplit(candidate[0].url).hostname or "").casefold().removeprefix("www.")
                if host and host in seen_hosts:
                    continue
                choice = candidate
                if host:
                    seen_hosts.add(host)
                break
            if choice is not None:
                selected.append(choice)
                if bucket:
                    remaining_classes.append(source_class)
            elif bucket:
                remaining_classes.append(source_class)
            if len(selected) >= limit:
                break
        classes = remaining_classes
    return selected


def _source_target_rejection(
    *,
    requested_url: str,
    final_url: str,
    actual_class: str,
    requested_class: str,
    allowed_classes: list[str],
    include_domains: list[str],
    exclude_domains: list[str],
) -> str | None:
    """Check both the requested and final redirect destination against saved policy."""
    try:
        requested_host = (
            urlsplit(normalize_candidate_url(requested_url)).hostname or ""
        ).casefold()
        final_host = (urlsplit(normalize_candidate_url(final_url)).hostname or "").casefold()
    except ValueError:
        return "source_domain_excluded"
    for host in (requested_host, final_host):
        if any(_domain_matches(host, domain) for domain in exclude_domains):
            return "source_domain_excluded"
        if include_domains and not any(_domain_matches(host, domain) for domain in include_domains):
            return "source_domain_excluded"
    if allowed_classes and actual_class not in allowed_classes:
        return "source_class_mismatch"
    accepted_actual = {
        "manufacturer_specification": {"manufacturer_specification"},
        "independent_measurement": {"independent_measurement"},
        "editorial_assessment": {"editorial_assessment"},
        "retailer_listing": {"retailer_listing"},
        "community_observation": {"community_observation", "individual_anecdote"},
    }.get(requested_class, set())
    if actual_class not in accepted_actual:
        return "source_class_mismatch"
    return None


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
    if await with_session(
        lambda session: has_validated_extraction(
            session,
            owner_id=owner_id,
            snapshot_id=UUID(source["snapshot_id"]),
            prompt_version=claim_task.PROMPT_VERSION,
        )
    ):
        return
    request = claim_task.build_request(target=target, source=source, text=text_content)
    input_chars = len(json.dumps(request.input, ensure_ascii=False, separators=(",", ":")))
    for attempt_number in range(2):
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
                partial(
                    persist_extraction,
                    owner_id=owner_id,
                    run_id=run_id,
                    project_id=project_id,
                    target_id=target_id,
                    source_attempt_id=source_attempt_id,
                    stage_attempt_id=stage.id,
                    extraction=extraction,
                    provider_request_id=response.provider_request_id,
                    output_chars=len(json.dumps(response.output, ensure_ascii=False)),
                )
            )
            return
        except (TimeoutError, AIProviderError, ValueError) as error:
            code = (
                "provider_timeout"
                if isinstance(error, TimeoutError)
                else (error.code if isinstance(error, AIProviderError) else "malformed_response")
            )
            await with_session(
                partial(
                    finish_stage_attempt,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    attempt_id=stage.id,
                    status="failed",
                    error_code=code,
                )
            )
            # Retry only explicit transient provider responses. Timeouts and
            # malformed responses may represent a charged, completed call.
            if (
                attempt_number == 0
                and isinstance(error, AIProviderError)
                and error.code in {"provider_unavailable", "rate_limited"}
                and await remaining_seconds() > 0.5
            ):
                await asyncio.sleep(0.25)
                continue
            return
        except Exception as error:
            logger.warning("Claim extraction failed for %s (%s)", run_id, type(error).__name__)
            await with_session(
                partial(
                    finish_stage_attempt,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    attempt_id=stage.id,
                    status="failed",
                    error_code="extraction_failed",
                )
            )
            return


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
