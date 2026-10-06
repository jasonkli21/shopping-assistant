from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.projects import repository
from shopping.projects.errors import ProjectError
from shopping.projects.models import ProjectRequirement, ShoppingProject, UserNote
from shopping.projects.schemas import (
    ProjectCreate,
    ProjectPage,
    ProjectPatch,
    ProjectRead,
    ProjectSummary,
    RequirementCreate,
    RequirementPatch,
    RequirementRead,
    money_string,
    validate_budget,
    validate_criterion_fields,
)


def create_project(
    session: Session,
    owner_id: UUID,
    command: ProjectCreate,
) -> ProjectRead:
    project = ShoppingProject(
        owner_id=owner_id,
        title=command.title,
        goal=command.goal,
        category=command.category,
        budget_target=command.budget_target,
        budget_maximum=command.budget_maximum,
        budget_currency=command.budget_currency,
        notes=command.notes,
        status="active",
        revision=1,
    )
    project.requirements = [
        _requirement_model(item, position=position)
        for position, item in enumerate(command.requirements)
    ]
    session.add(project)
    return _commit_and_read(session, project)


def list_projects(
    session: Session,
    owner_id: UUID,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> ProjectPage:
    before_updated_at = None
    before_id = None
    if cursor:
        before_updated_at, before_id = _decode_cursor(cursor)
    statement = repository.owned_projects(
        session,
        owner_id,
        before_updated_at=before_updated_at,
        before_id=before_id,
    )
    projects = list(session.scalars(statement.limit(limit + 1)).all())
    has_more = len(projects) > limit
    page = projects[:limit]
    next_cursor = _encode_cursor(page[-1]) if has_more and page else None
    return ProjectPage(
        items=[_summary(project) for project in page],
        next_cursor=next_cursor,
    )


def get_project(session: Session, owner_id: UUID, project_id: UUID) -> ProjectRead:
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    return _project_read(session, project)


def patch_project(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    command: ProjectPatch,
) -> ProjectRead:
    project = _lock_project(session, owner_id, project_id, command.expected_version)
    changes = command.model_dump(exclude_unset=True, exclude={"expected_version"})
    for name in ("title", "goal", "status"):
        if name in changes and changes[name] is None:
            raise _invalid(f"{name} cannot be cleared")
    target = changes.get("budget_target", project.budget_target)
    maximum = changes.get("budget_maximum", project.budget_maximum)
    currency = changes.get("budget_currency", project.budget_currency)
    _validate_budget_or_raise(target, maximum, currency)
    if "notes" in changes:
        legacy_note = session.scalar(
            select(UserNote)
            .where(
                UserNote.owner_id == owner_id,
                UserNote.project_id == project.id,
                UserNote.project_product_id.is_(None),
            )
            .with_for_update()
        )
        if legacy_note is not None:
            session.delete(legacy_note)
    for name, value in changes.items():
        setattr(project, name, value)
    _advance_revision(project)
    return _commit_and_read(session, project)


def delete_project(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    expected_version: int,
) -> None:
    project = _lock_project(session, owner_id, project_id, expected_version)
    project.deleted_at = datetime.now(UTC)
    _advance_revision(project)
    from shopping.research.service import interrupt_project_runs

    interrupt_project_runs(session, owner_id, project_id)
    _commit(session)


def list_requirements(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
) -> list[RequirementRead]:
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    return [
        _requirement_read(requirement)
        for requirement in repository.ordered_requirements(session, project_id)
    ]


def create_requirement(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    expected_version: int,
    command: RequirementCreate,
) -> ProjectRead:
    project = _lock_project(session, owner_id, project_id, expected_version)
    current = len(repository.ordered_requirements(session, project.id))
    if current >= 100:
        raise _invalid("A project can have at most 100 requirements")
    project.requirements.append(
        _requirement_model(command, position=repository.append_position(session, project.id))
    )
    _advance_revision(project)
    return _commit_and_read(session, project)


def patch_requirement(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    requirement_id: UUID,
    command: RequirementPatch,
) -> ProjectRead:
    project, requirement = _lock_requirement(
        session, owner_id, project_id, requirement_id, command.expected_version
    )

    changes = command.model_dump(exclude_unset=True, exclude={"expected_version"})
    for name in ("kind", "label"):
        if name in changes and changes[name] is None:
            raise _invalid(f"{name} cannot be cleared")
    if "position" in changes and changes["position"] is None:
        raise _invalid("position cannot be cleared")

    criterion_fields = {"attribute_key", "operator", "value", "unit"}
    required_criterion_fields = {"attribute_key", "operator", "value"}
    if any(name in changes and changes[name] is None for name in required_criterion_fields):
        for name in criterion_fields:
            changes.pop(name, None)
        changes.update(attribute_key=None, operator=None, value=None, unit=None)

    merged = {
        "attribute_key": changes.get("attribute_key", requirement.attribute_key),
        "operator": changes.get("operator", requirement.operator),
        "value": changes.get("value", requirement.value),
        "unit": changes.get("unit", requirement.unit),
    }
    try:
        validate_criterion_fields(**merged)
    except ValueError as error:
        raise _invalid(str(error)) from error

    requested_position = changes.pop("position", None)
    if requested_position is not None:
        requirements = repository.ordered_requirements(session, project.id)
        if requested_position >= len(requirements):
            raise _invalid("position must refer to an existing requirement slot")
        reordered = [item for item in requirements if item.id != requirement.id]
        reordered.insert(requested_position, requirement)
        _set_requirement_positions(reordered)

    for name, value in changes.items():
        setattr(requirement, name, value)
    requirement.updated_at = datetime.now(UTC)
    _advance_revision(project)
    return _commit_and_read(session, project)


def delete_requirement(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    requirement_id: UUID,
    expected_version: int,
) -> ProjectRead:
    project, requirement = _lock_requirement(
        session, owner_id, project_id, requirement_id, expected_version
    )
    remaining = [
        item
        for item in repository.ordered_requirements(session, project.id)
        if item.id != requirement.id
    ]
    session.delete(requirement)
    _set_requirement_positions(remaining)
    _advance_revision(project)
    return _commit_and_read(session, project)


def apply_ai_proposal(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    expected_version: int,
    project_updates: dict,
    requirement_operations: list[dict],
    *,
    commit: bool = True,
) -> ProjectRead:
    """Apply a validated assistant proposal as one project-context transaction.

    This uses the same field validators and requirement model helpers as manual
    edits, while intentionally advancing the project revision only once for
    the complete proposal.
    """
    project = _lock_project(session, owner_id, project_id, expected_version)
    if project_updates:
        try:
            command = ProjectPatch.model_validate(
                {**project_updates, "expected_version": expected_version}
            )
        except ValueError as error:
            raise _invalid("The proposal contains invalid project fields") from error
        changes = command.model_dump(exclude_unset=True, exclude={"expected_version"})
        for name in ("title", "goal"):
            if name in changes and changes[name] is None:
                raise _invalid(f"{name} cannot be cleared")
        target = changes.get("budget_target", project.budget_target)
        maximum = changes.get("budget_maximum", project.budget_maximum)
        currency = changes.get("budget_currency", project.budget_currency)
        _validate_budget_or_raise(target, maximum, currency)
        for name, value in changes.items():
            setattr(project, name, value)

    requirements = repository.ordered_requirements(session, project.id)
    removes = sum(operation.get("operation") == "remove" for operation in requirement_operations)
    adds = sum(operation.get("operation") == "add" for operation in requirement_operations)
    if len(requirements) - removes + adds > 100:
        raise _invalid("A project can have at most 100 requirements")
    # Process removals first so a valid final set of 100 items is accepted even
    # when the model lists an add before the later removal it makes room for.
    ordered_operations = [
        *[item for item in requirement_operations if item.get("operation") == "remove"],
        *[item for item in requirement_operations if item.get("operation") != "remove"],
    ]
    for operation in ordered_operations:
        kind = operation["operation"]
        if kind == "add":
            fields = RequirementCreate.model_validate(operation["fields"])
            requirement = _requirement_model(fields, position=len(requirements))
            requirement.origin = "ai_confirmed"
            project.requirements.append(requirement)
            requirements.append(requirement)
        elif kind == "update":
            requirement_id = UUID(operation["id"])
            requirement = next((item for item in requirements if item.id == requirement_id), None)
            if requirement is None:
                raise _not_found("Requirement not found")
            fields = RequirementPatch.model_validate(
                {**operation["fields"], "expected_version": expected_version}
            )
            changes = fields.model_dump(exclude_unset=True, exclude={"expected_version"})
            for name in ("kind", "label"):
                if name in changes and changes[name] is None:
                    raise _invalid(f"{name} cannot be cleared")
            criterion_fields = {"attribute_key", "operator", "value", "unit"}
            required = {"attribute_key", "operator", "value"}
            if any(name in changes and changes[name] is None for name in required):
                for name in criterion_fields:
                    changes.pop(name, None)
                changes.update(attribute_key=None, operator=None, value=None, unit=None)
            merged = {
                "attribute_key": changes.get("attribute_key", requirement.attribute_key),
                "operator": changes.get("operator", requirement.operator),
                "value": changes.get("value", requirement.value),
                "unit": changes.get("unit", requirement.unit),
            }
            try:
                validate_criterion_fields(**merged)
            except ValueError as error:
                raise _invalid(str(error)) from error
            for name, value in changes.items():
                setattr(requirement, name, value)
            requirement.origin = "ai_confirmed"
            requirement.updated_at = datetime.now(UTC)
        elif kind == "remove":
            requirement_id = UUID(operation["id"])
            requirement = next((item for item in requirements if item.id == requirement_id), None)
            if requirement is None:
                raise _not_found("Requirement not found")
            requirements.remove(requirement)
            session.delete(requirement)
            _set_requirement_positions(requirements)
        else:
            raise _invalid("The proposal contains an unsupported requirement operation")

    _advance_revision(project)
    if commit:
        return _commit_and_read(session, project)
    session.flush()
    return _project_read(session, project)


def _requirement_model(command: RequirementCreate, position: int) -> ProjectRequirement:
    return ProjectRequirement(
        kind=command.kind,
        label=command.label,
        detail=command.detail,
        attribute_key=command.attribute_key,
        operator=command.operator,
        value=command.value,
        unit=command.unit,
        position=position,
        origin="user",
    )


def _lock_project(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    expected_version: int,
) -> ShoppingProject:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    _check_revision(project, expected_version)
    return project


def _lock_requirement(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    requirement_id: UUID,
    expected_version: int,
) -> tuple[ShoppingProject, ProjectRequirement]:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    requirement = repository.requirement_by_project(session, project.id, requirement_id)
    if requirement is None:
        raise _not_found("Requirement not found")
    _check_revision(project, expected_version)
    return project, requirement


def _check_revision(project: ShoppingProject, expected_version: int) -> None:
    if project.revision != expected_version:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded. Review the latest version before saving.",
            {"current_version": project.revision},
        )


