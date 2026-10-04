"""Persist only claims grounded in a stored, owner-scoped source snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.evidence.claim_task import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TASK_NAME,
    ValidatedExtraction,
)
from shopping.evidence.models import Claim, ClaimEvidence, ResearchRunSource, Source, SourceSnapshot
from shopping.research.models import ResearchRunTarget


def extraction_input(
    session: Session, *, owner_id: UUID, run_id: UUID, target_id: UUID, attempt_id: UUID
) -> tuple[dict, dict, str] | None:
    row = session.execute(
        select(ResearchRunSource, SourceSnapshot, Source, ResearchRunTarget)
        .join(SourceSnapshot, SourceSnapshot.id == ResearchRunSource.snapshot_id)
        .join(Source, Source.id == SourceSnapshot.source_id)
        .join(
            ResearchRunTarget,
            (ResearchRunTarget.research_run_id == ResearchRunSource.research_run_id)
            & (ResearchRunTarget.project_product_id == ResearchRunSource.project_product_id),
        )
        .where(
            ResearchRunSource.id == attempt_id,
            ResearchRunSource.owner_id == owner_id,
            ResearchRunSource.research_run_id == run_id,
            ResearchRunSource.project_product_id == target_id,
            ResearchRunSource.status == "retrieved",
            SourceSnapshot.owner_id == owner_id,
            Source.owner_id == owner_id,
            ResearchRunTarget.owner_id == owner_id,
        )
    ).one_or_none()
    if row is None:
        return None
    attempt, snapshot, source, target = row
    run_target = session.get(type(target), target.id)
    del run_target
    target_data = {
        "project_product_id": str(target.project_product_id),
        "product_id": str(target.product_id),
        "variant_id": str(target.variant_id),
    }
    source_data = {
        "snapshot_id": str(snapshot.id),
        "final_url": attempt.final_url,
        "classification": source.classification,
        "published_at": snapshot.published_at.isoformat() if snapshot.published_at else None,
    }
    return target_data, source_data, snapshot.relevant_text


def persist_extraction(
    session: Session,
    *,
    owner_id: UUID,
    run_id: UUID,
    target_id: UUID,
    source_attempt_id: UUID,
    extraction: ValidatedExtraction,
) -> int:
    row = session.execute(
        select(ResearchRunSource, SourceSnapshot, Source, ResearchRunTarget)
        .join(SourceSnapshot, SourceSnapshot.id == ResearchRunSource.snapshot_id)
        .join(Source, Source.id == SourceSnapshot.source_id)
        .join(
            ResearchRunTarget,
            (ResearchRunTarget.research_run_id == ResearchRunSource.research_run_id)
            & (ResearchRunTarget.project_product_id == ResearchRunSource.project_product_id),
        )
        .where(
            ResearchRunSource.id == source_attempt_id,
            ResearchRunSource.owner_id == owner_id,
            ResearchRunSource.research_run_id == run_id,
            ResearchRunSource.project_product_id == target_id,
            ResearchRunSource.status == "retrieved",
            SourceSnapshot.owner_id == owner_id,
            Source.owner_id == owner_id,
            ResearchRunTarget.owner_id == owner_id,
        )
        .with_for_update(of=ResearchRunTarget)
    ).one_or_none()
    if row is None:
        raise ValueError("Source snapshot is unavailable for this research target")
    _attempt, snapshot, source, target = row
    if source.classification == "unknown":
        return 0
    created = 0
    for validated in extraction.claims:
        candidate = validated.candidate
        # Recheck against the immutable stored excerpt inside the write transaction.
        if snapshot.relevant_text[validated.start : validated.end] != candidate.quote:
            raise ValueError("The quoted claim is absent from the saved source snapshot")
        fingerprint = hashlib.sha256(
            json.dumps(
                [candidate.attribute_key, candidate.quote, candidate.qualifiers],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        existing = session.scalar(
            select(Claim.id).where(
                Claim.snapshot_id == snapshot.id,
                Claim.subject_variant_id == target.variant_id,
                Claim.prompt_version == PROMPT_VERSION,
                Claim.fingerprint == fingerprint,
            )
        )
        if existing is not None:
            continue
        claim = Claim(
            owner_id=owner_id,
            snapshot_id=snapshot.id,
            subject_product_id=target.product_id,
            subject_variant_id=target.variant_id,
            attribute_key=candidate.attribute_key,
            assertion_text=candidate.quote,
            normalized_value=candidate.normalized_value,
            qualifiers={
                **candidate.qualifiers,
                **({"unit": candidate.unit} if candidate.unit else {}),
            },
            evidence_category=source.classification,
            extracted_at=datetime.now(UTC),
            task_name=TASK_NAME,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            extraction_confidence=candidate.extraction_confidence,
            validation_warnings=[],
            fingerprint=fingerprint,
        )
        session.add(claim)
        session.flush()
        session.add(
            ClaimEvidence(
                claim_id=claim.id,
                excerpt=candidate.quote,
                locator={"start": validated.start, "end": validated.end},
                content_hash=snapshot.content_hash,
                measurement_details=candidate.measurement_details,
            )
        )
        created += 1
    target.claims_created += created
    target.updated_at = datetime.now(UTC)
    session.commit()
    return created
