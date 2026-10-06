from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from shopping.catalog.models import (
    CatalogObservation,
    EntityResolutionEvent,
    OwnerCatalogState,
    Product,
    ProductIdentifier,
    ProductVariant,
    ProjectProduct,
    RetailOffer,
)
from shopping.catalog.schemas import (
    CandidateNormalizationState,
    CatalogVariantChoice,
    CatalogVariantChoicePage,
    OfferPage,
    OfferRead,
    ProductIdentifierRead,
    ProductRead,
    ProductVariantRead,
    ProjectProductPage,
    ProjectProductRead,
    money_text,
)
from shopping.evidence.freshness import offer_freshness
from shopping.projects.errors import ProjectError
from shopping.projects.repository import project_by_owner
from shopping.research.models import DiscoveryCandidate


def list_project_products(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> ProjectProductPage:
    project = project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    before = _decode_cursor(cursor, "project_products") if cursor else None
    statement = (
        select(ProjectProduct, ProductVariant, Product)
        .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProjectProduct.project_id == project_id, Product.owner_id == owner_id)
        .order_by(ProjectProduct.created_at.asc(), ProjectProduct.id.asc())
    )
    if before:
        before_time, before_id = before
        statement = statement.where(
            or_(
                ProjectProduct.created_at > before_time,
                and_(ProjectProduct.created_at == before_time, ProjectProduct.id > before_id),
            )
        )
    rows = session.execute(statement.limit(limit + 1)).all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = (
        _encode_cursor("project_products", page_rows[-1][0].created_at, page_rows[-1][0].id)
        if has_more
        else None
    )
    catalog_version = _catalog_version(session, owner_id)
    return ProjectProductPage(
        items=[_project_product_read(session, owner_id, *row) for row in page_rows],
        next_cursor=next_cursor,
        catalog_version=catalog_version,
        project_version=project.revision,
    )


def get_product(session: Session, owner_id: UUID, product_id: UUID) -> ProductRead:
    product = session.scalar(
        select(Product).where(Product.id == product_id, Product.owner_id == owner_id)
    )
    if product is None:
        raise _not_found("Product not found")
    variants = list(
        session.scalars(
            select(ProductVariant)
            .where(ProductVariant.product_id == product_id)
            .order_by(ProductVariant.created_at.asc(), ProductVariant.id.asc())
        )
    )
    return ProductRead(
        id=product.id,
        canonical_name=product.canonical_name,
        brand=product.brand,
        category=product.category,
        model_family=product.model_family,
        revision=product.revision,
        created_at=product.created_at,
        updated_at=product.updated_at,
        variants=[_variant_read(session, owner_id, product, variant) for variant in variants],
    )


def list_catalog_variants(
    session: Session,
    owner_id: UUID,
    *,
    query: str = "",
    limit: int = 20,
    cursor: str | None = None,
) -> CatalogVariantChoicePage:
    before = _decode_cursor(cursor, "variants") if cursor else None
    statement = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.owner_id == owner_id)
        .order_by(ProductVariant.created_at.desc(), ProductVariant.id.desc())
    )
    normalized_query = query.strip()
    if normalized_query:
        pattern = f"%{_escape_like(normalized_query)}%"
        statement = statement.where(
            or_(
                Product.canonical_name.ilike(pattern, escape="\\"),
                Product.brand.ilike(pattern, escape="\\"),
                Product.model_family.ilike(pattern, escape="\\"),
                ProductVariant.display_name.ilike(pattern, escape="\\"),
            )
        )
    if before:
        before_time, before_id = before
        statement = statement.where(
            or_(
                ProductVariant.created_at < before_time,
                and_(
                    ProductVariant.created_at == before_time,
                    ProductVariant.id < before_id,
                ),
            )
        )
    rows = session.execute(statement.limit(limit + 1)).all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = (
        _encode_cursor("variants", page_rows[-1][0].created_at, page_rows[-1][0].id)
        if has_more
        else None
    )
    return CatalogVariantChoicePage(
        items=[
            CatalogVariantChoice(
                variant_id=variant.id,
                product_id=product.id,
                canonical_name=product.canonical_name,
                brand=product.brand,
                category=product.category,
                model_family=product.model_family,
                variant_name=variant.display_name,
                identity_attributes=variant.identity_attributes,
            )
            for variant, product in page_rows
        ],
        next_cursor=next_cursor,
        catalog_version=_catalog_version(session, owner_id),
    )


