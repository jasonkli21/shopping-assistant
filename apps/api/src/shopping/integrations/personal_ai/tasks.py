"""Shopping-owned delegated project commands and permanent transactional receipts.

Transport identity and live PAI/source authorization must be supplied by the host.
The host commits this service's transaction; no receipt can outlive a rolled-back
write. Reconciliation only observes the original key, including after expiry.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from shopping.accounts.lifecycle import lock_active_owner_lifecycle
from shopping.integrations.personal_ai.task_wire import (
    DelegatedTargetChoicesResult,
    DelegatedTaskRequest,
    DelegatedTaskResult,
    ShoppingTargetChoice,
    canonical_bytes,
)
from shopping.projects import repository
from shopping.projects.errors import ProjectError
from shopping.projects.models import DelegatedTaskReceipt, ShoppingProject
from shopping.projects.schemas import SUPPORTED_CURRENCIES, ProjectPatch
from shopping.projects.service import _validate_budget_or_raise, get_project, patch_project


class BudgetAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    amount: str = Field(pattern=r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("currency")
    @classmethod
    def supported_currency(cls, value: str) -> str:
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError("budget_currency_unsupported")
        return value


OPERATION_ID = "project.set_budget"
PAYLOAD_SCHEMA_ID = "shopping-budget-allocation-v1"
OPERATION_DESCRIPTOR = {
    "operation_id": OPERATION_ID,
    "version": 1,
    "payload_schema_id": PAYLOAD_SCHEMA_ID,
    "entity_types": ["project"],
    "sensitivity": "restricted",
    "effect": (
        "set budget_target and budget_currency using normal ProjectPatch validators; "
        "preserve maximum"
    ),
    "payload_schema": BudgetAllocation.model_json_schema(),
    "supported_currencies": sorted(SUPPORTED_CURRENCIES),
}
OPERATION_FINGERPRINT = sha256(canonical_bytes(OPERATION_DESCRIPTOR)).hexdigest()


class SharedContextNote(BaseModel):
    """An explicitly accepted contextual note; it grants no hard-constraint authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    content: str = Field(min_length=1, max_length=1000)


NOTE_OPERATION_ID = "project.append_context_note"
NOTE_PAYLOAD_SCHEMA_ID = "shopping-context-note-v1"
NOTE_OPERATION_DESCRIPTOR = {
    "operation_id": NOTE_OPERATION_ID,
    "version": 1,
    "payload_schema_id": NOTE_PAYLOAD_SCHEMA_ID,
    "entity_types": ["project"],
    "sensitivity": "restricted",
    "effect": (
        "append user-authorized source context to existing canonical project notes; "
        "preserve all hard constraints and prior notes; reject capacity overflow"
    ),
    "maximum_project_notes_length": 10000,
    "payload_schema": SharedContextNote.model_json_schema(),
}
NOTE_OPERATION_FINGERPRINT = sha256(canonical_bytes(NOTE_OPERATION_DESCRIPTOR)).hexdigest()
OPERATION_CONTRACTS = {
    OPERATION_ID: (OPERATION_FINGERPRINT, PAYLOAD_SCHEMA_ID, BudgetAllocation),
    NOTE_OPERATION_ID: (NOTE_OPERATION_FINGERPRINT, NOTE_PAYLOAD_SCHEMA_ID, SharedContextNote),
}


BudgetTaskResult = DelegatedTaskResult


def list_target_choices(session: Session, owner_id: UUID) -> DelegatedTargetChoicesResult:
    """Expose only active owned project labels and revisions to a linked user."""
    if not lock_active_owner_lifecycle(session, owner_id):
        raise PermissionError("task_owner_unavailable")
    projects = session.scalars(
        repository.owned_projects(session, owner_id)
        .where(ShoppingProject.status == "active")
        .limit(32)
    ).all()
    return DelegatedTargetChoicesResult(
        choices=tuple(
            ShoppingTargetChoice(
                project_id=project.id,
                label=project.title,
                revision=project.revision,
            )
            for project in projects
        )
    )


def _receipt_result(receipt: DelegatedTaskReceipt, intent_digest: str) -> BudgetTaskResult:
    return BudgetTaskResult(
        execution_key=receipt.execution_key,
        intent_digest=intent_digest,
        state=receipt.state,
        code=receipt.code,
        domain_version=str(receipt.domain_version),
        reference_id=str(receipt.execution_key),
    )


