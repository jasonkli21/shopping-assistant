"""Bounded private typed-task host; domain services own transactions and effects."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from shopping.accounts.models import OwnerPrivacyLifecycle
from shopping.config import Settings, get_settings
from shopping.db.session import SessionLocal
from shopping.integrations.personal_ai.auth import _bearer_token, _verify_token
from shopping.integrations.personal_ai.task_auth import (
    PersonalAITaskAuthority,
    TaskAuthorityUnavailable,
    task_owner,
)
from shopping.integrations.personal_ai.task_wire import (
    DelegatedTargetRequest,
    DelegatedTaskRequest,
    task_manifest,
)
from shopping.integrations.personal_ai.tasks import (
    NOTE_OPERATION_DESCRIPTOR,
    NOTE_OPERATION_FINGERPRINT,
    OPERATION_DESCRIPTOR,
    OPERATION_FINGERPRINT,
    BudgetTaskResult,
    process_budget_task,
)
from shopping.projects import repository
from shopping.projects.models import DelegatedTaskReceipt

router = APIRouter(prefix="/v1/integrations/personal-ai/tasks", tags=["personal-ai-tasks"])
MAX_TASK_BYTES = 24576


def _enabled(settings: Settings) -> None:
    if not settings.personal_ai_tasks_enabled:
        raise HTTPException(404, "not_found")


async def _body(request: Request) -> dict:
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise HTTPException(415, "task_content_type_invalid")
    raw = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > MAX_TASK_BYTES:
                    raise HTTPException(413, "task_request_too_large")
    except TimeoutError as error:
        raise HTTPException(408, "task_request_timeout") from error

    try:
        body = json.loads(raw)
    except (ValueError, TypeError, RecursionError) as error:
        raise HTTPException(422, "task_contract_invalid") from error
    if not isinstance(body, dict):
        raise HTTPException(422, "task_contract_invalid")
    return body


def _factory(request: Request):
    return getattr(request.app.state, "task_session_factory", SessionLocal)


def get_task_service(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    """Metadata is service-only; it discloses no owner or domain records."""
    _enabled(settings)
    claims = _verify_token(
        _bearer_token(request.headers.get("authorization")),
        audience=settings.personal_ai_context_service_audience,
        identity_unavailable="service_identity_unavailable",
    )
    if claims.get("email") != settings.personal_ai_context_service_account:
        raise HTTPException(403, "service_identity_denied")


@dataclass(frozen=True)
class VerifiedTaskInput:
    owner_id: UUID
    delegation: str
    body: dict


async def get_task_identity(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> VerifiedTaskInput:
    _enabled(settings)
    body = await _body(request)

    def verify():
        with _factory(request)() as session:
            owner, assertion = task_owner(request, body, session, settings)
            return VerifiedTaskInput(owner, assertion, body)

    return await run_in_threadpool(verify)


@router.get("/contracts", dependencies=[Depends(get_task_service)])
def contracts():
    return {
        **task_manifest(),
        "application_id": "shopping",
        "operations": [
            {**OPERATION_DESCRIPTOR, "contract_fingerprint": OPERATION_FINGERPRINT},
            {**NOTE_OPERATION_DESCRIPTOR, "contract_fingerprint": NOTE_OPERATION_FINGERPRINT},
        ],
        "retained_operation_contracts": [OPERATION_FINGERPRINT, NOTE_OPERATION_FINGERPRINT],
    }


@router.post("/target-authority")
async def target_authority(
    request: Request, identity: Annotated[VerifiedTaskInput, Depends(get_task_identity)]
):
    body = identity.body
    try:
        target = DelegatedTargetRequest.model_validate(body)
        target_id = UUID(target.target_entity_id)
        if (
            target.destination_application_id != "shopping"
            or target.workspace_id is not None
            or target.target_entity_type != "project"
        ):
            raise ValueError
    except ValueError as error:
        raise HTTPException(409, "task_contract_unsupported") from error

    def read():
        with _factory(request)() as session:
            owner = identity.owner_id
            state = session.scalar(
                select(OwnerPrivacyLifecycle.state).where(OwnerPrivacyLifecycle.owner_id == owner)
            )
            if state not in {None, "active"}:
                return {"allowed": False}
            project = repository.project_by_owner(session, target_id, owner)
            if project is not None:
                return {"allowed": True}
            if target.permission_action in {"read", "reconcile"}:
                receipt = session.scalar(
                    select(DelegatedTaskReceipt.execution_key)
                    .where(
                        DelegatedTaskReceipt.owner_id == owner,
                        DelegatedTaskReceipt.target_entity_id == target_id,
                    )
                    .limit(1)
                )
                return {"allowed": receipt is not None}
            return {"allowed": False}

    return await run_in_threadpool(read)


@router.post("", response_model=BudgetTaskResult)
async def dispatch_task(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    identity: Annotated[VerifiedTaskInput, Depends(get_task_identity)],
):
    body = identity.body
    try:
        task = DelegatedTaskRequest.model_validate(body)
    except ValueError as error:
        raise HTTPException(422, "task_contract_invalid") from error

    def execute():
        with _factory(request)() as session, session.begin():
            owner, user_delegation = identity.owner_id, identity.delegation
            authority = getattr(
                request.app.state, "task_authority_factory", PersonalAITaskAuthority
            )(settings, user_delegation)
            return process_budget_task(session, owner, task, authority)

    try:
        return await run_in_threadpool(execute)
    except TaskAuthorityUnavailable as error:
        raise HTTPException(503, "task_authority_unavailable") from error
    except PermissionError as error:
        raise HTTPException(403, "task_authority_denied") from error
    except ValueError as error:
        code = str(error)
        if code not in {
            "task_contract_unsupported",
            "task_payload_not_canonical",
            "task_domain_version_invalid",
            "task_idempotency_conflict",
        }:
            code = "task_contract_invalid"
        raise HTTPException(
            409 if code in {"task_contract_unsupported", "task_idempotency_conflict"} else 422, code
        ) from error
