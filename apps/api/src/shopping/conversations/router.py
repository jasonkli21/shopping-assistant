from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from shopping.conversations import service
from shopping.conversations.schemas import (
    ConversationPage,
    MessageCreate,
    MessageCreated,
    MessagePage,
    ProposalCommand,
    ProposalMutationResult,
)
from shopping.db.session import get_db
from shopping.projects.dependencies import get_owner_id

router = APIRouter(prefix="/projects", tags=["conversations"])
SessionDependency = Annotated[Session, Depends(get_db)]
OwnerDependency = Annotated[UUID, Depends(get_owner_id)]


@router.get("/{project_id}/conversations", response_model=ConversationPage)
def list_conversations(
    project_id: UUID, session: SessionDependency, owner_id: OwnerDependency
) -> ConversationPage:
    return service.list_conversations(session, owner_id, project_id)


@router.get("/{project_id}/messages", response_model=MessagePage)
def list_messages(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[str | None, Query(max_length=64)] = None,
) -> MessagePage:
    return service.list_messages(session, owner_id, project_id, limit=limit, before=before)


@router.post(
    "/{project_id}/messages",
    response_model=MessageCreated,
    status_code=202,
    responses={409: {"description": "Revision, idempotency, or conversation conflict"}},
)
async def create_message(
    project_id: UUID,
    command: MessageCreate,
    request: Request,
    owner_id: OwnerDependency,
) -> MessageCreated:
    supervisor = request.app.state.generation_supervisor
    session_factory = request.app.state.conversation_session_factory
    reserved = False

    def reserve_slot() -> bool:
        nonlocal reserved
        reserved = supervisor.reserve_slot()
        return reserved

    def create_command():
        with session_factory() as session:
            return service.create_message_command(
                session,
                owner_id,
                project_id,
                text=command.text,
                request_key=command.request_key,
                expected_version=command.expected_version,
                selected_project_product_ids=command.selected_project_product_ids,
                comparison_id=command.comparison_id,
                slot_reserver=reserve_slot,
            )

    try:
        result = await run_in_threadpool(create_command)
        if result.should_start:
            supervisor.submit(owner_id, project_id, result.response.assistant_message_id)
        return result.response
    except Exception:
        if reserved:
            supervisor.release_slot()
        raise


@router.get("/{project_id}/messages/stream")
async def attach_message_stream(
    project_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
    message_id: Annotated[UUID, Query()],
) -> StreamingResponse:
    session_factory = request.app.state.conversation_session_factory
    initial = await run_in_threadpool(
        _read_message, session_factory, owner_id, project_id, message_id
    )

    async def events():
        current = initial
        last_text = current.text
        proposal_sent = False
        started = time.monotonic()
        heartbeat_at = started
        yield _event("snapshot", _snapshot_data(current))
        if current.proposal is not None:
            yield _event(
                "proposal",
                {
                    "message_id": str(message_id),
                    "proposal": current.proposal.model_dump(mode="json"),
                },
            )
            proposal_sent = True
        terminal = _terminal_event(current)
        if terminal is not None:
            yield terminal
            return

        while time.monotonic() - started < 120:
            await asyncio.sleep(0.2)
            if await request.is_disconnected():
                return
            current = await run_in_threadpool(
                _read_message, session_factory, owner_id, project_id, message_id
            )
            if current.text.startswith(last_text) and len(current.text) > len(last_text):
                delta = current.text[len(last_text) :]
                yield _event(
                    "delta",
                    {"message_id": str(message_id), "sequence": current.sequence, "delta": delta},
                )
                last_text = current.text
            elif current.text != last_text:
                # Output is append-only; a mismatch is treated as a safe terminal failure.
                yield _event(
                    "error",
                    {
                        "message_id": str(message_id),
                        "code": "stream_state_invalid",
                        "message": "The response changed unexpectedly. Reload history.",
                    },
                )
                return
            if current.proposal is not None and not proposal_sent:
                yield _event(
                    "proposal",
                    {
                        "message_id": str(message_id),
                        "proposal": current.proposal.model_dump(mode="json"),
                    },
                )
                proposal_sent = True
            terminal = _terminal_event(current)
            if terminal is not None:
                yield terminal
                return
            if time.monotonic() - heartbeat_at >= 15:
                yield ": heartbeat\n\n"
                heartbeat_at = time.monotonic()
        yield _event(
            "error",
            {
                "message_id": str(message_id),
                "code": "stream_wait_expired",
                "message": "The response is still being prepared. Reload to check its status.",
            },
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{project_id}/proposals/{proposal_id}/apply",
    response_model=ProposalMutationResult,
    responses={
        404: {"description": "Proposal not found"},
        409: {"description": "Proposal conflict"},
    },
)
def apply_proposal(
    project_id: UUID,
    proposal_id: UUID,
    command: ProposalCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ProposalMutationResult:
    return service.apply_proposal(
        session, owner_id, project_id, proposal_id, command.expected_version
    )


@router.post(
    "/{project_id}/proposals/{proposal_id}/dismiss",
    response_model=ProposalMutationResult,
)
def dismiss_proposal(
    project_id: UUID,
    proposal_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ProposalMutationResult:
    return service.dismiss_proposal(session, owner_id, project_id, proposal_id)


def _read_message(session_factory, owner_id: UUID, project_id: UUID, message_id: UUID):
    with session_factory() as session:
        return service.get_message_for_stream(session, owner_id, project_id, message_id)


def _snapshot_data(message) -> dict:
    return {
        "message": message.model_dump(mode="json"),
        "sequence": message.sequence,
        "text": message.text,
    }


def _terminal_event(message) -> str | None:
    if message.status == "completed":
        return _event("complete", {"message": message.model_dump(mode="json")})
    if message.status in {"failed", "interrupted"}:
        messages = {
            "provider_unavailable": "Assistant suggestions are unavailable until AI is configured.",
            "provider_timeout": "The assistant took too long to respond. You can try again.",
            "provider_refused": "The assistant could not process this. Rephrase it and try again.",
            "invalid_output": (
                "The assistant response could not be validated. No project changes were made."
            ),
            "context_too_large": (
                "Project context is too large to send safely. Remove old requirements or start a "
                "new conversation."
            ),
            "generation_interrupted": (
                "The response was interrupted by a local service restart. Send a new message to "
                "try again."
            ),
            "project_unavailable": "The project is no longer available.",
        }
        code = message.error_code or "generation_failed"
        return _event(
            "error",
            {
                "message_id": str(message.id),
                "code": code,
                "message": messages.get(
                    code, "The assistant could not complete this response. You can try again."
                ),
            },
        )
    return None


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
