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
    Uuid,
    desc,
    func,
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
