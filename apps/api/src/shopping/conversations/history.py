from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from shopping.conversations.models import Conversation, ConversationMessage, ProjectUpdateProposal
from shopping.conversations.schemas import (
    ConversationPage,
    ConversationRead,
    MessagePage,
    MessageRead,
)

from .serializers import _decode_cursor, _encode_cursor, _message_read, _proposals_for_messages
from .shared import _not_found, _require_project


def list_conversations(session: Session, owner_id: UUID, project_id: UUID) -> ConversationPage:
    _require_project(session, owner_id, project_id)
    items = list(
        session.scalars(
            select(Conversation).where(
                Conversation.owner_id == owner_id,
                Conversation.project_id == project_id,
            )
        ).all()
    )
    return ConversationPage(
        items=[
            ConversationRead(
                id=item.id,
                project_id=item.project_id,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]
    )


def list_messages(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    limit: int = 50,
    before: str | None = None,
) -> MessagePage:
    _require_project(session, owner_id, project_id)
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.owner_id == owner_id,
            Conversation.project_id == project_id,
        )
    )
    if conversation is None:
        return MessagePage(items=[])
    before_ordinal = _decode_cursor(before) if before else None
    statement = select(ConversationMessage).where(
        ConversationMessage.conversation_id == conversation.id
    )
    if before_ordinal is not None:
        statement = statement.where(ConversationMessage.ordinal < before_ordinal)
    rows = list(
        session.scalars(
            statement.order_by(desc(ConversationMessage.ordinal)).limit(limit + 1)
        ).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    page.reverse()
    next_cursor = _encode_cursor(page[0].ordinal) if has_more and page else None
    proposals = _proposals_for_messages(
        session, [row.id for row in page if row.role == "assistant"]
    )
    return MessagePage(
        items=[_message_read(row, proposals.get(row.id)) for row in page],
        next_cursor=next_cursor,
    )


def get_message_for_stream(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    message_id: UUID,
) -> MessageRead:
    _require_project(session, owner_id, project_id)
    message = session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.id == message_id,
            ConversationMessage.owner_id == owner_id,
            ConversationMessage.project_id == project_id,
            ConversationMessage.role == "assistant",
        )
    )
    if message is None:
        raise _not_found("Assistant message not found")
    proposal = session.scalar(
        select(ProjectUpdateProposal).where(
            ProjectUpdateProposal.assistant_message_id == message_id,
            ProjectUpdateProposal.owner_id == owner_id,
            ProjectUpdateProposal.project_id == project_id,
        )
    )
    return _message_read(message, proposal)
