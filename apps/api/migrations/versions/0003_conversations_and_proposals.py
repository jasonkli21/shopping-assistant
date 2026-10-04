"""Persist owner-scoped conversations and validated update proposals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_conversations_proposals"
down_revision: str | None = "0002_project_revision_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("next_ordinal", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("next_ordinal >= 1", name="ck_conversation_next_ordinal"),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_conversation_project"),
    )
    op.create_index("ix_conversations_owner_project", "conversations", ["owner_id", "project_id"])
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("paired_message_id", sa.Uuid(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_key", sa.String(length=100), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("snapshot_revision", sa.Integer(), nullable=True),
        sa.Column("sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("task_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
        sa.CheckConstraint(
            "status IN ('generating', 'completed', 'failed', 'interrupted')",
            name="ck_message_status",
        ),
        sa.CheckConstraint("ordinal >= 1", name="ck_message_ordinal"),
        sa.CheckConstraint("sequence >= 0", name="ck_message_sequence"),
        sa.CheckConstraint("char_length(content) <= 8000", name="ck_message_content_length"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["paired_message_id"], ["conversation_messages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "ordinal", name="uq_message_conversation_ordinal"),
    )
    op.create_index(
        "ix_messages_project_created", "conversation_messages", ["project_id", "created_at", "id"]
    )
    op.create_index(
        "uq_message_request_key",
        "conversation_messages",
        ["owner_id", "project_id", "request_key"],
        unique=True,
        postgresql_where=sa.text("request_key IS NOT NULL"),
    )
    op.create_table(
        "project_update_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("operations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("applied_revision", sa.Integer(), nullable=True),
        sa.Column("applied_project", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("base_revision >= 1", name="ck_proposal_base_revision"),
        sa.CheckConstraint("schema_version >= 1", name="ck_proposal_schema_version"),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'dismissed', 'stale')", name="ck_proposal_status"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"], ["conversation_messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assistant_message_id", name="uq_proposal_assistant_message"),
    )
    op.create_index(
        "ix_proposals_project_status",
        "project_update_proposals",
        ["owner_id", "project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposals_project_status", table_name="project_update_proposals")
    op.drop_table("project_update_proposals")
    op.drop_index("uq_message_request_key", table_name="conversation_messages")
    op.drop_index("ix_messages_project_created", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_owner_project", table_name="conversations")
    op.drop_table("conversations")