def _advance_revision(project: ShoppingProject) -> None:
    project.revision += 1
    project.updated_at = datetime.now(UTC)


def _set_requirement_positions(requirements: list[ProjectRequirement]) -> None:
    now = datetime.now(UTC)
    for position, item in enumerate(requirements):
        if item.position != position:
            item.position = position
            item.updated_at = now


def _validate_budget_or_raise(
    target: Decimal | None,
    maximum: Decimal | None,
    currency: str | None,
) -> None:
    try:
        validate_budget(target, maximum, currency)
    except ValueError as error:
        raise _invalid(str(error)) from error


def _commit_and_read(session: Session, project: ShoppingProject) -> ProjectRead:
    _commit(session)
    session.refresh(project)
    return _project_read(session, project)


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _invalid("Project data violates a database constraint") from error


def _project_read(session: Session, project: ShoppingProject) -> ProjectRead:
    # `ShoppingProject.notes` is the project note shown in the main workspace.
    # Merge a legacy Phase 6 project-level UserNote into that field so older
    # saved text remains visible through the same editing surface.
    from shopping.projects.notes import get_note

    project_note = get_note(session, project.owner_id, project.id)
    data = _summary_data(project)
    if project_note is not None:
        data["notes"] = project_note.text
    return ProjectRead(
        **data,
        requirements=[
            _requirement_read(requirement)
            for requirement in repository.ordered_requirements(session, project.id)
        ],
    )


