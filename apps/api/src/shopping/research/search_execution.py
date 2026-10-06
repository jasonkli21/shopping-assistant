"""Bounded retry policy for search provider calls."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from shopping.research import service
from shopping.search.provider import SearchProvider, SearchProviderError, SearchQuery

WithSession = Callable[[Callable[[Session], Any]], Awaitable[Any]]
RemainingSeconds = Callable[[], Awaitable[float]]
RETRYABLE_CODES = {"provider_timeout", "rate_limited", "provider_unavailable"}
MAX_RETRIES_PER_QUERY = 2
MAX_RETRY_DELAY_SECONDS = 8.0


async def execute_search_query(
    *,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    query_id: UUID,
    max_results: int,
    search_provider: SearchProvider,
    with_session: WithSession,
    remaining_seconds: RemainingSeconds,
    provider_timeout_seconds: int,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> bool:
    """Run one saved query, persisting every attempt and retry time before sleeping.

    False means ownership was lost while completing a search and the enclosing workflow
    should stop. Provider and validation failures are recorded and return True so later
    queries can still run.
    """
    while True:
        retry_at = await with_session(
            lambda session: service.query_retry_at(session, owner_id, project_id, run_id, query_id)
        )
        if retry_at is not None:
            delay = max(0.0, (_aware_utc(retry_at) - datetime.now(UTC)).total_seconds())
            remaining = await remaining_seconds()
            if delay > 0 and remaining > 0:
                await sleep(min(delay, remaining))

        started = await with_session(
            lambda session: service.start_attempt(
                session,
                owner_id=owner_id,
                project_id=project_id,
                run_id=run_id,
                query_id=query_id,
            )
        )
        if started is None:
            return True
        query, attempt_id, allowance, attempt_number = started
        timeout = min(provider_timeout_seconds, await remaining_seconds())
        if timeout <= 0:
            await _fail(
                with_session,
                owner_id,
                project_id,
                run_id,
                query_id,
                attempt_id,
                "deadline_exceeded",
            )
            return True

        try:
            async with asyncio.timeout(timeout):
                response = await search_provider.search(
                    SearchQuery(text=query.text, max_results=min(max_results, allowance))
                )
            completed = await with_session(
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
            return bool(completed)
        except TimeoutError:
            code = "provider_timeout"
            retry_after = None
        except SearchProviderError as error:
            code = error.code
            retry_after = error.retry_after_seconds
        except ValueError:
            await _fail(
                with_session,
                owner_id,
                project_id,
                run_id,
                query_id,
                attempt_id,
                "malformed_response",
            )
            return True
        except Exception:
            await _fail(
                with_session, owner_id, project_id, run_id, query_id, attempt_id, "provider_error"
            )
            return True

        delay = (
            _retry_delay(attempt_number, retry_after, jitter) if code in RETRYABLE_CODES else None
        )
        remaining = await remaining_seconds()
        if delay is not None and delay < remaining:
            retry_at = datetime.now(UTC) + timedelta(seconds=delay)
            scheduled = await with_session(
                partial(
                    service.schedule_attempt_retry,
                    owner_id=owner_id,
                    project_id=project_id,
                    run_id=run_id,
                    query_id=query_id,
                    attempt_id=attempt_id,
                    error_code=code,
                    retry_at=retry_at,
                )
            )
            if scheduled:
                continue

        await _fail(with_session, owner_id, project_id, run_id, query_id, attempt_id, code)
        return True


def _retry_delay(
    attempt_number: int,
    retry_after_seconds: float | None,
    jitter: Callable[[float, float], float],
) -> float | None:
    if attempt_number > MAX_RETRIES_PER_QUERY:
        return None
    if retry_after_seconds is not None and retry_after_seconds > MAX_RETRY_DELAY_SECONDS:
        return None
    ceiling = min(MAX_RETRY_DELAY_SECONDS, 0.75 * 2 ** (attempt_number - 1))
    randomized = min(MAX_RETRY_DELAY_SECONDS, max(0.0, jitter(ceiling * 0.75, ceiling * 1.25)))
    return max(randomized, retry_after_seconds or 0.0)


async def _fail(
    with_session: WithSession,
    owner_id: UUID,
    project_id: UUID,
    run_id: UUID,
    query_id: UUID,
    attempt_id: UUID,
    error_code: str,
) -> None:
    await with_session(
        lambda session: service.fail_attempt(
            session,
            owner_id=owner_id,
            project_id=project_id,
            run_id=run_id,
            query_id=query_id,
            attempt_id=attempt_id,
            error_code=error_code,
        )
    )


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
