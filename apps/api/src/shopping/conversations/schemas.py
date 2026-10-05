from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shopping.comparisons.schemas import ComparisonDimensionInput, DisplayMode
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


class RefineRequirements(StrictModel):
    operation: Literal["refine_requirements"]
    project_updates: IntentProjectUpdates = Field(default_factory=IntentProjectUpdates)
    requirement_operations: list[RequirementOperation] = Field(default_factory=list, max_length=20)


class ShortlistProduct(StrictModel):
    operation: Literal["shortlist"]
    project_product_id: UUID
    reason: str = Field(default="", max_length=2000)
    concerns: list[str] = Field(default_factory=list, max_length=20)


class RejectProduct(StrictModel):
    operation: Literal["reject"]
    project_product_id: UUID
    rejection_reason: Literal[
        "too_expensive",
        "missing_feature",
        "too_large",
        "appearance",
        "weak_evidence",
        "wrong_category",
        "already_owned",
        "other",
    ]
    reason: str = Field(default="", max_length=2000)
    concerns: list[str] = Field(default_factory=list, max_length=20)


class AddNote(StrictModel):
    operation: Literal["add_note"]
    project_product_id: UUID | None = None
    text: str = Field(min_length=1, max_length=10000)


class SetComparisonDimensions(StrictModel):
    operation: Literal["set_comparison_dimensions"]
    project_product_ids: list[UUID] = Field(min_length=2, max_length=6)
    dimensions: list[ComparisonDimensionInput] = Field(min_length=1, max_length=20)
    title: str = Field(default="Assistant comparison", min_length=1, max_length=160)
    display_mode: DisplayMode = "all"
    comparison_id: UUID | None = None
    expected_comparison_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def unique_scope(self):
        if len(self.project_product_ids) != len(set(self.project_product_ids)):
            raise ValueError("comparison products must be unique")
        if len({item.key for item in self.dimensions}) != len(self.dimensions):
            raise ValueError("comparison dimension keys must be unique")
        if (self.comparison_id is None) != (self.expected_comparison_version is None):
            raise ValueError("an existing comparison ID requires its expected version")
        return self


AssistantOperation = Annotated[
    RefineRequirements | ShortlistProduct | RejectProduct | AddNote | SetComparisonDimensions,
    Field(discriminator="operation"),
]


class InterpretationOutput(StrictModel):
    assistant_message: str = Field(min_length=1, max_length=6000)
    clarification_questions: list[str] = Field(default_factory=list, max_length=5)
    citation_ids: list[UUID] = Field(default_factory=list, max_length=30)
    project_updates: IntentProjectUpdates = Field(default_factory=IntentProjectUpdates)
    requirement_operations: list[RequirementOperation] = Field(default_factory=list, max_length=20)
    operations: list[AssistantOperation] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bound_questions(self) -> InterpretationOutput:
        if any(not question or len(question) > 500 for question in self.clarification_questions):
            raise ValueError("clarification questions must contain 1 to 500 characters")
        return self

    @model_validator(mode="after")
    def unambiguous_operations(self) -> InterpretationOutput:
        if self.operations and (
            self.project_updates.model_fields_set or self.requirement_operations
        ):
            raise ValueError("use either explicit operations or the compatibility fields, not both")
        if sum(isinstance(item, RefineRequirements) for item in self.operations) > 1:
            raise ValueError("only one requirements refinement operation is allowed")
        return self

    def mutation_payload(self) -> dict[str, Any] | None:
        updates = self.project_updates.model_dump(exclude_unset=True, exclude_none=True)
        requirement_operations = [
            item.model_dump(mode="json", exclude_unset=True) for item in self.requirement_operations
        ]
        decision_operations: list[dict[str, Any]] = []
        for operation in self.operations:
            if isinstance(operation, RefineRequirements):
                updates = operation.project_updates.model_dump(
                    exclude_unset=True, exclude_none=True
                )
                requirement_operations = [
                    item.model_dump(mode="json", exclude_unset=True)
                    for item in operation.requirement_operations
                ]
            else:
                decision_operations.append(operation.model_dump(mode="json", exclude_unset=True))
        if not updates and not requirement_operations and not decision_operations:
            return None
        return {
            "project_updates": updates,
            "requirement_operations": requirement_operations,
            "decision_operations": decision_operations,
        }


class MessageCreate(StrictModel):
    text: str = Field(min_length=1, max_length=8000)
    request_key: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    selected_project_product_ids: list[UUID] = Field(default_factory=list, max_length=6)
    comparison_id: UUID | None = None

    @model_validator(mode="after")
    def nonblank_text(self) -> MessageCreate:
        if not self.text:
            raise ValueError("text must contain non-whitespace characters")
        if len(self.selected_project_product_ids) != len(set(self.selected_project_product_ids)):
            raise ValueError("assistant scope products must be unique")
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
    citation_ids: list[UUID] = Field(default_factory=list)
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
