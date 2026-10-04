from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.conversations.models import ConversationMessage, ProjectUpdateProposal
from shopping.conversations.schemas import InterpretationOutput
from shopping.projects import repository

from .shared import SAFE_GENERATION_ERRORS, _bounded_request_id, _lock_assistant


def complete_generation(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    message_id: UUID,
    output: InterpretationOutput,
    provider_request_id: str | None,
) -> None:
    message = _lock_assistant(session, owner_id, project_id, message_id)
    if message.status != "generating":
        return
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        fail_generation(session, owner_id, project_id, message_id, "project_unavailable")
        return
    message.content = output.assistant_message
    message.status = "completed"
    message.sequence += 1 if output.assistant_message else 0
    message.input_snapshot = None
    message.completed_at = datetime.now(UTC)
    message.error_code = None
    metadata = dict(message.task_metadata or {})
    metadata["provider_request_id"] = _bounded_request_id(provider_request_id)
    metadata["clarification_questions"] = output.clarification_questions
    message.task_metadata = metadata
    mutation_payload = output.mutation_payload()
    if mutation_payload is not None:
        proposal = ProjectUpdateProposal(
            project_id=project_id,
            owner_id=owner_id,
            assistant_message_id=message.id,
            base_revision=message.snapshot_revision,
            schema_version=1,
            operations=mutation_payload,
            status="pending" if project.revision == message.snapshot_revision else "stale",
        )
        session.add(proposal)
    session.commit()


def fail_generation(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    message_id: UUID,
    code: str,
) -> None:
    message = _lock_assistant(session, owner_id, project_id, message_id)
    if message.status != "generating":
        return
    message.status = "failed"
    message.error_code = code if code in SAFE_GENERATION_ERRORS else "generation_failed"
    message.input_snapshot = None
    message.completed_at = datetime.now(UTC)
    session.commit()


def interrupt_generation(session: Session, message_id: UUID) -> None:
    message = session.get(ConversationMessage, message_id)
    if message is None or message.status != "generating":
        return
    message.status = "interrupted"
    message.error_code = "generation_interrupted"
    message.input_snapshot = None
    message.completed_at = datetime.now(UTC)
    session.commit()


def interrupt_all_unfinished(session: Session) -> int:
    rows = list(
        session.scalars(
            select(ConversationMessage).where(
                ConversationMessage.role == "assistant",
                ConversationMessage.status == "generating",
            )
        ).all()
    )
    for row in rows:
        row.status = "interrupted"
        row.error_code = "generation_interrupted"
        row.input_snapshot = None
        row.completed_at = datetime.now(UTC)
    if rows:
        session.commit()
    return len(rows)


def load_generation_input(
    session: Session, owner_id: UUID, project_id: UUID, message_id: UUID
) -> tuple[dict | None, str | None]:
    message = _lock_assistant(session, owner_id, project_id, message_id)
    return message.input_snapshot, message.task_metadata.get(
        "task"
    ) if message.task_metadata else None
