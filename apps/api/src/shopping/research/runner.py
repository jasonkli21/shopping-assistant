"""Drain one persisted research run from the command line."""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from shopping.config import get_settings
from shopping.db.session import SessionLocal
from shopping.extraction.http_retriever import HTTPPageRetriever
from shopping.integrations.personal_ai.client import UnavailablePersonalAIClient
from shopping.integrations.personal_ai.fake import FakePersonalAIClient
from shopping.research.supervisor import DiscoverySupervisor
from shopping.search.factory import create_search_provider


async def _drain(run_id: UUID) -> None:
    settings = get_settings()
    client = (
        FakePersonalAIClient()
        if settings.personal_ai_mode == "fake"
        else UnavailablePersonalAIClient()
    )
    supervisor = DiscoverySupervisor(
        client=client,
        search_provider=create_search_provider(settings),
        session_factory=SessionLocal,
        provider_timeout_seconds=settings.research_provider_timeout_seconds,
        max_concurrent=settings.research_max_concurrent_runs,
        page_retriever=HTTPPageRetriever(),
    )
    try:
        await supervisor.submit(run_id)
        await supervisor.wait(run_id)
    finally:
        await supervisor.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Drain a queued shopping research run locally.")
    parser.add_argument("--run-id", type=UUID, required=True, help="Persisted research run UUID")
    args = parser.parse_args()
    asyncio.run(_drain(args.run_id))


if __name__ == "__main__":
    main()
