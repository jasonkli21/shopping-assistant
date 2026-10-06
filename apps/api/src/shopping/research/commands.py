from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from shopping.catalog.models import Product, ProductVariant, ProjectProduct, RetailOffer
from shopping.evidence.claim_task import PROMPT_VERSION
from shopping.evidence.freshness import PLANNING_FRESHNESS, evidence_freshness, offer_freshness
from shopping.evidence.models import Claim, Source, SourceSnapshot
from shopping.projects.models import ShoppingProject
from shopping.research.common import (
    ACTIVE_STATES,
    _conflict,
    _invalid,
    _live_project,
    _money,
    _not_found,
    normalize_candidate_url,
)
from shopping.research.jobs import enqueue_run_job
from shopping.research.models import ResearchJob, ResearchRun, ResearchRunTarget, SearchQueryRecord
from shopping.research.reads import _run_read
from shopping.research.schemas import (
    ResearchBudgets,
    ResearchCreate,
    ResearchRunRead,
    ResearchSourceTargets,
)


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
        .options(selectinload(ResearchRun.jobs).selectinload(ResearchJob.attempts))
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.request_key == command.request_key,
        )
    )
    if run is None:
        return None
    if not _request_matches(run, command):
        raise _conflict("request_key_conflict", "This request key was used for another command")
    return _run_read(run, replayed=True)


def request_key_exists(
    session: Session, owner_id: UUID, project_id: UUID, request_key: str
) -> bool:
    _live_project(session, owner_id, project_id)
    return (
        session.scalar(
            select(ResearchRun.id).where(
                ResearchRun.owner_id == owner_id,
                ResearchRun.project_id == project_id,
                ResearchRun.request_key == request_key,
            )
        )
        is not None
    )


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
        .options(selectinload(ResearchRun.jobs).selectinload(ResearchJob.attempts))
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.request_key == command.request_key,
        )
    )
    if existing is not None:
        if not _request_matches(existing, command):
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

    budgets = effective_budgets(command.budgets, settings, command.mode)
    if command.manual_queries and len(command.manual_queries) > budgets["max_queries"]:
        raise _invalid("The supplied query list exceeds the effective query budget")
    if command.type == "product_research":
        selected_ids = command.selected_project_product_ids or []
        if len(selected_ids) > budgets["max_products"]:
            raise _invalid("The selected product list exceeds the effective product budget")
        if len(selected_ids) > budgets["max_queries"]:
            raise _invalid("The query budget must include at least one query per selected product")
        if command.refresh_of_run_id is not None:
            previous = session.scalar(
                select(ResearchRun).where(
                    ResearchRun.id == command.refresh_of_run_id,
                    ResearchRun.owner_id == owner_id,
                    ResearchRun.project_id == project_id,
                    ResearchRun.run_type == "product_research",
                )
            )
            if previous is None or previous.status in ACTIVE_STATES:
                raise _not_found("Completed product research run not found")
            previous_targets = set(
                session.scalars(
                    select(ResearchRunTarget.project_product_id).where(
                        ResearchRunTarget.research_run_id == previous.id
                    )
                ).all()
            )
            if not set(selected_ids) <= previous_targets:
                raise _invalid("A refresh can only target variants from the selected source run")
    snapshot = _snapshot(session, project, command)
    run = ResearchRun(
        project_id=project.id,
        owner_id=owner_id,
        objective=command.objective,
        run_type=command.type,
        research_mode=command.mode,
        refresh_of_run_id=command.refresh_of_run_id,
        status="queued",
        request_key=command.request_key,
        request_hash=_request_hash(command),
        snapshot_revision=project.revision,
        input_snapshot=snapshot,
        effective_budgets=budgets,
        task_name=(
            "plan_product_research.v1"
            if command.type == "product_research"
            else "plan_discovery.v1"
        ),
        prompt_version=(
            "shopping-product-research-2"
            if command.type == "product_research"
            else "shopping-discovery-1"
        ),
        schema_version=2,
        ai_provider=ai_provider_name,
        search_provider=search_provider_name,
    )
    session.add(run)
    session.flush()
    for target in snapshot.get("selected_products", []):
        session.add(
            ResearchRunTarget(
                owner_id=owner_id,
                research_run_id=run.id,
                project_product_id=UUID(target["project_product_id"]),
                product_id=UUID(target["product_id"]),
                variant_id=UUID(target["variant_id"]),
                product_revision=target["product_revision"],
                variant_revision=target["variant_revision"],
            )
        )
    enqueue_run_job(session, run)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _conflict(
            "research_active", "A discovery run is already active for this project"
        ) from error
    session.refresh(run)
    return _run_read(run), True


