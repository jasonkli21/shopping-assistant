from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from shopping.config import get_settings
from shopping.projects.dependencies import get_owner_id
from shopping.research import service
from shopping.research.schemas import (
    CancelResult,
    CandidatePage,
    ResearchCreate,
    ResearchCreated,
    ResearchRunPage,
    ResearchRunRead,
)
from shopping.research.supervisor import DiscoverySupervisor

router = APIRouter(prefix="/projects/{project_id}", tags=["research"])
OwnerDependency = Annotated[UUID, Depends(get_owner_id)]


async def _with_session(request: Request, operation: Callable[[Session], object]):
    factory = request.app.state.research_session_factory

    def call():
        with factory() as session:
            return operation(session)

    worker = asyncio.create_task(asyncio.to_thread(call))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        try:
            await worker
        except Exception:
            pass
        raise


def _supervisor(request: Request) -> DiscoverySupervisor:
    supervisor = getattr(request.app.state, "discovery_supervisor", None)
    if supervisor is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "research_unavailable",
                "message": "The local discovery supervisor is not available.",
            },
        )
    return supervisor


@router.post("/research", response_model=ResearchCreated, status_code=202)
async def create_research(
    project_id: UUID,
    command: ResearchCreate,
    request: Request,
    owner_id: OwnerDependency,
) -> ResearchCreated:
    supervisor = _supervisor(request)
    replay = await _with_session(
        request,
        lambda session: service.exact_replay(session, owner_id, project_id, command),
    )
    if replay is not None:
        if (
            replay.status == "queued"
            and not supervisor.has_task(replay.id)
            and supervisor.reserve_slot()
        ):
            supervisor.submit(owner_id, project_id, replay.id)
        return ResearchCreated(run_id=replay.id, status=replay.status, replayed=True)

    if not supervisor.reserve_slot():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "research_capacity",
                "message": "Discovery is at capacity. Retry when another run finishes.",
            },
        )
    try:
        run, created = await _with_session(
            request,
            lambda session: service.create_run(
                session,
                owner_id=owner_id,
                project_id=project_id,
                command=command,
                settings=get_settings(),
                ai_provider_name=supervisor.ai_provider_name,
                search_provider_name=supervisor.provider_name,
            ),
        )
    except Exception:
        supervisor.release_slot()
        raise

    if created:
        supervisor.submit(owner_id, project_id, run.id)
    else:
        supervisor.release_slot()
        if run.status == "queued" and not supervisor.has_task(run.id) and supervisor.reserve_slot():
            supervisor.submit(owner_id, project_id, run.id)
    return ResearchCreated(run_id=run.id, status=run.status, replayed=not created)


@router.get("/research", response_model=ResearchRunPage)
async def list_research(
    project_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResearchRunPage:
    return await _with_session(
        request, lambda session: service.list_runs(session, owner_id, project_id, limit)
    )


@router.get("/research/{research_run_id}", response_model=ResearchRunRead)
async def get_research(
    project_id: UUID,
    research_run_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
) -> ResearchRunRead:
    return await _with_session(
        request,
        lambda session: service.get_run(session, owner_id, project_id, research_run_id),
    )


@router.post("/research/{research_run_id}/cancel", response_model=CancelResult)
async def cancel_research(
    project_id: UUID,
    research_run_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
) -> CancelResult:
    supervisor = _supervisor(request)
    run, changed = await _with_session(
        request,
        lambda session: service.cancel_run(session, owner_id, project_id, research_run_id),
    )
    if changed:
        await supervisor.cancel(research_run_id)
        run = await _with_session(
            request,
            lambda session: service.get_run(session, owner_id, project_id, research_run_id),
        )
    return CancelResult(run=run, replayed=not changed)


@router.get("/candidates", response_model=CandidatePage)
async def list_candidates(
    project_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> CandidatePage:
    return await _with_session(
        request,
        lambda session: service.list_candidates(
            session, owner_id, project_id, limit=limit, cursor=cursor
        ),
    )
