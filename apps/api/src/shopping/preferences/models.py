from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shopping.db.base import Base


class ShoppingProfile(Base):
    __tablename__ = "shopping_profiles"
    __table_args__ = (CheckConstraint("revision >= 1", name="ck_shopping_profile_revision"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    reuse_enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ShoppingPreference(Base):
    __tablename__ = "shopping_preferences"
    __table_args__ = (
        CheckConstraint("char_length(btrim(label)) BETWEEN 1 AND 300", name="ck_preference_label"),
        CheckConstraint("char_length(key) BETWEEN 1 AND 100", name="ck_preference_key"),
        CheckConstraint(
            "(lower(key) = 'statement' AND operator IS NULL) OR "
            "(lower(key) <> 'statement' AND operator IS NOT NULL)",
            name="ck_preference_criterion",
        ),
        CheckConstraint(
            "operator IS NULL OR operator IN ('eq', 'gte', 'lte', 'contains', 'one_of')",
            name="ck_preference_operator",
        ),
        CheckConstraint("char_length(unit) <= 50", name="ck_preference_unit"),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_preference_status"),
        CheckConstraint("strength = 'soft'", name="ck_preference_strength"),
        CheckConstraint("revision >= 1", name="ck_preference_revision"),
        CheckConstraint(
            "source_kind IN ('requirement', 'decision')", name="ck_preference_source_kind"
        ),
        CheckConstraint("octet_length(value::text) <= 8000", name="ck_preference_value_size"),
        CheckConstraint(
            "octet_length(category_scopes::text) <= 4000", name="ck_preference_scopes_size"
        ),
        Index("ix_preferences_profile_status", "profile_id", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_profiles.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("preference_candidates.id", ondelete="SET NULL"), unique=True
    )
    source_project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="SET NULL")
    )
    source_requirement_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_requirements.id", ondelete="SET NULL")
    )
    source_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requirement", server_default="requirement"
    )
    source_project_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="SET NULL")
    )
    source_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_product_decisions.id", ondelete="SET NULL")
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[str | None] = mapped_column(String(16))
    value: Mapped[dict | list | str | int | float | bool] = mapped_column(JSONB, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    category_scopes: Mapped[list] = mapped_column(JSONB, nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    monetary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    strength: Mapped[str] = mapped_column(
        String(8), nullable=False, default="soft", server_default="soft"
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="active", server_default="active"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PreferenceCandidate(Base):
    __tablename__ = "preference_candidates"
    __table_args__ = (
        CheckConstraint("char_length(btrim(label)) BETWEEN 1 AND 300", name="ck_candidate_label"),
        CheckConstraint("char_length(key) BETWEEN 1 AND 100", name="ck_candidate_key"),
        CheckConstraint(
            "(lower(key) = 'statement' AND operator IS NULL) OR "
            "(lower(key) <> 'statement' AND operator IS NOT NULL)",
            name="ck_candidate_criterion",
        ),
        CheckConstraint(
            "operator IS NULL OR operator IN ('eq', 'gte', 'lte', 'contains', 'one_of')",
            name="ck_candidate_operator",
        ),
        CheckConstraint("char_length(unit) <= 50", name="ck_candidate_unit"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'dismissed', 'stale')", name="ck_candidate_status"
        ),
        CheckConstraint("source_project_revision >= 1", name="ck_candidate_source_revision"),
        CheckConstraint(
            "source_kind IN ('requirement', 'decision')", name="ck_candidate_source_kind"
        ),
        CheckConstraint("proposition_hash ~ '^[0-9a-f]{64}$'", name="ck_candidate_hash"),
        CheckConstraint("octet_length(value::text) <= 8000", name="ck_candidate_value_size"),
        CheckConstraint(
            "octet_length(category_scopes::text) <= 4000", name="ck_candidate_scopes_size"
        ),
        Index(
            "uq_preference_candidate_requirement_version",
            "owner_id",
            "source_requirement_id",
            "source_project_revision",
            "proposition_hash",
            unique=True,
            postgresql_where=text(
                "source_kind = 'requirement' AND source_requirement_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_preference_candidate_decision_version",
            "owner_id",
            "source_project_product_id",
            "source_project_revision",
            "proposition_hash",
            unique=True,
            postgresql_where=text(
                "source_kind = 'decision' AND source_project_product_id IS NOT NULL"
            ),
        ),
        Index("ix_preference_candidates_owner_status", "owner_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="SET NULL")
    )
    source_requirement_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_requirements.id", ondelete="SET NULL")
    )
    source_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requirement", server_default="requirement"
    )
    source_project_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="SET NULL")
    )
    source_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_product_decisions.id", ondelete="SET NULL")
    )
    source_project_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    proposition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[str | None] = mapped_column(String(16))
    value: Mapped[dict | list | str | int | float | bool] = mapped_column(JSONB, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    category_scopes: Mapped[list] = mapped_column(JSONB, nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    monetary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    rationale: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default=""
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
