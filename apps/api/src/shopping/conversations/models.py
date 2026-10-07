from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shopping.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_conversation_project"),
        CheckConstraint("next_ordinal >= 1", name="ck_conversation_next_ordinal"),
        Index("ix_conversations_owner_project", "owner_id", "project_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    next_ordinal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
        CheckConstraint(
            "status IN ('generating', 'completed', 'failed', 'interrupted')",
            name="ck_message_status",
        ),
        CheckConstraint("ordinal >= 1", name="ck_message_ordinal"),
        CheckConstraint("sequence >= 0", name="ck_message_sequence"),
        CheckConstraint("char_length(content) <= 8000", name="ck_message_content_length"),
        CheckConstraint(
            "(generation_owner IS NULL AND generation_lease_token IS NULL "
            "AND generation_lease_expires_at IS NULL AND generation_heartbeat_at IS NULL) "
            "OR (status = 'generating' AND generation_owner IS NOT NULL "
            "AND generation_lease_token IS NOT NULL "
            "AND generation_lease_expires_at IS NOT NULL AND generation_heartbeat_at IS NOT NULL)",
            name="ck_message_generation_lease_state",
        ),
        UniqueConstraint("conversation_id", "ordinal", name="uq_message_conversation_ordinal"),
        Index("ix_messages_project_created", "project_id", "created_at", "id"),
        Index(
            "ix_messages_generation_lease",
            "generation_lease_expires_at",
            postgresql_where=text("status = 'generating'"),
        ),
        Index(
            "uq_message_request_key",
            "owner_id",
            "project_id",
            "request_key",
            unique=True,
            postgresql_where=text("request_key IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    paired_message_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL")
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_key: Mapped[str | None] = mapped_column(String(100))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    snapshot_revision: Mapped[int | None] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(50))
    generation_owner: Mapped[str | None] = mapped_column(String(100))
    generation_lease_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    generation_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    task_metadata: Mapped[dict | None] = mapped_column(JSONB)
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectUpdateProposal(Base):
    __tablename__ = "project_update_proposals"
    __table_args__ = (
        CheckConstraint("base_revision >= 1", name="ck_proposal_base_revision"),
        CheckConstraint("schema_version >= 1", name="ck_proposal_schema_version"),
        CheckConstraint(
            "status IN ('pending', 'applied', 'dismissed', 'stale')", name="ck_proposal_status"
        ),
        UniqueConstraint("assistant_message_id", name="uq_proposal_assistant_message"),
        Index("ix_proposals_project_status", "owner_id", "project_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assistant_message_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversation_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    operations: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    applied_revision: Mapped[int | None] = mapped_column(Integer)
    applied_project: Mapped[dict | None] = mapped_column(JSONB)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