def _summary(project: ShoppingProject) -> ProjectSummary:
    return ProjectSummary(**_summary_data(project))


def _summary_data(project: ShoppingProject) -> dict:
    return {
        "id": project.id,
        "title": project.title,
        "goal": project.goal,
        "category": project.category,
        "status": project.status,
        "budget_target": money_string(project.budget_target),
        "budget_maximum": money_string(project.budget_maximum),
        "budget_currency": project.budget_currency,
        "notes": project.notes,
        "reuse_preferences": project.reuse_preferences,
        "revision": project.revision,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _requirement_read(requirement: ProjectRequirement) -> RequirementRead:
    return RequirementRead(
        id=requirement.id,
        project_id=requirement.project_id,
        kind=requirement.kind,
        label=requirement.label,
        detail=requirement.detail,
        attribute_key=requirement.attribute_key,
        operator=requirement.operator,
        value=requirement.value,
        unit=requirement.unit,
        position=requirement.position,
        origin=requirement.origin,
        source_preference_id=requirement.source_preference_id,
        source_preference_revision=requirement.source_preference_revision,
        source_preference_scope=requirement.source_preference_scope,
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
    )


def _encode_cursor(project: ShoppingProject) -> str:
    payload = json.dumps([project.updated_at.isoformat(), str(project.id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError("cursor must contain exactly two values")
        updated_at = datetime.fromisoformat(payload[0])
        if updated_at.tzinfo is None or not isinstance(payload[1], str):
            raise ValueError("cursor values are invalid")
        return updated_at.astimezone(UTC), UUID(payload[1])
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise _invalid("Invalid project pagination cursor") from error


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _invalid(message: str) -> ProjectError:
    return ProjectError(422, "invalid_request", message)
