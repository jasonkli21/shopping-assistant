from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct, RetailOffer
from shopping.comparisons.models import ComparisonDimension, ComparisonItem, SavedComparison
from shopping.conversations.models import Conversation, ConversationMessage
from shopping.conversations.schemas import MessageCreated
from shopping.conversations.task import build_request
from shopping.evidence.models import Claim, ProductAssessment, Source, SourceSnapshot
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.errors import ProjectError
from shopping.projects.models import ProjectProductDecision, UserNote


@dataclass(frozen=True)
class MessageCommandResult:
    response: MessageCreated
    should_start: bool


def create_message_command(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    *,
    text: str,
    request_key: str,
    expected_version: int,
    slot_reserver: Callable[[], bool] | None = None,
) -> MessageCommandResult:
    project = repository.project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")

    request_hash = hashlib.sha256(
        json.dumps(
            {"text": text, "expected_version": expected_version},
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
            _current_state(session, owner_id, project_id),
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
    )


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _current_state(session: Session, owner_id: UUID, project_id: UUID) -> dict:
    """Bounded, owner-scoped context for explicit Phase 6 assistant proposals."""
    rows = session.execute(
        select(ProjectProduct, ProductVariant, Product)
        .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProjectProduct.project_id == project_id, Product.owner_id == owner_id)
        .order_by(ProjectProduct.created_at, ProjectProduct.id)
        .limit(8)
    ).all()
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
                    }
                    for claim, snapshot, source in claim_rows
                ],
            }
        )
    comparisons = []
    for comparison in session.scalars(
        select(SavedComparison)
        .where(SavedComparison.owner_id == owner_id, SavedComparison.project_id == project_id)
        .order_by(SavedComparison.updated_at.desc(), SavedComparison.id)
        .limit(10)
    ).all():
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
    return {"products": products, "comparisons": comparisons}


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
