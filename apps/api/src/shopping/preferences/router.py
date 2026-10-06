from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shopping.db.session import get_db
from shopping.preferences import service
from shopping.preferences.schemas import (
    CandidateAction,
    CandidateCreate,
    CandidateMutation,
    PreferencePatch,
    PreferenceSuggestionsRead,
    ProfilePatch,
    ProfileRead,
)
from shopping.projects.dependencies import get_owner_id
from shopping.projects.schemas import ApiErrorEnvelope, ProjectRead

router = APIRouter(tags=["preferences"])
SessionDependency = Annotated[Session, Depends(get_db)]
OwnerDependency = Annotated[UUID, Depends(get_owner_id)]
ERROR_RESPONSES = {
    404: {"model": ApiErrorEnvelope, "description": "Resource not found"},
    409: {"model": ApiErrorEnvelope, "description": "Revision or lifecycle conflict"},
    422: {"model": ApiErrorEnvelope, "description": "Invalid request"},
}


@router.get("/profile", response_model=ProfileRead)
def get_profile(session: SessionDependency, owner_id: OwnerDependency) -> ProfileRead:
    return service.get_profile(session, owner_id)


@router.patch("/profile", response_model=ProfileRead, responses=ERROR_RESPONSES)
def patch_profile(
    command: ProfilePatch, session: SessionDependency, owner_id: OwnerDependency
) -> ProfileRead:
    return service.patch_profile(session, owner_id, command)


@router.post(
    "/profile/preference-candidates/{candidate_id}/accept",
    response_model=CandidateMutation,
    responses=ERROR_RESPONSES,
)
def accept_candidate(
    candidate_id: UUID,
    command: CandidateAction,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> CandidateMutation:
    return service.accept_candidate(session, owner_id, candidate_id, command)


@router.post(
    "/profile/preference-candidates/{candidate_id}/dismiss",
    response_model=CandidateMutation,
    responses=ERROR_RESPONSES,
)
def dismiss_candidate(
    candidate_id: UUID,
    command: CandidateAction,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> CandidateMutation:
    return service.dismiss_candidate(session, owner_id, candidate_id, command)


@router.patch(
    "/profile/preferences/{preference_id}",
    response_model=ProfileRead,
    responses=ERROR_RESPONSES,
)
def patch_preference(
    preference_id: UUID,
    command: PreferencePatch,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ProfileRead:
    return service.patch_preference(session, owner_id, preference_id, command)


@router.delete(
    "/profile/preferences/{preference_id}",
    response_model=ProfileRead,
    responses=ERROR_RESPONSES,
)
def revoke_preference(
    preference_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    expected_profile_version: Annotated[int, Query(ge=1)],
) -> ProfileRead:
    return service.revoke_preference(session, owner_id, preference_id, expected_profile_version)


@router.post(
    "/projects/{project_id}/preference-candidates",
    response_model=CandidateMutation,
    status_code=201,
    responses=ERROR_RESPONSES,
)
def create_candidate(
    project_id: UUID,
    command: CandidateCreate,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> CandidateMutation:
    return service.create_candidate(session, owner_id, project_id, command)


@router.get(
    "/projects/{project_id}/preference-suggestions",
    response_model=PreferenceSuggestionsRead,
    responses=ERROR_RESPONSES,
)
def preference_suggestions(
    project_id: UUID, session: SessionDependency, owner_id: OwnerDependency
) -> PreferenceSuggestionsRead:
    return service.preference_suggestions(session, owner_id, project_id)


@router.post(
    "/projects/{project_id}/preferences/{preference_id}/apply",
    response_model=ProjectRead,
    responses=ERROR_RESPONSES,
)
def apply_preference(
    project_id: UUID,
    preference_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    expected_project_version: Annotated[int, Query(ge=1)],
) -> ProjectRead:
    return service.apply_preference(
        session, owner_id, project_id, preference_id, expected_project_version
    )
