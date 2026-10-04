from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shopping.projects.schemas import (
    ProjectRead,
    RequirementCreate,
    RequirementKind,
    RequirementOperator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IntentProjectUpdates(StrictModel):
    goal: str | None = Field(default=None, min_length=1, max_length=4000)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    budget_target: str | None = Field(default=None, pattern=r"^\d{1,12}(\.\d{1,2})?$")
    budget_maximum: str | None = Field(default=None, pattern=r"^\d{1,12}(\.\d{1,2})?$")
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def check_budget_shape(self) -> IntentProjectUpdates:
        amounts = self.budget_target is not None or self.budget_maximum is not None
        if amounts and self.budget_currency is None:
            raise ValueError("budget_currency is required with a proposed budget amount")
        if self.budget_currency is not None:
            if self.budget_currency != self.budget_currency.upper():
                raise ValueError("budget_currency must use uppercase ISO currency form")
        if self.budget_target is not None and self.budget_maximum is not None:
            from decimal import Decimal

            if Decimal(self.budget_target) > Decimal(self.budget_maximum):
                raise ValueError("budget_target cannot exceed budget_maximum")
        return self


class RequirementChanges(StrictModel):
    kind: RequirementKind | None = None
    label: str | None = Field(default=None, min_length=1, max_length=300)
    detail: str | None = Field(default=None, max_length=2000)
    attribute_key: str | None = Field(default=None, min_length=1, max_length=100)
    operator: RequirementOperator | None = None
    value: Any = None
    unit: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def require_fields(self) -> RequirementChanges:
        if not self.model_fields_set:
            raise ValueError("requirement update must change at least one field")
        return self


class AddRequirement(StrictModel):
    operation: Literal["add"]
    fields: RequirementCreate


class UpdateRequirement(StrictModel):
    operation: Literal["update"]
    id: UUID
    fields: RequirementChanges


class RemoveRequirement(StrictModel):
    operation: Literal["remove"]
    id: UUID


RequirementOperation = Annotated[
    AddRequirement | UpdateRequirement | RemoveRequirement,
    Field(discriminator="operation"),
]


class InterpretationOutput(StrictModel):
    assistant_message: str = Field(min_length=1, max_length=6000)
    clarification_questions: list[str] = Field(default_factory=list, max_length=5)
    project_updates: IntentProjectUpdates = Field(default_factory=IntentProjectUpdates)
    requirement_operations: list[RequirementOperation] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bound_questions(self) -> InterpretationOutput:
        if any(not question or len(question) > 500 for question in self.clarification_questions):
            raise ValueError("clarification questions must contain 1 to 500 characters")
        return self

    def mutation_payload(self) -> dict[str, Any] | None:
        updates = self.project_updates.model_dump(exclude_unset=True, exclude_none=True)
        operations = [
            item.model_dump(mode="json", exclude_unset=True) for item in self.requirement_operations
        ]
        if not updates and not operations:
            return None
        return {
            "project_updates": updates,
            "requirement_operations": operations,
        }


class MessageCreate(StrictModel):
    text: str = Field(min_length=1, max_length=8000)
    request_key: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def nonblank_text(self) -> MessageCreate:
        if not self.text:
            raise ValueError("text must contain non-whitespace characters")
        return self


class MessageCreated(StrictModel):
    user_message_id: UUID
    assistant_message_id: UUID
    conversation_id: UUID
    replayed: bool


class ConversationRead(StrictModel):
    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime


class ConversationPage(StrictModel):
    items: list[ConversationRead]
    next_cursor: str | None = None


class MessageRead(StrictModel):
    id: UUID
    conversation_id: UUID
    project_id: UUID
    paired_message_id: UUID | None
    ordinal: int
    role: Literal["user", "assistant"]
    text: str
    status: Literal["generating", "completed", "failed", "interrupted"]
    request_key: str | None = None
    snapshot_revision: int | None
    sequence: int
    error_code: str | None
    clarification_questions: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None
    proposal: ProposalRead | None = None


class MessagePage(StrictModel):
    items: list[MessageRead]
    next_cursor: str | None = None


class ProposalRead(StrictModel):
    id: UUID
    project_id: UUID
    assistant_message_id: UUID
    base_revision: int
    schema_version: int
    operations: dict[str, Any]
    status: Literal["pending", "applied", "dismissed", "stale"]
    applied_revision: int | None
    applied_at: datetime | None
    applied_project: ProjectRead | None = None
    created_at: datetime
    updated_at: datetime


class ProposalCommand(StrictModel):
    expected_version: int = Field(ge=1)


class ProposalMutationResult(StrictModel):
    proposal: ProposalRead
    project: ProjectRead | None
    replayed: bool


class ErrorPayload(StrictModel):
    code: str
    message: str


MessageRead.model_rebuild()
