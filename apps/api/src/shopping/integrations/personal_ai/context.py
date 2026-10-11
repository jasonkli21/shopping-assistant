"""Shopping-owned, versioned read projection for Personal AI context requests."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from shopping.conversations.commands import _current_state
from shopping.evidence.freshness import DISPLAY_FRESHNESS, evidence_freshness, offer_freshness
from shopping.projects import repository
from shopping.projects import service as project_service
from shopping.projects.errors import ProjectError

SCHEMA_VERSION = "shopping-context-read-v1"
MAX_RESPONSE_BYTES = 65_536


class ContextSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["record", "evidence"]
    reference_id: str = Field(min_length=1, max_length=500)
    fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ContextPermissionDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    permission_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=200)


class ContextFieldSensitivity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,79}$")
    sensitivity: Literal["public", "personal", "sensitive", "restricted", "unknown"]


class ContextReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopping-context-read-v1"] = SCHEMA_VERSION
    application_id: Literal["shopping"] = "shopping"
    # A Shopping Project is an entity reference; workspace mapping is undefined.
    workspace_id: None = None
    operation: Literal["current", "search", "verify"]
    project_id: UUID
    selected_project_product_ids: tuple[UUID, ...] = Field(default=(), max_length=16)
    fields: tuple[str, ...] = Field(min_length=1, max_length=32)
    max_results: int = Field(ge=1, le=50)
    max_bytes: int = Field(ge=1, le=MAX_RESPONSE_BYTES)
    timeout_seconds: float = Field(default=3.0, gt=0, le=5.0)

    @field_validator("fields")
    @classmethod
    def fields_are_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(
            not isinstance(value, str)
            or len(value) > 80
            or not re.fullmatch(r"[a-z][a-z0-9_.-]*", value)
            for value in values
        ):
            raise ValueError("shopping_context_fields_must_be_unique")
        return values

    @field_validator("selected_project_product_ids")
    @classmethod
    def product_references_are_unique(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(values) != len(set(values)):
            raise ValueError("shopping_context_product_references_must_be_unique")
        return values

    @model_validator(mode="after")
    def fields_match_operation(self) -> ContextReadRequest:
        allowed = {
            "current": {
                "project_title",
                "project_goal",
                "category",
                "requirements",
                "budget_target",
                "budget_maximum",
                "budget_currency",
                "project_notes",
                "project_revision",
                "selected_products",
            },
            "search": {"catalog_observations"},
            "verify": {"project_revision"},
        }[self.operation]
        if not set(self.fields).issubset(allowed):
            raise ValueError("shopping_context_fields_invalid")
        if self.operation == "search" and not self.selected_project_product_ids:
            raise ValueError("shopping_catalog_selection_required")
        if self.operation == "verify" and self.selected_project_product_ids:
            raise ValueError("shopping_context_verify_products_unsupported")
        if self.operation == "verify" and self.fields != ("project_revision",):
            raise ValueError("shopping_context_verify_fields_invalid")
        return self


class ContextRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: Literal["project", "project_product", "evidence"]
    entity_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=200)
    source_version: str = Field(min_length=1, max_length=100)
    source_class: Literal["domain_current", "external_research"]
    authority: Literal["authoritative", "external"]
    observed_at: datetime | None = None
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    sensitivity: Literal["public", "personal", "sensitive", "restricted", "unknown"]
    payload: dict[str, object] = Field(max_length=32)
    source_refs: tuple[ContextSourceRef, ...] = Field(min_length=1, max_length=16)
    permission_dependencies: tuple[ContextPermissionDependency, ...] = Field(
        default=(), max_length=16
    )
    field_sensitivity: tuple[ContextFieldSensitivity, ...] = Field(default=(), max_length=32)


class ContextReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopping-context-read-v1"] = SCHEMA_VERSION
    application_id: Literal["shopping"] = "shopping"
    workspace_id: None = None
    items: tuple[ContextRecord, ...] = Field(default=(), max_length=50)


PROJECT_FIELD_SENSITIVITY = {
    "project_title": "personal",
    "project_goal": "personal",
    "category": "personal",
    "requirements": "sensitive",
    "budget_target": "sensitive",
    "budget_maximum": "sensitive",
    "budget_currency": "sensitive",
    "project_notes": "sensitive",
    "project_revision": "personal",
    "selected_products": "sensitive",
    "catalog_observations": "personal",
}


def read_context(
    session: Session,
    owner_id: UUID,
    request: ContextReadRequest,
) -> ContextReadResponse:
    """Read an authorized bounded view; the Shopping store remains canonical."""
    project = repository.project_by_owner(session, request.project_id, owner_id)
    if project is None:
        raise ProjectError(404, "not_found", "Project not found")

    if request.operation == "verify":
        item = _project_record(
            project,
            {"project_revision": project.revision},
            fields=("project_revision",),
        )
        return _bounded_response((item,), request.max_bytes, request.max_results)

    project_read = project_service.get_project(session, owner_id, request.project_id)
    current = _current_state(
        session,
        owner_id,
        request.project_id,
        selected_project_product_ids=list(request.selected_project_product_ids),
        selected_context_only=True,
        include_external_evidence=request.operation == "search",
    )

    if request.operation == "current":
        values: dict[str, object] = {
            "project_title": project_read.title,
            "project_goal": project_read.goal,
            "category": project_read.category,
            "requirements": [_requirement_projection(item) for item in project_read.requirements],
            "budget_target": project_read.budget_target,
            "budget_maximum": project_read.budget_maximum,
            "budget_currency": project_read.budget_currency,
            "project_notes": project_read.notes,
            "project_revision": project_read.revision,
            "selected_products": [_product_projection(item) for item in current["products"]],
        }
        payload = {name: values[name] for name in request.fields if name in values}
        record = _project_record(project, payload, fields=tuple(payload))
        return _bounded_response((record,), request.max_bytes, request.max_results)

    evidence_records: list[ContextRecord] = []
    for product in current["products"]:
        observations = _observation_projections(product)
        if observations:
            evidence_records.append(
                _evidence_record(
                    project,
                    product,
                    observations,
                    ("catalog_observations",),
                )
            )
    return _bounded_response(
        tuple(evidence_records[: request.max_results]), request.max_bytes, request.max_results
    )


def _requirement_projection(item) -> dict[str, object]:
    return {
        "requirement_id": str(item.id),
        "kind": item.kind,
        "classification": "soft" if item.kind == "preference" else "hard",
        "label": item.label[:300],
        "detail": item.detail[:2000] if item.detail else None,
        "attribute_key": item.attribute_key,
        "operator": item.operator,
        "value": item.value,
        "unit": item.unit,
        "origin": item.origin,
        "source_preference_id": str(item.source_preference_id)
        if item.source_preference_id
        else None,
        "source_preference_revision": item.source_preference_revision,
        "source_preference_scope": item.source_preference_scope,
    }


def _product_projection(item: dict) -> dict[str, object]:
    decision = item["decision"]
    return {
        "project_product_id": item["project_product_id"],
        "product_id": item["product_id"],
        "variant_id": item["variant_id"],
        "canonical_name": item["canonical_name"],
        "brand": item["brand"],
        "variant_name": item["variant_name"],
        "identity_attributes": item["identity_attributes"],
        "category_attributes": item["category_attributes"],
        "decision_state": decision["state"],
        "saved": decision["state"] == "shortlisted",
        "rejection_reason": decision["rejection_reason"],
    }


def _observation_projections(item: dict) -> list[dict[str, object]]:
    now = datetime.now(UTC)
    result: list[dict[str, object]] = []
    for offer in item["offers"]:
        observed_at = _parse_timestamp(offer["observed_at"])
        result.append(
            {
                "kind": "merchant_offer",
                "observation_id": offer["offer_id"],
                "source_url": offer.get("source_url"),
                "merchant": offer["retailer"],
                "amount": offer["amount"],
                "currency": offer["currency"],
                "availability": offer.get("availability"),
                "condition": offer.get("condition"),
                "authority": "external_observation",
                "observed_at": observed_at.isoformat(),
                "expires_at": (
                    observed_at + timedelta(hours=DISPLAY_FRESHNESS["offer_max_age_hours"])
                ).isoformat(),
                "freshness": offer_freshness(observed_at, now=now),
            }
        )
    for claim in item["claims"]:
        retrieved_at = _parse_timestamp(claim["retrieved_at"])
        published_at = (
            _parse_timestamp(claim["published_at"]) if claim.get("published_at") else None
        )
        if claim["evidence_category"] in {"retailer_listing", "offer"}:
            expires_at = retrieved_at + timedelta(hours=DISPLAY_FRESHNESS["offer_max_age_hours"])
        elif published_at is not None:
            day_limit = (
                DISPLAY_FRESHNESS["specification_max_age_days"]
                if claim["evidence_category"]
                in {"manufacturer_specification", "manufacturer_claim"}
                else DISPLAY_FRESHNESS["claim_max_age_days"]
            )
            expires_at = published_at + timedelta(days=day_limit)
        else:
            expires_at = None
        result.append(
            {
                "kind": "evidence_claim",
                "observation_id": claim["claim_id"],
                "snapshot_id": claim["snapshot_id"],
                "source_url": claim["source_url"],
                "source_title": claim["source_title"],
                "attribute_key": claim["attribute_key"],
                "assertion": claim["assertion"],
                "normalized_value": claim["normalized_value"],
                "qualifiers": claim["qualifiers"],
                "evidence_category": claim["evidence_category"],
                "authority": "external_observation",
                "observed_at": retrieved_at.isoformat(),
                "expires_at": expires_at.isoformat() if expires_at else None,
                "freshness": evidence_freshness(
                    claim["evidence_category"],
                    published_at=published_at,
                    retrieved_at=retrieved_at,
                    now=now,
                ),
            }
        )
    return result[:5]


def _project_record(project, payload: dict, *, fields: tuple[str, ...]) -> ContextRecord:
    return ContextRecord(
        entity_type="project",
        entity_id=str(project.id),
        source_id=f"shopping-project:{project.id}",
        source_version=str(project.revision),
        source_class="domain_current",
        authority="authoritative",
        observed_at=project.updated_at,
        sensitivity="sensitive",
        payload=payload,
        source_refs=(
            ContextSourceRef(
                kind="record",
                reference_id=str(project.id),
                fingerprint=_fingerprint(f"{project.id}:{project.revision}"),
            ),
        ),
        permission_dependencies=(_project_permission(project.id, project.revision),),
        field_sensitivity=tuple(
            ContextFieldSensitivity(
                field=name,
                sensitivity=PROJECT_FIELD_SENSITIVITY.get(name, "sensitive"),
            )
            for name in fields
        ),
    )


def _evidence_record(
    project,
    product: dict,
    observations: list[dict],
    fields: tuple[str, ...],
) -> ContextRecord:
    project_product_id = UUID(product["project_product_id"])
    references = tuple(
        ContextSourceRef(
            kind="evidence",
            reference_id=str(value["observation_id"]),
            fingerprint=_fingerprint(_canonical_json(value)),
        )
        for value in observations[:16]
    )
    product_reference = ContextSourceRef(
        kind="record",
        reference_id=str(project_product_id),
        fingerprint=_fingerprint(f"{project_product_id}:{project.revision}"),
    )
    observed = [
        _parse_timestamp(value["observed_at"]) for value in observations if value.get("observed_at")
    ]
    expiries = [
        _parse_timestamp(value["expires_at"]) for value in observations if value.get("expires_at")
    ]
    return ContextRecord(
        entity_type="evidence",
        entity_id=str(project_product_id),
        source_id=f"shopping-catalog:{project_product_id}",
        source_version=_fingerprint(
            _canonical_json(
                {
                    "project_product_id": str(project_product_id),
                    "product_id": product["product_id"],
                    "variant_id": product["variant_id"],
                    "observations": observations,
                }
            )
        ),
        source_class="external_research",
        authority="external",
        observed_at=max(observed) if observed else None,
        expires_at=max(expiries) if expiries else None,
        sensitivity="personal",
        payload={
            **(
                {
                    "catalog_observations": {
                        "project_product_id": str(project_product_id),
                        "product_id": product["product_id"],
                        "variant_id": product["variant_id"],
                        "observations": observations,
                    }
                }
                if "catalog_observations" in fields
                else {}
            ),
        },
        source_refs=(product_reference, *references[:15]),
        permission_dependencies=(_project_permission(project.id, project.revision),),
        field_sensitivity=tuple(
            ContextFieldSensitivity(
                field=name,
                sensitivity=PROJECT_FIELD_SENSITIVITY.get(name, "personal"),
            )
            for name in fields
        ),
    )


def _project_permission(project_id: UUID, revision: int) -> ContextPermissionDependency:
    return ContextPermissionDependency(
        permission_id=f"shopping_project_read:{project_id}",
        version=str(revision),
        purpose="verify current Shopping project ownership and revision",
    )


def _bounded_response(
    items: tuple[ContextRecord, ...], max_bytes: int, max_results: int
) -> ContextReadResponse:
    if len(items) > max_results:
        raise ProjectError(413, "context_result_limit", "Context result limit exceeded")
    response = ContextReadResponse(items=items)
    try:
        encoded = json.dumps(
            response.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ProjectError(
            422, "context_projection_invalid", "Context could not be projected"
        ) from error
    if len(encoded) > max_bytes:
        raise ProjectError(413, "context_byte_limit", "Context byte limit exceeded")
    return response


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