def retry_run(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    request_key: str,
    expected_version: int,
    settings: Any,
    ai_provider_name: str,
    search_provider_name: str,
) -> tuple[ResearchRunRead, bool]:
    _live_project(session, owner_id, project_id, lock=True)
    run = session.scalar(
        select(ResearchRun).where(
            ResearchRun.id == run_id,
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
        )
    )
    if run is None:
        raise _not_found("Research run not found")
    if run.status not in {"partial", "failed", "canceled", "interrupted"}:
        raise _conflict("research_not_retryable", "Only incomplete research can be retried")

    snapshot = run.input_snapshot
    selected_ids = list(
        session.scalars(
            select(ResearchRunTarget.project_product_id).where(
                ResearchRunTarget.research_run_id == run.id
            )
        ).all()
    )
    target_budgets = ResearchBudgets.model_validate(run.effective_budgets)
    command = ResearchCreate(
        objective=run.objective,
        type=run.run_type,
        mode=run.research_mode,
        request_key=request_key,
        expected_version=expected_version,
        budgets=target_budgets,
        source_targets=(
            ResearchSourceTargets.model_validate(snapshot.get("source_targets", {}))
            if run.run_type == "product_research"
            else None
        ),
        refresh_of_run_id=run.id if run.run_type == "product_research" else None,
        refresh_targets=(
            snapshot.get("refresh_targets") or ["claims"]
            if run.run_type == "product_research"
            else None
        ),
        manual_queries=(snapshot.get("manual_queries") if run.run_type == "discovery" else None),
        selected_project_product_ids=selected_ids if run.run_type == "product_research" else None,
    )
    return create_run(
        session,
        owner_id=owner_id,
        project_id=project_id,
        command=command,
        settings=settings,
        ai_provider_name=ai_provider_name,
        search_provider_name=search_provider_name,
    )


def effective_budgets(
    requested: ResearchBudgets, settings: Any, mode: str = "deep"
) -> dict[str, int]:
    quick_caps = {
        "max_queries": 3,
        "max_candidates": 10,
        "max_results": 20,
        "max_results_per_query": 5,
        "max_attempts": 4,
        "max_products": 1,
        "max_sources_per_product": 2,
        "max_pages": 4,
        "max_total_bytes": 600_000,
        "max_ai_calls": 6,
        "max_output_chars": 8_000,
        "deadline_seconds": 45,
        "max_concurrent": 1,
    }

    def cap(name: str, server: int) -> int:
        mode_limit = min(server, quick_caps[name]) if mode == "quick" else server
        selected = getattr(requested, name)
        return min(mode_limit, selected) if selected is not None else mode_limit

    return {
        "max_queries": cap("max_queries", settings.research_max_queries),
        "max_candidates": cap("max_candidates", settings.research_max_candidates),
        "max_results": cap("max_results", settings.research_max_results),
        "max_results_per_query": cap(
            "max_results_per_query", settings.research_max_results_per_query
        ),
        "max_attempts": cap("max_attempts", settings.research_max_attempts),
        "max_products": cap("max_products", settings.research_max_products),
        "max_sources_per_product": cap(
            "max_sources_per_product", settings.research_max_sources_per_product
        ),
        "max_pages": cap("max_pages", settings.research_max_pages),
        "max_total_bytes": cap("max_total_bytes", settings.research_max_total_bytes),
        "max_ai_calls": cap("max_ai_calls", settings.research_max_ai_calls),
        "max_output_chars": cap("max_output_chars", settings.research_max_output_chars),
        "deadline_seconds": cap("deadline_seconds", settings.research_deadline_seconds),
        "max_concurrent": cap("max_concurrent", settings.research_max_concurrent_searches),
    }


def _snapshot(
    session: Session, project: ShoppingProject, command: ResearchCreate
) -> dict[str, Any]:
    requirements = list(
        sorted(project.requirements, key=lambda item: (item.position, str(item.id)))
    )[:100]
    snapshot = {
        "objective": command.objective,
        "mode": command.mode,
        "refresh_of_run_id": str(command.refresh_of_run_id) if command.refresh_of_run_id else None,
        "refresh_targets": command.refresh_targets or [],
        "source_targets": (
            command.source_targets.model_dump(mode="json")
            if command.source_targets
            else {
                "source_classes": [
                    "manufacturer_specification",
                    "independent_measurement",
                    "editorial_assessment",
                    "retailer_listing",
                    "community_observation",
                ],
                "include_domains": [],
                "exclude_domains": [],
            }
        ),
        "freshness_needs": PLANNING_FRESHNESS[command.mode],
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
    if command.type == "product_research":
        selected_ids = command.selected_project_product_ids or []
        rows = session.execute(
            select(ProjectProduct, ProductVariant, Product)
            .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProjectProduct.id.in_(selected_ids),
                ProjectProduct.project_id == project.id,
                Product.owner_id == project.owner_id,
            )
        ).all()
        if len(rows) != len(selected_ids):
            raise _not_found("One or more selected project products were not found")
        by_id = {
            str(project_product.id): (project_product, variant, product)
            for project_product, variant, product in rows
        }
        snapshot["selected_products"] = [
            {
                "project_product_id": str(selected_id),
                "product_id": str(by_id[str(selected_id)][2].id),
                "variant_id": str(by_id[str(selected_id)][1].id),
                "product_name": by_id[str(selected_id)][2].canonical_name,
                "brand": by_id[str(selected_id)][2].brand,
                "category": by_id[str(selected_id)][2].category,
                "model_family": by_id[str(selected_id)][2].model_family,
                "variant_name": by_id[str(selected_id)][1].display_name,
                "identity_attributes": by_id[str(selected_id)][1].identity_attributes,
                "category_attributes": by_id[str(selected_id)][1].category_attributes,
                "product_revision": by_id[str(selected_id)][2].revision,
                "variant_revision": by_id[str(selected_id)][1].revision,
            }
            for selected_id in selected_ids
        ]
        for target in snapshot["selected_products"]:
            target.update(
                _planning_context(
                    session,
                    owner_id=project.owner_id,
                    variant_id=UUID(target["variant_id"]),
                    mode=command.mode,
                    freshness_needs=snapshot["freshness_needs"],
                    refresh_targets=command.refresh_targets or ["claims"],
                )
            )
    encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    # This is a durable user-context snapshot, not the bounded planner prompt.
    # A project may validly contain 100 detailed requirements; the planner builds
    # a smaller search-hint view before any AI call.
    if len(encoded) > 1_500_000:
        raise _invalid("Project discovery context exceeds its configured size limit")
    return snapshot