def list_product_offers(
    session: Session,
    owner_id: UUID,
    product_id: UUID,
    variant_id: UUID,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> OfferPage:
    product = session.scalar(
        select(Product).where(Product.id == product_id, Product.owner_id == owner_id)
    )
    if product is None:
        raise _not_found("Product not found")
    variant = session.scalar(
        select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
        )
    )
    if variant is None:
        raise _not_found("Product variant not found")
    before = _decode_cursor(cursor, "offers") if cursor else None
    statement = select(RetailOffer).where(
        RetailOffer.owner_id == owner_id,
        RetailOffer.variant_id == variant_id,
    )
    if before:
        before_time, before_id = before
        statement = statement.where(
            or_(
                RetailOffer.observed_at < before_time,
                and_(RetailOffer.observed_at == before_time, RetailOffer.id < before_id),
            )
        )
    offers = list(
        session.scalars(
            statement.order_by(RetailOffer.observed_at.desc(), RetailOffer.id.desc()).limit(
                limit + 1
            )
        )
    )
    has_more = len(offers) > limit
    page = offers[:limit]
    next_cursor = _encode_cursor("offers", page[-1].observed_at, page[-1].id) if has_more else None
    return OfferPage(
        items=[_offer_read(offer) for offer in page],
        next_cursor=next_cursor,
        catalog_version=_catalog_version(session, owner_id),
    )


def candidate_normalization_state(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    candidate: DiscoveryCandidate,
) -> CandidateNormalizationState | None:
    if candidate.canonical_mapping_id is None:
        mapping = None
    else:
        mapping = session.execute(
            select(ProjectProduct, ProductVariant, Product)
            .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProjectProduct.id == candidate.canonical_mapping_id,
                ProjectProduct.project_id == project_id,
                Product.owner_id == owner_id,
            )
        ).first()
    latest_event = session.scalar(
        select(EntityResolutionEvent)
        .where(
            EntityResolutionEvent.owner_id == owner_id,
            EntityResolutionEvent.project_id == project_id,
            EntityResolutionEvent.candidate_id == candidate.id,
        )
        .order_by(EntityResolutionEvent.created_at.desc(), EntityResolutionEvent.id.desc())
        .limit(1)
    )
    latest_observation = session.scalar(
        select(CatalogObservation)
        .where(
            CatalogObservation.owner_id == owner_id,
            CatalogObservation.project_id == project_id,
            CatalogObservation.candidate_id == candidate.id,
        )
        .order_by(CatalogObservation.retrieved_at.desc(), CatalogObservation.id.desc())
        .limit(1)
    )
    reverted_ids = select(EntityResolutionEvent.reversed_event_id).where(
        EntityResolutionEvent.owner_id == owner_id,
        EntityResolutionEvent.project_id == project_id,
        EntityResolutionEvent.candidate_id == candidate.id,
        EntityResolutionEvent.reversed_event_id.is_not(None),
    )
    active_correction = session.scalar(
        select(EntityResolutionEvent)
        .where(
            EntityResolutionEvent.owner_id == owner_id,
            EntityResolutionEvent.project_id == project_id,
            EntityResolutionEvent.candidate_id == candidate.id,
            EntityResolutionEvent.actor == "owner",
            EntityResolutionEvent.status == "manual_linked",
            EntityResolutionEvent.id.not_in(reverted_ids),
        )
        .order_by(EntityResolutionEvent.created_at.desc(), EntityResolutionEvent.id.desc())
        .limit(1)
    )
    if mapping is None and latest_event is None and latest_observation is None:
        return None
    project = project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    pp, variant, product = mapping if mapping else (None, None, None)
    return CandidateNormalizationState(
        candidate_id=candidate.id,
        project_product_id=pp.id if pp else None,
        product_id=product.id if product else None,
        variant_id=variant.id if variant else None,
        status=latest_event.status if latest_event else None,
        latest_observation_status=latest_observation.status if latest_observation else None,
        latest_failure_code=latest_observation.failure_code if latest_observation else None,
        catalog_version=_catalog_version(session, owner_id),
        project_version=project.revision,
        reason=latest_event.reason if latest_event else None,
        warnings=latest_observation.warnings if latest_observation else [],
        observed_at=latest_observation.retrieved_at if latest_observation else None,
        can_revert_correction=bool(
            active_correction
            and candidate.canonical_mapping_id == active_correction.selected_project_product_id
        ),
    )


