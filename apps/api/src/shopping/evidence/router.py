from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shopping.evidence import reads
from shopping.evidence.schemas import (
    ClaimDetailRead,
    ProductSourcesRead,
    ProjectProductResearchRead,
    SourceSnapshotRead,
)
from shopping.projects.dependencies import get_owner_id

router = APIRouter(tags=["evidence"])
OwnerDependency = Annotated[UUID, Depends(get_owner_id)]


async def _with_session(request: Request, operation: Callable[[Session], object]):
    factory = request.app.state.research_session_factory

    def call():
        with factory() as session:
            return operation(session)

    return await asyncio.to_thread(call)


@router.get(
    "/projects/{project_id}/products/{project_product_id}/research",
    response_model=ProjectProductResearchRead,
)
async def product_research(
    project_id: UUID,
    project_product_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
) -> ProjectProductResearchRead:
    return await _with_session(
        request,
        lambda session: reads.project_product_research(
            session, owner_id, project_id, project_product_id
        ),
    )


@router.get("/projects/{project_id}/claims/{claim_id}", response_model=ClaimDetailRead)
async def claim_detail(
    project_id: UUID,
    claim_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
) -> ClaimDetailRead:
    return await _with_session(
        request,
        lambda session: reads.claim_detail(session, owner_id, project_id, claim_id),
    )


@router.get("/projects/{project_id}/sources/{snapshot_id}", response_model=SourceSnapshotRead)
async def source_snapshot(
    project_id: UUID,
    snapshot_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
) -> SourceSnapshotRead:
    return await _with_session(
        request,
        lambda session: reads.source_snapshot_detail(session, owner_id, project_id, snapshot_id),
    )


@router.get("/products/{product_id}/sources", response_model=ProductSourcesRead)
async def product_sources(
    product_id: UUID,
    request: Request,
    owner_id: OwnerDependency,
    variant_id: UUID | None = None,
) -> ProductSourcesRead:
    return await _with_session(
        request,
        lambda session: reads.product_sources(session, owner_id, product_id, variant_id),
    )
