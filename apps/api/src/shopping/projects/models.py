from __future__ import annotations

from datetime import UTC, datetime
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
    Text,
    UniqueConstraint,
    Uuid,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shopping.db.base import Base


class ShoppingProject(Base):
    __tablename__ = "shopping_projects"
    __table_args__ = (
        CheckConstraint("char_length(btrim(title)) BETWEEN 1 AND 200", name="ck_project_title"),
        CheckConstraint("char_length(btrim(goal)) BETWEEN 1 AND 4000", name="ck_project_goal"),
        CheckConstraint("revision >= 1", name="ck_project_revision_positive"),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 10000", name="ck_project_notes_length"
        ),
        CheckConstraint(
            "category IS NULL OR char_length(category) <= 100", name="ck_project_category_length"
        ),
        CheckConstraint("status IN ('active', 'completed', 'archived')", name="ck_project_status"),
        CheckConstraint(
            "budget_target IS NULL OR budget_target >= 0",
            name="ck_project_budget_target_nonnegative",
        ),
        CheckConstraint(
            "budget_maximum IS NULL OR budget_maximum >= 0",
            name="ck_project_budget_maximum_nonnegative",
        ),
        CheckConstraint(
            "budget_target IS NULL OR budget_maximum IS NULL OR budget_target <= budget_maximum",
            name="ck_project_budget_order",
        ),
        CheckConstraint(
            "(budget_target IS NULL AND budget_maximum IS NULL) = (budget_currency IS NULL)",
            name="ck_project_budget_currency_pair",
        ),
        CheckConstraint(
            "budget_currency IS NULL OR budget_currency ~ '^[A-Z]{3}$'",
            name="ck_project_budget_currency_format",
        ),
        Index("ix_projects_owner_updated", "owner_id", desc("updated_at"), "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str] = mapped_column(String(4000), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    budget_target: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_maximum: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_currency: Mapped[str | None] = mapped_column(String(3))
    notes: Mapped[str | None] = mapped_column(Text)
    reuse_preferences: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requirements: Mapped[list[ProjectRequirement]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by=lambda: (ProjectRequirement.position, ProjectRequirement.id),
    )


class ProjectRequirement(Base):
    __tablename__ = "project_requirements"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('must_have', 'preference', 'constraint')", name="ck_requirement_kind"
        ),
        CheckConstraint("char_length(btrim(label)) BETWEEN 1 AND 300", name="ck_requirement_label"),
        CheckConstraint(
            "detail IS NULL OR char_length(detail) <= 2000", name="ck_requirement_detail_length"
        ),
        CheckConstraint(
            "attribute_key IS NULL OR char_length(attribute_key) BETWEEN 1 AND 100",
            name="ck_requirement_attribute_key",
        ),
        CheckConstraint(
            "operator IS NULL OR operator IN ('eq', 'gte', 'lte', 'contains', 'one_of')",
            name="ck_requirement_operator",
        ),
        CheckConstraint(
            "(attribute_key IS NULL AND operator IS NULL AND value IS NULL AND unit IS NULL) OR "
            "(attribute_key IS NOT NULL AND operator IS NOT NULL AND value IS NOT NULL)",
            name="ck_requirement_criterion_complete",
        ),
        CheckConstraint("position >= 0", name="ck_requirement_position_nonnegative"),
        CheckConstraint("origin IN ('user', 'ai_confirmed')", name="ck_requirement_origin"),
        Index("ix_requirements_project_position", "project_id", "position", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shopping_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(2000))
    attribute_key: Mapped[str | None] = mapped_column(String(100))
    operator: Mapped[str | None] = mapped_column(String(16))
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    unit: Mapped[str | None] = mapped_column(String(50))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user", server_default="user"
    )
    source_preference_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "shopping_preferences.id",
            name="fk_project_requirements_source_preference",
            ondelete="SET NULL",
        ),
    )
    source_preference_revision: Mapped[int | None] = mapped_column(Integer)
    source_preference_scope: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    project: Mapped[ShoppingProject] = relationship(back_populates="requirements")


class ProjectProductDecision(Base):
    __tablename__ = "project_product_decisions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('considering', 'shortlisted', 'rejected', 'purchased')",
            name="ck_decision_state",
        ),
        CheckConstraint(
            "rejection_reason IS NULL OR rejection_reason IN "
            "('too_expensive', 'missing_feature', 'too_large', 'appearance', 'weak_evidence', "
            "'wrong_category', 'already_owned', 'other')",
            name="ck_decision_rejection_reason",
        ),
        CheckConstraint(
            "(state = 'rejected') = (rejection_reason IS NOT NULL)",
            name="ck_decision_rejection_state",
        ),
        CheckConstraint("char_length(reason) <= 2000", name="ck_decision_reason_length"),
        CheckConstraint("octet_length(concerns::text) <= 12000", name="ck_decision_concerns_size"),
        CheckConstraint("actor IN ('owner', 'assistant')", name="ck_decision_actor"),
        CheckConstraint("origin IN ('command', 'proposal')", name="ck_decision_origin"),
        CheckConstraint("version >= 1", name="ck_decision_version"),
        UniqueConstraint("project_product_id", name="uq_project_product_decision"),
        Index("ix_decisions_project_state", "project_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    project_product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="considering")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rejection_reason: Mapped[str | None] = mapped_column(String(24))
    concerns: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    selected_offer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("retail_offers.id", ondelete="SET NULL")
    )
    actor: Mapped[str] = mapped_column(String(16), nullable=False, default="owner")
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="command")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DecisionEvent(Base):
    __tablename__ = "decision_events"
    __table_args__ = (
        CheckConstraint(
            "char_length(command_type) BETWEEN 1 AND 40", name="ck_decision_event_type"
        ),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="ck_decision_event_hash"),
        CheckConstraint("project_version >= 1", name="ck_decision_event_project_version"),
        CheckConstraint(
            "from_state IN ('considering', 'shortlisted', 'rejected', 'purchased')",
            name="ck_decision_event_from_state",
        ),
        CheckConstraint(
            "to_state IN ('considering', 'shortlisted', 'rejected', 'purchased')",
            name="ck_decision_event_to_state",
        ),
        CheckConstraint("actor IN ('owner', 'assistant')", name="ck_decision_event_actor"),
        CheckConstraint(
            "char_length(request_key) BETWEEN 8 AND 100", name="ck_decision_event_request_key"
        ),
        CheckConstraint(
            "octet_length(concerns::text) <= 12000", name="ck_decision_event_concerns_size"
        ),
        UniqueConstraint(
            "owner_id",
            "project_id",
            "command_type",
            "request_key",
            name="uq_decision_event_request",
        ),
        Index("ix_decision_events_product_time", "project_product_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    project_product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="CASCADE"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    request_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[str] = mapped_column(String(16), nullable=False)
    to_state: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rejection_reason: Mapped[str | None] = mapped_column(String(24))
    concerns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    selected_offer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("retail_offers.id", ondelete="SET NULL")
    )
    project_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserNote(Base):
    __tablename__ = "user_notes"
    __table_args__ = (
        CheckConstraint("char_length(btrim(text)) BETWEEN 1 AND 10000", name="ck_user_note_text"),
        CheckConstraint("version >= 1", name="ck_user_note_version"),
        Index(
            "uq_user_note_project_product",
            "project_id",
            "project_product_id",
            unique=True,
            postgresql_where=text("project_product_id IS NOT NULL"),
        ),
        Index(
            "uq_user_note_project_only",
            "project_id",
            unique=True,
            postgresql_where=text("project_product_id IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    project_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
