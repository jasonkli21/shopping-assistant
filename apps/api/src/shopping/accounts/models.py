from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shopping.db.base import Base


class FirebaseOwnerBinding(Base):
    __tablename__ = "firebase_owner_bindings"
    __table_args__ = (
        CheckConstraint("char_length(firebase_uid) BETWEEN 1 AND 128", name="ck_binding_uid"),
        UniqueConstraint("owner_id", name="uq_binding_owner"),
    )

    firebase_uid: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OwnerPrivacyEvent(Base):
    __tablename__ = "owner_privacy_events"
    __table_args__ = (
        CheckConstraint("event_type = 'purge'", name="ck_owner_privacy_event_type"),
        Index("ix_owner_privacy_events_owner_time", "owner_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    record_counts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
