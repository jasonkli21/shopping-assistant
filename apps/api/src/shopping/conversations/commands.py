from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct, RetailOffer
from shopping.comparisons.models import ComparisonDimension, ComparisonItem, SavedComparison
from shopping.conversations.generation import GENERATION_LEASE_SECONDS
from shopping.conversations.models import Conversation, ConversationMessage
from shopping.conversations.schemas import MessageCreated
from shopping.conversations.task import build_request
from shopping.evidence.models import Claim, ClaimRelation, ProductAssessment, Source, SourceSnapshot
from shopping.evidence.reads import assessment_context_stale, freshness
from shopping.projects import notes as note_service
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.errors import ProjectError
from shopping.projects.models import ProjectProductDecision, UserNote


@dataclass(frozen=True)
class MessageCommandResult:
    response: MessageCreated
    should_start: bool
    lease_token: UUID | None = None


def create_message_command(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    text: str,
    request_key: str,
    expected_version: int,
    selected_project_product_ids: list[UUID] | None = None,
    comparison_id: UUID | None = None,
    slot_reserver: Callable[[], bool] | None = None,
    worker_id: str | None = None,
) -> MessageCommandResult:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")

    request_payload = {"text": text, "expected_version": expected_version}
    if selected_project_product_ids or comparison_id:
        request_payload["selected_project_product_ids"] = [
            str(item) for item in selected_project_product_ids or []
        ]
        request_payload["comparison_id"] = str(comparison_id) if comparison_id else None
    request_hash = hashlib.sha256(
        json.dumps(
            request_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    previous = session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.owner_id == owner_id,
            ConversationMessage.project_id == project_id,
            ConversationMessage.role == "user",
            ConversationMessage.request_key == request_key,
        )
    )
    if previous is not None:
        if previous.request_hash != request_hash:
            raise ProjectError(409, "idempotency_conflict", "This request key was already used.")
        assistant = session.get(ConversationMessage, previous.paired_message_id)
        conversation = session.get(Conversation, previous.conversation_id)
        if assistant is None or conversation is None:
            raise ProjectError(
                500, "conversation_incomplete", "The saved message could not be read."
            )
        return MessageCommandResult(
            MessageCreated(
                user_message_id=previous.id,
                assistant_message_id=assistant.id,
                conversation_id=conversation.id,
                replayed=True,
            ),
            should_start=False,
        )

    if project.revision != expected_version:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded. Review the latest version before sending.",
            {"current_version": project.revision},
        )

    conversation = session.scalar(
        select(Conversation)
        .where(
            Conversation.owner_id == owner_id,
            Conversation.project_id == project_id,
        )
        .with_for_update()
    )
    if conversation is None:
        conversation = Conversation(owner_id=owner_id, project_id=project_id)
        session.add(conversation)
        session.flush()

    active = session.scalar(
        select(ConversationMessage.id).where(
            ConversationMessage.conversation_id == conversation.id,
            ConversationMessage.role == "assistant",
            ConversationMessage.status == "generating",
        )
    )
    if active is not None:
        raise ProjectError(409, "conversation_busy", "A response is already being prepared.")

    project_read = project_service.get_project(session, owner_id, project_id)
    history = list(
        session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation.id,
                ConversationMessage.status == "completed",
            )
            .order_by(desc(ConversationMessage.ordinal))
            .limit(12)
        ).all()
    )
    history.reverse()
    try:
        task_request = build_request(
            project_read,
            text,
            [{"role": item.role, "text": item.content} for item in history],
            _current_state(
                session,
                owner_id,
                project_id,
                selected_project_product_ids=selected_project_product_ids or [],
                comparison_id=comparison_id,
            ),
        )
        input_snapshot = task_request.input["context"]
        context_error = None
    except ValueError:
        input_snapshot = None
        context_error = "context_too_large"

    slot_reserved = False
    if context_error is None and slot_reserver is not None:
        slot_reserved = slot_reserver()
        if not slot_reserved:
            raise ProjectError(
                503, "generation_capacity", "Assistant generation is busy. Try again shortly."
            )

    user_id = uuid4()
    assistant_id = uuid4()
    user_message = ConversationMessage(
        id=user_id,
        conversation_id=conversation.id,
        project_id=project_id,
        owner_id=owner_id,
        paired_message_id=None,
        ordinal=conversation.next_ordinal,
        role="user",
        content=text,
        status="completed",
        request_key=request_key,
        request_hash=request_hash,
    )
    lease_token = uuid4() if context_error is None else None
    generation_owner = (
        (worker_id or f"conversation-{uuid4()}").strip()[:100] if lease_token is not None else None
    )
    lease_now = (
        session.scalar(select(func.clock_timestamp())) or datetime.now(UTC)
        if lease_token is not None
        else None
    )
    assistant_message = ConversationMessage(
        id=assistant_id,
        conversation_id=conversation.id,
        project_id=project_id,
        owner_id=owner_id,
        paired_message_id=None,
        ordinal=conversation.next_ordinal + 1,
        role="assistant",
        content="",
        status="failed" if context_error else "generating",
        snapshot_revision=project.revision,
        task_metadata={
            "task": "interpret_shopping_intent.v2",
            "prompt_version": "shopping-intent-2",
            "schema_version": 2,
            "provider_request_id": None,
        },
        input_snapshot=input_snapshot,
        error_code=context_error,
        generation_owner=generation_owner,
        generation_lease_token=lease_token,
        generation_lease_expires_at=(
            lease_now + timedelta(seconds=GENERATION_LEASE_SECONDS) if lease_now else None
        ),
        generation_heartbeat_at=lease_now,
        completed_at=datetime.now(UTC) if context_error else None,
    )
    session.add(user_message)
    session.flush()
    assistant_message.paired_message_id = user_id
    session.add(assistant_message)
    session.flush()
    user_message.paired_message_id = assistant_id
    conversation.next_ordinal += 2
    conversation.updated_at = datetime.now(UTC)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ProjectError(
            409, "conversation_conflict", "The message could not be reserved."
        ) from error

    return MessageCommandResult(
        MessageCreated(
            user_message_id=user_id,
            assistant_message_id=assistant_id,
            conversation_id=conversation.id,
            replayed=False,
        ),
        should_start=context_error is None,
        lease_token=lease_token,
    )


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _current_state(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    selected_project_product_ids: list[UUID] | None = None,
    comparison_id: UUID | None = None,
) -> dict:
    """Bounded, owner-scoped context for explicit Phase 6 assistant proposals."""
    project = repository.project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    scoped_ids = list(selected_project_product_ids or [])
    if comparison_id is not None:
        comparison = session.scalar(
            select(SavedComparison).where(
                SavedComparison.id == comparison_id,
                SavedComparison.owner_id == owner_id,
                SavedComparison.project_id == project_id,
            )
        )
        if comparison is None:
            raise _not_found("Comparison not found")
        scoped_ids = list(
            session.scalars(
                select(ComparisonItem.project_product_id)
                .where(ComparisonItem.comparison_id == comparison.id)
                .order_by(ComparisonItem.position)
            ).all()
        )
    product_statement = (
        select(ProjectProduct, ProductVariant, Product)
        .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProjectProduct.project_id == project_id, Product.owner_id == owner_id)
    )
    scoped_rows = []
    if scoped_ids:
        scoped_by_id = {
            row[0].id: row
            for row in session.execute(
                product_statement.where(ProjectProduct.id.in_(scoped_ids))
            ).all()
        }
        if len(scoped_by_id) != len(scoped_ids):
            raise _not_found("One or more selected variants are not in this project")
        scoped_rows = [scoped_by_id[item] for item in scoped_ids]
    remaining = max(0, 8 - len(scoped_rows))
    rows = [*scoped_rows]
    if remaining:
        rest_statement = product_statement
        if scoped_ids:
            rest_statement = rest_statement.where(~ProjectProduct.id.in_(scoped_ids))
        rows.extend(
            session.execute(
                rest_statement.order_by(ProjectProduct.created_at, ProjectProduct.id).limit(
                    remaining
                )
            ).all()
        )
    total_products = (
        session.scalar(
            select(func.count(ProjectProduct.id))
            .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(ProjectProduct.project_id == project_id, Product.owner_id == owner_id)
        )
        or 0
    )
    products = []
    for membership, variant, product in rows:
        decision = session.scalar(
            select(ProjectProductDecision).where(
                ProjectProductDecision.owner_id == owner_id,
                ProjectProductDecision.project_product_id == membership.id,
            )
        )
        note = session.scalar(
            select(UserNote).where(
                UserNote.owner_id == owner_id,
                UserNote.project_id == project_id,
                UserNote.project_product_id == membership.id,
            )
        )
        offers = list(
            session.scalars(
                select(RetailOffer)
                .where(RetailOffer.owner_id == owner_id, RetailOffer.variant_id == variant.id)
                .order_by(RetailOffer.observed_at.desc(), RetailOffer.id.desc())
                .limit(2)
            ).all()
        )
        assessment = session.scalar(
            select(ProductAssessment)
            .where(
                ProductAssessment.owner_id == owner_id,
                ProductAssessment.project_product_id == membership.id,
            )
            .order_by(ProductAssessment.generated_at.desc(), ProductAssessment.id.desc())
            .limit(1)
        )
        claim_rows = session.execute(
            select(Claim, SourceSnapshot, Source)
            .join(SourceSnapshot, SourceSnapshot.id == Claim.snapshot_id)
            .join(Source, Source.id == SourceSnapshot.source_id)
            .where(
                Claim.owner_id == owner_id,
                Claim.subject_variant_id == variant.id,
                SourceSnapshot.owner_id == owner_id,
                Source.owner_id == owner_id,
            )
            .order_by(Claim.extracted_at.desc(), Claim.id)
            .limit(3)
        ).all()
        claim_ids = [claim.id for claim, _snapshot, _source in claim_rows]
        claim_relations = (
            list(
                session.scalars(
                    select(ClaimRelation).where(
                        ClaimRelation.owner_id == owner_id,
                        or_(
                            ClaimRelation.claim_id.in_(claim_ids),
                            ClaimRelation.related_claim_id.in_(claim_ids),
                        ),
                    )
                ).all()
            )
            if claim_ids
            else []
        )
        products.append(
            {
                "project_product_id": str(membership.id),
                "product_id": str(product.id),
                "variant_id": str(variant.id),
                "canonical_name": product.canonical_name[:250],
                "brand": product.brand,
                "variant_name": variant.display_name[:250],
                "identity_attributes": _compact_attributes(variant.identity_attributes),
                "category_attributes": _compact_attributes(variant.category_attributes),
                "decision": {
                    "state": decision.state if decision else "considering",
                    "reason": decision.reason[:600] if decision else "",
                    "rejection_reason": decision.rejection_reason if decision else None,
                },
                "note": note.text[:1000] if note else None,
                "offers": [
                    {
                        "offer_id": str(offer.id),
                        "amount": format(offer.amount, ".2f") if offer.amount is not None else None,
                        "currency": offer.currency,
                        "retailer": offer.retailer_name[:100],
                        "observed_at": offer.observed_at.isoformat(),
                    }
                    for offer in offers
                ],
                "assessment": (
                    {
                        "assessment_id": str(assessment.id),
                        "summary": assessment.summary[:600],
                        "conclusions": assessment.conclusions[:6],
                        "project_revision": assessment.project_revision,
                        "context_stale": assessment_context_stale(
                            assessment, project, product, variant
                        ),
                        "product_revision": assessment.product_revision,
                        "variant_revision": assessment.variant_revision,
                        "claim_ids": assessment.claim_ids[:20],
                    }
                    if assessment
                    else None
                ),
                "claims": [
                    {
                        "claim_id": str(claim.id),
                        "snapshot_id": str(snapshot.id),
                        "attribute_key": claim.attribute_key,
                        "assertion": claim.assertion_text[:400],
                        "normalized_value": claim.normalized_value,
                        "qualifiers": claim.qualifiers,
                        "evidence_category": claim.evidence_category,
                        "source_title": (snapshot.title or source.title or "")[:200],
                        "source_url": source.normalized_url[:1000],
                        "retrieved_at": snapshot.retrieved_at.isoformat(),
                        "freshness": freshness(
                            claim.evidence_category,
                            published_at=snapshot.published_at,
                            retrieved_at=snapshot.retrieved_at,
                            now=datetime.now(UTC),
                        ),
                    }
                    for claim, snapshot, source in claim_rows
                ],
                "claim_relations": [
                    {
                        "claim_id": str(item.claim_id),
                        "related_claim_id": str(item.related_claim_id),
                        "relation": item.relation,
                        "basis": item.basis[:300],
                    }
                    for item in claim_relations
                ],
            }
        )
    comparisons = []
    comparison_rows = list(
        session.scalars(
            select(SavedComparison)
            .where(SavedComparison.owner_id == owner_id, SavedComparison.project_id == project_id)
            .order_by(SavedComparison.updated_at.desc(), SavedComparison.id)
            .limit(10)
        ).all()
    )
    if comparison_id is not None:
        prioritized = session.scalar(
            select(SavedComparison).where(
                SavedComparison.id == comparison_id,
                SavedComparison.owner_id == owner_id,
                SavedComparison.project_id == project_id,
            )
        )
        comparison_rows = [
            prioritized,
            *[item for item in comparison_rows if item.id != comparison_id],
        ]
    for comparison in comparison_rows[:10]:
        item_ids = list(
            session.scalars(
                select(ComparisonItem.project_product_id)
                .where(ComparisonItem.comparison_id == comparison.id)
                .order_by(ComparisonItem.position)
            ).all()
        )
        dimensions = list(
            session.scalars(
                select(ComparisonDimension)
                .where(ComparisonDimension.comparison_id == comparison.id)
                .order_by(ComparisonDimension.position)
            ).all()
        )
        comparisons.append(
            {
                "id": str(comparison.id),
                "title": comparison.title,
                "comparison_revision": comparison.comparison_revision,
                "project_product_ids": [str(item) for item in item_ids],
                "dimensions": [
                    {
                        "key": item.key,
                        "label": item.label,
                        "unit": item.unit,
                        "dimension_type": item.dimension_type,
                    }
                    for item in dimensions
                ],
            }
        )
    project_note = note_service.get_note(session, owner_id, project_id)
    return {
        "products": products,
        "comparisons": comparisons,
        "project_notes": project_note.text[:2000] if project_note else "",
        "scope": {
            "type": "comparison" if comparison_id else "selection" if scoped_ids else "project",
            "comparison_id": str(comparison_id) if comparison_id else None,
            "project_product_ids": [str(item) for item in scoped_ids],
        },
        "omitted_product_count": max(0, total_products - len(rows)),
    }


def _compact_attributes(attributes: dict) -> dict:
    compact = {}
    for key, value in list(attributes.items())[:12]:
        if isinstance(value, dict):
            bounded = dict(value)
            if isinstance(bounded.get("value"), str):
                bounded["value"] = bounded["value"][:200]
            compact[key[:100]] = bounded
        elif isinstance(value, str):
            compact[key[:100]] = value[:200]
        elif isinstance(value, (int, float, bool)) or value is None:
            compact[key[:100]] = value
    return compact
