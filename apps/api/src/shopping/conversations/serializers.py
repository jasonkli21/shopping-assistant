from __future__ import annotations

import base64
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.conversations.models import ConversationMessage, ProjectUpdateProposal
from shopping.conversations.schemas import MessageRead, ProposalRead
from shopping.projects.errors import ProjectError


def _message_read(
    message: ConversationMessage, proposal: ProjectUpdateProposal | None
) -> MessageRead:
    metadata = message.task_metadata or {}
    return MessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        project_id=message.project_id,
        paired_message_id=message.paired_message_id,
        ordinal=message.ordinal,
        role=message.role,
        text=message.content,
        status=message.status,
        request_key=message.request_key,
        snapshot_revision=message.snapshot_revision,
        sequence=message.sequence,
        error_code=message.error_code,
        clarification_questions=metadata.get("clarification_questions", []),
        created_at=message.created_at,
        completed_at=message.completed_at,
        proposal=_proposal_read(proposal) if proposal else None,
    )


def _proposal_read(proposal: ProjectUpdateProposal) -> ProposalRead:
    return ProposalRead(
        id=proposal.id,
        project_id=proposal.project_id,
        assistant_message_id=proposal.assistant_message_id,
        base_revision=proposal.base_revision,
        schema_version=proposal.schema_version,
        operations=proposal.operations,
        status=proposal.status,
        applied_revision=proposal.applied_revision,
        applied_project=proposal.applied_project,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


def _proposals_for_messages(
    session: Session, message_ids: list[UUID]
) -> dict[UUID, ProjectUpdateProposal]:
    if not message_ids:
        return {}
    return {
        proposal.assistant_message_id: proposal
        for proposal in session.scalars(
            select(ProjectUpdateProposal).where(
                ProjectUpdateProposal.assistant_message_id.in_(message_ids)
            )
        ).all()
    }


def _encode_cursor(ordinal: int) -> str:
    return base64.urlsafe_b64encode(str(ordinal).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = int(base64.urlsafe_b64decode(padded.encode()).decode())
        if value < 1:
            raise ValueError
        return value
    except (ValueError, UnicodeDecodeError) as error:
        raise ProjectError(422, "invalid_request", "Invalid message pagination cursor") from error
