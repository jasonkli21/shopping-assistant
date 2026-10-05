from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shopping.db.base import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("char_length(normalized_url) BETWEEN 1 AND 2048", name="ck_source_url"),
        CheckConstraint("char_length(title) <= 300", name="ck_source_title"),
        CheckConstraint("char_length(publisher) <= 200", name="ck_source_publisher"),
        CheckConstraint("char_length(domain) <= 253", name="ck_source_domain"),
        CheckConstraint(
            "classification IN ('manufacturer_specification', 'manufacturer_claim', "
            "'retailer_listing', 'independent_measurement', 'editorial_assessment', "
            "'community_observation', 'individual_anecdote', 'unknown')",
            name="ck_source_classification",
        ),
        UniqueConstraint("owner_id", "normalized_url", name="uq_source_owner_url"),
        Index("ix_sources_owner_domain", "owner_id", "domain"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    publisher: Mapped[str | None] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    classification_basis: Mapped[str | None] = mapped_column(String(500))
    classification_actor: Mapped[str] = mapped_column(String(24), nullable=False, default="system")
    classification_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="source-classifier.v1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_source_snapshot_hash"),
        CheckConstraint("char_length(media_type) <= 200", name="ck_source_snapshot_media_type"),
        CheckConstraint("char_length(title) <= 300", name="ck_source_snapshot_title"),
        CheckConstraint(
            "octet_length(relevant_text) <= 12000", name="ck_source_snapshot_text_size"
        ),
        CheckConstraint(
            "octet_length(excerpts::text) <= 12000", name="ck_source_snapshot_excerpts_size"
        ),
        UniqueConstraint("source_id", "content_hash", name="uq_source_snapshot_content"),
        UniqueConstraint("id", "owner_id", name="uq_source_snapshot_owner"),
        Index("ix_source_snapshots_source_time", "source_id", "retrieved_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    relevant_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    excerpts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    extractor_version: Mapped[str] = mapped_column(String(80), nullable=False)


class ResearchRunSource(Base):
    __tablename__ = "research_run_sources"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'retrieved', 'blocked', 'timeout', 'unsupported', "
            "'failed', 'skipped')",
            name="ck_research_run_source_status",
        ),
        CheckConstraint("attempt_number >= 1", name="ck_research_run_source_attempt"),
        CheckConstraint(
            "bytes_read IS NULL OR bytes_read BETWEEN 0 AND 20000000",
            name="ck_research_run_source_bytes",
        ),
        CheckConstraint(
            "char_length(requested_url) <= 2048 AND char_length(final_url) <= 2048",
            name="ck_research_run_source_urls",
        ),
        UniqueConstraint(
            "research_run_id",
            "project_product_id",
            "source_id",
            "attempt_number",
            name="uq_research_run_source_attempt",
        ),
        Index(
            "ix_research_run_sources_target_time",
            "research_run_id",
            "project_product_id",
            "retrieved_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    research_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    project_product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="RESTRICT"), nullable=False
    )
    search_result_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("search_results.id", ondelete="SET NULL")
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_snapshots.id", ondelete="RESTRICT")
    )
    requested_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80))
    bytes_read: Mapped[int | None] = mapped_column(Integer)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("char_length(attribute_key) BETWEEN 1 AND 100", name="ck_claim_attribute"),
        CheckConstraint("char_length(assertion_text) BETWEEN 1 AND 800", name="ck_claim_text"),
        CheckConstraint(
            "evidence_category IN ('manufacturer_specification', 'manufacturer_claim', "
            "'retailer_listing', 'independent_measurement', 'editorial_assessment', "
            "'community_observation', 'individual_anecdote')",
            name="ck_claim_category",
        ),
        CheckConstraint("octet_length(qualifiers::text) <= 6000", name="ck_claim_qualifiers_size"),
        CheckConstraint(
            "octet_length(validation_warnings::text) <= 4000", name="ck_claim_warnings_size"
        ),
        UniqueConstraint("id", "owner_id", name="uq_claim_owner"),
        UniqueConstraint(
            "snapshot_id",
            "subject_variant_id",
            "prompt_version",
            "fingerprint",
            name="uq_claim_extraction_fingerprint",
        ),
        Index("ix_claims_subject_attribute", "owner_id", "subject_variant_id", "attribute_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    subject_product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    subject_variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    attribute_key: Mapped[str] = mapped_column(String(100), nullable=False)
    assertion_text: Mapped[str] = mapped_column(String(800), nullable=False)
    normalized_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONB)
    qualifiers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_category: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    task_name: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    extraction_confidence: Mapped[str | None] = mapped_column(String(24))
    validation_warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        CheckConstraint(
            "char_length(excerpt) BETWEEN 1 AND 1000", name="ck_claim_evidence_excerpt"
        ),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_claim_evidence_hash"),
        UniqueConstraint("claim_id", "content_hash", "excerpt", name="uq_claim_evidence_quote"),
        Index("ix_claim_evidence_claim", "claim_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("claims.id", ondelete="RESTRICT"), nullable=False
    )
    excerpt: Mapped[str] = mapped_column(String(1000), nullable=False)
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ClaimRelation(Base):
    __tablename__ = "claim_relations"
    __table_args__ = (
        CheckConstraint(
            "relation IN ('supports', 'contradicts', 'different_context', 'duplicate')",
            name="ck_claim_relation_type",
        ),
        CheckConstraint("origin IN ('system', 'ai', 'user')", name="ck_claim_relation_origin"),
        CheckConstraint("claim_id < related_claim_id", name="ck_claim_relation_order"),
        UniqueConstraint("claim_id", "related_claim_id", "relation", name="uq_claim_relation"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("claims.id", ondelete="RESTRICT"), nullable=False
    )
    related_claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("claims.id", ondelete="RESTRICT"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(24), nullable=False)
    basis: Mapped[str] = mapped_column(String(500), nullable=False)
    origin: Mapped[str] = mapped_column(String(8), nullable=False)
    task_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductAssessment(Base):
    __tablename__ = "product_assessments"
    __table_args__ = (
        CheckConstraint("char_length(summary) <= 1200", name="ck_assessment_summary"),
        CheckConstraint(
            "octet_length(requirements_snapshot::text) <= 1500000",
            name="ck_assessment_requirements_size",
        ),
        CheckConstraint(
            "octet_length(conclusions::text) <= 1500000", name="ck_assessment_conclusions_size"
        ),
        UniqueConstraint(
            "owner_id",
            "research_run_id",
            "project_product_id",
            "task_version",
            name="uq_assessment_run_target_task",
        ),
        Index(
            "ix_assessments_project_product_time", "owner_id", "project_product_id", "generated_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("shopping_projects.id", ondelete="CASCADE"), nullable=False
    )
    project_product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_products.id", ondelete="RESTRICT"), nullable=False
    )
    research_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    project_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    requirements_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    product_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    snapshot_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    conclusions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(String(1200), nullable=False, default="")
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    concerns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    uncertainties: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    task_name: Mapped[str] = mapped_column(String(80), nullable=False)
    task_version: Mapped[str] = mapped_column(String(80), nullable=False)
    ai_provider: Mapped[str] = mapped_column(String(40), nullable=False)


class AssessmentCitation(Base):
    __tablename__ = "assessment_citations"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "claim_id", "requirement_id", name="uq_assessment_citation"
        ),
        Index("ix_assessment_citations_claim", "claim_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    assessment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_assessments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("claims.id", ondelete="RESTRICT"), nullable=False
    )
    requirement_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_requirements.id", ondelete="SET NULL")
    )
    rationale: Mapped[str] = mapped_column(String(500), nullable=False, default="")
