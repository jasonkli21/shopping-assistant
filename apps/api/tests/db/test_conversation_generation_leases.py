from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker

from shopping.conversations import service
from shopping.conversations.generation import GENERATION_LEASE_SECONDS
from shopping.conversations.models import ConversationMessage
from shopping.conversations.schemas import InterpretationOutput
from shopping.conversations.supervisor import GenerationSupervisor
from shopping.integrations.personal_ai.client import AIRequest, AIResponse
from shopping.projects.errors import ProjectError
from shopping.projects.models import ShoppingProject

pytestmark = pytest.mark.db


def _project(engine) -> tuple[UUID, UUID]:
    owner_id = uuid4()
    project_id = uuid4()
    with Session(engine) as session:
        session.add(
            ShoppingProject(
                id=project_id,
                owner_id=owner_id,
                title="Lease test",
                goal="Test conversation ownership",
                revision=1,
            )
        )
        session.commit()
    return owner_id, project_id


def _command(session, owner_id: UUID, project_id: UUID, worker_id: str, key: str):
    return service.create_message_command(
        session,
        owner_id,
        project_id,
        text="Find a quiet vacuum",
        request_key=key,
        expected_version=1,
        worker_id=worker_id,
    )


def _expire(engine, message_id: UUID) -> datetime:
    with Session(engine) as session:
        now = session.scalar(select(func.now()))
        message = session.get(ConversationMessage, message_id)
        assert now is not None and message is not None
        message.generation_lease_expires_at = now - timedelta(seconds=1)
        session.commit()
        return now


def _output() -> InterpretationOutput:
    return InterpretationOutput(assistant_message="A stale response must not be saved.")


def test_second_supervisor_startup_preserves_live_foreign_lease(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    first = GenerationSupervisor(client=object(), session_factory=factory)  # type: ignore[arg-type]
    second = GenerationSupervisor(client=object(), session_factory=factory)  # type: ignore[arg-type]

    with factory() as session:
        accepted = _command(session, owner_id, project_id, first.worker_id, "live-owner-key-01")

    assert first.worker_id != second.worker_id
    assert accepted.lease_token is not None
    assert second.recover_after_restart() == 0
    with factory() as session:
        message = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert message is not None
        assert message.status == "generating"
        assert message.generation_owner == first.worker_id
        assert message.generation_lease_token == accepted.lease_token


def test_second_supervisor_waits_for_legacy_row_recovery_grace(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        accepted = _command(session, owner_id, project_id, "legacy-worker", "legacy-key-001")
    with factory() as session:
        message = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert message is not None
        message.generation_owner = None
        message.generation_lease_token = None
        message.generation_lease_expires_at = None
        message.generation_heartbeat_at = None
        session.commit()

    second = GenerationSupervisor(client=object(), session_factory=factory)  # type: ignore[arg-type]
    assert second.recover_after_restart() == 0
    with factory() as session:
        message = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert message is not None
        assert message.status == "generating"


def test_concurrent_command_claims_allow_one_live_generation(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    barrier = Barrier(2)

    def attempt(index: int):
        barrier.wait()
        with factory() as session:
            try:
                return _command(
                    session, owner_id, project_id, f"process-{index}", f"race-key-{index:02}"
                )
            except ProjectError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, range(2)))

    winners = [item for item in outcomes if not isinstance(item, str)]
    assert len(winners) == 1
    assert winners[0].lease_token is not None
    assert "conversation_busy" in outcomes
    with factory() as session:
        active = list(
            session.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.project_id == project_id,
                    ConversationMessage.role == "assistant",
                    ConversationMessage.status == "generating",
                )
            ).all()
        )
        assert len(active) == 1
        assert active[0].generation_lease_token == winners[0].lease_token


