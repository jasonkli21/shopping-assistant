from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ResearchExecutionContext:
    research_run_id: str


class ResearchExecutor(Protocol):
    """Execution boundary for research work.

    This callable interface supports in-process execution. Before remote execution,
    evolve it to dispatch a persisted run/job ID; Python closures cannot be shipped
    to Cloud Run Jobs. Research semantics stay in the shopping application.
    """

    async def execute(
        self,
        context: ResearchExecutionContext,
        work: Callable[[], Awaitable[T]],
    ) -> T: ...


class InProcessResearchExecutor:
    async def execute(
        self,
        context: ResearchExecutionContext,
        work: Callable[[], Awaitable[T]],
    ) -> T:
        del context
        return await work()
