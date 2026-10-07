from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from threading import Lock
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from shopping.conversations import service
from shopping.conversations.generation import GENERATION_LEASE_SECONDS
from shopping.conversations.task import request_for_saved_context, validate_output
from shopping.integrations.personal_ai.client import AIProviderError, PersonalAIClient

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]
RECOVERY_INTERVAL_SECONDS = 5
HEARTBEAT_INTERVAL_SECONDS = GENERATION_LEASE_SECONDS / 3


def _call_in_session[Result](
    session_factory: SessionFactory, operation: Callable[[Session], Result]
) -> Result:
    with session_factory() as session:
        return operation(session)


class GenerationSupervisor:
    """Lifespan-owned local runner for database-fenced generation leases."""

    def __init__(
        self,
        *,
        client: PersonalAIClient,
        session_factory: SessionFactory,
        timeout_seconds: int = 30,
        max_concurrent: int = 4,
    ) -> None:
        self.client = client
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.max_concurrent = max_concurrent
        self.worker_id = f"conversation-{uuid4()}"
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._reserved = 0
        self._running_count = 0
        self._capacity_lock = Lock()
        self._maintenance_task: asyncio.Task[None] | None = None

    def recover_after_restart(self) -> int:
        with self.session_factory() as session:
            claims = service.claim_expired_generations(
                session,
                worker_id=self.worker_id,
                lease_seconds=GENERATION_LEASE_SECONDS,
            )
        recovered = 0
        for claim in claims:
            try:
                with self.session_factory() as session:
                    recovered += service.interrupt_generation(
                        session,
                        claim.owner_id,
                        claim.project_id,
                        claim.message_id,
                        claim.token,
                    )
            except Exception as error:
                logger.warning(
                    "Expired assistant generation recovery failed (%s)", type(error).__name__
                )
        return recovered

    def start_maintenance(self) -> None:
        if self._maintenance_task is None:
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    def reserve_slot(self) -> bool:
        with self._capacity_lock:
            if self._running_count + self._reserved >= self.max_concurrent:
                return False
            self._reserved += 1
            return True

    def release_slot(self) -> None:
        with self._capacity_lock:
            self._reserved = max(0, self._reserved - 1)

    def submit(self, owner_id: UUID, project_id: UUID, message_id: UUID, lease_token: UUID) -> None:
        with self._capacity_lock:
            self._reserved = max(0, self._reserved - 1)
            self._running_count += 1
        task = asyncio.create_task(self._run(owner_id, project_id, message_id, lease_token))
        self._tasks[message_id] = task
        task.add_done_callback(self._task_finished)

    async def shutdown(self) -> None:
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            await asyncio.gather(self._maintenance_task, return_exceptions=True)
            self._maintenance_task = None
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _task_finished(self, task: asyncio.Task[None]) -> None:
        message_id = next((key for key, value in self._tasks.items() if value is task), None)
        if message_id is not None:
            self._tasks.pop(message_id, None)
        with self._capacity_lock:
            self._running_count = max(0, self._running_count - 1)

    async def _run(
        self, owner_id: UUID, project_id: UUID, message_id: UUID, lease_token: UUID
    ) -> None:
        worker_task = asyncio.current_task()
        heartbeat_task = asyncio.create_task(
            self._heartbeat(owner_id, project_id, message_id, lease_token, worker_task)
        )
        try:
            context, task_name = await self._with_session(
                lambda session: service.load_generation_input(
                    session, owner_id, project_id, message_id, lease_token
                )
            )
            if context is None or task_name not in {
                "interpret_shopping_intent.v1",
                "interpret_shopping_intent.v2",
            }:
                await self._fail(owner_id, project_id, message_id, lease_token, "context_too_large")
                return
            request = request_for_saved_context(context)
            async with asyncio.timeout(self.timeout_seconds):
                response = await self.client.generate(request)
            if response.refused:
                await self._fail(owner_id, project_id, message_id, lease_token, "provider_refused")
                return
            output = validate_output(response.output, context)
            await self._with_session(
                lambda session: service.complete_generation(
                    session,
                    owner_id=owner_id,
                    project_id=project_id,
                    message_id=message_id,
                    lease_token=lease_token,
                    output=output,
                    provider_request_id=response.provider_request_id,
                )
            )
        except TimeoutError:
            await self._fail(owner_id, project_id, message_id, lease_token, "provider_timeout")
        except AIProviderError as error:
            allowed = {"provider_unavailable", "provider_timeout", "provider_refused"}
            await self._fail(
                owner_id,
                project_id,
                message_id,
                lease_token,
                error.code if error.code in allowed else "generation_failed",
            )
        except ValueError:
            await self._fail(owner_id, project_id, message_id, lease_token, "invalid_output")
        except asyncio.CancelledError:
            try:
                await self._with_session(
                    lambda session: service.interrupt_generation(
                        session, owner_id, project_id, message_id, lease_token
                    )
                )
            except Exception as error:
                logger.error(
                    "Could not persist interrupted assistant generation (%s)",
                    type(error).__name__,
                )
            raise
        except Exception as error:
            logger.error(
                "Assistant generation failed for message %s (%s)",
                message_id,
                type(error).__name__,
            )
            await self._fail(owner_id, project_id, message_id, lease_token, "generation_failed")
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _heartbeat(
        self,
        owner_id: UUID,
        project_id: UUID,
        message_id: UUID,
        lease_token: UUID,
        owner_task: asyncio.Task[None] | None,
    ) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                alive = await self._with_session(
                    lambda session: service.heartbeat_generation(
                        session,
                        owner_id=owner_id,
                        project_id=project_id,
                        message_id=message_id,
                        lease_token=lease_token,
                        lease_seconds=GENERATION_LEASE_SECONDS,
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Assistant generation heartbeat failed (%s)", type(error).__name__)
                alive = False
            if not alive:
                if owner_task is not None:
                    owner_task.cancel()
                return

    async def _fail(
        self,
        owner_id: UUID,
        project_id: UUID,
        message_id: UUID,
        lease_token: UUID,
        code: str,
    ) -> None:
        try:
            await self._with_session(
                lambda session: service.fail_generation(
                    session, owner_id, project_id, message_id, lease_token, code
                )
            )
        except Exception as error:
            logger.error(
                "Could not persist assistant generation failure for message %s (%s)",
                message_id,
                type(error).__name__,
            )

    async def _maintenance_loop(self) -> None:
        while True:
            await asyncio.sleep(RECOVERY_INTERVAL_SECONDS)
            try:
                await asyncio.to_thread(self.recover_after_restart)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Conversation lease recovery failed (%s)", type(error).__name__)

    async def _with_session[Result](self, operation: Callable[[Session], Result]) -> Result:
        """Run one bounded synchronous database unit off the event loop.

        Shield the worker from task cancellation and wait for its session to
        close before returning cancellation to the supervisor. This prevents
        shutdown from abandoning an in-flight database write.
        """
        worker = asyncio.create_task(
            asyncio.to_thread(_call_in_session, self.session_factory, operation)
        )
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                await worker
            except Exception:
                pass
            raise