def test_expired_lease_can_be_reclaimed_but_old_worker_cannot_complete(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    old_worker, recovery_worker = "process-old", "process-recovery"
    with factory() as session:
        accepted = _command(session, owner_id, project_id, old_worker, "expired-lease-key-01")
    old_token = accepted.lease_token
    assert old_token is not None
    now = _expire(db_engine, accepted.response.assistant_message_id)

    with factory() as session:
        assert not service.complete_generation(
            session,
            owner_id=owner_id,
            project_id=project_id,
            message_id=accepted.response.assistant_message_id,
            lease_token=old_token,
            output=_output(),
            provider_request_id="charged-but-stale",
            now=now,
        )

    with factory() as session:
        claims = service.claim_expired_generations(session, worker_id=recovery_worker, now=now)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.token != old_token

    with factory() as session:
        replacement = session.get(ConversationMessage, claim.message_id)
        assert replacement is not None
        assert replacement.status == "generating"
        assert replacement.generation_owner == recovery_worker
        assert replacement.generation_lease_token == claim.token

    with factory() as session:
        assert not service.complete_generation(
            session,
            owner_id=owner_id,
            project_id=project_id,
            message_id=claim.message_id,
            lease_token=old_token,
            output=_output(),
            provider_request_id="late-result",
            now=now + timedelta(seconds=1),
        )
    with factory() as session:
        assert service.interrupt_generation(
            session, owner_id, project_id, claim.message_id, claim.token, now=now
        )
        assert not service.complete_generation(
            session,
            owner_id=owner_id,
            project_id=project_id,
            message_id=claim.message_id,
            lease_token=old_token,
            output=_output(),
            provider_request_id="late-result-after-interrupt",
            now=now + timedelta(seconds=2),
        )
    with factory() as session:
        message = session.get(ConversationMessage, claim.message_id)
        assert message is not None
        assert message.status == "interrupted"
        assert message.error_code == "generation_interrupted"
        assert message.generation_lease_token is None
        assert message.input_snapshot is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ConversationMessage)
                .where(
                    ConversationMessage.id == claim.message_id,
                    ConversationMessage.status.in_(("completed", "failed", "interrupted")),
                )
            )
            == 1
        )


def test_concurrent_expired_lease_claims_have_one_recovery_owner(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        accepted = _command(session, owner_id, project_id, "original-worker", "claim-race-key-01")
    now = _expire(db_engine, accepted.response.assistant_message_id)
    barrier = Barrier(2)

    def claim(worker_id: str):
        barrier.wait()
        with factory() as session:
            return service.claim_expired_generations(session, worker_id=worker_id, now=now)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(claim, ["recovery-a", "recovery-b"]))
    claims = [claim for result in outcomes for claim in result]
    assert len(claims) == 1
    with factory() as session:
        message = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert message is not None
        assert message.generation_owner in {"recovery-a", "recovery-b"}
        assert message.generation_lease_token == claims[0].token


