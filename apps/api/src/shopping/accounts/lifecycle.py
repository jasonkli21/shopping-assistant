from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shopping.accounts.models import OwnerPrivacyLifecycle


def lock_active_owner_lifecycle(session: Session, owner_id: UUID) -> bool:
    """Acquire privacy authority before locking or writing owner-scoped rows."""
    lifecycle = OwnerPrivacyLifecycle.__table__
    session.execute(
        pg_insert(lifecycle)
        .values(owner_id=owner_id, state="active")
        .on_conflict_do_nothing(index_elements=[lifecycle.c.owner_id])
    )
    state = session.scalar(
        select(lifecycle.c.state).where(lifecycle.c.owner_id == owner_id).with_for_update(read=True)
    )
    return state == "active"
