from __future__ import annotations

import asyncio
from contextlib import contextmanager
from threading import Event

import pytest

from shopping.conversations.supervisor import GenerationSupervisor


def test_slow_database_work_does_not_block_coroutines_and_shutdown_waits_for_session():
    entered = Event()
    release = Event()
    closed = Event()

    @contextmanager
    def session_factory():
        try:
            yield object()
        finally:
            closed.set()

    supervisor = GenerationSupervisor(
        client=object(),  # type: ignore[arg-type]
        session_factory=session_factory,
    )

    def slow_write(_session):
        entered.set()
        if not release.wait(timeout=2):
            raise TimeoutError("the test did not release the database operation")
        return "committed"

    async def exercise_supervisor():
        database_task = asyncio.create_task(supervisor._with_session(slow_write))
        assert await asyncio.to_thread(entered.wait, 1)

        # A separate coroutine remains responsive while the synchronous session is
        # blocked, then cancellation waits for its context manager to close cleanly.
        await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)
        database_task.cancel()
        asyncio.get_running_loop().call_later(0.02, release.set)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(database_task, timeout=0.5)

    asyncio.run(exercise_supervisor())
    assert closed.is_set()
