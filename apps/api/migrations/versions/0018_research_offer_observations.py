"""Attach append-only offer observations to research source attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_research_offer_observations"
down_revision: str | None = "0017_bounded_search_retries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_run_sources", sa.Column("offer_status", sa.String(20), nullable=True))
    op.add_column(
        "research_run_sources", sa.Column("offer_error_code", sa.String(60), nullable=True)
    )
    op.add_column(
        "research_run_sources",
        sa.Column(
            "offer_observation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_research_run_source_offer_status",
        "research_run_sources",
        "offer_status IS NULL OR offer_status IN "
        "('succeeded', 'no_offer', 'identity_mismatch', 'unsupported', 'failed')",
    )
    op.create_check_constraint(
        "ck_research_run_source_offer_size",
        "research_run_sources",
        "octet_length(offer_observation::text) <= 4000",
    )
    op.add_column(
        "retail_offers", sa.Column("research_source_attempt_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_retail_offers_research_source_attempt_id",
        "retail_offers",
        "research_run_sources",
        ["research_source_attempt_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_offer_research_source_attempt",
        "retail_offers",
        ["owner_id", "research_source_attempt_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_offer_research_source_attempt", "retail_offers", type_="unique")
    op.drop_constraint(
        "fk_retail_offers_research_source_attempt_id", "retail_offers", type_="foreignkey"
    )
    op.drop_column("retail_offers", "research_source_attempt_id")
    op.drop_constraint("ck_research_run_source_offer_size", "research_run_sources", type_="check")
    op.drop_constraint("ck_research_run_source_offer_status", "research_run_sources", type_="check")
    op.drop_column("research_run_sources", "offer_observation")
    op.drop_column("research_run_sources", "offer_error_code")
    op.drop_column("research_run_sources", "offer_status")
