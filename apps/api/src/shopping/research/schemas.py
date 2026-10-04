from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchBudgets(StrictModel):
    max_queries: int | None = Field(default=None, ge=1, le=20)
    max_candidates: int | None = Field(default=None, ge=1, le=100)
    max_results: int | None = Field(default=None, ge=1, le=200)
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)
    max_attempts: int | None = Field(default=None, ge=1, le=20)
    deadline_seconds: int | None = Field(default=None, ge=1, le=300)
    max_concurrent: int | None = Field(default=None, ge=1, le=16)


class ResearchCreate(StrictModel):
    objective: str = Field(min_length=1, max_length=2000)
    type: Literal["discovery"] = "discovery"
    request_key: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    budgets: ResearchBudgets = Field(default_factory=ResearchBudgets)
    manual_queries: list[Annotated[str, Field(min_length=1, max_length=300)]] | None = Field(
        default=None, min_length=1, max_length=20
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
    type: Literal["discovery"]
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


class ResearchCreated(BaseModel):
    run_id: UUID
    status: str
    replayed: bool


class ResearchRunPage(BaseModel):
    items: list[ResearchRunRead]


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


class CandidatePage(BaseModel):
    items: list[CandidateRead]
    next_cursor: str | None = None


class CancelResult(BaseModel):
    run: ResearchRunRead
    replayed: bool
