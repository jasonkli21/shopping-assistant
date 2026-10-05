from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct, RetailOffer
from shopping.catalog.reads import _project_product_read
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.decision_schemas import (
    DecisionCommand,
    DecisionEventRead,
    DecisionMutationResult,
    DecisionPage,
    DecisionRead,
    ProjectProductDecisionRead,
)
from shopping.projects.errors import ProjectError
from shopping.projects.models import DecisionEvent, ProjectProductDecision, ShoppingProject


def list_decisions(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    state: str,
    limit: int = 50,
    cursor: str | None = None,
) -> DecisionPage:
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    before = _decode_cursor(cursor) if cursor else None
    statement = (
        select(ProjectProduct, ProductVariant, Product, ProjectProductDecision)
        .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(
            ProjectProductDecision, ProjectProductDecision.project_product_id == ProjectProduct.id
        )
        .where(ProjectProduct.project_id == project_id, Product.owner_id == owner_id)
    )
    if state == "shortlisted":
        statement = statement.where(ProjectProductDecision.state == "shortlisted")
    elif state == "rejected":
        statement = statement.where(ProjectProductDecision.state == "rejected")
    elif state == "considering":
        statement = statement.where(
            or_(ProjectProductDecision.id.is_(None), ProjectProductDecision.state == "considering")
        )
    if before:
        before_time, before_id = before
        statement = statement.where(
            or_(
                ProjectProduct.created_at > before_time,
                and_(ProjectProduct.created_at == before_time, ProjectProduct.id > before_id),
            )
        )
    rows = session.execute(
        statement.order_by(ProjectProduct.created_at, ProjectProduct.id).limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1][0].created_at, page[-1][0].id) if has_more else None
    return DecisionPage(
        items=[
            ProjectProductDecisionRead(
                product=_project_product_read(session, owner_id, row[0], row[1], row[2]),
                decision=_decision_read(session, row[0].id, row[3]),
            )
            for row in page
        ],
        project_version=project.revision,
        next_cursor=next_cursor,
    )


def get_decision(
    session: Session, owner_id: UUID, project_id: UUID, project_product_id: UUID
) -> DecisionRead:
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    membership = _membership(session, owner_id, project_id, project_product_id)
    row = session.scalar(
        select(ProjectProductDecision).where(
            ProjectProductDecision.project_product_id == membership.id,
            ProjectProductDecision.owner_id == owner_id,
        )
    )
    return _decision_read(session, membership.id, row)


def set_decision(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    project_product_id: UUID,
    state: str,
    command: DecisionCommand,
    *,
    actor: str = "owner",
    origin: str = "command",
) -> DecisionMutationResult:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    member = _membership(session, owner_id, project_id, project_product_id)
    replay = _find_replay(session, project, owner_id, member, state, command)
    if replay is not None:
        event, replayed = replay
        session.rollback()
        return DecisionMutationResult(
            event=_event_read(event, replayed=replayed), replayed=replayed
        )
    _check_revision(project, command.expected_version)
    event, replayed = apply_decision_locked(
        session,
        project,
        owner_id,
        member,
        state,
        command,
        actor=actor,
        origin=origin,
    )
    if not replayed:
        project_service._advance_revision(project)
        event.project_version = project.revision
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _invalid("Decision violates a project constraint") from error
    return DecisionMutationResult(event=_event_read(event, replayed=replayed), replayed=replayed)