def _project_product_read(
    session: Session,
    owner_id: UUID,
    project_product: ProjectProduct,
    variant: ProductVariant,
    product: Product,
) -> ProjectProductRead:
    offers = list(
        session.scalars(
            select(RetailOffer)
            .where(RetailOffer.owner_id == owner_id, RetailOffer.variant_id == variant.id)
            .order_by(RetailOffer.observed_at.desc(), RetailOffer.id.desc())
            .limit(3)
        )
    )
    return ProjectProductRead(
        id=project_product.id,
        project_id=project_product.project_id,
        product_id=product.id,
        variant_id=variant.id,
        canonical_name=product.canonical_name,
        brand=product.brand,
        category=product.category,
        model_family=product.model_family,
        variant_name=variant.display_name,
        identity_attributes=variant.identity_attributes,
        category_attributes=variant.category_attributes,
        first_candidate_id=project_product.first_candidate_id,
        discovery_reason=project_product.discovery_reason,
        created_at=project_product.created_at,
        offers=[_offer_read(offer) for offer in offers],
    )


def _variant_read(
    session: Session, owner_id: UUID, product: Product, variant: ProductVariant
) -> ProductVariantRead:
    identifiers = list(
        session.scalars(
            select(ProductIdentifier)
            .where(
                ProductIdentifier.product_id == product.id,
                ProductIdentifier.variant_id == variant.id,
            )
            .order_by(ProductIdentifier.scheme, ProductIdentifier.namespace, ProductIdentifier.id)
        )
    )
    offers = list(
        session.scalars(
            select(RetailOffer)
            .where(RetailOffer.owner_id == owner_id, RetailOffer.variant_id == variant.id)
            .order_by(RetailOffer.observed_at.desc(), RetailOffer.id.desc())
            .limit(3)
        )
    )
    return ProductVariantRead(
        id=variant.id,
        product_id=product.id,
        display_name=variant.display_name,
        identity_attributes=variant.identity_attributes,
        category_attributes=variant.category_attributes,
        revision=variant.revision,
        identifiers=[
            ProductIdentifierRead(
                id=item.id,
                scheme=item.scheme,
                namespace=item.namespace,
                value=item.value,
                observation_id=item.observation_id,
            )
            for item in identifiers
        ],
        offers=[_offer_read(offer) for offer in offers],
    )


def _offer_read(offer: RetailOffer) -> OfferRead:
    return OfferRead(
        id=offer.id,
        variant_id=offer.variant_id,
        observation_id=offer.observation_id,
        research_source_attempt_id=offer.research_source_attempt_id,
        retailer_name=offer.retailer_name,
        retailer_domain=offer.retailer_domain,
        url=offer.url,
        amount=money_text(offer.amount),
        currency=offer.currency,
        availability=offer.availability,
        condition=offer.condition,
        observed_at=offer.observed_at,
        freshness=offer_freshness(offer.observed_at, now=datetime.now(UTC)),
    )


def _catalog_version(session: Session, owner_id: UUID) -> int:
    return (
        session.scalar(
            select(OwnerCatalogState.revision).where(OwnerCatalogState.owner_id == owner_id)
        )
        or 1
    )


def _encode_cursor(kind: str, value: datetime, item_id: UUID) -> str:
    payload = json.dumps(
        {"kind": kind, "at": value.astimezone(UTC).isoformat(), "id": str(item_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None, expected_kind: str) -> tuple[datetime, UUID]:
    if cursor is None or len(cursor) > 256:
        raise _invalid_cursor()
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw)
        if set(payload) != {"kind", "at", "id"} or payload["kind"] != expected_kind:
            raise ValueError
        value = datetime.fromisoformat(payload["at"])
        item_id = UUID(payload["id"])
        if value.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError, KeyError, binascii.Error, json.JSONDecodeError) as error:
        raise _invalid_cursor() from error
    return value, item_id


def _invalid_cursor() -> ProjectError:
    return ProjectError(422, "invalid_cursor", "The catalog page cursor is invalid.")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)
