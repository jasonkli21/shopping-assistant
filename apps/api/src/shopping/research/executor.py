from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ResearchExecutionContext:
    """Serializable work request; the worker loads all private context by run ID."""

    research_run_id: str


@dataclass(frozen=True)
class ExecutionReceipt:
    research_run_id: str
    accepted: bool


class ResearchExecutor(Protocol):
    async def submit(self, context: ResearchExecutionContext) -> ExecutionReceipt: ...


RunResearch = Callable[[ResearchExecutionContext], Awaitable[None]]


class InProcessResearchExecutor:
    """Local adapter that schedules the same ID-based runner used by manual drain."""

    def __init__(self, run: RunResearch) -> None:
        self.run = run
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    async def submit(self, context: ResearchExecutionContext) -> ExecutionReceipt:
        run_id = UUID(context.research_run_id)
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            return ExecutionReceipt(context.research_run_id, accepted=True)
        task = asyncio.create_task(self.run(context))
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed: self._discard(run_id, completed))
        return ExecutionReceipt(context.research_run_id, accepted=True)

    def has_task(self, run_id: UUID) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    @property
    def active_count(self) -> int:
        return sum(not task.done() for task in self._tasks.values())

    async def cancel(self, run_id: UUID) -> None:
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def wait(self, run_id: UUID) -> None:
        task = self._tasks.get(run_id)
        if task is not None:
            await task

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _discard(self, run_id: UUID, task: asyncio.Task[None]) -> None:
        if self._tasks.get(run_id) is task:
            self._tasks.pop(run_id, None)
