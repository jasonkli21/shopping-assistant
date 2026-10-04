"""Create owner-scoped projects and requirements."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_projects_requirements"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shopping_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("goal", sa.String(length=4000), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("budget_target", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("budget_maximum", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("budget_currency", sa.String(length=3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(btrim(title)) BETWEEN 1 AND 200", name="ck_project_title"),
        sa.CheckConstraint("char_length(btrim(goal)) BETWEEN 1 AND 4000", name="ck_project_goal"),
        sa.CheckConstraint(
            "category IS NULL OR char_length(category) <= 100",
            name="ck_project_category_length",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'archived')", name="ck_project_status"
        ),
        sa.CheckConstraint(
            "budget_target IS NULL OR budget_target >= 0",
            name="ck_project_budget_target_nonnegative",
        ),
        sa.CheckConstraint(
            "budget_maximum IS NULL OR budget_maximum >= 0",
            name="ck_project_budget_maximum_nonnegative",
        ),
        sa.CheckConstraint(
            "budget_target IS NULL OR budget_maximum IS NULL OR budget_target <= budget_maximum",
            name="ck_project_budget_order",
        ),
        sa.CheckConstraint(
            "(budget_target IS NULL AND budget_maximum IS NULL) = (budget_currency IS NULL)",
            name="ck_project_budget_currency_pair",
        ),
        sa.CheckConstraint(
            "budget_currency IS NULL OR budget_currency ~ '^[A-Z]{3}$'",
            name="ck_project_budget_currency_format",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_projects_owner_updated",
        "shopping_projects",
        ["owner_id", sa.text("updated_at DESC"), "id"],
    )

    op.create_table(
        "project_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("detail", sa.String(length=2000), nullable=True),
        sa.Column("attribute_key", sa.String(length=100), nullable=True),
        sa.Column("operator", sa.String(length=16), nullable=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=16), server_default="user", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('must_have', 'preference', 'constraint')", name="ck_requirement_kind"
        ),
        sa.CheckConstraint(
            "char_length(btrim(label)) BETWEEN 1 AND 300", name="ck_requirement_label"
        ),
        sa.CheckConstraint(
            "detail IS NULL OR char_length(detail) <= 2000",
            name="ck_requirement_detail_length",
        ),
        sa.CheckConstraint(
            "attribute_key IS NULL OR char_length(attribute_key) BETWEEN 1 AND 100",
            name="ck_requirement_attribute_key",
        ),
        sa.CheckConstraint(
            "operator IS NULL OR operator IN ('eq', 'gte', 'lte', 'contains', 'one_of')",
            name="ck_requirement_operator",
        ),
        sa.CheckConstraint(
            "(attribute_key IS NULL AND operator IS NULL AND value IS NULL AND unit IS NULL) OR "
            "(attribute_key IS NOT NULL AND operator IS NOT NULL AND value IS NOT NULL)",
            name="ck_requirement_criterion_complete",
        ),
        sa.CheckConstraint("position >= 0", name="ck_requirement_position_nonnegative"),
        sa.CheckConstraint("origin IN ('user', 'ai_confirmed')", name="ck_requirement_origin"),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_requirements_project_position",
        "project_requirements",
        ["project_id", "position", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_requirements_project_position", table_name="project_requirements")
    op.drop_table("project_requirements")
    op.drop_index("ix_projects_owner_updated", table_name="shopping_projects")
    op.drop_table("shopping_projects")
