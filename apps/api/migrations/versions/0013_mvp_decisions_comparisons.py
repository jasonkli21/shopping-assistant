"""Persist project decisions, private notes, favorites, and saved comparisons."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_mvp_decisions_comparisons"
down_revision: str | None = "0012_assessment_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_product_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("project_product_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=24), nullable=True),
        sa.Column("concerns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_offer_id", sa.Uuid(), nullable=True),
        sa.Column("actor", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('considering', 'shortlisted', 'rejected', 'purchased')",
            name="ck_decision_state",
        ),
        sa.CheckConstraint(
            "rejection_reason IS NULL OR rejection_reason IN "
            "('too_expensive', 'missing_feature', 'too_large', 'appearance', 'weak_evidence', "
            "'wrong_category', 'already_owned', 'other')",
            name="ck_decision_rejection_reason",
        ),
        sa.CheckConstraint(
            "(state = 'rejected') = (rejection_reason IS NOT NULL)",
            name="ck_decision_rejection_state",
        ),
        sa.CheckConstraint("char_length(reason) <= 2000", name="ck_decision_reason_length"),
        sa.CheckConstraint(
            "octet_length(concerns::text) <= 12000", name="ck_decision_concerns_size"
        ),
        sa.CheckConstraint("actor IN ('owner', 'assistant')", name="ck_decision_actor"),
        sa.CheckConstraint("origin IN ('command', 'proposal')", name="ck_decision_origin"),
        sa.CheckConstraint("version >= 1", name="ck_decision_version"),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_product_id"], ["project_products.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["selected_offer_id"], ["retail_offers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_product_id", name="uq_project_product_decision"),
    )
    op.create_index(
        "ix_decisions_project_state", "project_product_decisions", ["project_id", "state"]
    )

    op.create_table(
        "decision_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("project_product_id", sa.Uuid(), nullable=False),
        sa.Column("command_type", sa.String(length=40), nullable=False),
        sa.Column("request_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("from_state", sa.String(length=16), nullable=False),
        sa.Column("to_state", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=24), nullable=True),
        sa.Column("project_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(command_type) BETWEEN 1 AND 40", name="ck_decision_event_type"
        ),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="ck_decision_event_hash"),
        sa.CheckConstraint("project_version >= 1", name="ck_decision_event_project_version"),
        sa.CheckConstraint(
            "from_state IN ('considering', 'shortlisted', 'rejected', 'purchased')",
            name="ck_decision_event_from_state",
        ),
        sa.CheckConstraint(
            "to_state IN ('considering', 'shortlisted', 'rejected', 'purchased')",
            name="ck_decision_event_to_state",
        ),
        sa.CheckConstraint("actor IN ('owner', 'assistant')", name="ck_decision_event_actor"),
        sa.CheckConstraint(
            "char_length(request_key) BETWEEN 8 AND 100", name="ck_decision_event_request_key"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_product_id"], ["project_products.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "project_id",
            "command_type",
            "request_key",
            name="uq_decision_event_request",
        ),
    )
    op.create_index(
        "ix_decision_events_product_time", "decision_events", ["project_product_id", "created_at"]
    )

    op.create_table(
        "user_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("project_product_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(btrim(text)) BETWEEN 1 AND 10000", name="ck_user_note_text"
        ),
        sa.CheckConstraint("version >= 1", name="ck_user_note_version"),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_product_id"], ["project_products.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_user_note_project_product",
        "user_notes",
        ["project_id", "project_product_id"],
        unique=True,
        postgresql_where=sa.text("project_product_id IS NOT NULL"),
    )
    op.create_index(
        "uq_user_note_project_only",
        "user_notes",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("project_product_id IS NULL"),
    )

    op.create_table(
        "saved_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("favorite", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name="ck_saved_product_version"),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "variant_id", name="uq_saved_product_owner_variant"),
    )
    op.create_index(
        "ix_saved_products_owner_favorite", "saved_products", ["owner_id", "favorite", "updated_at"]
    )

    op.create_table(
        "comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("display_mode", sa.String(length=16), nullable=False),
        sa.Column("comparison_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 160", name="ck_comparison_title"
        ),
        sa.CheckConstraint("display_mode IN ('all', 'differences')", name="ck_comparison_mode"),
        sa.CheckConstraint("comparison_revision >= 1", name="ck_comparison_revision"),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_comparisons_owner_project_updated",
        "comparisons",
        ["owner_id", "project_id", "updated_at"],
    )

    op.create_table(
        "comparison_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("project_product_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position BETWEEN 0 AND 5", name="ck_comparison_item_position"),
        sa.ForeignKeyConstraint(["comparison_id"], ["comparisons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_product_id"], ["project_products.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comparison_id", "project_product_id", name="uq_comparison_item_member"
        ),
        sa.UniqueConstraint("comparison_id", "position", name="uq_comparison_item_position"),
    )

    op.create_table(
        "comparison_dimensions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=True),
        sa.Column("dimension_type", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position BETWEEN 0 AND 19", name="ck_comparison_dimension_position"),
        sa.CheckConstraint(
            "char_length(btrim(key)) BETWEEN 1 AND 100", name="ck_comparison_dimension_key"
        ),
        sa.CheckConstraint(
            "char_length(btrim(label)) BETWEEN 1 AND 100", name="ck_comparison_dimension_label"
        ),
        sa.CheckConstraint(
            "unit IS NULL OR char_length(unit) <= 30", name="ck_comparison_dimension_unit"
        ),
        sa.CheckConstraint(
            "dimension_type IN ('fact', 'offer', 'evidence', 'project_fit', 'user_note')",
            name="ck_comparison_dimension_type",
        ),
        sa.ForeignKeyConstraint(["comparison_id"], ["comparisons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comparison_id", "key", name="uq_comparison_dimension_key"),
        sa.UniqueConstraint("comparison_id", "position", name="uq_comparison_dimension_position"),
    )

    op.create_table(
        "comparison_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("comparison_revision", sa.Integer(), nullable=False),
        sa.Column("project_revision", sa.Integer(), nullable=False),
        sa.Column("catalog_revision", sa.Integer(), nullable=False),
        sa.Column("view", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "comparison_revision >= 1 AND project_revision >= 1", name="ck_snapshot_revisions"
        ),
        sa.CheckConstraint(
            "octet_length(view::text) <= 1000000", name="ck_comparison_snapshot_size"
        ),
        sa.ForeignKeyConstraint(["comparison_id"], ["comparisons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comparison_id", "comparison_revision", name="uq_comparison_snapshot_revision"
        ),
    )
    op.create_index(
        "ix_comparison_snapshots_generated",
        "comparison_snapshots",
        ["comparison_id", "generated_at"],
    )


def downgrade() -> None:
    op.drop_table("comparison_snapshots")
    op.drop_table("comparison_dimensions")
    op.drop_table("comparison_items")
    op.drop_table("comparisons")
    op.drop_table("saved_products")
    op.drop_table("user_notes")
    op.drop_table("decision_events")
    op.drop_table("project_product_decisions")
