from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.conversations.models import ProjectUpdateProposal
from shopping.conversations.schemas import ProposalMutationResult
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.errors import ProjectError
from shopping.projects.schemas import ProjectRead

from .serializers import _proposal_read
from .shared import _not_found


def apply_proposal(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    proposal_id: UUID,
    expected_version: int,
) -> ProposalMutationResult:
    proposal = session.scalar(
        select(ProjectUpdateProposal)
        .where(
            ProjectUpdateProposal.id == proposal_id,
            ProjectUpdateProposal.owner_id == owner_id,
            ProjectUpdateProposal.project_id == project_id,
        )
        .with_for_update()
    )
    if proposal is None:
        raise _not_found("Proposal not found")
    if proposal.status == "applied":
        saved_project = ProjectRead.model_validate(proposal.applied_project)
        return ProposalMutationResult(
            proposal=_proposal_read(proposal), project=saved_project, replayed=True
        )
    if proposal.status == "dismissed":
        raise ProjectError(409, "proposal_dismissed", "This proposal was dismissed.")
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    if project.revision != proposal.base_revision:
        proposal.status = "stale"
        session.commit()
        raise ProjectError(
            409,
            "proposal_stale",
            (
                "The project changed after this suggestion was prepared. Review it and ask for a "
                "fresh suggestion."
            ),
            {"current_version": project.revision},
        )
    if project.revision != expected_version:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded. Refresh before applying the suggestion.",
            {"current_version": project.revision},
        )

    operations = proposal.operations
    try:
        updated = project_service.apply_ai_proposal(
            session,
            owner_id,
            project_id,
            expected_version,
            operations["project_updates"],
            operations["requirement_operations"],
            commit=False,
        )
    except (KeyError, TypeError, ValueError) as error:
        session.rollback()
        raise ProjectError(409, "proposal_invalid", "This proposal is no longer valid.") from error
    proposal.status = "applied"
    proposal.applied_revision = updated.revision
    proposal.applied_project = updated.model_dump(mode="json")
    session.commit()
    return ProposalMutationResult(
        proposal=_proposal_read(proposal), project=updated, replayed=False
    )


def dismiss_proposal(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    proposal_id: UUID,
) -> ProposalMutationResult:
    proposal = session.scalar(
        select(ProjectUpdateProposal)
        .where(
            ProjectUpdateProposal.id == proposal_id,
            ProjectUpdateProposal.owner_id == owner_id,
            ProjectUpdateProposal.project_id == project_id,
        )
        .with_for_update()
    )
    if proposal is None:
        raise _not_found("Proposal not found")
    if proposal.status == "applied":
        raise ProjectError(409, "proposal_applied", "An applied proposal cannot be dismissed.")
    replayed = proposal.status == "dismissed"
    if not replayed:
        proposal.status = "dismissed"
        session.commit()
    else:
        session.rollback()
    return ProposalMutationResult(
        proposal=_proposal_read(proposal), project=None, replayed=replayed
    )
