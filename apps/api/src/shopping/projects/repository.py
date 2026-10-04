from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from shopping.projects.models import ProjectRequirement, ShoppingProject


def project_by_owner(
    session: Session,
    project_id: UUID,
    owner_id: UUID,
    *,
    lock: bool = False,
) -> ShoppingProject | None:
    statement: Select[tuple[ShoppingProject]] = select(ShoppingProject).where(
        ShoppingProject.id == project_id,
        ShoppingProject.owner_id == owner_id,
        ShoppingProject.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def requirement_by_project(
    session: Session,
    project_id: UUID,
    requirement_id: UUID,
) -> ProjectRequirement | None:
    return session.scalar(
        select(ProjectRequirement).where(
            ProjectRequirement.project_id == project_id,
            ProjectRequirement.id == requirement_id,
        )
    )


def ordered_requirements(
    session: Session,
    project_id: UUID,
) -> list[ProjectRequirement]:
    return list(
        session.scalars(
            select(ProjectRequirement)
            .where(ProjectRequirement.project_id == project_id)
            .order_by(ProjectRequirement.position, ProjectRequirement.id)
        ).all()
    )


def owned_projects(
    session: Session,
    owner_id: UUID,
    *,
    before_updated_at: datetime | None = None,
    before_id: UUID | None = None,
) -> Select[tuple[ShoppingProject]]:
    statement = select(ShoppingProject).where(
        ShoppingProject.owner_id == owner_id,
        ShoppingProject.deleted_at.is_(None),
    )
    if before_updated_at is not None and before_id is not None:
        from sqlalchemy import or_

        statement = statement.where(
            or_(
                ShoppingProject.updated_at < before_updated_at,
                (ShoppingProject.updated_at == before_updated_at)
                & (ShoppingProject.id > before_id),
            )
        )
    return statement.order_by(ShoppingProject.updated_at.desc(), ShoppingProject.id.asc())


def append_position(session: Session, project_id: UUID) -> int:
    from sqlalchemy import func

    current = session.scalar(
        select(func.max(ProjectRequirement.position)).where(
            ProjectRequirement.project_id == project_id
        )
    )
    return 0 if current is None else current + 1