def process_project_task(
    session: Session,
    owner_id: UUID,
    request: DelegatedTaskRequest,
    authorize: Callable[[DelegatedTaskRequest, bool], bool],
    *,
    now: datetime | None = None,
) -> BudgetTaskResult:
    """Apply or observe under current owner and task authority, without committing.

    authorize(request, False) checks current identity and domain observation rights.
    authorize(request, True) additionally checks exact canonical PAI confirmation,
    grant epoch, source revision and source consent. Unknown authority must raise,
    never return success. Network checks are bounded by the authenticated host.
    """
    if (
        request.destination_application_id != "shopping"
        or request.workspace_id is not None
        or request.target_entity_type != "project"
        or request.source_application_id not in {"finance", "travel", "health"}
    ):
        raise ValueError("task_contract_unsupported")
    target_id = UUID(request.target_entity_id)
    if (
        not request.expected_domain_version.isdecimal()
        or str(int(request.expected_domain_version)) != request.expected_domain_version
        or int(request.expected_domain_version) < 1
    ):
        raise ValueError("task_domain_version_invalid")
    if authorize(request, False) is not True:
        raise PermissionError("task_observation_denied")
    if not lock_active_owner_lifecycle(session, owner_id):
        raise PermissionError("task_owner_unavailable")
    semantic = request.model_dump(mode="json", exclude={"action"})
    fingerprint = sha256(canonical_bytes(semantic)).hexdigest()
    lock_key = int.from_bytes(
        sha256(f"{owner_id}:{request.execution_key}".encode()).digest()[:8], "big", signed=True
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    receipt = session.get(DelegatedTaskReceipt, (owner_id, request.execution_key))
    if receipt:
        if receipt.intent_fingerprint != fingerprint:
            raise ValueError("task_idempotency_conflict")
        return _receipt_result(receipt, request.intent_digest)
    if request.operation_id not in OPERATION_CONTRACTS or request.operation_version != 1:
        raise ValueError("task_contract_unsupported")
    operation_fingerprint, schema_id, payload_model = OPERATION_CONTRACTS[request.operation_id]
    if (
        request.operation_contract_fingerprint != operation_fingerprint
        or request.payload_schema_id != schema_id
    ):
        raise ValueError("task_contract_unsupported")
    payload = payload_model.model_validate(request.payload)
    if payload.model_dump(mode="json") != request.payload:
        raise ValueError("task_payload_not_canonical")
    if request.action == "reconcile":
        return BudgetTaskResult(
            execution_key=request.execution_key,
            intent_digest=request.intent_digest,
            state="uncertain",
            code="no_receipt",
        )
    if request.expires_at <= (now or datetime.now(UTC)):
        return BudgetTaskResult(
            execution_key=request.execution_key,
            intent_digest=request.intent_digest,
            state="rejected",
            code="task_expired",
        )
    if authorize(request, True) is not True:
        return BudgetTaskResult(
            execution_key=request.execution_key,
            intent_digest=request.intent_digest,
            state="rejected",
            code="task_authority_denied",
        )
    project = repository.project_by_owner(session, target_id, owner_id, lock=True)
    if project is None:
        raise ProjectError(404, "not_found", "Project not found")
    if request.expires_at <= (now or datetime.now(UTC)):
        return BudgetTaskResult(
            execution_key=request.execution_key,
            intent_digest=request.intent_digest,
            state="rejected",
            code="task_expired",
        )
    code = "committed"
    state = "applied"
    if project.revision != int(request.expected_domain_version):
        code, state = "revision_conflict", "rejected"
    else:
        try:
            if isinstance(payload, BudgetAllocation):
                _validate_budget_or_raise(
                    Decimal(payload.amount), project.budget_maximum, payload.currency
                )
            else:
                current_notes = get_project(session, owner_id, target_id).notes or ""
                prefix = f"User-authorized {request.source_application_id.title()} context: "
                appended_notes = (
                    current_notes + ("\n\n" if current_notes else "") + prefix + payload.content
                )
                if len(appended_notes) > 10000:
                    code, state = "project_notes_full", "rejected"
        except ProjectError as error:
            code, state = error.code, "rejected"
    if request.action == "validate":
        return BudgetTaskResult(
            execution_key=request.execution_key,
            intent_digest=request.intent_digest,
            state="validated" if state == "applied" else "rejected",
            code="valid" if state == "applied" else code,
            domain_version=str(project.revision),
            preview=(
                f"Set project budget to {payload.amount} {payload.currency}"
                if isinstance(payload, BudgetAllocation)
                else (
                    f"Append shared {request.source_application_id.title()} context "
                    f"to existing notes: {payload.content}"
                )
            ),
        )
    if state == "applied":
        project_read = patch_project(
            session,
            owner_id,
            target_id,
            (
                ProjectPatch(
                    expected_version=project.revision,
                    budget_target=payload.amount,
                    budget_currency=payload.currency,
                )
                if isinstance(payload, BudgetAllocation)
                else ProjectPatch(expected_version=project.revision, notes=appended_notes)
            ),
            commit=False,
        )
        version = project_read.revision
    else:
        version = project.revision
    receipt = DelegatedTaskReceipt(
        owner_id=owner_id,
        execution_key=request.execution_key,
        intent_fingerprint=fingerprint,
        target_entity_id=target_id,
        state=state,
        code=code,
        domain_version=version,
    )
    session.add(receipt)
    session.flush()
    return _receipt_result(receipt, request.intent_digest)


# Compatibility for the original reference service entry point.
process_budget_task = process_project_task
