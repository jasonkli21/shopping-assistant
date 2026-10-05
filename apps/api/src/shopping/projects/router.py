from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from shopping.db.session import get_db
from shopping.projects import decisions, notes, service
from shopping.projects.decision_schemas import (
    DecisionCommand,
    DecisionMutationResult,
    DecisionPage,
    DecisionRead,
    NoteMutationResult,
    NoteRead,
    NoteWrite,
)
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


@router.get("/{project_id}/shortlist", response_model=DecisionPage, responses=ERROR_RESPONSES)
def list_shortlist(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> DecisionPage:
    return decisions.list_decisions(
        session, owner_id, project_id, state="shortlisted", limit=limit, cursor=cursor
    )


@router.get("/{project_id}/rejections", response_model=DecisionPage, responses=ERROR_RESPONSES)
def list_rejections(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> DecisionPage:
    return decisions.list_decisions(
        session, owner_id, project_id, state="rejected", limit=limit, cursor=cursor
    )


@router.get(
    "/{project_id}/products/{project_product_id}/decision",
    response_model=DecisionRead,
    responses=ERROR_RESPONSES,
)
def get_decision(
    project_id: UUID,
    project_product_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> DecisionRead:
    return decisions.get_decision(session, owner_id, project_id, project_product_id)


@router.post(
    "/{project_id}/shortlist/{project_product_id}",
    response_model=DecisionMutationResult,
    responses=ERROR_RESPONSES,
)
def shortlist_product(
    project_id: UUID,
    project_product_id: UUID,
    command: DecisionCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> DecisionMutationResult:
    return decisions.set_decision(
        session, owner_id, project_id, project_product_id, "shortlisted", command
    )


@router.delete(
    "/{project_id}/shortlist/{project_product_id}",
    response_model=DecisionMutationResult,
    responses=ERROR_RESPONSES,
)
def undo_shortlist(
    project_id: UUID,
    project_product_id: UUID,
    command: DecisionCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> DecisionMutationResult:
    return decisions.set_decision(
        session, owner_id, project_id, project_product_id, "considering", command
    )


@router.post(
    "/{project_id}/rejections/{project_product_id}",
    response_model=DecisionMutationResult,
    responses=ERROR_RESPONSES,
)
def reject_product(
    project_id: UUID,
    project_product_id: UUID,
    command: DecisionCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> DecisionMutationResult:
    return decisions.set_decision(
        session, owner_id, project_id, project_product_id, "rejected", command
    )


@router.delete(
    "/{project_id}/rejections/{project_product_id}",
    response_model=DecisionMutationResult,
    responses=ERROR_RESPONSES,
)
def undo_rejection(
    project_id: UUID,
    project_product_id: UUID,
    command: DecisionCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> DecisionMutationResult:
    return decisions.set_decision(
        session, owner_id, project_id, project_product_id, "considering", command
    )


@router.post(
    "/{project_id}/products/{project_product_id}/purchased",
    response_model=DecisionMutationResult,
    responses=ERROR_RESPONSES,
)
def mark_product_purchased(
    project_id: UUID,
    project_product_id: UUID,
    command: DecisionCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> DecisionMutationResult:
    return decisions.set_decision(
        session, owner_id, project_id, project_product_id, "purchased", command
    )


@router.delete(
    "/{project_id}/products/{project_product_id}/purchased",
    response_model=DecisionMutationResult,
    responses=ERROR_RESPONSES,
)
def undo_product_purchased(
    project_id: UUID,
    project_product_id: UUID,
    command: DecisionCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> DecisionMutationResult:
    return decisions.set_decision(
        session, owner_id, project_id, project_product_id, "considering", command
    )


@router.get("/{project_id}/notes", response_model=NoteRead | None, responses=ERROR_RESPONSES)
def get_project_note(
    project_id: UUID, session: SessionDependency, owner_id: OwnerDependency
) -> NoteRead | None:
    return notes.get_note(session, owner_id, project_id)


@router.put("/{project_id}/notes", response_model=NoteMutationResult, responses=ERROR_RESPONSES)
def put_project_note(
    project_id: UUID,
    command: NoteWrite,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> NoteMutationResult:
    note, version = notes.put_note(session, owner_id, project_id, None, command)
    return NoteMutationResult(note=note, project_version=version)


@router.delete("/{project_id}/notes", status_code=204, responses=ERROR_RESPONSES)
def delete_project_note(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    notes.delete_note(session, owner_id, project_id, None, expected_version)
    return Response(status_code=204)


@router.get(
    "/{project_id}/products/{project_product_id}/notes",
    response_model=NoteRead | None,
    responses=ERROR_RESPONSES,
)
def get_product_note(
    project_id: UUID,
    project_product_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> NoteRead | None:
    return notes.get_note(session, owner_id, project_id, project_product_id)


@router.put(
    "/{project_id}/products/{project_product_id}/notes",
    response_model=NoteMutationResult,
    responses=ERROR_RESPONSES,
)
def put_product_note(
    project_id: UUID,
    project_product_id: UUID,
    command: NoteWrite,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> NoteMutationResult:
    note, version = notes.put_note(session, owner_id, project_id, project_product_id, command)
    return NoteMutationResult(note=note, project_version=version)


@router.delete(
    "/{project_id}/products/{project_product_id}/notes",
    status_code=204,
    responses=ERROR_RESPONSES,
)
def delete_product_note(
    project_id: UUID,
    project_product_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    notes.delete_note(session, owner_id, project_id, project_product_id, expected_version)
    return Response(status_code=204)
