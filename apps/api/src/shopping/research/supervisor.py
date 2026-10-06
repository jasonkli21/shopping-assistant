from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from shopping.extraction.http_retriever import MAX_PAGE_BYTES, HTTPPageRetriever
from shopping.extraction.retriever import PageRetriever
from shopping.integrations.personal_ai.client import AIProviderError, PersonalAIClient
from shopping.research import service
from shopping.research.executor import (
    InProcessResearchExecutor,
    ResearchExecutionContext,
    ResearchExecutor,
)
from shopping.research.jobs import ACTIVE_RESEARCH_JOB_TOKEN
from shopping.research.product_persistence import (
    finish_stage_attempt,
    planning_attempt_uncertain,
    start_stage_attempt,
)
from shopping.research.search_execution import execute_search_query
from shopping.research.task import (
    PROMPT_VERSION as DISCOVERY_PROMPT_VERSION,
)
from shopping.research.task import (
    TASK_NAME as DISCOVERY_TASK_NAME,
)
from shopping.research.task import (
    build_request,
    validate_output,
)
from shopping.search.provider import SearchProvider

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
        page_retriever: PageRetriever | None = None,
    ) -> None:
        self.client = client
        self.search_provider = search_provider
        self.session_factory = session_factory
        self.provider_timeout_seconds = provider_timeout_seconds
        self.max_concurrent = max_concurrent
        self.executor = executor or InProcessResearchExecutor(self._run)
        self.page_retriever = page_retriever or HTTPPageRetriever(max_decoded_bytes=MAX_PAGE_BYTES)
        self._reserved = 0
        self._capacity_lock = Lock()
        self._worker_id = f"local-{uuid4()}"
        self._maintenance_task: asyncio.Task[None] | None = None

    @property
    def provider_name(self) -> str:
        return getattr(self.search_provider, "name", "configured")

    @property
    def ai_provider_name(self) -> str:
        return "fake" if self.client.__class__.__name__.startswith("Fake") else "external"

    def reserve_slot(self) -> bool:
        with self._capacity_lock:
            active_count = getattr(self.executor, "active_count", 0)
            if callable(active_count):
                active_count = active_count()
            if int(active_count) + self._reserved >= self.max_concurrent:
                return False
            self._reserved += 1
            return True

    def release_slot(self) -> None:
        with self._capacity_lock:
            self._reserved = max(0, self._reserved - 1)

    def has_task(self, run_id: UUID) -> bool:
        check = getattr(self.executor, "has_task", None)
        return bool(check(run_id)) if check is not None else False

    async def submit(self, run_id: UUID) -> None:
        try:
            await self.executor.submit(ResearchExecutionContext(research_run_id=str(run_id)))
        finally:
            with self._capacity_lock:
                self._reserved = max(0, self._reserved - 1)

    async def cancel(self, run_id: UUID) -> None:
        cancel = getattr(self.executor, "cancel", None)
        if cancel is not None:
            await cancel(run_id)

    async def shutdown(self) -> None:
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            await asyncio.gather(self._maintenance_task, return_exceptions=True)
            self._maintenance_task = None
        shutdown = getattr(self.executor, "shutdown", None)
        if shutdown is not None:
            await shutdown()

    async def recover_after_restart(self) -> int:
        try:
            submitted = await self._dispatch_once()
        except Exception as error:
            logger.warning("Initial research recovery pass failed (%s)", type(error).__name__)
            submitted = 0
        if self._maintenance_task is None:
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        return submitted

    async def _maintenance_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            try:
                await self._dispatch_once()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Research recovery pass failed (%s)", type(error).__name__)

    async def _dispatch_once(self) -> int:
        await self._with_session(lambda session: service.recover_expired_jobs(session))
        await self._with_session(lambda session: service.reconcile_terminal_run_jobs(session))
        run_ids = await self._with_session(lambda session: service.dispatchable_run_ids(session))
        submitted = 0
        for run_id in run_ids:
            if self.has_task(run_id):
                continue
            if not self.reserve_slot():
                break
            try:
                await self.submit(run_id)
                submitted += 1
            except Exception as error:
                self.release_slot()
                logger.warning("Research dispatch failed for %s (%s)", run_id, type(error).__name__)
        return submitted

    async def wait(self, run_id: UUID) -> None:
        wait = getattr(self.executor, "wait", None)
        if wait is not None:
            await wait(run_id)

    async def _run(self, context: ResearchExecutionContext) -> None:
        run_id = UUID(context.research_run_id)
        claim = await self._with_session(
            lambda session: service.claim_job(
                session,
                worker_id=self._worker_id,
                lease_seconds=30,
                run_id=run_id,
            )
        )
        if claim is None:
            return
        token = ACTIVE_RESEARCH_JOB_TOKEN.set(claim.token)
        worker_task = asyncio.current_task()
        heartbeat_task = asyncio.create_task(
            self._heartbeat(claim.job_id, claim.token, worker_task)
        )
        try:
            await self._run_workflow(claim.owner_id, claim.project_id, claim.run_id)
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            run = await self._with_session(
                lambda session: service.get_run(
                    session, claim.owner_id, claim.project_id, claim.run_id
                )
            )
            job_status = (
                "canceled"
                if run.status == "canceled"
                else "failed"
                if run.status in {"failed", "interrupted"}
                else "succeeded"
            )
            await self._with_session(
                lambda session: service.complete_job(
                    session,
                    job_id=claim.job_id,
                    token=claim.token,
                    status=job_status,
                    error_code=run.error_code,
                    budget_consumed={
                        "search_attempts": run.attempts_used,
                        "results": run.results_found,
                        "sources": sum(target.sources_attempted for target in run.targets),
                        "ai_attempts": len(run.stages),
                    },
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Leave the lease to expire. Recovery can then mark in-flight provider
            # calls uncertain and retry only work whose saved state permits it.
            logger.warning("Research runner stopped for %s (%s)", run_id, type(error).__name__)
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            ACTIVE_RESEARCH_JOB_TOKEN.reset(token)

    async def _heartbeat(
        self, job_id: UUID, token: UUID, worker_task: asyncio.Task[None] | None
    ) -> None:
        while True:
            await asyncio.sleep(10)
            owned = await self._with_session(
                lambda session: service.heartbeat_job(
                    session, job_id=job_id, token=token, lease_seconds=30
                )
            )
            if not owned:
                if worker_task is not None and not worker_task.done():
                    worker_task.cancel()
                return

    async def _run_workflow(self, owner_id: UUID, project_id: UUID, run_id: UUID) -> None:
        planning_attempt_id: UUID | None = None
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
            snapshot, budgets, run_type = loaded
            if run_type == "product_research":
                from shopping.research.product_execution import run_product_research

                await run_product_research(
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    snapshot=snapshot,
                    budgets=budgets,
                    client=self.client,
                    search_provider=self.search_provider,
                    with_session=self._with_session,
                    remaining_seconds=lambda: self._remaining_seconds(
                        owner_id, project_id, run_id, budgets
                    ),
                    provider_timeout_seconds=self.provider_timeout_seconds,
                    page_retriever=self.page_retriever,
                )
                return
            saved_plan = await self._with_session(
                lambda session: service.load_saved_plan(session, owner_id, project_id, run_id)
            )
            if saved_plan is not None:
                plan = {"queries": saved_plan["queries"], "explanation": saved_plan["summary"]}
                plan_provider_request_id = None
                plan_output_chars = 0
            elif snapshot.get("manual_queries") is not None:
                plan = {
                    "queries": [
                        {"text": text, "purpose": "Explicit user-supplied product search."}
                        for text in snapshot["manual_queries"]
                    ],
                    "clarification": None,
                    "explanation": "Searches were supplied directly by the user.",
                }
                plan_provider_request_id = None
                plan_output_chars = 0
            else:
                if await self._with_session(
                    lambda session: planning_attempt_uncertain(
                        session,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                    )
                ):
                    await self._fail_run(
                        owner_id,
                        project_id,
                        run_id,
                        "uncertain_completion",
                        "The discovery planning call ended without a saved result "
                        "and was not repeated.",
                    )
                    return
                request = build_request(snapshot, budgets["max_queries"])
                planning_input_chars = len(
                    json.dumps(request.input, ensure_ascii=False, separators=(",", ":"))
                )
                planning_attempt = await self._with_session(
                    lambda session: start_stage_attempt(
                        session,
                        owner_id=owner_id,
                        project_id=project_id,
                        run_id=run_id,
                        target_project_product_id=None,
                        stage="planning",
                        task_name=DISCOVERY_TASK_NAME,
                        prompt_version=DISCOVERY_PROMPT_VERSION,
                        input_chars=planning_input_chars,
                    )
                )
                if planning_attempt is None:
                    await self._fail_run(
                        owner_id,
                        project_id,
                        run_id,
                        "ai_call_budget_exhausted",
                        "The discovery planner could not start within the saved AI-call budget.",
                    )
                    return
                planning_attempt_id = planning_attempt.id
                for planning_call_number in range(2):
                    if planning_call_number:
                        planning_attempt = await self._with_session(
                            lambda session: start_stage_attempt(
                                session,
                                owner_id=owner_id,
                                project_id=project_id,
                                run_id=run_id,
                                target_project_product_id=None,
                                stage="planning",
                                task_name=DISCOVERY_TASK_NAME,
                                prompt_version=DISCOVERY_PROMPT_VERSION,
                                input_chars=planning_input_chars,
                            )
                        )
                        if planning_attempt is None:
                            planning_attempt_id = None
                            await self._fail_run(
                                owner_id,
                                project_id,
                                run_id,
                                "ai_call_budget_exhausted",
                                "The discovery planner could not retry within the saved "
                                "AI-call budget.",
                            )
                            return
                        planning_attempt_id = planning_attempt.id
                    remaining = max(
                        0,
                        await self._remaining_seconds(owner_id, project_id, run_id, budgets),
                    )
                    if remaining < 1:
                        raise TimeoutError
                    try:
                        async with asyncio.timeout(remaining):
                            response = await self.client.generate(request)
                    except AIProviderError as error:
                        await self._finish_planning_attempt(
                            owner_id, project_id, run_id, planning_attempt_id, error.code
                        )
                        if (
                            planning_call_number == 0
                            and error.code in {"provider_unavailable", "rate_limited"}
                            and await self._remaining_seconds(owner_id, project_id, run_id, budgets)
                            > 0.5
                        ):
                            planning_attempt_id = None
                            await asyncio.sleep(0.25)
                            continue
                        raise
                    break
                if response.refused:
                    raise AIProviderError("provider_refused")
                output = validate_output(response.output, snapshot, budgets["max_queries"])
                plan = output.model_dump(mode="json")
                plan_provider_request_id = response.provider_request_id
                plan_output_chars = len(
                    json.dumps(response.output, ensure_ascii=False, separators=(",", ":"))
                )

            saved = await self._with_session(
                lambda session: service.save_plan(
                    session,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    queries=plan["queries"],
                    summary=plan.get("clarification") or plan.get("explanation"),
                    stage_attempt_id=planning_attempt_id,
                    provider_request_id=plan_provider_request_id,
                    output_chars=plan_output_chars,
                )
            )
            if not saved:
                return
            query_rows = await self._with_session(
                lambda session: service.list_run_queries(session, owner_id, project_id, run_id)
            )
            for query_id, max_results in query_rows:
                if not await execute_search_query(
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    query_id=query_id,
                    max_results=max_results,
                    search_provider=self.search_provider,
                    with_session=self._with_session,
                    remaining_seconds=lambda: self._remaining_seconds(
                        owner_id, project_id, run_id, budgets
                    ),
                    provider_timeout_seconds=self.provider_timeout_seconds,
                ):
                    return
            await self._with_session(
                lambda session: service.finalize(session, owner_id, project_id, run_id)
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            await self._finish_planning_attempt(
                owner_id, project_id, run_id, planning_attempt_id, "planner_timeout"
            )
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
                if error.code
                in {"provider_unavailable", "provider_timeout", "provider_refused", "rate_limited"}
                else "planner_failed"
            )
            summary = (
                "Discovery query planning is unavailable. Provide explicit search queries "
                "or retry later."
                if code == "provider_unavailable"
                else "The discovery planner could not produce a usable query plan."
            )
            await self._finish_planning_attempt(
                owner_id, project_id, run_id, planning_attempt_id, code
            )
            await self._fail_run(owner_id, project_id, run_id, code, summary)
        except ValueError:
            await self._finish_planning_attempt(
                owner_id, project_id, run_id, planning_attempt_id, "invalid_plan"
            )
            await self._fail_run(
                owner_id,
                project_id,
                run_id,
                "invalid_plan",
                "The discovery planner returned a plan that did not meet the saved constraints.",
            )
        except Exception as error:
            logger.error("Discovery run failed for %s (%s)", run_id, type(error).__name__)
            await self._finish_planning_attempt(
                owner_id, project_id, run_id, planning_attempt_id, "provider_error"
            )
            await self._fail_run(
                owner_id,
                project_id,
                run_id,
                "discovery_failed",
                "Discovery could not finish. Saved search observations remain available.",
            )

    async def _finish_planning_attempt(
        self,
        owner_id: UUID,
        project_id: UUID,
        run_id: UUID,
        attempt_id: UUID | None,
        error_code: str,
    ) -> None:
        if attempt_id is None:
            return
        try:
            await self._with_session(
                lambda session: finish_stage_attempt(
                    session,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    status="failed",
                    error_code=error_code,
                )
            )
        except Exception as error:
            logger.info(
                "Could not settle planning attempt for %s (%s)", run_id, type(error).__name__
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
