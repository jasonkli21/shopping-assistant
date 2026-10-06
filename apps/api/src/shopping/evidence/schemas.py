from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SourceAttemptRead(BaseModel):
    id: UUID
    snapshot_id: UUID | None
    source_id: UUID
    requested_url: str
    final_url: str
    title: str | None
    publisher: str | None
    classification: str
    classification_basis: str | None
    status: str
    reason: str | None
    retrieved_at: datetime
    published_at: datetime | None
    freshness: Literal["current", "stale", "unknown"]
    bytes_read: int | None
    offer_status: (
        Literal["succeeded", "no_offer", "identity_mismatch", "unsupported", "failed"] | None
    ) = None
    offer_error_code: str | None = None
    offer_observation: dict[str, Any] = Field(default_factory=dict)


class ClaimSummaryRead(BaseModel):
    id: UUID
    attribute_key: str
    assertion_text: str
    evidence_category: str
    qualifiers: dict[str, Any]
    source_id: UUID
    snapshot_id: UUID
    source_title: str | None
    source_url: str
    published_at: datetime | None
    retrieved_at: datetime
    freshness: Literal["current", "stale", "unknown"]


class ClaimRelationRead(BaseModel):
    related_claim_id: UUID
    relation: str
    basis: str
    origin: str


class ClaimDetailRead(ClaimSummaryRead):
    normalized_value: Any = None
    evidence_excerpt: str
    locator: dict[str, Any]
    content_hash: str
    validation_warnings: list[dict[str, Any]]
    relations: list[ClaimRelationRead]


class AssessmentRead(BaseModel):
    id: UUID
    research_run_id: UUID
    project_product_id: UUID
    project_revision: int
    product_revision: int
    variant_revision: int
    generated_at: datetime
    context_stale: bool
    summary: str
    conclusions: list[dict[str, Any]]
    uncertainties: list[str]


class ProjectProductResearchRead(BaseModel):
    project_product_id: UUID
    latest_run_id: UUID | None
    latest_run_status: str | None
    assessments: list[AssessmentRead]
    has_more_assessments: bool
    claims: list[ClaimSummaryRead]
    has_more_claims: bool
    sources: list[SourceAttemptRead]
    has_more_sources: bool
    state: Literal["no_research", "no_evidence", "blocked", "partial", "researched"]


class SourceSnapshotRead(BaseModel):
    id: UUID
    source_id: UUID
    title: str | None
    final_url: str
    classification: str
    content_hash: str
    published_at: datetime | None
    retrieved_at: datetime
    excerpt: str = Field(max_length=1000)
    claims: list[ClaimSummaryRead]


class ProductSourcesRead(BaseModel):
    product_id: UUID
    variant_id: UUID | None
    sources: list[SourceAttemptRead]
