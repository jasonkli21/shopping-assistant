from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, RetailOffer, SavedProduct
from shopping.catalog.schemas import (
    FavoriteCommand,
    FavoriteRead,
    OfferRead,
    SavedProductPage,
    SavedProductRead,
    money_text,
)
from shopping.evidence.freshness import offer_freshness
from shopping.projects.errors import ProjectError


def list_favorites(
    session: Session, owner_id: UUID, *, limit: int = 20, cursor: str | None = None
) -> SavedProductPage:
    before = _decode_cursor(cursor) if cursor else None
    statement = (
        select(SavedProduct, ProductVariant, Product)
        .join(ProductVariant, ProductVariant.id == SavedProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(SavedProduct.owner_id == owner_id, SavedProduct.favorite.is_(True))
    )
    if before:
        before_at, before_id = before
        statement = statement.where(
            or_(
                SavedProduct.updated_at < before_at,
                and_(SavedProduct.updated_at == before_at, SavedProduct.id < before_id),
            )
        )
    rows = session.execute(
        statement.order_by(SavedProduct.updated_at.desc(), SavedProduct.id.desc()).limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1][0]) if has_more else None
    return SavedProductPage(
        items=[_saved_read(session, owner_id, *row) for row in page], next_cursor=next_cursor
    )


def get_favorite(session: Session, owner_id: UUID, variant_id: UUID) -> FavoriteRead:
    _owned_variant(session, owner_id, variant_id)
    saved = session.scalar(
        select(SavedProduct).where(
            SavedProduct.owner_id == owner_id, SavedProduct.variant_id == variant_id
        )
    )
    return FavoriteRead(
        variant_id=variant_id,
        favorite=saved.favorite if saved else False,
        version=saved.version if saved else 0,
        updated_at=saved.updated_at if saved else None,
    )


def set_favorite(
    session: Session,
    owner_id: UUID,
    variant_id: UUID,
    favorite: bool,
    command: FavoriteCommand,
) -> FavoriteRead:
    _owned_variant(session, owner_id, variant_id)
    saved = session.scalar(
        select(SavedProduct)
        .where(SavedProduct.owner_id == owner_id, SavedProduct.variant_id == variant_id)
        .with_for_update()
    )
    if saved is None:
        if command.expected_version != 0:
            raise _conflict(0)
        if not favorite:
            return FavoriteRead(variant_id=variant_id, favorite=False, version=0, updated_at=None)
        saved = SavedProduct(
            owner_id=owner_id,
            variant_id=variant_id,
            favorite=True,
            version=1,
            updated_at=datetime.now(UTC),
        )
        session.add(saved)
    else:
        if saved.version != command.expected_version:
            raise _conflict(saved.version)
        if saved.favorite != favorite:
            saved.favorite = favorite
            saved.version += 1
            saved.updated_at = datetime.now(UTC)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _conflict(1) from error
    return FavoriteRead(
        variant_id=variant_id,
        favorite=saved.favorite,
        version=saved.version,
        updated_at=saved.updated_at,
    )


def _owned_variant(session: Session, owner_id: UUID, variant_id: UUID):
    row = session.execute(
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.id == variant_id, Product.owner_id == owner_id)
    ).one_or_none()
    if row is None:
        raise _not_found("Product variant not found")
    return row


def _saved_read(session: Session, owner_id: UUID, saved, variant, product):
    offers = list(
        session.scalars(
            select(RetailOffer)
            .where(RetailOffer.owner_id == owner_id, RetailOffer.variant_id == variant.id)
            .order_by(RetailOffer.observed_at.desc(), RetailOffer.id.desc())
            .limit(3)
        ).all()
    )
    return SavedProductRead(
        variant_id=variant.id,
        favorite=saved.favorite,
        version=saved.version,
        updated_at=saved.updated_at,
        product_id=product.id,
        canonical_name=product.canonical_name,
        brand=product.brand,
        category=product.category,
        variant_name=variant.display_name,
        identity_attributes=variant.identity_attributes,
        offers=[
            OfferRead(
                id=offer.id,
                variant_id=offer.variant_id,
                observation_id=offer.observation_id,
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
            for offer in offers
        ],
    )


def _encode_cursor(saved: SavedProduct) -> str:
    payload = json.dumps(
        [saved.updated_at.astimezone(UTC).isoformat(), str(saved.id)], separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str):
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        instant = datetime.fromisoformat(payload[0])
        item_id = UUID(payload[1])
        if instant.tzinfo is None or len(payload) != 2:
            raise ValueError
    except (ValueError, TypeError, IndexError, binascii.Error, json.JSONDecodeError) as error:
        raise ProjectError(
            422, "invalid_cursor", "The saved products page cursor is invalid."
        ) from error
    return instant.astimezone(UTC), item_id


def _conflict(current_version: int) -> ProjectError:
    return ProjectError(
        409,
        "favorite_version_conflict",
        "Saved product changed since it was loaded.",
        {"current_version": current_version},
    )


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)
