"""Canonical owner-scoped Shopping project context projection."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct, RetailOffer
from shopping.comparisons.models import ComparisonDimension, ComparisonItem, SavedComparison
from shopping.evidence.models import Claim, ClaimRelation, ProductAssessment, Source, SourceSnapshot
from shopping.evidence.reads import assessment_context_stale, freshness
from shopping.projects import notes as note_service
from shopping.projects import repository
from shopping.projects.errors import ProjectError
from shopping.projects.models import ProjectProductDecision, UserNote


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def read_project_context(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    selected_project_product_ids: list[UUID] | None = None,
    comparison_id: UUID | None = None,
    selected_context_only: bool = False,
    include_external_evidence: bool = False,
) -> dict:
    """Return an owner-scoped bounded projection for conversation and Personal AI reads."""
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    scoped_ids = list(selected_project_product_ids or [])
    if comparison_id is not None:
        comparison = session.scalar(
            select(SavedComparison).where(
                SavedComparison.id == comparison_id,
                SavedComparison.owner_id == owner_id,
                SavedComparison.project_id == project_id,
            )
        )
        if comparison is None:
            raise _not_found("Comparison not found")
        scoped_ids = list(
            session.scalars(
                select(ComparisonItem.project_product_id)
                .where(ComparisonItem.comparison_id == comparison.id)
                .order_by(ComparisonItem.position)
            ).all()
        )
    product_statement = (
        select(ProjectProduct, ProductVariant, Product)
        .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProjectProduct.project_id == project_id, Product.owner_id == owner_id)
    )
    scoped_rows = []
    if scoped_ids:
        scoped_by_id = {
            row[0].id: row
            for row in session.execute(
                product_statement.where(ProjectProduct.id.in_(scoped_ids))
            ).all()
        }
        if len(scoped_by_id) != len(scoped_ids):
            raise _not_found("One or more selected variants are not in this project")
        scoped_rows = [scoped_by_id[item] for item in scoped_ids]
    remaining = 0 if selected_context_only else max(0, 8 - len(scoped_rows))
    rows = [*scoped_rows]
    if remaining:
        rest_statement = product_statement
        if scoped_ids:
            rest_statement = rest_statement.where(~ProjectProduct.id.in_(scoped_ids))
        rows.extend(
            session.execute(
                rest_statement.order_by(ProjectProduct.created_at, ProjectProduct.id).limit(
                    remaining
                )
            ).all()
        )
    total_products = 0
    if not selected_context_only:
        total_products = (
            session.scalar(
                select(func.count(ProjectProduct.id))
                .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
                .join(Product, Product.id == ProductVariant.product_id)
                .where(ProjectProduct.project_id == project_id, Product.owner_id == owner_id)
            )
            or 0
        )
    products = []
    for membership, variant, product in rows:
        decision = session.scalar(
            select(ProjectProductDecision).where(
                ProjectProductDecision.owner_id == owner_id,
                ProjectProductDecision.project_product_id == membership.id,
            )
        )
        note = (
            None
            if selected_context_only
            else session.scalar(
                select(UserNote).where(
                    UserNote.owner_id == owner_id,
                    UserNote.project_id == project_id,
                    UserNote.project_product_id == membership.id,
                )
            )
        )
        offers = (
            list(
                session.scalars(
                    select(RetailOffer)
                    .where(RetailOffer.owner_id == owner_id, RetailOffer.variant_id == variant.id)
                    .order_by(RetailOffer.observed_at.desc(), RetailOffer.id.desc())
                    .limit(5 if selected_context_only and include_external_evidence else 2)
                ).all()
            )
            if not selected_context_only or include_external_evidence
            else []
        )
        assessment = (
            None
            if selected_context_only
            else session.scalar(
                select(ProductAssessment)
                .where(
                    ProductAssessment.owner_id == owner_id,
                    ProductAssessment.project_product_id == membership.id,
                )
                .order_by(ProductAssessment.generated_at.desc(), ProductAssessment.id.desc())
                .limit(1)
            )
        )
        claim_rows = (
            session.execute(
                select(Claim, SourceSnapshot, Source)
                .join(SourceSnapshot, SourceSnapshot.id == Claim.snapshot_id)
                .join(Source, Source.id == SourceSnapshot.source_id)
                .where(
                    Claim.owner_id == owner_id,
                    Claim.subject_variant_id == variant.id,
                    SourceSnapshot.owner_id == owner_id,
                    Source.owner_id == owner_id,
                )
                .order_by(Claim.extracted_at.desc(), Claim.id)
                .limit(5 if selected_context_only and include_external_evidence else 3)
            ).all()
            if not selected_context_only or include_external_evidence
            else []
        )
        offer_total_available = len(offers)
        claim_total_available = len(claim_rows)
        if selected_context_only and include_external_evidence:
            offer_total_available = session.scalar(
                select(func.count(RetailOffer.id)).where(
                    RetailOffer.owner_id == owner_id,
                    RetailOffer.variant_id == variant.id,
                )
            ) or 0
            claim_total_available = session.scalar(
                select(func.count(Claim.id))
                .select_from(Claim)
                .join(SourceSnapshot, SourceSnapshot.id == Claim.snapshot_id)
                .join(Source, Source.id == SourceSnapshot.source_id)
                .where(
                    Claim.owner_id == owner_id,
                    Claim.subject_variant_id == variant.id,
                    SourceSnapshot.owner_id == owner_id,
                    Source.owner_id == owner_id,
                )
            ) or 0
        claim_ids = [claim.id for claim, _snapshot, _source in claim_rows]
        claim_relations = (
            list(
                session.scalars(
                    select(ClaimRelation).where(
                        ClaimRelation.owner_id == owner_id,
                        or_(
                            ClaimRelation.claim_id.in_(claim_ids),
                            ClaimRelation.related_claim_id.in_(claim_ids),
                        ),
                    )
                ).all()
            )
            if claim_ids and not selected_context_only
            else []
        )
        products.append(
            {
                "project_product_id": str(membership.id),
                "product_id": str(product.id),
                "product_revision": product.revision,
                "variant_id": str(variant.id),
                "variant_revision": variant.revision,
                "evidence_total_available": offer_total_available + claim_total_available,
                "canonical_name": product.canonical_name[:250],
                "brand": product.brand,
                "variant_name": variant.display_name[:250],
                "identity_attributes": _compact_attributes(variant.identity_attributes),
                "category_attributes": _compact_attributes(variant.category_attributes),
                "decision": {
                    "state": decision.state if decision else "considering",
                    "reason": decision.reason[:600] if decision else "",
                    "rejection_reason": decision.rejection_reason if decision else None,
                },
                "note": note.text[:1000] if note else None,
                "offers": [
                    {
                        "offer_id": str(offer.id),
                        "source_url": offer.url[:2048],
                        "amount": format(offer.amount, ".2f") if offer.amount is not None else None,
                        "currency": offer.currency,
                        "retailer": offer.retailer_name[:100],
                        "availability": offer.availability,
                        "condition": offer.condition,
                        "observed_at": offer.observed_at.isoformat(),
                    }
                    for offer in offers
                ],
                "assessment": (
                    {
                        "assessment_id": str(assessment.id),
                        "summary": assessment.summary[:600],
                        "conclusions": assessment.conclusions[:6],
                        "project_revision": assessment.project_revision,
                        "context_stale": assessment_context_stale(
                            assessment, project, product, variant
                        ),
                        "product_revision": assessment.product_revision,
                        "variant_revision": assessment.variant_revision,
                        "claim_ids": assessment.claim_ids[:20],
                    }
                    if assessment
                    else None
                ),
                "claims": [
                    {
                        "claim_id": str(claim.id),
                        "snapshot_id": str(snapshot.id),
                        "attribute_key": claim.attribute_key,
                        "assertion": claim.assertion_text[:400],
                        "normalized_value": claim.normalized_value,
                        "qualifiers": claim.qualifiers,
                        "evidence_category": claim.evidence_category,
                        "source_title": (snapshot.title or source.title or "")[:200],
                        "source_url": source.normalized_url[:1000],
                        "published_at": (
                            snapshot.published_at.isoformat() if snapshot.published_at else None
                        ),
                        "retrieved_at": snapshot.retrieved_at.isoformat(),
                        "freshness": freshness(
                            claim.evidence_category,
                            published_at=snapshot.published_at,
                            retrieved_at=snapshot.retrieved_at,
                            now=datetime.now(UTC),
                        ),
                    }
                    for claim, snapshot, source in claim_rows
                ],
                "claim_relations": [
                    {
                        "claim_id": str(item.claim_id),
                        "related_claim_id": str(item.related_claim_id),
                        "relation": item.relation,
                        "basis": item.basis[:300],
                    }
                    for item in claim_relations
                ],
            }
        )
    if selected_context_only:
        return {"products": products}
    comparisons = []
    comparison_rows = list(
        session.scalars(
            select(SavedComparison)
            .where(SavedComparison.owner_id == owner_id, SavedComparison.project_id == project_id)
            .order_by(SavedComparison.updated_at.desc(), SavedComparison.id)
            .limit(10)
        ).all()
    )
    if comparison_id is not None:
        prioritized = session.scalar(
            select(SavedComparison).where(
                SavedComparison.id == comparison_id,
                SavedComparison.owner_id == owner_id,
                SavedComparison.project_id == project_id,
            )
        )
        comparison_rows = [
            prioritized,
            *[item for item in comparison_rows if item.id != comparison_id],
        ]
    for comparison in comparison_rows[:10]:
        item_ids = list(
            session.scalars(
                select(ComparisonItem.project_product_id)
                .where(ComparisonItem.comparison_id == comparison.id)
                .order_by(ComparisonItem.position)
            ).all()
        )
        dimensions = list(
            session.scalars(
                select(ComparisonDimension)
                .where(ComparisonDimension.comparison_id == comparison.id)
                .order_by(ComparisonDimension.position)
            ).all()
        )
        comparisons.append(
            {
                "id": str(comparison.id),
                "title": comparison.title,
                "comparison_revision": comparison.comparison_revision,
                "project_product_ids": [str(item) for item in item_ids],
                "dimensions": [
                    {
                        "key": item.key,
                        "label": item.label,
                        "unit": item.unit,
                        "dimension_type": item.dimension_type,
                    }
                    for item in dimensions
                ],
            }
        )
    project_note = note_service.get_note(session, owner_id, project_id)
    return {
        "products": products,
        "comparisons": comparisons,
        "project_notes": project_note.text[:2000] if project_note else "",
        "scope": {
            "type": "comparison" if comparison_id else "selection" if scoped_ids else "project",
            "comparison_id": str(comparison_id) if comparison_id else None,
            "project_product_ids": [str(item) for item in scoped_ids],
        },
        "omitted_product_count": max(0, total_products - len(rows)),
    }


def _compact_attributes(attributes: dict) -> dict:
    compact = {}
    for key, value in list(attributes.items())[:12]:
        if isinstance(value, dict):
            bounded = dict(value)
            if isinstance(bounded.get("value"), str):
                bounded["value"] = bounded["value"][:200]
            compact[key[:100]] = bounded
        elif isinstance(value, str):
            compact[key[:100]] = value[:200]
        elif isinstance(value, (int, float, bool)) or value is None:
            compact[key[:100]] = value
    return compact


def compact_requirement_descriptions(
    context: dict[str, Any],
    *,
    max_chars: int,
    measure: Callable[[dict[str, Any]], int] | None = None,
) -> dict[str, Any]:
    """Fit requirement descriptions while preserving all structured context."""
    if max_chars <= 0:
        raise ValueError("context size limit must be positive")
    measure_size = measure or _json_size
    original = copy.deepcopy(context)
    requirements = original.get("requirements", [])
    if not isinstance(requirements, list) or any(
        not isinstance(item, dict) for item in requirements
    ):
        raise ValueError("project requirements must be a list of objects")
    labels = [
        item.get("label") if isinstance(item.get("label"), str) else ""
        for item in requirements
    ]
    details = [item.get("detail") for item in requirements]
    full_label_lengths = [len(label) for label in labels]
    full_detail_lengths = [len(detail) if isinstance(detail, str) else 0 for detail in details]

    def build(label_lengths: list[int], detail_lengths: list[int] | None) -> dict[str, Any]:
        result = copy.deepcopy(original)
        compacted = copy.deepcopy(requirements)
        for index, item in enumerate(compacted):
            item["label"] = _fit_text(labels[index], label_lengths[index])
            detail = details[index]
            if isinstance(detail, str):
                item["detail"] = (
                    None
                    if detail_lengths is None or detail_lengths[index] == 0
                    else _fit_text(detail, detail_lengths[index])
                )
        result["requirements"] = compacted
        return result

    full = build(full_label_lengths, full_detail_lengths)
    if measure_size(full) <= max_chars:
        return full
    labels_only = build(full_label_lengths, None)
    if measure_size(labels_only) <= max_chars:
        detail_lengths = _allocate_text(
            details, [0] * len(details), max_chars=max_chars, measure=measure_size,
            build=lambda lengths: build(full_label_lengths, lengths),
        )
        return build(full_label_lengths, detail_lengths)
    minimum_label_lengths = [min(1, len(label)) for label in labels]
    minimum_labels = build(minimum_label_lengths, None)
    if measure_size(minimum_labels) > max_chars:
        raise ValueError("project context exceeds its configured size limit after compaction")
    label_lengths = _allocate_text(
        labels, minimum_label_lengths, max_chars=max_chars, measure=measure_size,
        build=lambda lengths: build(lengths, None),
    )
    detail_lengths = _allocate_text(
        details, [0] * len(details), max_chars=max_chars, measure=measure_size,
        build=lambda lengths: build(label_lengths, lengths),
    )
    return build(label_lengths, detail_lengths)


def _allocate_text(
    values: list[Any], initial_lengths: list[int], *, max_chars: int,
    measure: Callable[[dict[str, Any]], int],
    build: Callable[[list[int]], dict[str, Any]],
) -> list[int]:
    texts = [value if isinstance(value, str) else "" for value in values]
    upper = max((len(value) for value in texts), default=0)
    low = min(initial_lengths, default=0)
    high = upper
    while low < high:
        middle = (low + high + 1) // 2
        candidate_lengths = [
            max(initial_lengths[index], min(middle, len(text)))
            for index, text in enumerate(texts)
        ]
        if measure(build(candidate_lengths)) <= max_chars:
            low = middle
        else:
            high = middle - 1
    allocated = [
        max(initial_lengths[index], min(low, len(text)))
        for index, text in enumerate(texts)
    ]
    while True:
        advanced = False
        for index, text in enumerate(texts):
            if allocated[index] >= len(text):
                continue
            candidate_lengths = list(allocated)
            candidate_lengths[index] += 1
            if measure(build(candidate_lengths)) <= max_chars:
                allocated[index] += 1
                advanced = True
        if not advanced:
            return allocated


def _fit_text(value: str, length: int) -> str:
    if length >= len(value):
        return value
    return f"{value[:length]}…"


def _json_size(value: dict[str, Any]) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("project context must be bounded JSON") from error
