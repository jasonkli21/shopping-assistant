"""Retain decision concerns and selected offers in transition history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_decision_event_metadata"
down_revision: str | None = "0013_mvp_decisions_comparisons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "decision_events",
        sa.Column(
            "concerns",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("decision_events", sa.Column("selected_offer_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_decision_events_selected_offer_id_retail_offers",
        "decision_events",
        "retail_offers",
        ["selected_offer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_decision_event_concerns_size",
        "decision_events",
        "octet_length(concerns::text) <= 12000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_decision_event_concerns_size", "decision_events", type_="check")
    op.drop_constraint(
        "fk_decision_events_selected_offer_id_retail_offers",
        "decision_events",
        type_="foreignkey",
    )
    op.drop_column("decision_events", "selected_offer_id")
    op.drop_column("decision_events", "concerns")
