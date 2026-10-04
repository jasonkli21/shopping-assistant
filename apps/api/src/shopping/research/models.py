from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shopping.db.base import Base


class ResearchRun(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type IN ('discovery', 'product_research')", name="ck_research_run_type"
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', "
            "'canceled', 'interrupted')",
            name="ck_research_run_status",
        ),
        CheckConstraint("char_length(objective) BETWEEN 1 AND 2000", name="ck_research_objective"),
        CheckConstraint("snapshot_revision >= 1", name="ck_research_snapshot_revision"),
        CheckConstraint(
            "queries_planned >= 0 AND queries_completed >= 0 AND queries_failed >= 0",
            name="ck_research_query_counts",
        ),
        CheckConstraint(
            "attempts_used >= 0 AND results_found >= 0 AND candidates_found >= 0 "
            "AND skipped_count >= 0",
            name="ck_research_work_counts",
        ),
        Index("ix_research_runs_project_queued", "owner_id", "project_id", "queued_at"),
        UniqueConstraint(
            "owner_id", "project_id", "request_key", name="uq_research_runs_request_key"
        ),
        Index(
            "uq_research_runs_one_active_project",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    objective: Mapped[str] = mapped_column(String(2000), nullable=False)
    run_type: Mapped[str] = mapped_column(String(24), nullable=False, default="discovery")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    request_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    effective_budgets: Mapped[dict] = mapped_column(JSONB, nullable=False)
    task_name: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ai_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    search_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    queries_planned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queries_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queries_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    results_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidates_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(String(2000))
    error_code: Mapped[str | None] = mapped_column(String(60))
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    queries: Mapped[list[SearchQueryRecord]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="SearchQueryRecord.ordinal"
    )
    targets: Mapped[list[ResearchRunTarget]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ResearchRunTarget.created_at",
    )


class SearchQueryRecord(Base):
    __tablename__ = "search_queries"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_search_query_ordinal"),
        CheckConstraint("max_results BETWEEN 1 AND 20", name="ck_search_query_max_results"),
        CheckConstraint(
            "state IN ('queued', 'running', 'succeeded', 'failed', 'skipped', 'canceled')",
            name="ck_search_query_state",
        ),
        UniqueConstraint("run_id", "ordinal", name="uq_search_query_run_ordinal"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    target_project_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="SET NULL")
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidates_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[ResearchRun] = relationship(back_populates="queries")
    attempts: Mapped[list[SearchAttempt]] = relationship(
        back_populates="query",
        cascade="all, delete-orphan",
        order_by="SearchAttempt.attempt_number",
    )


class ResearchRunTarget(Base):
    __tablename__ = "research_run_targets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'skipped')",
            name="ck_research_run_target_status",
        ),
        CheckConstraint(
            "sources_attempted >= 0 AND sources_retrieved >= 0 AND claims_created >= 0",
            name="ck_research_run_target_counts",
        ),
        UniqueConstraint("research_run_id", "project_product_id", name="uq_research_run_target"),
        Index("ix_research_run_targets_status", "research_run_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    research_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    project_product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    product_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    sources_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_retrieved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    run: Mapped[ResearchRun] = relationship(back_populates="targets")


class ResearchStageAttempt(Base):
    __tablename__ = "research_stage_attempts"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('planning', 'extraction', 'relations', 'assessment')",
            name="ck_research_stage_attempt_stage",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'skipped', 'canceled')",
            name="ck_research_stage_attempt_status",
        ),
        CheckConstraint("attempt_number BETWEEN 1 AND 3", name="ck_research_stage_attempt_number"),
        CheckConstraint(
            "input_chars BETWEEN 0 AND 24000 AND output_chars BETWEEN 0 AND 16000",
            name="ck_research_stage_attempt_chars",
        ),
        Index(
            "uq_research_stage_attempt_global",
            "research_run_id",
            "stage",
            "attempt_number",
            unique=True,
            postgresql_where=text("target_project_product_id IS NULL"),
        ),
        Index(
            "uq_research_stage_attempt_target",
            "research_run_id",
            "target_project_product_id",
            "stage",
            "attempt_number",
            unique=True,
            postgresql_where=text("target_project_product_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    research_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    target_project_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="SET NULL")
    )
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    task_name: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60))
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchAttempt(Base):
    __tablename__ = "search_attempts"
    __table_args__ = (
        CheckConstraint("attempt_number >= 1", name="ck_search_attempt_number"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'canceled')",
            name="ck_search_attempt_status",
        ),
        CheckConstraint(
            "usage_units IS NULL OR usage_units BETWEEN 0 AND 100000",
            name="ck_search_attempt_usage_units",
        ),
        UniqueConstraint("query_id", "attempt_number", name="uq_search_attempt_query_number"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    query_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("search_queries.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    error_code: Mapped[str | None] = mapped_column(String(60))
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_units: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    query: Mapped[SearchQueryRecord] = relationship(back_populates="attempts")


class SearchResult(Base):
    __tablename__ = "search_results"
    __table_args__ = (
        CheckConstraint("result_rank >= 1", name="ck_search_result_rank"),
        CheckConstraint("char_length(title) <= 300", name="ck_search_result_title_length"),
        CheckConstraint("char_length(url) <= 2048", name="ck_search_result_url_length"),
        CheckConstraint(
            "snippet IS NULL OR char_length(snippet) <= 2000",
            name="ck_search_result_snippet_length",
        ),
        UniqueConstraint("query_id", "result_rank", name="uq_search_result_query_rank"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    query_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("search_queries.id", ondelete="CASCADE"), nullable=False
    )
    attempt_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("search_attempts.id", ondelete="CASCADE"), nullable=False
    )
    result_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    snippet: Mapped[str | None] = mapped_column(String(2000))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    provider_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class DiscoveryCandidate(Base):
    __tablename__ = "discovery_candidates"
    __table_args__ = (
        CheckConstraint(
            "char_length(provisional_name) BETWEEN 1 AND 300", name="ck_candidate_name"
        ),
        CheckConstraint("char_length(normalized_url) <= 2048", name="ck_candidate_normalized_url"),
        UniqueConstraint("run_id", "normalized_url", name="uq_candidate_run_normalized_url"),
        Index("ix_candidates_project_created", "project_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    provisional_name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand_clue: Mapped[str | None] = mapped_column(String(200))
    model_clue: Mapped[str | None] = mapped_column(String(200))
    category_clue: Mapped[str | None] = mapped_column(String(100))
    discovery_reason: Mapped[str] = mapped_column(String(300), nullable=False)
    indicative_price_text: Mapped[str | None] = mapped_column(String(200))
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_mapping_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "project_products.id",
            name="fk_discovery_candidate_canonical_mapping",
            ondelete="SET NULL",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    search_results: Mapped[list[SearchResult]] = relationship(
        secondary="candidate_search_results", order_by="SearchResult.received_at"
    )


class CandidateSearchResult(Base):
    __tablename__ = "candidate_search_results"
    __table_args__ = (
        UniqueConstraint("candidate_id", "search_result_id", name="uq_candidate_search_result"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("discovery_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    search_result_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("search_results.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
