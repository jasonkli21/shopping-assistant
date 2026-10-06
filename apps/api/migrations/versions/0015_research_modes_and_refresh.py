"""Persist bounded research mode and refresh lineage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_research_modes_and_refresh"
down_revision: str | None = "0014_decision_event_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column(
            "research_mode",
            sa.String(length=12),
            server_default="deep",
            nullable=False,
        ),
    )
    op.add_column("research_runs", sa.Column("refresh_of_run_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        "ck_research_mode", "research_runs", "research_mode IN ('quick', 'deep')"
    )
    op.create_foreign_key(
        "fk_research_runs_refresh_of_run_id",
        "research_runs",
        "research_runs",
        ["refresh_of_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_research_runs_refresh_of_run_id", "research_runs", ["refresh_of_run_id"])


def downgrade() -> None:
    op.drop_index("ix_research_runs_refresh_of_run_id", table_name="research_runs")
    op.drop_constraint("fk_research_runs_refresh_of_run_id", "research_runs", type_="foreignkey")
    op.drop_constraint("ck_research_mode", "research_runs", type_="check")
    op.drop_column("research_runs", "refresh_of_run_id")
    op.drop_column("research_runs", "research_mode")