def _planning_context(
    session: Session,
    *,
    owner_id: UUID,
    variant_id: UUID,
    mode: str,
    freshness_needs: dict[str, int],
    refresh_targets: list[str],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    latest_offer = (
        select(
            RetailOffer.id.label("offer_id"),
            func.row_number()
            .over(
                partition_by=RetailOffer.url,
                order_by=(RetailOffer.observed_at.desc(), RetailOffer.id.desc()),
            )
            .label("position"),
        )
        .where(RetailOffer.owner_id == owner_id, RetailOffer.variant_id == variant_id)
        .subquery()
    )
    offers = list(
        session.scalars(
            select(RetailOffer)
            .join(latest_offer, latest_offer.c.offer_id == RetailOffer.id)
            .where(latest_offer.c.position == 1)
            .order_by(RetailOffer.observed_at.desc(), RetailOffer.id.desc())
        ).all()
    )
    offer_observations = []
    seen_offer_urls: set[str] = set()
    for offer in offers:
        try:
            identity = normalize_candidate_url(offer.url)
        except ValueError:
            continue
        if identity in seen_offer_urls:
            continue
        seen_offer_urls.add(identity)
        offer_observations.append(
            {
                "offer_id": str(offer.id),
                "url": offer.url,
                "retailer_name": offer.retailer_name,
                "domain": offer.retailer_domain,
                "observed_at": offer.observed_at.isoformat(),
                "freshness": offer_freshness(
                    offer.observed_at,
                    now=now,
                    max_age_hours=freshness_needs["offer_max_age_hours"],
                ),
            }
        )
        if len(offer_observations) >= 50:
            break
    rows = session.execute(
        select(Claim, Source, SourceSnapshot)
        .join(SourceSnapshot, SourceSnapshot.id == Claim.snapshot_id)
        .join(Source, Source.id == SourceSnapshot.source_id)
        .where(
            Claim.owner_id == owner_id,
            Claim.subject_variant_id == variant_id,
            Claim.prompt_version == PROMPT_VERSION,
        )
        .order_by(Claim.extracted_at.desc(), Claim.id.desc())
        .limit(50)
    ).all()
    dimensions: dict[str, dict[str, str]] = {}
    for claim, source, source_snapshot in rows:
        freshness = evidence_freshness(
            claim.evidence_category,
            published_at=source_snapshot.published_at,
            retrieved_at=source_snapshot.retrieved_at,
            now=now,
            thresholds=freshness_needs,
        )
        key = claim.attribute_key
        if key not in dimensions:
            dimensions[key] = {
                "attribute_key": key,
                "source_class": source.classification,
                "freshness": freshness,
            }
    return {
        "known_evidence_dimensions": list(dimensions.values())[:30],
        "offer_observations": offer_observations,
        "requested_refresh_targets": refresh_targets,
        "research_mode": mode,
    }


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _request_hash(command: ResearchCreate) -> str:
    encoded = json.dumps(
        command.model_dump(mode="json", exclude_none=False),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _request_matches(run: ResearchRun, command: ResearchCreate) -> bool:
    if run.request_hash == _request_hash(command):
        return True
    # Runs created before modes and targeting used schema version 1. Preserve their
    # exact replay contract when a client retries its original command after upgrade.
    if (
        run.schema_version == 1
        and command.mode == "deep"
        and command.source_targets is None
        and command.refresh_of_run_id is None
        and command.refresh_targets is None
    ):
        return run.request_hash == _legacy_request_hash(command)
    return False


def _legacy_request_hash(command: ResearchCreate) -> str:
    payload = command.model_dump(mode="json", exclude_none=False)
    for key in ("mode", "source_targets", "refresh_of_run_id", "refresh_targets"):
        payload.pop(key, None)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
