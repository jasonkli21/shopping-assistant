"""Add local profiles, explicit preference promotion and provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_explicit_shopping_preferences"
down_revision: str | None = "0018_research_offer_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shopping_projects",
        sa.Column("reuse_preferences", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "project_requirements", sa.Column("source_preference_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "project_requirements",
        sa.Column("source_preference_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "project_requirements",
        sa.Column(
            "source_preference_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    op.create_table(
        "shopping_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("reuse_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision >= 1", name="ck_shopping_profile_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id"),
    )
    op.create_table(
        "preference_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("source_project_id", sa.Uuid(), nullable=True),
        sa.Column("source_requirement_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source_kind", sa.String(length=16), server_default="requirement", nullable=False
        ),
        sa.Column("source_project_product_id", sa.Uuid(), nullable=True),
        sa.Column("source_decision_id", sa.Uuid(), nullable=True),
        sa.Column("source_project_revision", sa.Integer(), nullable=False),
        sa.Column("proposition_hash", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("operator", sa.String(length=16), nullable=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unit", sa.String(length=50), server_default="", nullable=False),
        sa.Column("category_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("rationale", sa.String(length=500), server_default="", nullable=False),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(btrim(label)) BETWEEN 1 AND 300", name="ck_candidate_label"
        ),
        sa.CheckConstraint("char_length(key) BETWEEN 1 AND 100", name="ck_candidate_key"),
        sa.CheckConstraint(
            "(lower(key) = 'statement' AND operator IS NULL) OR "
            "(lower(key) <> 'statement' AND operator IS NOT NULL)",
            name="ck_candidate_criterion",
        ),
        sa.CheckConstraint("char_length(unit) <= 50", name="ck_candidate_unit"),
        sa.CheckConstraint("proposition_hash ~ '^[0-9a-f]{64}$'", name="ck_candidate_hash"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'dismissed', 'stale')", name="ck_candidate_status"
        ),
        sa.CheckConstraint(
            "operator IS NULL OR operator IN ('eq', 'gte', 'lte', 'contains', 'one_of')",
            name="ck_candidate_operator",
        ),
        sa.CheckConstraint("source_project_revision >= 1", name="ck_candidate_source_revision"),
        sa.CheckConstraint(
            "source_kind IN ('requirement', 'decision')", name="ck_candidate_source_kind"
        ),
        sa.CheckConstraint("octet_length(value::text) <= 8000", name="ck_candidate_value_size"),
        sa.CheckConstraint(
            "octet_length(category_scopes::text) <= 4000", name="ck_candidate_scopes_size"
        ),
        sa.ForeignKeyConstraint(
            ["source_project_id"], ["shopping_projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_requirement_id"], ["project_requirements.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_project_product_id"], ["project_products.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_decision_id"], ["project_product_decisions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_preference_candidates_owner_status",
        "preference_candidates",
        ["owner_id", "status", "created_at"],
    )
    op.create_index(
        "uq_preference_candidate_requirement_version",
        "preference_candidates",
        ["owner_id", "source_requirement_id", "source_project_revision", "proposition_hash"],
        unique=True,
        postgresql_where=sa.text(
            "source_kind = 'requirement' AND source_requirement_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_preference_candidate_decision_version",
        "preference_candidates",
        ["owner_id", "source_project_product_id", "source_project_revision", "proposition_hash"],
        unique=True,
        postgresql_where=sa.text(
            "source_kind = 'decision' AND source_project_product_id IS NOT NULL"
        ),
    )
    op.create_table(
        "shopping_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("source_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("source_project_id", sa.Uuid(), nullable=True),
        sa.Column("source_requirement_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source_kind", sa.String(length=16), server_default="requirement", nullable=False
        ),
        sa.Column("source_project_product_id", sa.Uuid(), nullable=True),
        sa.Column("source_decision_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("operator", sa.String(length=16), nullable=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unit", sa.String(length=50), server_default="", nullable=False),
        sa.Column("category_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("strength", sa.String(length=8), server_default="soft", nullable=False),
        sa.Column("status", sa.String(length=12), server_default="active", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(btrim(label)) BETWEEN 1 AND 300", name="ck_preference_label"
        ),
        sa.CheckConstraint("char_length(key) BETWEEN 1 AND 100", name="ck_preference_key"),
        sa.CheckConstraint(
            "(lower(key) = 'statement' AND operator IS NULL) OR "
            "(lower(key) <> 'statement' AND operator IS NOT NULL)",
            name="ck_preference_criterion",
        ),
        sa.CheckConstraint(
            "operator IS NULL OR operator IN ('eq', 'gte', 'lte', 'contains', 'one_of')",
            name="ck_preference_operator",
        ),
        sa.CheckConstraint("char_length(unit) <= 50", name="ck_preference_unit"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_preference_status"),
        sa.CheckConstraint("strength = 'soft'", name="ck_preference_strength"),
        sa.CheckConstraint("revision >= 1", name="ck_preference_revision"),
        sa.CheckConstraint(
            "source_kind IN ('requirement', 'decision')", name="ck_preference_source_kind"
        ),
        sa.CheckConstraint("octet_length(value::text) <= 8000", name="ck_preference_value_size"),
        sa.CheckConstraint(
            "octet_length(category_scopes::text) <= 4000", name="ck_preference_scopes_size"
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["shopping_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_candidate_id"], ["preference_candidates.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_project_id"], ["shopping_projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_requirement_id"], ["project_requirements.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_project_product_id"], ["project_products.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_decision_id"], ["project_product_decisions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_candidate_id"),
    )
    op.create_index(
        "ix_preferences_profile_status",
        "shopping_preferences",
        ["profile_id", "status", "updated_at"],
    )
    op.create_foreign_key(
        "fk_project_requirements_source_preference",
        "project_requirements",
        "shopping_preferences",
        ["source_preference_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_project_requirements_source_preference", "project_requirements", type_="foreignkey"
    )
    op.drop_index("ix_preferences_profile_status", table_name="shopping_preferences")
    op.drop_table("shopping_preferences")
    op.drop_index("ix_preference_candidates_owner_status", table_name="preference_candidates")
    op.drop_index("uq_preference_candidate_decision_version", table_name="preference_candidates")
    op.drop_index("uq_preference_candidate_requirement_version", table_name="preference_candidates")
    op.drop_table("preference_candidates")
    op.drop_table("shopping_profiles")
    op.drop_column("project_requirements", "source_preference_scope")
    op.drop_column("project_requirements", "source_preference_revision")
    op.drop_column("project_requirements", "source_preference_id")
    op.drop_column("shopping_projects", "reuse_preferences")
