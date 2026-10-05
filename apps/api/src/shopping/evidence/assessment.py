"""Conservative, cited project assessments over validated stored claims."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.evidence.models import (
    AssessmentCitation,
    Claim,
    ClaimEvidence,
    ClaimRelation,
    ProductAssessment,
    ResearchRunSource,
)
from shopping.projects.models import ProjectRequirement
from shopping.research.models import ResearchRun, ResearchRunTarget

TASK_VERSION = "deterministic-cited-assessment.v1"
WEAK_CATEGORIES = {
    "community_observation",
    "individual_anecdote",
    "editorial_assessment",
    "unknown",
}


def _context(claim: Claim) -> tuple:
    qualifiers = claim.qualifiers or {}
    return tuple(
        (key, str(qualifiers.get(key, "")).casefold())
        for key in ("unit", "mode", "region", "variant", "test_duration", "sample", "limit")
    )


def _relation(left: Claim, right: Claim) -> tuple[str, str]:
    if left.assertion_text.casefold() == right.assertion_text.casefold():
        return "duplicate", "Matching source wording; independent corroboration is unverified."
    if _context(left) != _context(right):
        return "different_context", "The stated conditions or sample differ."
    if left.normalized_value is not None and right.normalized_value is not None:
        if left.normalized_value == right.normalized_value:
            return "supports", "The stated values agree under matching recorded conditions."
        return "contradicts", "The stated values differ under matching recorded conditions."
    return "different_context", "The claims cannot be compared as equivalent measurements."


def _meets_requirement(claim: Claim, requirement: dict) -> bool | None:
    value = claim.normalized_value
    threshold = requirement.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        return None
    unit = (claim.qualifiers or {}).get("unit")
    if (
        not isinstance(unit, str)
        or not isinstance(requirement.get("unit"), str)
        or unit != requirement["unit"]
    ):
        return None
    operator = requirement.get("operator")
    bound = (claim.qualifiers or {}).get("limit")
    if bound == "up_to":
        if operator == "gte":
            return False if value < threshold else None
        if operator == "lte":
            return True if value <= threshold else None
        # A bound is not an exact observed value, even when its endpoint happens
        # to equal a project threshold.
        return None
    elif bound == "at_least":
        if operator == "gte":
            return True if value >= threshold else None
        if operator == "lte":
            return False if value > threshold else None
        return None
    if operator == "gte":
        return value >= threshold
    if operator == "lte":
        return value <= threshold
    if operator == "eq":
        return value == threshold
    return None


def record_assessment(session: Session, run: ResearchRun, target: ResearchRunTarget) -> None:
    if session.scalar(
        select(ProductAssessment.id).where(
            ProductAssessment.owner_id == run.owner_id,
            ProductAssessment.research_run_id == run.id,
            ProductAssessment.project_product_id == target.project_product_id,
            ProductAssessment.task_version == TASK_VERSION,
        )
    ):
        return
    snapshot_ids = list(
        session.scalars(
            select(ResearchRunSource.snapshot_id).where(
                ResearchRunSource.research_run_id == run.id,
                ResearchRunSource.owner_id == run.owner_id,
                ResearchRunSource.project_product_id == target.project_product_id,
                ResearchRunSource.status == "retrieved",
                ResearchRunSource.snapshot_id.is_not(None),
            )
        ).all()
    )
    claims = list(
        session.scalars(
            select(Claim)
            .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
            .where(
                Claim.owner_id == run.owner_id,
                Claim.subject_product_id == target.product_id,
                Claim.subject_variant_id == target.variant_id,
                Claim.snapshot_id.in_(snapshot_ids),
            )
            .distinct()
            .order_by(Claim.extracted_at, Claim.id)
        ).all()
    )
    # Relations describe evidence; they never delete or average competing claims.
    for first, second in combinations(claims[:80], 2):
        if first.attribute_key != second.attribute_key:
            continue
        left, right = sorted((first, second), key=lambda claim: claim.id)
        relation, basis = _relation(left, right)
        exists = session.scalar(
            select(ClaimRelation.id).where(
                ClaimRelation.claim_id == left.id,
                ClaimRelation.related_claim_id == right.id,
                ClaimRelation.relation == relation,
            )
        )
        if exists is None:
            session.add(
                ClaimRelation(
                    owner_id=run.owner_id,
                    claim_id=left.id,
                    related_claim_id=right.id,
                    relation=relation,
                    basis=basis,
                    origin="system",
                    task_version=TASK_VERSION,
                )
            )

    requirements = run.input_snapshot.get("requirements", [])
    conclusions: list[dict] = []
    citations: list[tuple[UUID, UUID]] = []
    current_requirement_ids = set(
        session.scalars(
            select(ProjectRequirement.id).where(ProjectRequirement.project_id == run.project_id)
        ).all()
    )
    for requirement in requirements:
        attribute = requirement.get("attribute_key")
        related = (
            [claim for claim in claims if claim.attribute_key == attribute] if attribute else []
        )
        evaluated = [
            (claim, _meets_requirement(claim, requirement))
            for claim in related
            if claim.evidence_category not in WEAK_CATEGORIES
        ]
        supported = [claim for claim, outcome in evaluated if outcome is True]
        conflicted = [claim for claim, outcome in evaluated if outcome is False]
        if supported and conflicted:
            status = "mixed"
            rationale = (
                "Cited source values disagree on this requirement under their recorded conditions."
            )
            cited = supported + conflicted
        elif supported:
            status = "supports"
            rationale = (
                "Cited source values meet the saved requirement under their recorded conditions."
            )
            cited = supported
        elif conflicted:
            status = "conflicts"
            rationale = (
                "Cited source values do not meet the saved requirement "
                "under their recorded conditions."
            )
            cited = conflicted
        else:
            status = "unknown"
            rationale = (
                "No comparable, sufficiently grounded source value establishes this requirement."
            )
            cited = []
        requirement_id = UUID(requirement["id"])
        claim_ids = list(dict.fromkeys(str(claim.id) for claim in cited))
        conclusions.append(
            {
                "requirement_id": str(requirement_id),
                "requirement_label": requirement["label"],
                "status": status,
                "rationale": rationale,
                "claim_ids": claim_ids,
            }
        )
        if requirement_id in current_requirement_ids:
            citations.extend((requirement_id, UUID(claim_id)) for claim_id in claim_ids)

    assessment = ProductAssessment(
        owner_id=run.owner_id,
        project_id=run.project_id,
        project_product_id=target.project_product_id,
        research_run_id=run.id,
        project_revision=run.snapshot_revision,
        requirements_snapshot=requirements,
        product_revision=target.product_revision,
        variant_revision=target.variant_revision,
        claim_ids=[str(claim.id) for claim in claims],
        snapshot_ids=[str(snapshot_id) for snapshot_id in dict.fromkeys(snapshot_ids)],
        conclusions=conclusions,
        summary=(
            "Grounded source claims were compared with the saved requirements."
            if claims
            else "No grounded source claims were available for this selected variant."
        ),
        strengths=[],
        concerns=[],
        uncertainties=[
            "An unknown conclusion needs more relevant evidence."
            for item in conclusions
            if item["status"] == "unknown"
        ][:10],
        generated_at=datetime.now(UTC),
        task_name="assess_project_fit.v1",
        task_version=TASK_VERSION,
        ai_provider="deterministic",
    )
    session.add(assessment)
    session.flush()
    for requirement_id, claim_id in citations:
        session.add(
            AssessmentCitation(
                assessment_id=assessment.id,
                claim_id=claim_id,
                requirement_id=requirement_id,
                rationale="Comparable saved requirement and validated source claim.",
            )
        )
