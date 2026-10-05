from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from threading import Lock
from uuid import UUID

from sqlalchemy.orm import Session

from shopping.conversations import service
from shopping.conversations.task import request_for_saved_context, validate_output
from shopping.integrations.personal_ai.client import AIProviderError, PersonalAIClient

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]


def _call_in_session[Result](
    session_factory: SessionFactory, operation: Callable[[Session], Result]
) -> Result:
    with session_factory() as session:
        return operation(session)


class GenerationSupervisor:
    """Lifespan-owned, single-process supervisor for bounded generation tasks."""

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
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._reserved = 0
        self._running_count = 0
        self._capacity_lock = Lock()

    def recover_after_restart(self) -> int:
        with self.session_factory() as session:
            return service.interrupt_all_unfinished(session)

    def reserve_slot(self) -> bool:
        with self._capacity_lock:
            if self._running_count + self._reserved >= self.max_concurrent:
                return False
            self._reserved += 1
            return True

    def release_slot(self) -> None:
        with self._capacity_lock:
            self._reserved = max(0, self._reserved - 1)

    def submit(self, owner_id: UUID, project_id: UUID, message_id: UUID) -> None:
        with self._capacity_lock:
            self._reserved = max(0, self._reserved - 1)
            self._running_count += 1
        task = asyncio.create_task(self._run(owner_id, project_id, message_id))
        self._tasks[message_id] = task
        task.add_done_callback(self._task_finished)

    async def shutdown(self) -> None:
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

    async def _run(self, owner_id: UUID, project_id: UUID, message_id: UUID) -> None:
        try:
            context, task_name = await self._with_session(
                lambda session: service.load_generation_input(
                    session, owner_id, project_id, message_id
                )
            )
            if context is None or task_name not in {
                "interpret_shopping_intent.v1",
                "interpret_shopping_intent.v2",
            }:
                await self._fail(owner_id, project_id, message_id, "context_too_large")
                return
            request = request_for_saved_context(context)
            async with asyncio.timeout(self.timeout_seconds):
                response = await self.client.generate(request)
            if response.refused:
                await self._fail(owner_id, project_id, message_id, "provider_refused")
                return
            output = validate_output(response.output, context)
            await self._with_session(
                lambda session: service.complete_generation(
                    session,
                    owner_id=owner_id,
                    project_id=project_id,
                    message_id=message_id,
                    output=output,
                    provider_request_id=response.provider_request_id,
                )
            )
        except TimeoutError:
            await self._fail(owner_id, project_id, message_id, "provider_timeout")
        except AIProviderError as error:
            allowed = {"provider_unavailable", "provider_timeout", "provider_refused"}
            await self._fail(
                owner_id,
                project_id,
                message_id,
                error.code if error.code in allowed else "generation_failed",
            )
        except ValueError:
            await self._fail(owner_id, project_id, message_id, "invalid_output")
        except asyncio.CancelledError:
            try:
                await self._with_session(
                    lambda session: service.interrupt_generation(session, message_id)
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
            await self._fail(owner_id, project_id, message_id, "generation_failed")

    async def _fail(self, owner_id: UUID, project_id: UUID, message_id: UUID, code: str) -> None:
        try:
            await self._with_session(
                lambda session: service.fail_generation(
                    session, owner_id, project_id, message_id, code
                )
            )
        except Exception as error:
            logger.error(
                "Could not persist assistant generation failure for message %s (%s)",
                message_id,
                type(error).__name__,
            )

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
