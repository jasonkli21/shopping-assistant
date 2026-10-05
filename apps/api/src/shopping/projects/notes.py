from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.decision_schemas import NoteRead, NoteWrite
from shopping.projects.errors import ProjectError
from shopping.projects.models import ShoppingProject, UserNote


def get_note(
    session: Session, owner_id: UUID, project_id: UUID, project_product_id: UUID | None = None
) -> NoteRead | None:
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    if project_product_id is not None:
        _membership(session, owner_id, project_id, project_product_id)
    else:
        # ShoppingProject.notes is the original project-note field. A UserNote
        # created by an earlier Phase 6 build is merged on read so upgrades keep
        # both texts visible until the next write consolidates them.
        legacy = session.scalar(
            select(UserNote).where(
                UserNote.owner_id == owner_id,
                UserNote.project_id == project_id,
                UserNote.project_product_id.is_(None),
            )
        )
        text = _merge_note_text(project.notes, legacy.text if legacy else None)
        if not text:
            return None
        return NoteRead(
            id=project.id,
            project_id=project.id,
            project_product_id=None,
            text=text,
            version=project.revision,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
    statement = select(UserNote).where(
        UserNote.owner_id == owner_id,
        UserNote.project_id == project_id,
        UserNote.project_product_id == project_product_id,
    )
    return _read(session.scalar(statement))


def put_note(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    project_product_id: UUID | None,
    command: NoteWrite,
) -> tuple[NoteRead, int]:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    if project.revision != command.expected_version:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded.",
            {"current_version": project.revision},
        )
    if project_product_id is not None:
        _membership(session, owner_id, project_id, project_product_id)
    if project_product_id is None:
        legacy = session.scalar(
            select(UserNote)
            .where(
                UserNote.owner_id == owner_id,
                UserNote.project_id == project.id,
                UserNote.project_product_id.is_(None),
            )
            .with_for_update()
        )
        project.notes = _merge_note_text(project.notes, legacy.text if legacy else None)
        if legacy is not None:
            session.delete(legacy)
        project.notes = command.text
        project_service._advance_revision(project)
        session.commit()
        return _project_note_read(project), project.revision
    note = put_note_locked(session, project, owner_id, project_product_id, command.text)
    project_service._advance_revision(project)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _invalid("A note already exists for this project item") from error
    return _read(note), project.revision


def delete_note(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    project_product_id: UUID | None,
    expected_version: int,
) -> int:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    if project.revision != expected_version:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded.",
            {"current_version": project.revision},
        )
    if project_product_id is not None:
        _membership(session, owner_id, project_id, project_product_id)
    if project_product_id is None:
        legacy = session.scalar(
            select(UserNote)
            .where(
                UserNote.owner_id == owner_id,
                UserNote.project_id == project_id,
                UserNote.project_product_id.is_(None),
            )
            .with_for_update()
        )
        if project.notes is None and legacy is None:
            raise _not_found("Note not found")
        project.notes = None
        if legacy is not None:
            session.delete(legacy)
        project_service._advance_revision(project)
        session.commit()
        return project.revision
    note = session.scalar(
        select(UserNote)
        .where(
            UserNote.owner_id == owner_id,
            UserNote.project_id == project_id,
            UserNote.project_product_id == project_product_id,
        )
        .with_for_update()
    )
    if note is None:
        raise _not_found("Note not found")
    session.delete(note)
    project_service._advance_revision(project)
    session.commit()
    return project.revision


def put_note_locked(
    session: Session,
    project: ShoppingProject,
    owner_id: UUID,
    project_product_id: UUID | None,
    text: str,
) -> UserNote:
    if project_product_id is None:
        raise ValueError("put_note_locked only writes product notes")
    _membership(session, owner_id, project.id, project_product_id)
    note = session.scalar(
        select(UserNote)
        .where(
            UserNote.owner_id == owner_id,
            UserNote.project_id == project.id,
            UserNote.project_product_id == project_product_id,
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    if note is None:
        note = UserNote(
            owner_id=owner_id,
            project_id=project.id,
            project_product_id=project_product_id,
            text=text,
            version=1,
        )
        session.add(note)
    else:
        note.text = text
        note.version += 1
        note.updated_at = now
    session.flush()
    return note


def append_note_locked(
    session: Session,
    project: ShoppingProject,
    owner_id: UUID,
    project_product_id: UUID | None,
    text: str,
) -> None:
    """Append an assistant addition without replacing saved user-authored text."""
    if project_product_id is None:
        legacy = session.scalar(
            select(UserNote)
            .where(
                UserNote.owner_id == owner_id,
                UserNote.project_id == project.id,
                UserNote.project_product_id.is_(None),
            )
            .with_for_update()
        )
        current = _merge_note_text(project.notes, legacy.text if legacy else None)
        combined = _append_text(current, text)
        if len(combined) > 10000:
            raise ProjectError(
                409, "proposal_invalid", "The proposed project note exceeds 10,000 characters."
            )
        project.notes = combined
        if legacy is not None:
            session.delete(legacy)
        return
    _membership(session, owner_id, project.id, project_product_id)
    note = session.scalar(
        select(UserNote)
        .where(
            UserNote.owner_id == owner_id,
            UserNote.project_id == project.id,
            UserNote.project_product_id == project_product_id,
        )
        .with_for_update()
    )
    combined = _append_text(note.text if note else None, text)
    if len(combined) > 10000:
        raise ProjectError(
            409, "proposal_invalid", "The proposed product note exceeds 10,000 characters."
        )
    put_note_locked(session, project, owner_id, project_product_id, combined)


def _append_text(existing: str | None, addition: str) -> str:
    return f"{existing}\n\n{addition}" if existing else addition


def _merge_note_text(first: str | None, second: str | None) -> str | None:
    first = first.strip() if first else ""
    second = second.strip() if second else ""
    if not first:
        return second or None
    if not second or first == second:
        return first
    if second in first:
        return first
    if first in second:
        return second
    return f"{first}\n\n{second}"


def _project_note_read(project: ShoppingProject) -> NoteRead:
    return NoteRead(
        id=project.id,
        project_id=project.id,
        project_product_id=None,
        text=project.notes or "",
        version=project.revision,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _membership(session, owner_id, project_id, project_product_id):
    membership = session.scalar(
        select(ProjectProduct)
        .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProjectProduct.id == project_product_id,
            ProjectProduct.project_id == project_id,
            Product.owner_id == owner_id,
        )
    )
    if membership is None:
        raise _not_found("Selected product not found in this project")
    return membership


def _read(note: UserNote | None) -> NoteRead | None:
    if note is None:
        return None
    return NoteRead(
        id=note.id,
        project_id=note.project_id,
        project_product_id=note.project_product_id,
        text=note.text,
        version=note.version,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _invalid(message: str) -> ProjectError:
    return ProjectError(422, "invalid_request", message)
