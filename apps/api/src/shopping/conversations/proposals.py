from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct
from shopping.comparisons import service as comparison_service
from shopping.conversations.models import ProjectUpdateProposal
from shopping.conversations.schemas import ProposalMutationResult
from shopping.projects import decisions as decision_service
from shopping.projects import notes as note_service
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.decision_schemas import DecisionCommand
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
    # All proposal lifecycle paths lock the live project first, then the
    # proposal. This also makes deleted and foreign-owned project paths 404
    # before an applied replay can disclose a saved project snapshot.
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
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
        decision_operations = operations.get("decision_operations", [])
        for index, operation in enumerate(decision_operations):
            kind = operation.get("operation")
            if kind in {"shortlist", "reject"}:
                project_product_id = UUID(operation["project_product_id"])
                membership = session.scalar(
                    select(ProjectProduct)
                    .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
                    .join(Product, Product.id == ProductVariant.product_id)
                    .where(
                        ProjectProduct.id == project_product_id,
                        ProjectProduct.project_id == project.id,
                        Product.owner_id == owner_id,
                    )
                )
                if membership is None:
                    raise ProjectError(
                        409, "proposal_invalid", "A proposed product is no longer available."
                    )
                command_data = {
                    "expected_version": project.revision,
                    "request_key": f"assistant-{proposal.id}-{index}",
                    "reason": operation.get("reason", ""),
                    "concerns": operation.get("concerns", []),
                }
                if kind == "reject":
                    command_data["rejection_reason"] = operation.get("rejection_reason")
                command = DecisionCommand.model_validate(command_data)
                decision_service.apply_decision_locked(
                    session,
                    project,
                    owner_id,
                    membership,
                    "shortlisted" if kind == "shortlist" else "rejected",
                    command,
                    actor="assistant",
                    origin="proposal",
                )
            elif kind == "add_note":
                target = (
                    UUID(operation["project_product_id"])
                    if operation.get("project_product_id")
                    else None
                )
                text = operation.get("text")
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 10000:
                    raise ProjectError(409, "proposal_invalid", "A proposed note is invalid.")
                note_service.append_note_locked(session, project, owner_id, target, text.strip())
            elif kind == "set_comparison_dimensions":
                continue
            else:
                raise ProjectError(
                    409, "proposal_invalid", "The proposal contains an unsupported operation."
                )

        updated = project_service.apply_ai_proposal(
            session,
            owner_id,
            project_id,
            expected_version,
            operations["project_updates"],
            operations["requirement_operations"],
            commit=False,
        )
        for operation in decision_operations:
            if operation.get("operation") == "set_comparison_dimensions":
                comparison_service.apply_proposal_locked(session, owner_id, project, operation)
        proposal.status = "applied"
        proposal.applied_revision = updated.revision
        proposal.applied_project = updated.model_dump(mode="json")
        proposal.applied_at = datetime.now(UTC)
        session.commit()
    except Exception as error:
        session.rollback()
        if isinstance(error, (KeyError, TypeError, ValueError)):
            raise ProjectError(
                409, "proposal_invalid", "This proposal is no longer valid."
            ) from error
        raise
    return ProposalMutationResult(
        proposal=_proposal_read(proposal), project=updated, replayed=False
    )


def dismiss_proposal(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    proposal_id: UUID,
) -> ProposalMutationResult:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
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
