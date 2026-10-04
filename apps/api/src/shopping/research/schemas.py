from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shopping.catalog.schemas import CandidateNormalizationState


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchBudgets(StrictModel):
    max_queries: int | None = Field(default=None, ge=1, le=20)
    max_candidates: int | None = Field(default=None, ge=1, le=100)
    max_results: int | None = Field(default=None, ge=1, le=200)
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)
    max_attempts: int | None = Field(default=None, ge=1, le=20)
    max_products: int | None = Field(default=None, ge=1, le=5)
    max_sources_per_product: int | None = Field(default=None, ge=1, le=12)
    max_pages: int | None = Field(default=None, ge=1, le=30)
    max_total_bytes: int | None = Field(default=None, ge=1, le=10_000_000)
    max_ai_calls: int | None = Field(default=None, ge=1, le=60)
    max_output_chars: int | None = Field(default=None, ge=1, le=32_000)
    deadline_seconds: int | None = Field(default=None, ge=1, le=300)
    max_concurrent: int | None = Field(default=None, ge=1, le=16)


class ResearchCreate(StrictModel):
    objective: str = Field(min_length=1, max_length=2000)
    type: Literal["discovery", "product_research"] = "discovery"
    request_key: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    budgets: ResearchBudgets = Field(default_factory=ResearchBudgets)
    manual_queries: list[Annotated[str, Field(min_length=1, max_length=300)]] | None = Field(
        default=None, min_length=1, max_length=20
    )
    selected_project_product_ids: list[UUID] | None = Field(
        default=None, min_length=1, max_length=5
    )

    @field_validator("objective")
    @classmethod
    def objective_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("objective must contain non-whitespace characters")
        return value

    @field_validator("manual_queries")
    @classmethod
    def validate_manual_queries(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [item.casefold() for item in values]
        if any(not item for item in values) or len(normalized) != len(set(normalized)):
            raise ValueError("manual queries must be nonblank and unique")
        return values

    @field_validator("selected_project_product_ids")
    @classmethod
    def selected_products_unique(cls, values: list[UUID] | None) -> list[UUID] | None:
        if values is not None and len(values) != len(set(values)):
            raise ValueError("selected project products must be unique")
        return values

    @model_validator(mode="after")
    def research_type_requires_targets(self):
        if self.type == "product_research" and not self.selected_project_product_ids:
            raise ValueError("product research requires selected project products")
        if self.type == "discovery" and self.selected_project_product_ids is not None:
            raise ValueError("selected products are only valid for product research")
        if self.type == "product_research" and self.manual_queries is not None:
            raise ValueError("manual queries are only valid for discovery")
        return self


class SearchAttemptRead(BaseModel):
    id: UUID
    attempt_number: int
    provider: str
    status: Literal["running", "succeeded", "failed", "canceled"]
    error_code: str | None = None
    provider_request_id: str | None = None
    results_count: int
    usage_units: int | None = None
    started_at: datetime
    finished_at: datetime | None = None


class SearchQueryRead(BaseModel):
    id: UUID
    target_project_product_id: UUID | None = None
    ordinal: int
    text: str
    purpose: str
    max_results: int
    state: Literal["queued", "running", "succeeded", "failed", "skipped", "canceled"]
    results_count: int
    candidates_count: int
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: list[SearchAttemptRead]


class ResearchRunRead(BaseModel):
    id: UUID
    project_id: UUID
    objective: str
    type: Literal["discovery", "product_research"]
    status: Literal[
        "queued", "running", "succeeded", "partial", "failed", "canceled", "interrupted"
    ]
    snapshot_revision: int
    effective_budgets: dict[str, int]
    queries_planned: int
    queries_completed: int
    queries_failed: int
    attempts_used: int
    results_found: int
    candidates_found: int
    skipped_count: int
    summary: str | None = None
    error_code: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    replayed: bool = False
    queries: list[SearchQueryRead] = Field(default_factory=list)
    targets: list[ResearchTargetProgressRead] = Field(default_factory=list)
    stages: list[ResearchStageProgressRead] = Field(default_factory=list)


class ResearchStageProgressRead(BaseModel):
    stage: Literal["planning", "extraction", "relations", "assessment"]
    target_project_product_id: UUID | None
    source_snapshot_id: UUID | None
    attempt_number: int
    status: Literal["running", "succeeded", "failed", "skipped", "canceled"]
    error_code: str | None
    validation_warnings: list[dict[str, object]]


class ResearchTargetProgressRead(BaseModel):
    project_product_id: UUID
    product_id: UUID
    variant_id: UUID
    status: Literal["queued", "running", "succeeded", "partial", "failed", "skipped"]
    sources_attempted: int
    sources_retrieved: int
    claims_created: int
    error_code: str | None = None


class ResearchCreated(BaseModel):
    run_id: UUID
    status: str
    replayed: bool


class ResearchRunPage(BaseModel):
    items: list[ResearchRunRead]
    next_cursor: str | None = None


class CandidateResultRead(BaseModel):
    search_result_id: UUID
    query_id: UUID
    query_text: str
    purpose: str
    title: str
    url: str
    snippet: str | None
    result_rank: int
    received_at: datetime


class CandidateRead(BaseModel):
    id: UUID
    project_id: UUID
    research_run_id: UUID
    provisional_name: str
    brand_clue: str | None = None
    model_clue: str | None = None
    category_clue: str | None = None
    discovery_reason: str
    indicative_price_text: str | None = None
    observed_at: datetime
    search_results: list[CandidateResultRead]
    normalization: CandidateNormalizationState | None = None


class CandidatePage(BaseModel):
    items: list[CandidateRead]
    next_cursor: str | None = None


class CancelResult(BaseModel):
    run: ResearchRunRead
    replayed: bool
