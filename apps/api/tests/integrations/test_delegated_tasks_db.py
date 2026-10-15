"""Native Shopping receipt/effect atomicity, concurrency and privacy boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shopping.accounts.export import purge_owner_data
from shopping.accounts.models import OwnerPrivacyLifecycle
from shopping.integrations.personal_ai.task_wire import DelegatedTaskRequest
from shopping.integrations.personal_ai.tasks import (
    OPERATION_FINGERPRINT,
    OPERATION_ID,
    PAYLOAD_SCHEMA_ID,
    list_target_choices,
    process_budget_task,
)
from shopping.projects.errors import ProjectError
from shopping.projects.models import DelegatedTaskReceipt, ShoppingProject
from shopping.projects.schemas import ProjectCreate
from shopping.projects.service import create_project, delete_project

pytestmark = pytest.mark.db


@pytest.fixture
def budget_task(db_engine):
    owner = uuid4()
    with Session(db_engine) as session:
        project = create_project(
            session,
            owner,
            ProjectCreate(
                title="Synthetic delegated budget",
                goal="Bounded allocation",
                budget_target="10.00",
                budget_maximum="100.00",
                budget_currency="USD",
            ),
        )
    request = DelegatedTaskRequest(
        source_application_id="finance",
        destination_application_id="shopping",
        purpose="shopping_budget",
        action="execute",
        proposal_id=uuid4(),
        execution_key=uuid4(),
        operation_id=OPERATION_ID,
        operation_version=1,
        operation_contract_fingerprint=OPERATION_FINGERPRINT,
        payload_schema_id=PAYLOAD_SCHEMA_ID,
        target_entity_type="project",
        target_entity_id=str(project.id),
        expected_domain_version="1",
        payload={"amount": "50.00", "currency": "USD"},
        intent_digest="a" * 64,
        confirmation_binding="b" * 64,
        source_dependencies=({"permission_id": "synthetic_grant", "version": "1"},),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    return owner, project.id, request


def run(db_engine, owner, request, authorize=lambda request, effect: True):
    with Session(db_engine) as session, session.begin():
        return process_budget_task(session, owner, request, authorize)


def test_concurrent_duplicates_commit_one_effect_and_receipt(db_engine, budget_task):
    owner, project, request = budget_task
    barrier = Barrier(2)

    def submit(_):
        barrier.wait(timeout=5)
        return run(db_engine, owner, request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    assert results[0].state == "applied"
    with Session(db_engine) as session:
        row = session.get(ShoppingProject, project)
        assert row.revision == 2 and str(row.budget_target) == "50.00"
        assert session.scalar(select(func.count()).select_from(DelegatedTaskReceipt)) == 1


def test_receipt_rejects_changed_payload_and_observes_after_expiry(db_engine, budget_task):
    owner, project, request = budget_task
    first = run(db_engine, owner, request)
    with pytest.raises(ValueError, match="idempotency_conflict"):
        run(
            db_engine,
            owner,
            request.model_copy(update={"payload": {"amount": "60.00", "currency": "USD"}}),
        )
    with Session(db_engine) as session, session.begin():
        observed = process_budget_task(
            session,
            owner,
            request.model_copy(update={"action": "reconcile"}),
            lambda request, effect: not effect,
            now=request.expires_at + timedelta(seconds=1),
        )
    assert first == observed
    with Session(db_engine) as session:
        assert session.get(ShoppingProject, project).revision == 2


def test_rollback_cannot_publish_receipt_and_missing_receipt_never_executes(db_engine, budget_task):
    owner, project, request = budget_task
    with pytest.raises(RuntimeError, match="process_died"):
        with Session(db_engine) as session, session.begin():
            assert (
                process_budget_task(session, owner, request, lambda request, effect: True).state
                == "applied"
            )
            raise RuntimeError("process_died_before_commit")
    observed = run(db_engine, owner, request.model_copy(update={"action": "reconcile"}))
    assert observed.state == "uncertain" and observed.code == "no_receipt"
    with Session(db_engine) as session:
        assert session.get(ShoppingProject, project).revision == 1
        assert session.scalar(select(func.count()).select_from(DelegatedTaskReceipt)) == 0


def test_revocation_and_constraints_prevent_effect(db_engine, budget_task):
    owner, project, request = budget_task
    denied = run(db_engine, owner, request, lambda request, effect: not effect)
    assert denied.state == "rejected" and denied.code == "task_authority_denied"
    too_large = request.model_copy(update={"payload": {"amount": "150.00", "currency": "USD"}})
    rejected = run(db_engine, owner, too_large)
    assert rejected.state == "rejected"
    assert run(db_engine, owner, too_large).state == "rejected"
    with Session(db_engine) as session:
        assert session.get(ShoppingProject, project).revision == 1


def test_wrong_owner_and_workspace_cannot_write(db_engine, budget_task):
    owner, project, request = budget_task
    with pytest.raises(ProjectError):
        run(db_engine, uuid4(), request)
    with pytest.raises(ValueError, match="contract_unsupported"):
        run(db_engine, owner, request.model_copy(update={"workspace_id": "other"}))
    with Session(db_engine) as session:
        assert session.get(ShoppingProject, project).revision == 1


def test_target_choices_are_minimal_owned_active_projects(db_engine, budget_task):
    owner, first_id, _request = budget_task
    other_owner = uuid4()
    with Session(db_engine) as session:
        second = create_project(
            session,
            owner,
            ProjectCreate(title="Second private title", goal="Never disclose goal"),
        )
        create_project(
            session,
            other_owner,
            ProjectCreate(title="Other owner secret", goal="Never enumerate"),
        )
    with Session(db_engine) as session, session.begin():
        result = list_target_choices(session, owner)
    serialized = result.model_dump(mode="json")
    assert serialized["schema_version"] == "suite-task-target-choices-v1"
    assert {item["project_id"] for item in serialized["choices"]} == {
        str(first_id), str(second.id)
    }
    assert all(set(item) == {"project_id", "label", "revision"} for item in serialized["choices"])
    assert "Never disclose goal" not in str(serialized)
    assert "Other owner secret" not in str(serialized)


def test_target_choices_fail_closed_when_owner_is_purging(db_engine, budget_task):
    owner, _project, _request = budget_task
    with Session(db_engine) as session, session.begin():
        lifecycle = session.get(OwnerPrivacyLifecycle, owner)
        assert lifecycle is not None
        lifecycle.state = "purging"
    with Session(db_engine) as session, session.begin(), pytest.raises(
        PermissionError, match="owner_unavailable"
    ):
        list_target_choices(session, owner)


def test_project_deletion_keeps_receipt_and_account_purge_fences_replay(db_engine, budget_task):
    owner, project, request = budget_task
    applied = run(db_engine, owner, request)
    with Session(db_engine) as session:
        delete_project(session, owner, project, expected_version=2)
    assert run(db_engine, owner, request.model_copy(update={"action": "reconcile"})) == applied
    with Session(db_engine) as session:
        purge_owner_data(session, owner, record_limit=None)
    with pytest.raises(PermissionError, match="owner_unavailable"):
        run(db_engine, owner, request)
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(DelegatedTaskReceipt)) == 0


def test_owner_purge_waits_for_effect_authorized_under_lifecycle_lock(db_engine, budget_task):
    owner, project, request = budget_task
    authority_allowed = Event()
    finish_authority = Event()
    purge_started = Event()
    purge_finished = Event()

    def authorize(_request, effect):
        if effect:
            authority_allowed.set()
            if not finish_authority.wait(timeout=5):
                raise TimeoutError("test did not release effect authority")
        return True

    def apply():
        with Session(db_engine) as session, session.begin():
            return process_budget_task(session, owner, request, authorize)

    def purge():
        with Session(db_engine) as session, session.begin():
            purge_started.set()
            purge_owner_data(session, owner, record_limit=None)
        purge_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            apply_result = pool.submit(apply)
            assert authority_allowed.wait(timeout=5)
            purge_result = pool.submit(purge)
            assert purge_started.wait(timeout=5)
            assert not purge_finished.wait(timeout=0.2)
            finish_authority.set()
            assert apply_result.result(timeout=10).state == "applied"
            purge_result.result(timeout=10)
        with Session(db_engine) as session:
            assert session.get(ShoppingProject, project) is None
            assert session.scalar(select(func.count()).select_from(DelegatedTaskReceipt)) == 0
            assert session.get(OwnerPrivacyLifecycle, owner).state == "purged"
    finally:
        finish_authority.set()


@pytest.mark.parametrize("source", ["travel", "health"])
def test_shared_context_note_keeps_prior_notes_and_hard_constraints(db_engine, budget_task, source):
    from shopping.integrations.personal_ai.tasks import (
        NOTE_OPERATION_FINGERPRINT,
        NOTE_OPERATION_ID,
        NOTE_PAYLOAD_SCHEMA_ID,
    )
    from shopping.projects.schemas import ProjectPatch
    from shopping.projects.service import patch_project

    owner, project_id, request = budget_task
    with Session(db_engine) as session:
        patch_project(
            session,
            owner,
            project_id,
            ProjectPatch(expected_version=1, notes="Keep existing context."),
        )
    note = request.model_copy(
        update={
            "source_application_id": source,
            "expected_domain_version": "2",
            "operation_id": NOTE_OPERATION_ID,
            "operation_contract_fingerprint": NOTE_OPERATION_FINGERPRINT,
            "payload_schema_id": NOTE_PAYLOAD_SCHEMA_ID,
            "payload": {"content": "Explicitly shared synthetic context."},
        }
    )
    result = run(db_engine, owner, note)
    assert result.state == "applied" and result.domain_version == "3"
    assert run(db_engine, owner, note) == result
    with Session(db_engine) as session:
        project = session.get(ShoppingProject, project_id)
        assert project.notes == (
            f"Keep existing context.\n\nUser-authorized {source.title()} context: "
            "Explicitly shared synthetic context."
        )
        assert str(project.budget_maximum) == "100.00" and str(project.budget_target) == "10.00"
        assert session.scalar(select(func.count()).select_from(DelegatedTaskReceipt)) == 1


def test_context_note_overflow_rejects_without_truncating_existing_data(db_engine, budget_task):
    from shopping.integrations.personal_ai.tasks import (
        NOTE_OPERATION_FINGERPRINT,
        NOTE_OPERATION_ID,
        NOTE_PAYLOAD_SCHEMA_ID,
    )
    from shopping.projects.schemas import ProjectPatch
    from shopping.projects.service import patch_project

    owner, project_id, request = budget_task
    original = "x" * 9950
    with Session(db_engine) as session:
        patch_project(session, owner, project_id, ProjectPatch(expected_version=1, notes=original))
    request = request.model_copy(
        update={
            "source_application_id": "health",
            "expected_domain_version": "2",
            "operation_id": NOTE_OPERATION_ID,
            "operation_contract_fingerprint": NOTE_OPERATION_FINGERPRINT,
            "payload_schema_id": NOTE_PAYLOAD_SCHEMA_ID,
            "payload": {"content": "y" * 100},
        }
    )
    result = run(db_engine, owner, request)
    assert result.state == "rejected" and result.code == "project_notes_full"
    with Session(db_engine) as session:
        assert session.get(ShoppingProject, project_id).notes == original
        assert session.get(ShoppingProject, project_id).revision == 2


def test_retired_fingerprint_can_observe_only_a_known_exact_receipt(
    db_engine, budget_task, monkeypatch
):
    from shopping.integrations.personal_ai import tasks

    owner, project, request = budget_task
    first = run(db_engine, owner, request)
    monkeypatch.setitem(
        tasks.OPERATION_CONTRACTS,
        tasks.OPERATION_ID,
        ("f" * 64, tasks.PAYLOAD_SCHEMA_ID, tasks.BudgetAllocation),
    )
    assert run(db_engine, owner, request.model_copy(update={"action": "reconcile"})) == first
    assert run(db_engine, owner, request) == first
    with pytest.raises(ValueError, match="contract_unsupported"):
        run(db_engine, owner, request.model_copy(update={"execution_key": uuid4()}))
    with Session(db_engine) as session:
        assert session.get(ShoppingProject, project).revision == 2
