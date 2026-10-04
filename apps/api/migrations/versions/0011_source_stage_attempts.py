"""Track source-specific extraction attempts and bounded validation warnings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0011_source_stage_attempts"
down_revision: str | None = "0010_research_stage_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_stage_attempts",
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "research_stage_attempts",
        sa.Column(
            "validation_warnings",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_foreign_key(
        "fk_research_stage_attempt_snapshot",
        "research_stage_attempts",
        "source_snapshots",
        ["source_snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_research_stage_attempt_warnings_size",
        "research_stage_attempts",
        "octet_length(validation_warnings::text) <= 4000",
    )
    op.drop_index("uq_research_stage_attempt_global", table_name="research_stage_attempts")
    op.drop_index("uq_research_stage_attempt_target", table_name="research_stage_attempts")
    op.create_index(
        "uq_research_stage_attempt_global",
        "research_stage_attempts",
        ["research_run_id", "stage", "attempt_number"],
        unique=True,
        postgresql_where=sa.text(
            "target_project_product_id IS NULL AND source_snapshot_id IS NULL"
        ),
    )
    op.create_index(
        "uq_research_stage_attempt_target",
        "research_stage_attempts",
        ["research_run_id", "target_project_product_id", "stage", "attempt_number"],
        unique=True,
        postgresql_where=sa.text(
            "target_project_product_id IS NOT NULL AND source_snapshot_id IS NULL"
        ),
    )
    op.create_index(
        "uq_research_stage_attempt_source",
        "research_stage_attempts",
        [
            "research_run_id",
            "target_project_product_id",
            "stage",
            "source_snapshot_id",
            "attempt_number",
        ],
        unique=True,
        postgresql_where=sa.text("source_snapshot_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_research_stage_attempt_source", table_name="research_stage_attempts")
    op.drop_index("uq_research_stage_attempt_target", table_name="research_stage_attempts")
    op.drop_index("uq_research_stage_attempt_global", table_name="research_stage_attempts")
    op.create_index(
        "uq_research_stage_attempt_global",
        "research_stage_attempts",
        ["research_run_id", "stage", "attempt_number"],
        unique=True,
        postgresql_where=sa.text("target_project_product_id IS NULL"),
    )
    op.create_index(
        "uq_research_stage_attempt_target",
        "research_stage_attempts",
        ["research_run_id", "target_project_product_id", "stage", "attempt_number"],
        unique=True,
        postgresql_where=sa.text("target_project_product_id IS NOT NULL"),
    )
    op.drop_constraint(
        "ck_research_stage_attempt_warnings_size", "research_stage_attempts", type_="check"
    )
    op.drop_constraint(
        "fk_research_stage_attempt_snapshot", "research_stage_attempts", type_="foreignkey"
    )
    op.drop_column("research_stage_attempts", "validation_warnings")
    op.drop_column("research_stage_attempts", "source_snapshot_id")
