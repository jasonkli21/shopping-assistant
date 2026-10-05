from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from shopping.catalog.schemas import ProjectProductRead
from shopping.projects.schemas import StrictModel

DecisionState = Literal["considering", "shortlisted", "rejected", "purchased"]
RejectionReason = Literal[
    "too_expensive",
    "missing_feature",
    "too_large",
    "appearance",
    "weak_evidence",
    "wrong_category",
    "already_owned",
    "other",
]


class DecisionCommand(StrictModel):
    expected_version: int = Field(ge=1)
    request_key: str = Field(min_length=8, max_length=100)
    reason: str = Field(default="", max_length=2000)
    rejection_reason: RejectionReason | None = None
    concerns: list[str] = Field(default_factory=list, max_length=20)
    selected_offer_id: UUID | None = None

    @field_validator("concerns")
    @classmethod
    def bounded_concerns(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 500 for item in value):
            raise ValueError("each concern must contain 1 to 500 characters")
        return value

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class DecisionEventRead(StrictModel):
    id: UUID
    project_product_id: UUID
    command_type: str
    from_state: DecisionState
    to_state: DecisionState
    actor: Literal["owner", "assistant"]
    reason: str
    rejection_reason: RejectionReason | None
    project_version: int
    created_at: datetime
    replayed: bool = False


class DecisionRead(StrictModel):
    project_product_id: UUID
    state: DecisionState
    reason: str
    rejection_reason: RejectionReason | None
    concerns: list[str]
    selected_offer_id: UUID | None
    version: int
    updated_at: datetime | None
    events: list[DecisionEventRead] = Field(default_factory=list)


class DecisionMutationResult(StrictModel):
    event: DecisionEventRead
    replayed: bool


class ProjectProductDecisionRead(StrictModel):
    product: ProjectProductRead
    decision: DecisionRead


class DecisionPage(StrictModel):
    items: list[ProjectProductDecisionRead]
    project_version: int
    next_cursor: str | None = None


class NoteWrite(StrictModel):
    expected_version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=10000)

    @field_validator("text")
    @classmethod
    def strip_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must contain non-whitespace characters")
        return value


class NoteRead(StrictModel):
    id: UUID
    project_id: UUID
    project_product_id: UUID | None
    text: str
    version: int
    created_at: datetime
    updated_at: datetime


class NoteMutationResult(StrictModel):
    note: NoteRead
    project_version: int