def test_heartbeat_extends_only_current_unexpired_lease(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        accepted = _command(session, owner_id, project_id, "heartbeat-worker", "heartbeat-key-01")
    token = accepted.lease_token
    assert token is not None
    with factory() as session:
        before = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert before is not None
        old_expiry = before.generation_lease_expires_at
    now = datetime.now(UTC) + timedelta(seconds=1)
    with factory() as session:
        assert service.heartbeat_generation(
            session,
            owner_id=owner_id,
            project_id=project_id,
            message_id=accepted.response.assistant_message_id,
            lease_token=token,
            now=now,
            lease_seconds=GENERATION_LEASE_SECONDS,
        )
    with factory() as session:
        after = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert after is not None
        assert after.generation_heartbeat_at == now
        assert after.generation_lease_expires_at == now + timedelta(
            seconds=GENERATION_LEASE_SECONDS
        )
        assert after.generation_lease_expires_at > old_expiry


def test_competing_terminal_writes_commit_only_one_state(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        accepted = _command(session, owner_id, project_id, "terminal-worker", "terminal-key-01")
    token = accepted.lease_token
    assert token is not None
    barrier = Barrier(2)

    def complete():
        barrier.wait()
        with factory() as session:
            return service.complete_generation(
                session,
                owner_id=owner_id,
                project_id=project_id,
                message_id=accepted.response.assistant_message_id,
                lease_token=token,
                output=_output(),
                provider_request_id="request-1",
            )

    def fail():
        barrier.wait()
        with factory() as session:
            return service.fail_generation(
                session,
                owner_id,
                project_id,
                accepted.response.assistant_message_id,
                token,
                "generation_failed",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda call: call(), [complete, fail]))
    assert sorted(results) == [False, True]
    with factory() as session:
        message = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert message is not None
        assert message.status in {"completed", "failed"}
        assert message.completed_at is not None
        assert message.generation_lease_token is None
        terminal_count = session.scalar(
            select(func.count())
            .select_from(ConversationMessage)
            .where(
                ConversationMessage.id == message.id,
                ConversationMessage.status.in_(("completed", "failed", "interrupted")),
            )
        )
        assert terminal_count == 1


class _WaitingClient:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def generate(self, _request: AIRequest) -> AIResponse:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return AIResponse(output={"assistant_message": "The provider returned once."})


def test_shutdown_cancels_provider_and_persists_fenced_interruption(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    client = _WaitingClient()
    supervisor = GenerationSupervisor(client=client, session_factory=factory)
    with factory() as session:
        accepted = _command(session, owner_id, project_id, supervisor.worker_id, "shutdown-key-001")
    assert accepted.lease_token is not None

    async def run_and_shutdown():
        assert supervisor.reserve_slot()
        supervisor.submit(
            owner_id,
            project_id,
            accepted.response.assistant_message_id,
            accepted.lease_token,
        )
        await asyncio.wait_for(client.started.wait(), timeout=2)
        await supervisor.shutdown()

    asyncio.run(run_and_shutdown())
    with factory() as session:
        message = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert message is not None
        assert message.status == "interrupted"
        assert message.error_code == "generation_interrupted"
        assert client.calls == 1


def test_shutdown_waits_for_running_maintenance_recovery(db_engine, monkeypatch):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    supervisor = GenerationSupervisor(client=object(), session_factory=factory)  # type: ignore[arg-type]
    with factory() as session:
        accepted = _command(
            session, owner_id, project_id, supervisor.worker_id, "recovery-shutdown-01"
        )
    message_id = accepted.response.assistant_message_id
    _expire(db_engine, message_id)

    recovery_entered = Event()
    release_recovery = Event()

    def block_actual_recovery(_conn, _cursor, statement, _parameters, _context, _many):
        if (
            "FROM conversation_messages" in statement
            and "DISTINCT" in statement.upper()
            and "FOR UPDATE" not in statement.upper()
            and not recovery_entered.is_set()
        ):
            recovery_entered.set()
            assert release_recovery.wait(timeout=5), "recovery was not released"

    event.listen(db_engine, "after_cursor_execute", block_actual_recovery)
    monkeypatch.setattr("shopping.conversations.supervisor.RECOVERY_INTERVAL_SECONDS", 0.01)

    async def shutdown_while_recovering():
        supervisor.start_maintenance()
        assert await asyncio.to_thread(recovery_entered.wait, 2), (
            "maintenance recovery did not start"
        )
        shutdown = asyncio.create_task(supervisor.shutdown())
        await asyncio.sleep(0.05)
        assert not shutdown.done(), "shutdown returned while the recovery thread was blocked"
        release_recovery.set()
        await asyncio.wait_for(shutdown, timeout=3)

    try:
        asyncio.run(shutdown_while_recovering())
    finally:
        release_recovery.set()
        event.remove(db_engine, "after_cursor_execute", block_actual_recovery)

    with factory() as session:
        message = session.get(ConversationMessage, message_id)
        assert message is not None
        assert message.status == "interrupted"
        assert message.error_code == "generation_interrupted"


def test_ambiguous_provider_result_is_not_retried_after_recovery_takeover(db_engine):
    owner_id, project_id = _project(db_engine)
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    client = _WaitingClient()
    first = GenerationSupervisor(client=client, session_factory=factory)
    recovery = GenerationSupervisor(client=client, session_factory=factory)
    with factory() as session:
        accepted = _command(session, owner_id, project_id, first.worker_id, "ambiguous-key-01")
    assert accepted.lease_token is not None

    async def execute_expired_provider_call():
        assert first.reserve_slot()
        first.submit(
            owner_id,
            project_id,
            accepted.response.assistant_message_id,
            accepted.lease_token,
        )
        await asyncio.wait_for(client.started.wait(), timeout=2)
        await asyncio.to_thread(_expire, db_engine, accepted.response.assistant_message_id)
        assert await asyncio.to_thread(recovery.recover_after_restart) == 1
        client.release.set()
        await first._tasks[accepted.response.assistant_message_id]

    asyncio.run(execute_expired_provider_call())
    with factory() as session:
        message = session.get(ConversationMessage, accepted.response.assistant_message_id)
        assert message is not None
        assert message.status == "interrupted"
        assert message.error_code == "generation_interrupted"
        assert client.calls == 1
