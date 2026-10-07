from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from shopping.accounts.lifecycle import lock_active_owner_lifecycle
from shopping.conversations.models import ConversationMessage, ProjectUpdateProposal
from shopping.conversations.schemas import InterpretationOutput
from shopping.projects import repository

from .shared import SAFE_GENERATION_ERRORS, _bounded_request_id, _lock_assistant

GENERATION_LEASE_SECONDS = 30
LEGACY_GENERATION_GRACE_SECONDS = 180


@dataclass(frozen=True)
class GenerationRecoveryClaim:
    owner_id: UUID
    project_id: UUID
    message_id: UUID
    token: UUID


def complete_generation(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    message_id: UUID,
    lease_token: UUID,
    output: InterpretationOutput,
    provider_request_id: str | None,
    now: datetime | None = None,
) -> bool:
    if not lock_active_owner_lifecycle(session, owner_id):
        return False
    message = _lock_assistant(session, owner_id, project_id, message_id)
    if not _matches_lease(message, lease_token):
        return False
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    now = _now(session, now)
    if not _owns_live_lease(message, lease_token, now):
        return False
    if project is None:
        _finish(message, "failed", "project_unavailable", now)
        session.commit()
        return True
    message.content = output.assistant_message
    message.status = "completed"
    message.sequence += 1 if output.assistant_message else 0
    message.input_snapshot = None
    message.completed_at = now
    message.error_code = None
    _clear_lease(message)
    metadata = dict(message.task_metadata or {})
    metadata["provider_request_id"] = _bounded_request_id(provider_request_id)
    metadata["clarification_questions"] = output.clarification_questions
    metadata["citation_ids"] = [str(item) for item in output.citation_ids]
    message.task_metadata = metadata
    mutation_payload = output.mutation_payload()
    if mutation_payload is not None:
        proposal = ProjectUpdateProposal(
            project_id=project_id,
            owner_id=owner_id,
            assistant_message_id=message.id,
            base_revision=message.snapshot_revision,
            schema_version=2,
            operations=mutation_payload,
            status="pending" if project.revision == message.snapshot_revision else "stale",
        )
        session.add(proposal)
    session.commit()
    return True


def fail_generation(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    message_id: UUID,
    lease_token: UUID,
    code: str,
    *,
    now: datetime | None = None,
) -> bool:
    if not lock_active_owner_lifecycle(session, owner_id):
        return False
    message = _lock_assistant(session, owner_id, project_id, message_id)
    now = _now(session, now)
    if not _owns_live_lease(message, lease_token, now):
        return False
    safe_code = code if code in SAFE_GENERATION_ERRORS else "generation_failed"
    _finish(message, "failed", safe_code, now)
    session.commit()
    return True


def interrupt_generation(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    message_id: UUID,
    lease_token: UUID,
    *,
    now: datetime | None = None,
) -> bool:
    if not lock_active_owner_lifecycle(session, owner_id):
        return False
    message = _lock_assistant(session, owner_id, project_id, message_id)
    now = _now(session, now)
    if not _owns_live_lease(message, lease_token, now):
        return False
    _finish(message, "interrupted", "generation_interrupted", now)
    session.commit()
    return True


