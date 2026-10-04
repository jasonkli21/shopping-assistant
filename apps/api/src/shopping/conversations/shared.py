from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.conversations.models import ConversationMessage
from shopping.projects import repository
from shopping.projects.errors import ProjectError
from shopping.projects.models import ShoppingProject


def _require_project(session: Session, owner_id: UUID, project_id: UUID) -> ShoppingProject:
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    return project


def _lock_assistant(
    session: Session, owner_id: UUID, project_id: UUID, message_id: UUID
) -> ConversationMessage:
    message = session.scalar(
        select(ConversationMessage)
        .where(
            ConversationMessage.id == message_id,
            ConversationMessage.owner_id == owner_id,
            ConversationMessage.project_id == project_id,
            ConversationMessage.role == "assistant",
        )
        .with_for_update()
    )
    if message is None:
        raise _not_found("Assistant message not found")
    return message


def _bounded_request_id(value: str | None) -> str | None:
    if not value:
        return None
    return value[:100]


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


SAFE_GENERATION_ERRORS = {
    "provider_unavailable",
    "provider_timeout",
    "provider_refused",
    "invalid_output",
    "generation_failed",
    "generation_interrupted",
    "project_unavailable",
    "context_too_large",
}
