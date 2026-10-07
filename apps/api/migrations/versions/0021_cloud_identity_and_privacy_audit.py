"""Bind the configured Firebase identity and retain content-free privacy audit."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_cloud_identity_and_privacy_audit"
down_revision: str | None = "0020_explicit_monetary_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "firebase_owner_bindings",
        sa.Column("firebase_uid", sa.String(length=128), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("char_length(firebase_uid) BETWEEN 1 AND 128", name="ck_binding_uid"),
        sa.PrimaryKeyConstraint("firebase_uid"),
        sa.UniqueConstraint("owner_id", name="uq_binding_owner"),
    )
    op.create_table(
        "owner_privacy_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("record_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("event_type = 'purge'", name="ck_owner_privacy_event_type"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_owner_privacy_events_owner_time",
        "owner_privacy_events",
        ["owner_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_owner_privacy_events_owner_time", table_name="owner_privacy_events")
    op.drop_table("owner_privacy_events")
    op.drop_table("firebase_owner_bindings")
