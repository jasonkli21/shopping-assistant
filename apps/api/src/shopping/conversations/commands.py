from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.conversations.generation import GENERATION_LEASE_SECONDS
from shopping.conversations.models import Conversation, ConversationMessage
from shopping.conversations.schemas import MessageCreated
from shopping.conversations.task import (
    PROMPT_VERSION as INTENT_PROMPT_VERSION,
)
from shopping.conversations.task import (
    SCHEMA_VERSION as INTENT_SCHEMA_VERSION,
)
from shopping.conversations.task import (
    TASK_NAME as INTENT_TASK_NAME,
)
from shopping.conversations.task import (
    build_request,
)
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.context import read_project_context
from shopping.projects.errors import ProjectError


@dataclass(frozen=True)
class MessageCommandResult:
    response: MessageCreated
    should_start: bool
    lease_token: UUID | None = None


def create_message_command(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    text: str,
    request_key: str,
    expected_version: int,
    selected_project_product_ids: list[UUID] | None = None,
    comparison_id: UUID | None = None,
    slot_reserver: Callable[[], bool] | None = None,
    worker_id: str | None = None,
) -> MessageCommandResult:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")

    request_payload = {"text": text, "expected_version": expected_version}
    if selected_project_product_ids or comparison_id:
        request_payload["selected_project_product_ids"] = [
            str(item) for item in selected_project_product_ids or []
        ]
        request_payload["comparison_id"] = str(comparison_id) if comparison_id else None
    request_hash = hashlib.sha256(
        json.dumps(
            request_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    previous = session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.owner_id == owner_id,
            ConversationMessage.project_id == project_id,
            ConversationMessage.role == "user",
            ConversationMessage.request_key == request_key,
        )
    )
    if previous is not None:
        if previous.request_hash != request_hash:
            raise ProjectError(409, "idempotency_conflict", "This request key was already used.")
        assistant = session.get(ConversationMessage, previous.paired_message_id)
        conversation = session.get(Conversation, previous.conversation_id)
        if assistant is None or conversation is None:
            raise ProjectError(
                500, "conversation_incomplete", "The saved message could not be read."
            )
        return MessageCommandResult(
            MessageCreated(
                user_message_id=previous.id,
                assistant_message_id=assistant.id,
                conversation_id=conversation.id,
                replayed=True,
            ),
            should_start=False,
        )

    if project.revision != expected_version:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded. Review the latest version before sending.",
            {"current_version": project.revision},
        )

    conversation = session.scalar(
        select(Conversation)
        .where(
            Conversation.owner_id == owner_id,
            Conversation.project_id == project_id,
        )
        .with_for_update()
    )
    if conversation is None:
        conversation = Conversation(owner_id=owner_id, project_id=project_id)
        session.add(conversation)
        session.flush()

    active = session.scalar(
        select(ConversationMessage.id).where(
            ConversationMessage.conversation_id == conversation.id,
            ConversationMessage.role == "assistant",
            ConversationMessage.status == "generating",
        )
    )
    if active is not None:
        raise ProjectError(409, "conversation_busy", "A response is already being prepared.")

    project_read = project_service.get_project(session, owner_id, project_id)
    history = list(
        session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation.id,
                ConversationMessage.status == "completed",
            )
            .order_by(desc(ConversationMessage.ordinal))
            .limit(12)
        ).all()
    )
    history.reverse()
    try:
        task_request = build_request(
            project_read,
            text,
            [{"role": item.role, "text": item.content} for item in history],
            _current_state(
                session,
                owner_id,
                project_id,
                selected_project_product_ids=selected_project_product_ids or [],
                comparison_id=comparison_id,
            ),
        )
        input_snapshot = task_request.input["context"]
        context_error = None
    except ValueError:
        input_snapshot = None
        context_error = "context_too_large"

    slot_reserved = False
    if context_error is None and slot_reserver is not None:
        slot_reserved = slot_reserver()
        if not slot_reserved:
            raise ProjectError(
                503, "generation_capacity", "Assistant generation is busy. Try again shortly."
            )

    user_id = uuid4()
    assistant_id = uuid4()
    user_message = ConversationMessage(
        id=user_id,
        conversation_id=conversation.id,
        project_id=project_id,
        owner_id=owner_id,
        paired_message_id=None,
        ordinal=conversation.next_ordinal,
        role="user",
        content=text,
        status="completed",
        request_key=request_key,
        request_hash=request_hash,
    )
    lease_token = uuid4() if context_error is None else None
    generation_owner = (
        (worker_id or f"conversation-{uuid4()}").strip()[:100] if lease_token is not None else None
    )
    lease_now = (
        session.scalar(select(func.clock_timestamp())) or datetime.now(UTC)
        if lease_token is not None
        else None
    )
    assistant_message = ConversationMessage(
        id=assistant_id,
        conversation_id=conversation.id,
        project_id=project_id,
        owner_id=owner_id,
        paired_message_id=None,
        ordinal=conversation.next_ordinal + 1,
        role="assistant",
        content="",
        status="failed" if context_error else "generating",
        snapshot_revision=project.revision,
        task_metadata={
            "task": INTENT_TASK_NAME,
            "prompt_version": INTENT_PROMPT_VERSION,
            "schema_version": INTENT_SCHEMA_VERSION,
            "provider_request_id": None,
        },
        input_snapshot=input_snapshot,
        error_code=context_error,
        generation_owner=generation_owner,
        generation_lease_token=lease_token,
        generation_lease_expires_at=(
            lease_now + timedelta(seconds=GENERATION_LEASE_SECONDS) if lease_now else None
        ),
        generation_heartbeat_at=lease_now,
        completed_at=datetime.now(UTC) if context_error else None,
    )
    session.add(user_message)
    session.flush()
    assistant_message.paired_message_id = user_id
    session.add(assistant_message)
    session.flush()
    user_message.paired_message_id = assistant_id
    conversation.next_ordinal += 2
    conversation.updated_at = datetime.now(UTC)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ProjectError(
            409, "conversation_conflict", "The message could not be reserved."
        ) from error

    return MessageCommandResult(
        MessageCreated(
            user_message_id=user_id,
            assistant_message_id=assistant_id,
            conversation_id=conversation.id,
            replayed=False,
        ),
        should_start=context_error is None,
        lease_token=lease_token,
    )


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _current_state(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    selected_project_product_ids: list[UUID] | None = None,
    comparison_id: UUID | None = None,
    selected_context_only: bool = False,
    include_external_evidence: bool = False,
) -> dict:
    """Compatibility wrapper over the canonical project context projection."""
    return read_project_context(
        session,
        owner_id,
        project_id,
        selected_project_product_ids=selected_project_product_ids,
        comparison_id=comparison_id,
        selected_context_only=selected_context_only,
        include_external_evidence=include_external_evidence,
    )
