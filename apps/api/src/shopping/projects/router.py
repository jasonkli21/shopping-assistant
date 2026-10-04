from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from shopping.db.session import get_db
from shopping.projects import service
from shopping.projects.dependencies import get_owner_id
from shopping.projects.schemas import (
    ApiErrorEnvelope,
    ProjectCreate,
    ProjectPage,
    ProjectPatch,
    ProjectRead,
    RequirementCreate,
    RequirementPatch,
    RequirementRead,
)

router = APIRouter(prefix="/projects", tags=["projects"])
SessionDependency = Annotated[Session, Depends(get_db)]
OwnerDependency = Annotated[UUID, Depends(get_owner_id)]
ERROR_RESPONSES = {
    404: {"model": ApiErrorEnvelope, "description": "Resource not found"},
    409: {"model": ApiErrorEnvelope, "description": "Project revision conflict"},
    422: {"model": ApiErrorEnvelope, "description": "Invalid request"},
}


@router.post("", response_model=ProjectRead, status_code=201, responses=ERROR_RESPONSES)
def create_project(
    command: ProjectCreate,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ProjectRead:
    return service.create_project(session, owner_id, command)


@router.get("", response_model=ProjectPage)
def list_projects(
    session: SessionDependency,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> ProjectPage:
    return service.list_projects(session, owner_id, limit=limit, cursor=cursor)


@router.get("/{project_id}", response_model=ProjectRead, responses=ERROR_RESPONSES)
def get_project(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ProjectRead:
    return service.get_project(session, owner_id, project_id)


@router.patch("/{project_id}", response_model=ProjectRead, responses=ERROR_RESPONSES)
def patch_project(
    project_id: UUID,
    command: ProjectPatch,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ProjectRead:
    return service.patch_project(session, owner_id, project_id, command)


@router.delete("/{project_id}", status_code=204, responses=ERROR_RESPONSES)
def delete_project(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    service.delete_project(session, owner_id, project_id, expected_version)
    return Response(status_code=204)


@router.get(
    "/{project_id}/requirements",
    response_model=list[RequirementRead],
    responses=ERROR_RESPONSES,
)
def list_requirements(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> list[RequirementRead]:
    return service.list_requirements(session, owner_id, project_id)


@router.post(
    "/{project_id}/requirements",
    response_model=ProjectRead,
    responses=ERROR_RESPONSES,
)
def create_requirement(
    project_id: UUID,
    command: RequirementCreate,
    session: SessionDependency,
    owner_id: OwnerDependency,
    expected_version: Annotated[int, Query(ge=1)],
) -> ProjectRead:
    return service.create_requirement(session, owner_id, project_id, expected_version, command)


@router.patch(
    "/{project_id}/requirements/{requirement_id}",
    response_model=ProjectRead,
    responses=ERROR_RESPONSES,
)
def patch_requirement(
    project_id: UUID,
    requirement_id: UUID,
    command: RequirementPatch,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ProjectRead:
    return service.patch_requirement(session, owner_id, project_id, requirement_id, command)


@router.delete(
    "/{project_id}/requirements/{requirement_id}",
    response_model=ProjectRead,
    responses=ERROR_RESPONSES,
)
def delete_requirement(
    project_id: UUID,
    requirement_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    expected_version: Annotated[int, Query(ge=1)],
) -> ProjectRead:
    return service.delete_requirement(
        session, owner_id, project_id, requirement_id, expected_version
    )