def apply_decision_locked(
    session: Session,
    project: ShoppingProject,
    owner_id: UUID,
    project_product: ProjectProduct,
    state: str,
    command: DecisionCommand,
    *,
    actor: str,
    origin: str,
) -> tuple[DecisionEvent, bool]:
    """Apply one assistant or owner transition inside an already locked project transaction."""
    replay = _find_replay(session, project, owner_id, project_product, state, command)
    if replay is not None:
        return replay

    decision = session.scalar(
        select(ProjectProductDecision)
        .where(ProjectProductDecision.project_product_id == project_product.id)
        .with_for_update()
    )
    previous_state = decision.state if decision else "considering"
    if previous_state == "purchased" and state != "considering":
        raise ProjectError(
            409,
            "decision_transition_conflict",
            "Undo the purchased state before changing this decision.",
        )
    if state not in {"considering", "shortlisted", "rejected", "purchased"}:
        raise _invalid("Unsupported decision state")
    if state == "rejected" and command.rejection_reason is None:
        raise _invalid("A rejection reason is required")
    if state != "rejected" and command.rejection_reason is not None:
        raise _invalid("A rejection reason is only valid for rejected products")
    if command.selected_offer_id is not None:
        offer = session.scalar(
            select(RetailOffer).where(
                RetailOffer.id == command.selected_offer_id,
                RetailOffer.owner_id == owner_id,
                RetailOffer.variant_id == project_product.variant_id,
            )
        )
        if offer is None:
            raise _not_found("Selected offer does not belong to this product variant")

    next_version = (decision.version + 1) if decision else 1
    next_reason = (
        command.reason
        if "reason" in command.model_fields_set or decision is None
        else decision.reason
    )
    next_concerns = (
        command.concerns
        if "concerns" in command.model_fields_set or decision is None
        else decision.concerns
    )
    next_selected_offer_id = (
        command.selected_offer_id
        if "selected_offer_id" in command.model_fields_set or decision is None
        else decision.selected_offer_id
    )
    if decision is None:
        decision = ProjectProductDecision(
            owner_id=owner_id,
            project_id=project.id,
            project_product_id=project_product.id,
            state=state,
            reason=next_reason,
            rejection_reason=command.rejection_reason,
            concerns=next_concerns,
            selected_offer_id=next_selected_offer_id,
            actor=actor,
            origin=origin,
            version=next_version,
        )
        session.add(decision)
    else:
        decision.state = state
        decision.reason = next_reason
        decision.rejection_reason = command.rejection_reason
        decision.concerns = next_concerns
        decision.selected_offer_id = next_selected_offer_id
        decision.actor = actor
        decision.origin = origin
        decision.version = next_version
        decision.updated_at = datetime.now(UTC)
    event = DecisionEvent(
        owner_id=owner_id,
        project_id=project.id,
        project_product_id=project_product.id,
        command_type=state,
        request_key=command.request_key,
        request_hash=_request_hash(state, command),
        from_state=previous_state,
        to_state=state,
        actor=actor,
        reason=command.reason if "reason" in command.model_fields_set else "",
        rejection_reason=command.rejection_reason,
        concerns=next_concerns,
        selected_offer_id=next_selected_offer_id,
        project_version=project.revision + 1,
    )
    session.add(event)
    session.flush()
    return event, False


def _find_replay(session, project, owner_id, project_product, state, command):
    prior = session.scalar(
        select(DecisionEvent).where(
            DecisionEvent.owner_id == owner_id,
            DecisionEvent.project_id == project.id,
            DecisionEvent.command_type == state,
            DecisionEvent.request_key == command.request_key,
        )
    )
    if prior:
        if (
            prior.request_hash != _request_hash(state, command)
            or prior.project_product_id != project_product.id
        ):
            raise ProjectError(
                409, "idempotency_conflict", "This request key was used for a different decision."
            )
        return prior, True


def _request_hash(state, command):
    payload = command.model_dump(mode="json", exclude={"expected_version", "request_key"})
    return hashlib.sha256(
        json.dumps({"state": state, **payload}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _membership(session: Session, owner_id: UUID, project_id: UUID, project_product_id: UUID):
    return session.scalar(
        select(ProjectProduct)
        .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProjectProduct.id == project_product_id,
            ProjectProduct.project_id == project_id,
            Product.owner_id == owner_id,
        )
    ) or _raise_not_found("Selected product not found in this project")


def _decision_read(session: Session, project_product_id: UUID, decision):
    events = list(
        session.scalars(
            select(DecisionEvent)
            .where(DecisionEvent.project_product_id == project_product_id)
            .order_by(DecisionEvent.created_at.desc(), DecisionEvent.id.desc())
            .limit(20)
        ).all()
    )
    return DecisionRead(
        project_product_id=project_product_id,
        state=decision.state if decision else "considering",
        reason=decision.reason if decision else "",
        rejection_reason=decision.rejection_reason if decision else None,
        concerns=decision.concerns if decision else [],
        selected_offer_id=decision.selected_offer_id if decision else None,
        version=decision.version if decision else 1,
        updated_at=decision.updated_at if decision else None,
        events=[_event_read(item) for item in events],
    )


def _event_read(event: DecisionEvent, replayed: bool = False):
    return DecisionEventRead(
        id=event.id,
        project_product_id=event.project_product_id,
        command_type=event.command_type,
        from_state=event.from_state,
        to_state=event.to_state,
        actor=event.actor,
        reason=event.reason,
        rejection_reason=event.rejection_reason,
        concerns=event.concerns,
        selected_offer_id=event.selected_offer_id,
        project_version=event.project_version,
        created_at=event.created_at,
        replayed=replayed,
    )


def _check_revision(project: ShoppingProject, expected: int) -> None:
    if project.revision != expected:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded.",
            {"current_version": project.revision},
        )


def _encode_cursor(created_at: datetime, item_id: UUID) -> str:
    import base64

    value = json.dumps(
        [created_at.astimezone(UTC).isoformat(), str(item_id)], separators=(",", ":")
    )
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str):
    import base64

    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        created_at, raw_id = json.loads(raw)
        instant = datetime.fromisoformat(created_at)
        if instant.tzinfo is None:
            raise ValueError
        return instant.astimezone(UTC), UUID(raw_id)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise _invalid("Invalid decision pagination cursor") from error


def _raise_not_found(message: str):
    raise _not_found(message)


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _invalid(message: str) -> ProjectError:
    return ProjectError(422, "invalid_request", message)
