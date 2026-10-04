from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from threading import Lock
from uuid import UUID

from sqlalchemy.orm import Session

from shopping.integrations.personal_ai.client import AIProviderError, PersonalAIClient
from shopping.research import service
from shopping.research.executor import (
    InProcessResearchExecutor,
    ResearchExecutionContext,
    ResearchExecutor,
)
from shopping.research.task import build_request, validate_output
from shopping.search.provider import SearchProvider, SearchProviderError, SearchQuery

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]


def _call_in_session[Result](
    session_factory: SessionFactory, operation: Callable[[Session], Result]
) -> Result:
    with session_factory() as session:
        return operation(session)


class DiscoverySupervisor:
    """Lifespan-owned single-process runner, separate from conversation tasks."""

    def __init__(
        self,
        *,
        client: PersonalAIClient,
        search_provider: SearchProvider,
        session_factory: SessionFactory,
        provider_timeout_seconds: int = 15,
        max_concurrent: int = 2,
        executor: ResearchExecutor | None = None,
    ) -> None:
        self.client = client
        self.search_provider = search_provider
        self.session_factory = session_factory
        self.provider_timeout_seconds = provider_timeout_seconds
        self.max_concurrent = max_concurrent
        self.executor = executor or InProcessResearchExecutor()
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._reserved = 0
        self._capacity_lock = Lock()

    @property
    def provider_name(self) -> str:
        return getattr(self.search_provider, "name", "configured")

    @property
    def ai_provider_name(self) -> str:
        return "fake" if self.client.__class__.__name__.startswith("Fake") else "external"

    def reserve_slot(self) -> bool:
        with self._capacity_lock:
            if len(self._tasks) + self._reserved >= self.max_concurrent:
                return False
            self._reserved += 1
            return True

    def release_slot(self) -> None:
        with self._capacity_lock:
            self._reserved = max(0, self._reserved - 1)

    def has_task(self, run_id: UUID) -> bool:
        return run_id in self._tasks

    def submit(self, owner_id: UUID, project_id: UUID, run_id: UUID) -> None:
        with self._capacity_lock:
            self._reserved = max(0, self._reserved - 1)
            existing = self._tasks.get(run_id)
            if existing and not existing.done():
                return
            context = ResearchExecutionContext(research_run_id=str(run_id))
            task = asyncio.create_task(
                self.executor.execute(
                    context,
                    lambda: self._run(owner_id, project_id, run_id),
                )
            )
            self._tasks[run_id] = task
        task.add_done_callback(lambda finished: self._task_finished(run_id, finished))

    async def cancel(self, run_id: UUID) -> None:
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.items())
        for _run_id, task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)

    def recover_after_restart(self) -> int:
        with self.session_factory() as session:
            return service.interrupt_all_unfinished(session)

    def _task_finished(self, run_id: UUID, task: asyncio.Task[None]) -> None:
        if self._tasks.get(run_id) is task:
            self._tasks.pop(run_id, None)

    async def _run(self, owner_id: UUID, project_id: UUID, run_id: UUID) -> None:
        try:
            started = await self._with_session(
                lambda session: service.mark_running(session, owner_id, project_id, run_id)
            )
            if not started:
                return
            loaded = await self._with_session(
                lambda session: service.load_execution_input(session, owner_id, project_id, run_id)
            )
            if loaded is None:
                return
            snapshot, budgets = loaded
            if snapshot.get("manual_queries") is not None:
                plan = {
                    "queries": [
                        {"text": text, "purpose": "Explicit user-supplied product search."}
                        for text in snapshot["manual_queries"]
                    ],
                    "clarification": None,
                    "explanation": "Searches were supplied directly by the user.",
                }
            else:
                request = build_request(snapshot, budgets["max_queries"])
                remaining = max(
                    0,
                    await self._remaining_seconds(owner_id, project_id, run_id, budgets),
                )
                if remaining < 1:
                    raise TimeoutError
                async with asyncio.timeout(remaining):
                    response = await self.client.generate(request)
                if response.refused:
                    raise AIProviderError("provider_refused")
                output = validate_output(response.output, snapshot, budgets["max_queries"])
                plan = output.model_dump(mode="json")

            saved = await self._with_session(
                lambda session: service.save_plan(
                    session,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    queries=plan["queries"],
                    summary=plan.get("clarification") or plan.get("explanation"),
                )
            )
            if not saved:
                return
            query_rows = await self._with_session(
                lambda session: service.list_run_queries(session, owner_id, project_id, run_id)
            )
            for query_id, max_results in query_rows:
                attempt = await self._with_session(
                    lambda session, current_id=query_id: service.start_attempt(
                        session,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        query_id=current_id,
                    )
                )
                if attempt is None:
                    continue
                query, attempt_id, allowance = attempt
                remaining = await self._remaining_seconds(owner_id, project_id, run_id, budgets)
                timeout = min(self.provider_timeout_seconds, remaining)
                if timeout <= 0:
                    await self._fail_attempt(
                        owner_id, project_id, run_id, query_id, attempt_id, "deadline_exceeded"
                    )
                    continue
                try:
                    async with asyncio.timeout(timeout):
                        response = await self.search_provider.search(
                            SearchQuery(text=query.text, max_results=min(max_results, allowance))
                        )
                    completed = await self._with_session(
                        partial(
                            service.complete_attempt,
                            owner_id=owner_id,
                            project_id=project_id,
                            run_id=run_id,
                            query_id=query_id,
                            attempt_id=attempt_id,
                            response=response,
                        )
                    )
                    if not completed:
                        return
                except TimeoutError:
                    await self._fail_attempt(
                        owner_id, project_id, run_id, query_id, attempt_id, "provider_timeout"
                    )
                except SearchProviderError as error:
                    await self._fail_attempt(
                        owner_id,
                        project_id,
                        run_id,
                        query_id,
                        attempt_id,
                        error.code,
                    )
                except ValueError:
                    await self._fail_attempt(
                        owner_id, project_id, run_id, query_id, attempt_id, "malformed_response"
                    )
                except Exception as error:
                    logger.warning(
                        "Search attempt failed for run %s (%s)", run_id, type(error).__name__
                    )
                    await self._fail_attempt(
                        owner_id, project_id, run_id, query_id, attempt_id, "provider_error"
                    )
            await self._with_session(
                lambda session: service.finalize(session, owner_id, project_id, run_id)
            )
        except asyncio.CancelledError:
            await self._interrupt_owned_run(owner_id, project_id, run_id)
            raise
        except TimeoutError:
            await self._fail_run(
                owner_id,
                project_id,
                run_id,
                "planner_timeout",
                "The discovery planner exceeded the run deadline.",
            )
        except AIProviderError as error:
            code = (
                error.code
                if error.code in {"provider_unavailable", "provider_timeout", "provider_refused"}
                else "planner_failed"
            )
            summary = (
                "Discovery query planning is unavailable. Provide explicit search queries "
                "or retry later."
                if code == "provider_unavailable"
                else "The discovery planner could not produce a usable query plan."
            )
            await self._fail_run(owner_id, project_id, run_id, code, summary)
        except ValueError:
            await self._fail_run(
                owner_id,
                project_id,
                run_id,
                "invalid_plan",
                "The discovery planner returned a plan that did not meet the saved constraints.",
            )
        except Exception as error:
            logger.error("Discovery run failed for %s (%s)", run_id, type(error).__name__)
            await self._fail_run(
                owner_id,
                project_id,
                run_id,
                "discovery_failed",
                "Discovery could not finish. Saved search observations remain available.",
            )

    async def _remaining_seconds(
        self, owner_id: UUID, project_id: UUID, run_id: UUID, budgets: dict[str, int]
    ) -> float:
        started_at = await self._with_session(
            lambda session: service.run_started_at(session, owner_id, project_id, run_id)
        )
        if started_at is None:
            return 0
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        return max(
            0.0,
            (
                started_at + timedelta(seconds=budgets["deadline_seconds"]) - datetime.now(UTC)
            ).total_seconds(),
        )

    async def _fail_attempt(
        self,
        owner_id: UUID,
        project_id: UUID,
        run_id: UUID,
        query_id: UUID,
        attempt_id: UUID,
        code: str,
    ) -> None:
        await self._with_session(
            lambda session: service.fail_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                query_id=query_id,
                attempt_id=attempt_id,
                error_code=code,
            )
        )

    async def _fail_run(
        self,
        owner_id: UUID,
        project_id: UUID,
        run_id: UUID,
        code: str,
        summary: str,
    ) -> None:
        try:
            await self._with_session(
                lambda session: service.fail_run(
                    session, owner_id, project_id, run_id, code, summary
                )
            )
        except Exception as error:
            logger.info("Run %s was already terminal (%s)", run_id, type(error).__name__)

    async def _interrupt_owned_run(self, owner_id: UUID, project_id: UUID, run_id: UUID) -> None:
        try:
            await self._with_session(
                lambda session: service.interrupt_run(
                    session, owner_id, project_id, run_id, "worker_interrupted"
                )
            )
        except Exception as error:
            logger.error(
                "Could not persist interrupted discovery run %s (%s)", run_id, type(error).__name__
            )

    async def _with_session[Result](self, operation: Callable[[Session], Result]) -> Result:
        """Run short SQLAlchemy units off-loop and await their close on cancellation."""
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
