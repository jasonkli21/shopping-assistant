"""Owner- and project-scoped evidence inspection views."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct
from shopping.evidence.models import (
    Claim,
    ClaimEvidence,
    ClaimRelation,
    ProductAssessment,
    ResearchRunSource,
    Source,
    SourceSnapshot,
)
from shopping.evidence.schemas import (
    AssessmentRead,
    ClaimDetailRead,
    ClaimRelationRead,
    ClaimSummaryRead,
    ProductSourcesRead,
    ProjectProductResearchRead,
    SourceAttemptRead,
    SourceSnapshotRead,
)
from shopping.projects.models import ShoppingProject
from shopping.research.common import _live_project, _not_found
from shopping.research.models import ResearchRun, ResearchRunTarget


def freshness(
    category: str, *, published_at: datetime | None, retrieved_at: datetime, now: datetime
) -> str:
    if category == "retailer_listing":
        date, limit = retrieved_at, timedelta(hours=24)
    elif published_at is None:
        return "unknown"
    elif category in {"manufacturer_specification", "manufacturer_claim"}:
        date, limit = published_at, timedelta(days=365)
    else:
        date, limit = published_at, timedelta(days=90)
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    return "stale" if now - date > limit else "current"


def _member(
    session: Session, owner_id: UUID, project_id: UUID, project_product_id: UUID
) -> tuple[ShoppingProject, ProjectProduct, ProductVariant, Product]:
    project = _live_project(session, owner_id, project_id)
    row = session.execute(
        select(ProjectProduct, ProductVariant, Product)
        .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProjectProduct.id == project_product_id,
            ProjectProduct.project_id == project_id,
            Product.owner_id == owner_id,
        )
    ).one_or_none()
    if row is None:
        raise _not_found("Selected product not found in this project")
    return project, *row


def _claim_summary(claim: Claim, snapshot: SourceSnapshot, source: Source, now: datetime):
    return ClaimSummaryRead(
        id=claim.id,
        attribute_key=claim.attribute_key,
        assertion_text=claim.assertion_text,
        evidence_category=claim.evidence_category,
        qualifiers=claim.qualifiers,
        source_id=source.id,
        snapshot_id=snapshot.id,
        source_title=snapshot.title or source.title,
        source_url=source.normalized_url,
        published_at=snapshot.published_at,
        retrieved_at=snapshot.retrieved_at,
        freshness=freshness(
            claim.evidence_category,
            published_at=snapshot.published_at,
            retrieved_at=snapshot.retrieved_at,
            now=now,
        ),
    )


def _source_read(
    attempt: ResearchRunSource, snapshot: SourceSnapshot | None, source: Source, now: datetime
):
    return SourceAttemptRead(
        id=attempt.id,
        snapshot_id=snapshot.id if snapshot else None,
        source_id=source.id,
        requested_url=attempt.requested_url,
        final_url=attempt.final_url,
        title=(snapshot.title if snapshot else None) or source.title,
        publisher=source.publisher,
        classification=source.classification,
        classification_basis=source.classification_basis,
        status=attempt.status,
        reason=attempt.reason,
        retrieved_at=attempt.retrieved_at,
        published_at=snapshot.published_at if snapshot else None,
        freshness=(
            freshness(
                source.classification,
                published_at=snapshot.published_at,
                retrieved_at=attempt.retrieved_at,
                now=now,
            )
            if snapshot
            else "unknown"
        ),
        bytes_read=attempt.bytes_read,
    )


def project_product_research(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    project_product_id: UUID,
    *,
    now: datetime | None = None,
) -> ProjectProductResearchRead:
    now = now or datetime.now(UTC)
    project, _membership, variant, product = _member(
        session, owner_id, project_id, project_product_id
    )
    assessments = list(
        session.scalars(
            select(ProductAssessment)
            .where(
                ProductAssessment.owner_id == owner_id,
                ProductAssessment.project_id == project_id,
                ProductAssessment.project_product_id == project_product_id,
            )
            .order_by(ProductAssessment.generated_at.desc(), ProductAssessment.id.desc())
            .limit(20)
        ).all()
    )
    assessment_reads = [
        AssessmentRead(
            id=item.id,
            research_run_id=item.research_run_id,
            project_product_id=item.project_product_id,
            project_revision=item.project_revision,
            product_revision=item.product_revision,
            variant_revision=item.variant_revision,
            generated_at=item.generated_at,
            context_stale=(
                item.project_revision != project.revision
                or item.product_revision != product.revision
                or item.variant_revision != variant.revision
            ),
            summary=item.summary,
            conclusions=item.conclusions,
            uncertainties=item.uncertainties,
        )
        for item in assessments
    ]
    source_rows = session.execute(
        select(ResearchRunSource, SourceSnapshot, Source)
        .join(ResearchRun, ResearchRun.id == ResearchRunSource.research_run_id)
        .join(Source, Source.id == ResearchRunSource.source_id)
        .outerjoin(SourceSnapshot, SourceSnapshot.id == ResearchRunSource.snapshot_id)
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRunSource.owner_id == owner_id,
            ResearchRunSource.project_product_id == project_product_id,
            Source.owner_id == owner_id,
        )
        .order_by(ResearchRunSource.retrieved_at.desc(), ResearchRunSource.id.desc())
        .limit(100)
    ).all()
    sources = [
        _source_read(attempt, snapshot, source, now) for attempt, snapshot, source in source_rows
    ]
    snapshot_ids = [source.snapshot_id for source in sources if source.snapshot_id is not None]
    claim_rows = session.execute(
        select(Claim, SourceSnapshot, Source)
        .join(SourceSnapshot, SourceSnapshot.id == Claim.snapshot_id)
        .join(Source, Source.id == SourceSnapshot.source_id)
        .where(
            Claim.owner_id == owner_id,
            Claim.subject_product_id == product.id,
            Claim.subject_variant_id == variant.id,
            Claim.snapshot_id.in_(snapshot_ids),
            SourceSnapshot.owner_id == owner_id,
            Source.owner_id == owner_id,
        )
        .order_by(Claim.extracted_at.desc(), Claim.id.desc())
        .limit(200)
    ).all()
    claims = [
        _claim_summary(claim, snapshot, source, now) for claim, snapshot, source in claim_rows
    ]
    if not sources:
        state = "no_research"
    elif not claims and all(
        item.status in {"blocked", "timeout", "unsupported", "failed", "skipped"}
        for item in sources
    ):
        state = "blocked"
    elif not claims:
        state = "no_evidence"
    elif any(item.status != "retrieved" for item in sources):
        state = "partial"
    else:
        state = "researched"
    return ProjectProductResearchRead(
        project_product_id=project_product_id,
        assessments=assessment_reads,
        claims=claims,
        sources=sources,
        state=state,
    )


def claim_detail(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    claim_id: UUID,
    *,
    now: datetime | None = None,
) -> ClaimDetailRead:
    now = now or datetime.now(UTC)
    _live_project(session, owner_id, project_id)
    row = session.execute(
        select(Claim, ClaimEvidence, SourceSnapshot, Source)
        .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
        .join(SourceSnapshot, SourceSnapshot.id == Claim.snapshot_id)
        .join(Source, Source.id == SourceSnapshot.source_id)
        .where(
            Claim.id == claim_id,
            Claim.owner_id == owner_id,
            SourceSnapshot.owner_id == owner_id,
            Source.owner_id == owner_id,
        )
    ).first()
    if row is None:
        raise _not_found("Claim not found in this project")
    claim, evidence, snapshot, source = row
    authorized = session.scalar(
        select(ResearchRunSource.id)
        .join(ResearchRun, ResearchRun.id == ResearchRunSource.research_run_id)
        .join(ProjectProduct, ProjectProduct.id == ResearchRunSource.project_product_id)
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRunSource.owner_id == owner_id,
            ResearchRunSource.snapshot_id == claim.snapshot_id,
            ProjectProduct.project_id == project_id,
            ProjectProduct.variant_id == claim.subject_variant_id,
        )
    )
    if authorized is None:
        raise _not_found("Claim not found in this project")
    relations = session.scalars(
        select(ClaimRelation).where(
            ClaimRelation.owner_id == owner_id,
            or_(ClaimRelation.claim_id == claim.id, ClaimRelation.related_claim_id == claim.id),
        )
    ).all()
    return ClaimDetailRead(
        **_claim_summary(claim, snapshot, source, now).model_dump(),
        normalized_value=claim.normalized_value,
        evidence_excerpt=evidence.excerpt,
        locator=evidence.locator,
        content_hash=evidence.content_hash,
        validation_warnings=claim.validation_warnings,
        relations=[
            ClaimRelationRead(
                related_claim_id=(
                    relation.related_claim_id
                    if relation.claim_id == claim.id
                    else relation.claim_id
                ),
                relation=relation.relation,
                basis=relation.basis,
                origin=relation.origin,
            )
            for relation in relations
        ],
    )


def source_snapshot_detail(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    snapshot_id: UUID,
    *,
    now: datetime | None = None,
) -> SourceSnapshotRead:
    now = now or datetime.now(UTC)
    _live_project(session, owner_id, project_id)
    row = session.execute(
        select(SourceSnapshot, Source, ResearchRunSource)
        .join(Source, Source.id == SourceSnapshot.source_id)
        .join(ResearchRunSource, ResearchRunSource.snapshot_id == SourceSnapshot.id)
        .join(ResearchRun, ResearchRun.id == ResearchRunSource.research_run_id)
        .where(
            SourceSnapshot.id == snapshot_id,
            SourceSnapshot.owner_id == owner_id,
            Source.owner_id == owner_id,
            ResearchRunSource.owner_id == owner_id,
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
        )
        .limit(1)
    ).first()
    if row is None:
        raise _not_found("Source snapshot not found in this project")
    snapshot, source, attempt = row
    claims = session.scalars(
        select(Claim)
        .join(ProjectProduct, ProjectProduct.variant_id == Claim.subject_variant_id)
        .where(
            Claim.owner_id == owner_id,
            Claim.snapshot_id == snapshot.id,
            ProjectProduct.id == attempt.project_product_id,
            ProjectProduct.project_id == project_id,
        )
        .limit(100)
    ).all()
    return SourceSnapshotRead(
        id=snapshot.id,
        source_id=source.id,
        title=snapshot.title or source.title,
        final_url=attempt.final_url,
        classification=source.classification,
        content_hash=snapshot.content_hash,
        published_at=snapshot.published_at,
        retrieved_at=snapshot.retrieved_at,
        excerpt=snapshot.relevant_text[:1000],
        claims=[_claim_summary(claim, snapshot, source, now) for claim in claims],
    )


def product_sources(
    session: Session,
    owner_id: UUID,
    product_id: UUID,
    variant_id: UUID | None,
    *,
    now: datetime | None = None,
) -> ProductSourcesRead:
    now = now or datetime.now(UTC)
    product = session.scalar(
        select(Product).where(Product.id == product_id, Product.owner_id == owner_id)
    )
    if product is None:
        raise _not_found("Product not found")
    if (
        variant_id is not None
        and session.scalar(
            select(ProductVariant.id).where(
                ProductVariant.id == variant_id, ProductVariant.product_id == product_id
            )
        )
        is None
    ):
        raise _not_found("Variant not found")
    query = (
        select(ResearchRunSource, SourceSnapshot, Source)
        .join(
            ResearchRunTarget,
            ResearchRunTarget.research_run_id == ResearchRunSource.research_run_id,
        )
        .join(Source, Source.id == ResearchRunSource.source_id)
        .outerjoin(SourceSnapshot, SourceSnapshot.id == ResearchRunSource.snapshot_id)
        .where(
            ResearchRunTarget.project_product_id == ResearchRunSource.project_product_id,
            ResearchRunTarget.owner_id == owner_id,
            ResearchRunTarget.product_id == product_id,
            ResearchRunSource.owner_id == owner_id,
            Source.owner_id == owner_id,
        )
        .order_by(ResearchRunSource.retrieved_at.desc())
        .limit(100)
    )
    if variant_id is not None:
        query = query.where(ResearchRunTarget.variant_id == variant_id)
    rows = session.execute(query).all()
    return ProductSourcesRead(
        product_id=product_id,
        variant_id=variant_id,
        sources=[
            _source_read(attempt, snapshot, source, now) for attempt, snapshot, source in rows
        ],
    )
