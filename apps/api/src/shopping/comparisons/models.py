from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shopping.db.base import Base


class SavedComparison(Base):
    __tablename__ = "comparisons"
    __table_args__ = (
        CheckConstraint("char_length(btrim(title)) BETWEEN 1 AND 160", name="ck_comparison_title"),
        CheckConstraint("display_mode IN ('all', 'differences')", name="ck_comparison_mode"),
        CheckConstraint("comparison_revision >= 1", name="ck_comparison_revision"),
        Index("ix_comparisons_owner_project_updated", "owner_id", "project_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    display_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    comparison_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ComparisonItem(Base):
    __tablename__ = "comparison_items"
    __table_args__ = (
        UniqueConstraint("comparison_id", "project_product_id", name="uq_comparison_item_member"),
        UniqueConstraint("comparison_id", "position", name="uq_comparison_item_position"),
        CheckConstraint("position BETWEEN 0 AND 5", name="ck_comparison_item_position"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    comparison_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comparisons.id", ondelete="CASCADE"), nullable=False
    )
    project_product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class ComparisonDimension(Base):
    __tablename__ = "comparison_dimensions"
    __table_args__ = (
        UniqueConstraint("comparison_id", "key", name="uq_comparison_dimension_key"),
        UniqueConstraint("comparison_id", "position", name="uq_comparison_dimension_position"),
        CheckConstraint("position BETWEEN 0 AND 19", name="ck_comparison_dimension_position"),
        CheckConstraint(
            "char_length(btrim(key)) BETWEEN 1 AND 100", name="ck_comparison_dimension_key"
        ),
        CheckConstraint(
            "char_length(btrim(label)) BETWEEN 1 AND 100", name="ck_comparison_dimension_label"
        ),
        CheckConstraint(
            "unit IS NULL OR char_length(unit) <= 30", name="ck_comparison_dimension_unit"
        ),
        CheckConstraint(
            "dimension_type IN ('fact', 'offer', 'evidence', 'project_fit', 'user_note')",
            name="ck_comparison_dimension_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    comparison_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comparisons.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(30))
    dimension_type: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class ComparisonSnapshot(Base):
    __tablename__ = "comparison_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "comparison_id", "comparison_revision", name="uq_comparison_snapshot_revision"
        ),
        CheckConstraint(
            "comparison_revision >= 1 AND project_revision >= 1", name="ck_snapshot_revisions"
        ),
        CheckConstraint("octet_length(view::text) <= 1000000", name="ck_comparison_snapshot_size"),
        Index("ix_comparison_snapshots_generated", "comparison_id", "generated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    comparison_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comparisons.id", ondelete="CASCADE"), nullable=False
    )
    comparison_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    project_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    view: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
