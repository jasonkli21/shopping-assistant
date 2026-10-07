"""Persist fenced conversation generation ownership."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p9_conversation_generation_leases"
down_revision: str | None = "p9_owner_privacy_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column("generation_owner", sa.String(length=100)))
    op.add_column("conversation_messages", sa.Column("generation_lease_token", sa.Uuid()))
    op.add_column(
        "conversation_messages",
        sa.Column("generation_lease_expires_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "conversation_messages", sa.Column("generation_heartbeat_at", sa.DateTime(timezone=True))
    )
    op.create_check_constraint(
        "ck_message_generation_lease_state",
        "conversation_messages",
        "(generation_owner IS NULL AND generation_lease_token IS NULL "
        "AND generation_lease_expires_at IS NULL AND generation_heartbeat_at IS NULL) "
        "OR (status = 'generating' AND generation_owner IS NOT NULL "
        "AND generation_lease_token IS NOT NULL "
        "AND generation_lease_expires_at IS NOT NULL AND generation_heartbeat_at IS NOT NULL)",
    )
    op.create_index(
        "ix_messages_generation_lease",
        "conversation_messages",
        ["generation_lease_expires_at"],
        postgresql_where=sa.text("status = 'generating'"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_generation_lease", table_name="conversation_messages")
    op.drop_constraint("ck_message_generation_lease_state", "conversation_messages", type_="check")
    op.drop_column("conversation_messages", "generation_heartbeat_at")
    op.drop_column("conversation_messages", "generation_lease_expires_at")
    op.drop_column("conversation_messages", "generation_lease_token")
    op.drop_column("conversation_messages", "generation_owner")
