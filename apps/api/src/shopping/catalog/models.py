from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shopping.db.base import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(canonical_name)) BETWEEN 1 AND 300", name="ck_product_name"
        ),
        CheckConstraint("brand IS NULL OR char_length(brand) <= 200", name="ck_product_brand"),
        CheckConstraint(
            "category IS NULL OR char_length(category) <= 100", name="ck_product_category"
        ),
        CheckConstraint(
            "model_family IS NULL OR char_length(model_family) <= 200",
            name="ck_product_model_family",
        ),
        CheckConstraint("revision >= 1", name="ck_product_revision"),
        Index("ix_products_owner_name", "owner_id", "canonical_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200))
    brand_key: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    model_family: Mapped[str | None] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(display_name)) BETWEEN 1 AND 300", name="ck_variant_name"
        ),
        CheckConstraint(
            "char_length(identity_key) BETWEEN 1 AND 500", name="ck_variant_identity_key"
        ),
        CheckConstraint("revision >= 1", name="ck_variant_revision"),
        UniqueConstraint("product_id", "identity_key", name="uq_variant_product_identity"),
        Index("ix_variants_product", "product_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    identity_key: Mapped[str] = mapped_column(String(500), nullable=False, default="unspecified")
    identity_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    category_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CatalogObservation(Base):
    __tablename__ = "catalog_observations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed', 'blocked', 'unsupported')",
            name="ck_catalog_observation_status",
        ),
        CheckConstraint(
            "char_length(requested_url) <= 2048 AND char_length(final_url) <= 2048",
            name="ck_catalog_observation_urls",
        ),
        CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_observation_hash",
        ),
        CheckConstraint(
            "char_length(extractor_version) BETWEEN 1 AND 80", name="ck_catalog_extractor_version"
        ),
        UniqueConstraint(
            "candidate_id", "idempotency_key", name="uq_catalog_observation_candidate_key"
        ),
        Index("ix_catalog_observations_candidate_time", "candidate_id", "retrieved_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("discovery_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    requested_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(80), nullable=False)
    task_version: Mapped[str] = mapped_column(String(80), nullable=False)
    extraction: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    excerpts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(60))


class ProductIdentifier(Base):
    __tablename__ = "product_identifiers"
    __table_args__ = (
        CheckConstraint(
            "scheme IN ('manufacturer_model', 'gtin', 'mpn', 'retailer_sku')",
            name="ck_identifier_scheme",
        ),
        CheckConstraint("char_length(btrim(value)) BETWEEN 1 AND 200", name="ck_identifier_value"),
        CheckConstraint("char_length(namespace) BETWEEN 1 AND 300", name="ck_identifier_namespace"),
        UniqueConstraint(
            "variant_id",
            "scheme",
            "namespace",
            "normalized_value",
            name="uq_identifier_variant_key",
        ),
        Index("ix_identifiers_lookup", "scheme", "namespace", "normalized_value"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    scheme: Mapped[str] = mapped_column(String(32), nullable=False)
    namespace: Mapped[str] = mapped_column(String(300), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(200), nullable=False)
    observation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("catalog_observations.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProjectProduct(Base):
    __tablename__ = "project_products"
    __table_args__ = (
        CheckConstraint("char_length(discovery_reason) <= 300", name="ck_project_product_reason"),
        UniqueConstraint("project_id", "variant_id", name="uq_project_product_project_variant"),
        Index("ix_project_products_project_created", "project_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    first_candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "discovery_candidates.id",
            name="fk_project_products_first_candidate",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )
    first_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_runs.id", ondelete="SET NULL")
    )
    discovery_reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RetailOffer(Base):
    __tablename__ = "retail_offers"
    __table_args__ = (
        CheckConstraint(
            "(amount IS NULL AND currency IS NULL) OR (amount >= 0 AND currency ~ '^[A-Z]{3}$')",
            name="ck_offer_amount_currency",
        ),
        CheckConstraint(
            "availability IN ('in_stock', 'out_of_stock', 'preorder', 'unknown')",
            name="ck_offer_availability",
        ),
        CheckConstraint(
            "condition IN ('new', 'used', 'refurbished', 'unknown')", name="ck_offer_condition"
        ),
        CheckConstraint(
            "char_length(retailer_name) BETWEEN 1 AND 200", name="ck_offer_retailer_name"
        ),
        CheckConstraint("char_length(url) BETWEEN 1 AND 2048", name="ck_offer_url"),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_offer_owner_idempotency"),
        Index("ix_offers_variant_observed", "variant_id", text("observed_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    observation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("catalog_observations.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    retailer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    retailer_domain: Mapped[str | None] = mapped_column(String(253))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    availability: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    condition: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntityResolutionEvent(Base):
    __tablename__ = "entity_resolution_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('auto_linked', 'manual_linked', 'unresolved', 'reverted')",
            name="ck_resolution_event_status",
        ),
        CheckConstraint("actor IN ('system', 'owner')", name="ck_resolution_actor"),
        UniqueConstraint(
            "owner_id",
            "project_id",
            "candidate_id",
            "request_key",
            name="uq_resolution_request_key",
        ),
        Index("ix_resolution_candidate_time", "candidate_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("discovery_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    observation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("catalog_observations.id", ondelete="SET NULL")
    )
    request_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    previous_project_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="SET NULL")
    )
    selected_project_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="SET NULL")
    )
    reversed_event_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entity_resolution_events.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
