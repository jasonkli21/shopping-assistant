from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from shopping.comparisons import service
from shopping.comparisons.schemas import (
    ComparisonCreate,
    ComparisonPage,
    ComparisonPatch,
    ComparisonRead,
    ComparisonRegenerate,
)
from shopping.db.session import get_db
from shopping.projects.dependencies import get_owner_id

router = APIRouter(prefix="/projects", tags=["comparisons"])
SessionDependency = Annotated[Session, Depends(get_db)]
OwnerDependency = Annotated[UUID, Depends(get_owner_id)]


@router.post("/{project_id}/comparisons", response_model=ComparisonRead, status_code=201)
def create_comparison(
    project_id: UUID,
    command: ComparisonCreate,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ComparisonRead:
    return service.create_comparison(session, owner_id, project_id, command)


@router.get("/{project_id}/comparisons", response_model=ComparisonPage)
def list_comparisons(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> ComparisonPage:
    return service.list_comparisons(session, owner_id, project_id, limit=limit, cursor=cursor)


@router.get("/{project_id}/comparisons/{comparison_id}", response_model=ComparisonRead)
def get_comparison(
    project_id: UUID,
    comparison_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ComparisonRead:
    return service.get_comparison(session, owner_id, project_id, comparison_id)


@router.patch("/{project_id}/comparisons/{comparison_id}", response_model=ComparisonRead)
def patch_comparison(
    project_id: UUID,
    comparison_id: UUID,
    command: ComparisonPatch,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ComparisonRead:
    return service.update_comparison(session, owner_id, project_id, comparison_id, command)


@router.post(
    "/{project_id}/comparisons/{comparison_id}/regenerate",
    response_model=ComparisonRead,
)
def regenerate_comparison(
    project_id: UUID,
    comparison_id: UUID,
    command: ComparisonRegenerate,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ComparisonRead:
    return service.regenerate_comparison(session, owner_id, project_id, comparison_id, command)


@router.delete("/{project_id}/comparisons/{comparison_id}", status_code=204)
def delete_comparison(
    project_id: UUID,
    comparison_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    expected_version: Annotated[int, Query(ge=1)],
    expected_comparison_version: Annotated[int, Query(ge=1)],
) -> Response:
    service.delete_comparison(
        session,
        owner_id,
        project_id,
        comparison_id,
        expected_version=expected_version,
        expected_comparison_version=expected_comparison_version,
    )
    return Response(status_code=204)
