from __future__ import annotations

import base64
import binascii
import json
import math
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.catalog.models import (
    OwnerCatalogState,
    Product,
    ProductVariant,
    ProjectProduct,
    RetailOffer,
)
from shopping.comparisons.models import (
    ComparisonDimension,
    ComparisonItem,
    ComparisonSnapshot,
    SavedComparison,
)
from shopping.comparisons.schemas import (
    ComparisonCreate,
    ComparisonDimensionInput,
    ComparisonDimensionRead,
    ComparisonPage,
    ComparisonPatch,
    ComparisonProductRead,
    ComparisonRead,
    ComparisonRegenerate,
)
from shopping.evidence.models import (
    Claim,
    ClaimEvidence,
    ClaimRelation,
    ProductAssessment,
    Source,
    SourceSnapshot,
)
from shopping.evidence.reads import freshness
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.errors import ProjectError
from shopping.projects.models import ProjectRequirement, ShoppingProject, UserNote


def create_comparison(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    command: ComparisonCreate,
) -> ComparisonRead:
    project = _lock_project(session, owner_id, project_id, command.expected_version)
    members = _members(session, owner_id, project_id, command.project_product_ids)
    _validate_dimensions(session, project_id, command.dimensions)
    comparison = SavedComparison(
        owner_id=owner_id,
        project_id=project_id,
        title=command.title,
        display_mode=command.display_mode,
        comparison_revision=1,
    )
    session.add(comparison)
    session.flush()
    _replace_members(session, comparison.id, command.project_product_ids)
    _replace_dimensions(session, comparison.id, command.dimensions)
    project_service._advance_revision(project)
    session.flush()
    view = _build_view(session, owner_id, project, members, command.dimensions)
    snapshot = ComparisonSnapshot(
        owner_id=owner_id,
        comparison_id=comparison.id,
        comparison_revision=comparison.comparison_revision,
        project_revision=project.revision,
        catalog_revision=_catalog_revision(session, owner_id),
        view=view,
    )
    session.add(snapshot)
    _commit(session)
    return _comparison_read(session, project, comparison, snapshot, current_view=view)