def claim_expired_generations(
    session: Session,
    *,
    worker_id: str,
    now: datetime | None = None,
    lease_seconds: int = GENERATION_LEASE_SECONDS,
    limit: int = 100,
) -> list[GenerationRecoveryClaim]:
    """Fence expired work for recovery; callers must interrupt, never rerun, it."""
    candidate_now = _now(session, now)
    worker_id = worker_id.strip()[:100]
    if not worker_id:
        raise ValueError("worker_id must not be blank")
    expired = or_(
        and_(
            ConversationMessage.generation_lease_token.is_not(None),
            ConversationMessage.generation_lease_expires_at <= candidate_now,
        ),
        and_(
            ConversationMessage.generation_owner.is_(None),
            ConversationMessage.generation_lease_token.is_(None),
            ConversationMessage.generation_lease_expires_at.is_(None),
            ConversationMessage.generation_heartbeat_at.is_(None),
            ConversationMessage.created_at
            <= candidate_now - timedelta(seconds=LEGACY_GENERATION_GRACE_SECONDS),
        ),
    )
    candidate_owners = list(
        session.scalars(
            select(ConversationMessage.owner_id)
            .where(
                ConversationMessage.role == "assistant",
                ConversationMessage.status == "generating",
                expired,
            )
            .distinct()
            .order_by(ConversationMessage.owner_id)
            .limit(limit)
        ).all()
    )
    active_owners = [
        owner_id for owner_id in candidate_owners if lock_active_owner_lifecycle(session, owner_id)
    ]
    if not active_owners:
        return []

    rows = list(
        session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.owner_id.in_(active_owners),
                ConversationMessage.role == "assistant",
                ConversationMessage.status == "generating",
                expired,
            )
            .order_by(
                ConversationMessage.generation_lease_expires_at,
                ConversationMessage.created_at,
                ConversationMessage.id,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
    )
    # Use the database wall clock after locks have been acquired. A wait on a
    # competing heartbeat must not let this recovery claim use a stale timestamp.
    now = _now(session, now)
    claims: list[GenerationRecoveryClaim] = []
    for message in rows:
        # Recheck after obtaining the row lock in case the candidate changed.
        has_expired_lease = (
            message.generation_lease_token is not None
            and message.generation_lease_expires_at is not None
            and _utc(message.generation_lease_expires_at) <= now
        )
        is_stale_legacy = (
            message.generation_owner is None
            and message.generation_lease_token is None
            and message.generation_lease_expires_at is None
            and message.generation_heartbeat_at is None
            and _utc(message.created_at) <= now - timedelta(seconds=LEGACY_GENERATION_GRACE_SECONDS)
        )
        if not has_expired_lease and not is_stale_legacy:
            continue
        token = uuid4()
        message.generation_owner = worker_id
        message.generation_lease_token = token
        message.generation_lease_expires_at = now + timedelta(seconds=lease_seconds)
        message.generation_heartbeat_at = now
        claims.append(
            GenerationRecoveryClaim(
                owner_id=message.owner_id,
                project_id=message.project_id,
                message_id=message.id,
                token=token,
            )
        )
    if claims:
        session.commit()
    return claims


def heartbeat_generation(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    message_id: UUID,
    lease_token: UUID,
    now: datetime | None = None,
    lease_seconds: int = GENERATION_LEASE_SECONDS,
) -> bool:
    if not lock_active_owner_lifecycle(session, owner_id):
        return False
    message = _lock_assistant(session, owner_id, project_id, message_id)
    now = _now(session, now)
    if not _owns_live_lease(message, lease_token, now):
        return False
    message.generation_heartbeat_at = now
    message.generation_lease_expires_at = now + timedelta(seconds=lease_seconds)
    session.commit()
    return True


def load_generation_input(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    message_id: UUID,
    lease_token: UUID,
    *,
    now: datetime | None = None,
) -> tuple[dict | None, str | None]:
    if not lock_active_owner_lifecycle(session, owner_id):
        return None, None
    message = _lock_assistant(session, owner_id, project_id, message_id)
    now = _now(session, now)
    if not _owns_live_lease(message, lease_token, now):
        return None, None
    return message.input_snapshot, message.task_metadata.get(
        "task"
    ) if message.task_metadata else None


def _owns_live_lease(message: ConversationMessage, token: UUID, now: datetime) -> bool:
    if not _matches_lease(message, token):
        return False
    expires_at = message.generation_lease_expires_at
    return expires_at is not None and _utc(expires_at) > now


def _matches_lease(message: ConversationMessage, token: UUID) -> bool:
    return (
        message.status == "generating"
        and message.generation_lease_token == token
        and message.generation_lease_expires_at is not None
    )


def _finish(message: ConversationMessage, status: str, code: str | None, now: datetime) -> None:
    message.status = status
    message.error_code = code
    message.input_snapshot = None
    message.completed_at = now
    _clear_lease(message)


def _clear_lease(message: ConversationMessage) -> None:
    message.generation_owner = None
    message.generation_lease_token = None
    message.generation_lease_expires_at = None
    message.generation_heartbeat_at = None


def _now(session: Session, value: datetime | None) -> datetime:
    return _utc(value or session.scalar(select(func.clock_timestamp())) or datetime.now(UTC))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