def list_comparisons(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> ComparisonPage:
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    before = _decode_cursor(cursor) if cursor else None
    statement = select(SavedComparison).where(
        SavedComparison.owner_id == owner_id, SavedComparison.project_id == project_id
    )
    if before:
        before_at, before_id = before
        statement = statement.where(
            or_(
                SavedComparison.updated_at < before_at,
                and_(SavedComparison.updated_at == before_at, SavedComparison.id > before_id),
            )
        )
    comparisons = list(
        session.scalars(
            statement.order_by(SavedComparison.updated_at.desc(), SavedComparison.id.asc()).limit(
                limit + 1
            )
        ).all()
    )
    has_more = len(comparisons) > limit
    page = comparisons[:limit]
    items = [_read_latest(session, owner_id, project, item) for item in page]
    next_cursor = _encode_cursor(page[-1]) if has_more else None
    return ComparisonPage(items=items, next_cursor=next_cursor)


def get_comparison(
    session: Session, owner_id: UUID, project_id: UUID, comparison_id: UUID
) -> ComparisonRead:
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    comparison = _comparison_by_owner(session, owner_id, project_id, comparison_id)
    if comparison is None:
        raise _not_found("Comparison not found")
    return _read_latest(session, owner_id, project, comparison)


def update_comparison(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    comparison_id: UUID,
    command: ComparisonPatch,
) -> ComparisonRead:
    project = _lock_project(session, owner_id, project_id, command.expected_version)
    comparison = _comparison_by_owner(session, owner_id, project_id, comparison_id, lock=True)
    if comparison is None:
        raise _not_found("Comparison not found")
    _check_comparison_version(comparison, command.expected_comparison_version)
    changes = command.model_dump(
        exclude_unset=True, exclude={"expected_version", "expected_comparison_version"}
    )
    item_ids = changes.get("project_product_ids") or _item_ids(session, comparison.id)
    dimensions = changes.get("dimensions") or _dimension_inputs(session, comparison.id)
    members = _members(session, owner_id, project_id, item_ids)
    _validate_dimensions(session, project_id, dimensions)
    if "title" in changes:
        if changes["title"] is None or not changes["title"].strip():
            raise _invalid("Comparison title cannot be empty")
        comparison.title = changes["title"].strip()
    if "display_mode" in changes:
        comparison.display_mode = changes["display_mode"]
    if "project_product_ids" in changes:
        _replace_members(session, comparison.id, item_ids)
    if "dimensions" in changes:
        _replace_dimensions(session, comparison.id, dimensions)
    comparison.comparison_revision += 1
    comparison.updated_at = datetime.now(UTC)
    project_service._advance_revision(project)
    session.flush()
    view = _build_view(session, owner_id, project, members, dimensions)
    snapshot = _save_snapshot(session, owner_id, project, comparison, view)
    _commit(session)
    return _comparison_read(session, project, comparison, snapshot, current_view=view)


def regenerate_comparison(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    comparison_id: UUID,
    command: ComparisonRegenerate,
) -> ComparisonRead:
    project = _lock_project(session, owner_id, project_id, command.expected_version)
    comparison = _comparison_by_owner(session, owner_id, project_id, comparison_id, lock=True)
    if comparison is None:
        raise _not_found("Comparison not found")
    _check_comparison_version(comparison, command.expected_comparison_version)
    ids = _item_ids(session, comparison.id)
    dimensions = _dimension_inputs(session, comparison.id)
    members = _members(session, owner_id, project_id, ids)
    _validate_dimensions(session, project_id, dimensions)
    comparison.comparison_revision += 1
    comparison.updated_at = datetime.now(UTC)
    project_service._advance_revision(project)
    session.flush()
    view = _build_view(session, owner_id, project, members, dimensions)
    snapshot = _save_snapshot(session, owner_id, project, comparison, view)
    _commit(session)
    return _comparison_read(session, project, comparison, snapshot, current_view=view)


def delete_comparison(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    comparison_id: UUID,
    *,
    expected_version: int,
    expected_comparison_version: int,
) -> None:
    project = _lock_project(session, owner_id, project_id, expected_version)
    comparison = _comparison_by_owner(session, owner_id, project_id, comparison_id, lock=True)
    if comparison is None:
        raise _not_found("Comparison not found")
    _check_comparison_version(comparison, expected_comparison_version)
    session.delete(comparison)
    project_service._advance_revision(project)
    _commit(session)


def apply_proposal_locked(
    session: Session,
    owner_id: UUID,
    project: ShoppingProject,
    operation: dict,
) -> UUID:
    """Persist an assistant comparison operation in its enclosing proposal transaction."""
    from shopping.conversations.schemas import SetComparisonDimensions

    try:
        command = SetComparisonDimensions.model_validate(operation)
    except Exception as error:
        raise _invalid("The comparison proposal is invalid") from error
    dimensions = command.dimensions
    ids = command.project_product_ids
    members = _members(session, owner_id, project.id, ids)
    _validate_dimensions(session, project.id, dimensions)
    comparison = None
    if command.comparison_id is not None:
        comparison = _comparison_by_owner(
            session, owner_id, project.id, command.comparison_id, lock=True
        )
        if comparison is None:
            raise _not_found("Comparison not found")
        _check_comparison_version(comparison, command.expected_comparison_version)
        comparison.title = command.title
        comparison.display_mode = command.display_mode
        comparison.comparison_revision += 1
        comparison.updated_at = datetime.now(UTC)
    else:
        comparison = SavedComparison(
            owner_id=owner_id,
            project_id=project.id,
            title=command.title,
            display_mode=command.display_mode,
            comparison_revision=1,
        )
        session.add(comparison)
        session.flush()
    _replace_members(session, comparison.id, ids)
    _replace_dimensions(session, comparison.id, dimensions)
    session.flush()
    view = _build_view(session, owner_id, project, members, dimensions)
    _save_snapshot(session, owner_id, project, comparison, view)
    return comparison.id


def _build_view(session, owner_id, project, members, dimensions):
    products = []
    for membership, variant, product in members:
        products.append(
            {
                "project_product_id": str(membership.id),
                "product_id": str(product.id),
                "variant_id": str(variant.id),
                "canonical_name": product.canonical_name,
                "brand": product.brand,
                "category": product.category,
                "variant_name": variant.display_name,
                "identity_attributes": variant.identity_attributes,
                "product_revision": product.revision,
                "variant_revision": variant.revision,
            }
        )
    dimension_views = []
    for dimension in dimensions:
        cells = [
            _cell(session, owner_id, project, membership, variant, product, dimension)
            for membership, variant, product in members
        ]
        dimension_views.append(
            {
                "key": dimension.key,
                "label": dimension.label,
                "unit": dimension.unit,
                "dimension_type": dimension.dimension_type,
                "cells": cells,
                "equal": _demonstrably_equal(cells),
            }
        )
    return {"products": products, "dimensions": dimension_views}


def _cell(session, owner_id, project, membership, variant, product, dimension):
    kind = dimension.dimension_type
    if kind == "fact":
        attribute = variant.category_attributes.get(dimension.key)
        if attribute is None:
            attribute = variant.identity_attributes.get(dimension.key)
        if attribute is None:
            return _cell_value(membership.id, "unknown")
        if isinstance(attribute, dict) and "value" in attribute:
            value, unit = attribute.get("value"), attribute.get("unit")
        else:
            value, unit = attribute, None
        normalized, normalized_unit, comparable = _normalize(
            value, unit or dimension.unit, dimension.key
        )
        origin = attribute.get("origin") if isinstance(attribute, dict) else None
        observation_id = attribute.get("observation_id") if isinstance(attribute, dict) else None
        return _cell_value(
            membership.id,
            "known" if comparable else "incomparable",
            value=value,
            unit=unit or dimension.unit,
            # Unit is part of equality when no deterministic conversion exists.
            # Without it, e.g. 12 L and 12 gal would disappear in differences mode.
            comparison_value={"value": normalized, "unit": normalized_unit},
            provenance={
                "catalog_product_id": str(product.id),
                "variant_id": str(variant.id),
                "product_revision": product.revision,
                "variant_revision": variant.revision,
                "attribute_origin": origin,
                "observation_id": str(observation_id) if observation_id else None,
            },
        )

    if kind == "offer":
        offer = session.scalar(
            select(RetailOffer)
            .where(RetailOffer.owner_id == owner_id, RetailOffer.variant_id == variant.id)
            .order_by(RetailOffer.observed_at.desc(), RetailOffer.id.desc())
            .limit(1)
        )
        if offer is None:
            return _cell_value(membership.id, "unknown")
        status = "known" if offer.amount is not None and offer.currency is not None else "unknown"
        value = {
            "amount": format(offer.amount, ".2f") if offer.amount is not None else None,
            "currency": offer.currency,
            "retailer": offer.retailer_name,
            "availability": offer.availability,
            "condition": offer.condition,
            "observed_at": offer.observed_at.isoformat(),
            "url": offer.url,
        }
        comparison_value = [value["amount"], value["currency"], value["observed_at"]]
        return _cell_value(
            membership.id,
            status,
            value=value,
            unit=offer.currency,
            comparison_value=comparison_value,
            provenance={
                "offer_id": str(offer.id),
                "observation_id": str(offer.observation_id) if offer.observation_id else None,
            },
        )

    if kind == "evidence":
        claims = list(
            session.scalars(
                select(Claim)
                .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
                .join(SourceSnapshot, SourceSnapshot.id == Claim.snapshot_id)
                .join(Source, Source.id == SourceSnapshot.source_id)
                .where(
                    Claim.owner_id == owner_id,
                    Claim.subject_variant_id == variant.id,
                    Claim.attribute_key == dimension.key,
                    SourceSnapshot.owner_id == owner_id,
                    Source.owner_id == owner_id,
                )
                .distinct()
                .order_by(Claim.extracted_at.desc(), Claim.id)
                .limit(20)
            ).all()
        )
        if not claims:
            return _cell_value(membership.id, "unknown")
        claim_ids = [claim.id for claim in claims]
        relations = list(
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
        conflict = any(item.relation == "contradicts" for item in relations)
        summaries = []
        stale = False
        comparison_values = []
        for claim in claims:
            snapshot = session.get(SourceSnapshot, claim.snapshot_id)
            source = session.get(Source, snapshot.source_id) if snapshot else None
            claim_freshness = (
                freshness(
                    claim.evidence_category,
                    published_at=snapshot.published_at,
                    retrieved_at=snapshot.retrieved_at,
                    now=datetime.now(UTC),
                )
                if snapshot
                else "unknown"
            )
            stale = stale or claim_freshness == "stale"
            summaries.append(
                {
                    "claim_id": str(claim.id),
                    "snapshot_id": str(claim.snapshot_id),
                    "assertion": claim.assertion_text,
                    "normalized_value": claim.normalized_value,
                    "qualifiers": claim.qualifiers,
                    "evidence_category": claim.evidence_category,
                    "source_title": (snapshot.title if snapshot else None)
                    or (source.title if source else None),
                    "source_url": source.normalized_url if source else None,
                    "retrieved_at": snapshot.retrieved_at.isoformat() if snapshot else None,
                    "freshness": claim_freshness,
                }
            )
            comparison_values.append(
                {"value": claim.normalized_value, "qualifiers": claim.qualifiers}
            )
        status = "conflict" if conflict else "stale" if stale else "known"
        return _cell_value(
            membership.id,
            status,
            value=summaries,
            comparison_value=comparison_values,
            provenance={
                "claim_ids": [str(item) for item in claim_ids],
                "snapshot_ids": [str(claim.snapshot_id) for claim in claims],
                "relations": [
                    {
                        "claim_id": str(item.claim_id),
                        "related_claim_id": str(item.related_claim_id),
                        "relation": item.relation,
                    }
                    for item in relations
                ],
            },
        )

    if kind == "project_fit":
        assessment = session.scalar(
            select(ProductAssessment)
            .where(
                ProductAssessment.owner_id == owner_id,
                ProductAssessment.project_id == project.id,
                ProductAssessment.project_product_id == membership.id,
            )
            .order_by(ProductAssessment.generated_at.desc(), ProductAssessment.id.desc())
            .limit(1)
        )
        if assessment is None:
            return _cell_value(membership.id, "unknown")
        stale = (
            assessment.project_revision != project.revision
            or assessment.product_revision != product.revision
            or assessment.variant_revision != variant.revision
        )
        conclusion = next(
            (
                item
                for item in assessment.conclusions
                if item.get("requirement_id") == dimension.key
            ),
            None,
        )
        if conclusion is None:
            return _cell_value(
                membership.id,
                "stale" if stale else "unknown",
                provenance={"assessment_id": str(assessment.id)},
            )
        status = (
            "stale" if stale else "unknown" if conclusion.get("status") == "unknown" else "known"
        )
        return _cell_value(
            membership.id,
            status,
            value={
                "status": conclusion.get("status"),
                "rationale": conclusion.get("rationale"),
                "claim_ids": conclusion.get("claim_ids", []),
            },
            comparison_value=conclusion.get("status"),
            provenance={
                "assessment_id": str(assessment.id),
                "claim_ids": conclusion.get("claim_ids", []),
                "snapshot_ids": assessment.snapshot_ids,
            },
        )

    if kind == "user_note":
        note = session.scalar(
            select(UserNote).where(
                UserNote.owner_id == owner_id,
                UserNote.project_id == project.id,
                UserNote.project_product_id == membership.id,
            )
        )
        if note is None:
            return _cell_value(membership.id, "unknown")
        normalized = " ".join(note.text.casefold().split())
        return _cell_value(
            membership.id,
            "known",
            value=note.text,
            comparison_value=normalized,
            provenance={"note_id": str(note.id), "note_version": note.version},
        )
    return _cell_value(membership.id, "unknown")


def _cell_value(
    project_product_id, status, *, value=None, unit=None, comparison_value=None, provenance=None
):
    return {
        "project_product_id": str(project_product_id),
        "status": status,
        "value": value,
        "unit": unit,
        "comparison_value": comparison_value,
        "provenance": provenance or {},
    }


def _normalize(value, unit, key):
    if value is None or isinstance(value, (dict, list)):
        return value, unit, False
    if isinstance(value, bool):
        return value, unit, True
    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and not math.isfinite(value):
            return value, unit, False
        number = Decimal(str(value))
        conversions = {
            "mm": ("length", Decimal("1")),
            "cm": ("length", Decimal("10")),
            "m": ("length", Decimal("1000")),
            "in": ("length", Decimal("25.4")),
            "inch": ("length", Decimal("25.4")),
            "inches": ("length", Decimal("25.4")),
            "ft": ("length", Decimal("304.8")),
            "g": ("mass", Decimal("1")),
            "kg": ("mass", Decimal("1000")),
            "oz": ("mass", Decimal("28.349523125")),
            "lb": ("mass", Decimal("453.59237")),
            "lbs": ("mass", Decimal("453.59237")),
            "s": ("time", Decimal("1")),
            "sec": ("time", Decimal("1")),
            "seconds": ("time", Decimal("1")),
            "min": ("time", Decimal("60")),
            "minutes": ("time", Decimal("60")),
            "h": ("time", Decimal("3600")),
            "hr": ("time", Decimal("3600")),
            "hours": ("time", Decimal("3600")),
        }
        normalized_unit = unit.casefold() if isinstance(unit, str) else None
        conversion = conversions.get(normalized_unit or "")
        if conversion:
            family, factor = conversion
            canonical = {"length": "mm", "mass": "g", "time": "s"}[family]
            return _decimal_text(number * factor), canonical, True
        return _decimal_text(number), unit, unit is None or isinstance(unit, str)
    if isinstance(value, str):
        return " ".join(value.casefold().split()), unit, True
    return value, unit, False


def _decimal_text(value: Decimal) -> str:
    """Use a stable non-exponent decimal form independent of input scale."""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _demonstrably_equal(cells):
    if len(cells) < 2 or any(cell["status"] != "known" for cell in cells):
        return False
    values = [_stable(cell["comparison_value"]) for cell in cells]
    return all(value == values[0] for value in values[1:])


def _stable(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _comparison_read(session, project, comparison, snapshot, *, current_view):
    stale = (
        snapshot.project_revision != project.revision
        or snapshot.catalog_revision != _catalog_revision(session, comparison.owner_id)
        or _stable(current_view) != _stable(snapshot.view)
    )
    all_dimensions = [
        ComparisonDimensionRead.model_validate(item) for item in snapshot.view["dimensions"]
    ]
    hidden = 0
    dimensions = all_dimensions
    if comparison.display_mode == "differences":
        kept = [item for item in all_dimensions if not item.equal]
        hidden = len(all_dimensions) - len(kept)
        dimensions = kept
    return ComparisonRead(
        id=comparison.id,
        project_id=comparison.project_id,
        title=comparison.title,
        display_mode=comparison.display_mode,
        comparison_revision=comparison.comparison_revision,
        project_revision=snapshot.project_revision,
        snapshot_id=snapshot.id,
        generated_at=snapshot.generated_at,
        stale=stale,
        products=[ComparisonProductRead.model_validate(item) for item in snapshot.view["products"]],
        dimensions=dimensions,
        hidden_equal_dimensions=hidden,
    )


def _read_latest(session, owner_id, project, comparison):
    snapshot = session.scalar(
        select(ComparisonSnapshot)
        .where(
            ComparisonSnapshot.owner_id == owner_id,
            ComparisonSnapshot.comparison_id == comparison.id,
        )
        .order_by(ComparisonSnapshot.comparison_revision.desc())
        .limit(1)
    )
    if snapshot is None:
        raise ProjectError(
            409, "comparison_snapshot_missing", "This saved comparison has no generated view."
        )
    members = _members(session, owner_id, project.id, _item_ids(session, comparison.id))
    current_view = _build_view(
        session, owner_id, project, members, _dimension_inputs(session, comparison.id)
    )
    return _comparison_read(session, project, comparison, snapshot, current_view=current_view)


def _save_snapshot(session, owner_id, project, comparison, view):
    snapshot = ComparisonSnapshot(
        owner_id=owner_id,
        comparison_id=comparison.id,
        comparison_revision=comparison.comparison_revision,
        project_revision=project.revision,
        catalog_revision=_catalog_revision(session, owner_id),
        view=view,
    )
    session.add(snapshot)
    return snapshot


def _members(session, owner_id, project_id, ids):
    if len(ids) < 2 or len(ids) > 6 or len(ids) != len(set(ids)):
        raise _invalid("A comparison must contain 2 to 6 distinct project products")
    rows_by_id = {
        row[0].id: row
        for row in session.execute(
            select(ProjectProduct, ProductVariant, Product)
            .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProjectProduct.project_id == project_id,
                ProjectProduct.id.in_(ids),
                Product.owner_id == owner_id,
            )
        ).all()
    }
    if len(rows_by_id) != len(ids):
        raise _not_found("One or more selected variants are not in this project")
    return [rows_by_id[item] for item in ids]


def _replace_members(session, comparison_id, ids):
    existing = list(
        session.scalars(
            select(ComparisonItem).where(ComparisonItem.comparison_id == comparison_id)
        ).all()
    )
    for item in existing:
        session.delete(item)
    session.flush()
    for position, item_id in enumerate(ids):
        session.add(
            ComparisonItem(
                comparison_id=comparison_id, project_product_id=item_id, position=position
            )
        )
    session.flush()


def _replace_dimensions(session, comparison_id, dimensions):
    existing = list(
        session.scalars(
            select(ComparisonDimension).where(ComparisonDimension.comparison_id == comparison_id)
        ).all()
    )
    for item in existing:
        session.delete(item)
    session.flush()
    for position, item in enumerate(dimensions):
        session.add(
            ComparisonDimension(
                comparison_id=comparison_id,
                key=item.key,
                label=item.label,
                unit=item.unit,
                dimension_type=item.dimension_type,
                position=position,
            )
        )
    session.flush()


def _item_ids(session, comparison_id):
    return list(
        session.scalars(
            select(ComparisonItem.project_product_id)
            .where(ComparisonItem.comparison_id == comparison_id)
            .order_by(ComparisonItem.position)
        ).all()
    )


def _dimension_inputs(session, comparison_id):
    return [
        ComparisonDimensionInput(
            key=item.key,
            label=item.label,
            unit=item.unit,
            dimension_type=item.dimension_type,
        )
        for item in session.scalars(
            select(ComparisonDimension)
            .where(ComparisonDimension.comparison_id == comparison_id)
            .order_by(ComparisonDimension.position)
        ).all()
    ]


def _validate_dimensions(session, project_id, dimensions):
    if len(dimensions) < 1 or len(dimensions) > 20:
        raise _invalid("A comparison must have 1 to 20 dimensions")
    for dimension in dimensions:
        if dimension.dimension_type == "project_fit":
            try:
                requirement_id = UUID(dimension.key)
            except ValueError as error:
                raise _invalid("Project fit dimensions must use a requirement ID") from error
            requirement = session.scalar(
                select(ProjectRequirement.id).where(
                    ProjectRequirement.id == requirement_id,
                    ProjectRequirement.project_id == project_id,
                )
            )
            if requirement is None:
                raise _not_found(
                    "A comparison fit dimension refers to a missing project requirement"
                )


def _lock_project(session, owner_id, project_id, expected_version):
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    if project.revision != expected_version:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded.",
            {"current_version": project.revision},
        )
    return project


def _comparison_by_owner(session, owner_id, project_id, comparison_id, *, lock=False):
    statement = select(SavedComparison).where(
        SavedComparison.id == comparison_id,
        SavedComparison.owner_id == owner_id,
        SavedComparison.project_id == project_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _check_comparison_version(comparison, expected):
    if comparison.comparison_revision != expected:
        raise ProjectError(
            409,
            "comparison_revision_conflict",
            "This comparison changed since it was loaded.",
            {"current_comparison_version": comparison.comparison_revision},
        )


def _catalog_revision(session, owner_id):
    return (
        session.scalar(
            select(OwnerCatalogState.revision).where(OwnerCatalogState.owner_id == owner_id)
        )
        or 1
    )


def _encode_cursor(comparison):
    payload = json.dumps(
        [comparison.updated_at.astimezone(UTC).isoformat(), str(comparison.id)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor):
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        instant, comparison_id = datetime.fromisoformat(payload[0]), UUID(payload[1])
        if instant.tzinfo is None or len(payload) != 2:
            raise ValueError
        return instant.astimezone(UTC), comparison_id
    except (ValueError, TypeError, IndexError, binascii.Error, json.JSONDecodeError) as error:
        raise _invalid("Invalid comparison pagination cursor") from error


def _commit(session):
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _invalid("Comparison data violates a project constraint") from error


def _not_found(message):
    return ProjectError(404, "not_found", message)


def _invalid(message):
    return ProjectError(422, "invalid_request", message)
