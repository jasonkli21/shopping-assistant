from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from shopping.projects.models import ShoppingProject
from shopping.research.common import ACTIVE_STATES, _conflict, _invalid, _live_project, _money
from shopping.research.models import ResearchRun, SearchQueryRecord
from shopping.research.reads import _run_read
from shopping.research.schemas import ResearchBudgets, ResearchCreate, ResearchRunRead


def exact_replay(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    command: ResearchCreate,
) -> ResearchRunRead | None:
    project = _live_project(session, owner_id, project_id)
    del project
    run = session.scalar(
        select(ResearchRun)
        .options(selectinload(ResearchRun.queries).selectinload(SearchQueryRecord.attempts))
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.request_key == command.request_key,
        )
    )
    if run is None:
        return None
    if run.request_hash != _request_hash(command):
        raise _conflict("request_key_conflict", "This request key was used for another command")
    return _run_read(run, replayed=True)


def create_run(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    command: ResearchCreate,
    settings: Any,
    ai_provider_name: str,
    search_provider_name: str,
) -> tuple[ResearchRunRead, bool]:
    project = _live_project(session, owner_id, project_id, lock=True)
    existing = session.scalar(
        select(ResearchRun)
        .options(selectinload(ResearchRun.queries).selectinload(SearchQueryRecord.attempts))
        .where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.request_key == command.request_key,
        )
    )
    if existing is not None:
        if existing.request_hash != _request_hash(command):
            raise _conflict("request_key_conflict", "This request key was used for another command")
        return _run_read(existing, replayed=True), False
    if project.revision != command.expected_version:
        raise _conflict(
            "revision_conflict",
            "The project changed before discovery started",
            {"current_version": project.revision},
        )
    active = session.scalar(
        select(ResearchRun.id).where(
            ResearchRun.owner_id == owner_id,
            ResearchRun.project_id == project_id,
            ResearchRun.status.in_(ACTIVE_STATES),
        )
    )
    if active is not None:
        raise _conflict("research_active", "A discovery run is already active for this project")

    snapshot = _snapshot(project, command)
    budgets = effective_budgets(command.budgets, settings)
    if command.manual_queries and len(command.manual_queries) > budgets["max_queries"]:
        raise _invalid("The supplied query list exceeds the effective query budget")
    run = ResearchRun(
        project_id=project.id,
        owner_id=owner_id,
        objective=command.objective,
        run_type=command.type,
        status="queued",
        request_key=command.request_key,
        request_hash=_request_hash(command),
        snapshot_revision=project.revision,
        input_snapshot=snapshot,
        effective_budgets=budgets,
        task_name="plan_discovery.v1",
        prompt_version="shopping-discovery-1",
        schema_version=1,
        ai_provider=ai_provider_name,
        search_provider=search_provider_name,
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _conflict(
            "research_active", "A discovery run is already active for this project"
        ) from error
    session.refresh(run)
    return _run_read(run), True


def effective_budgets(requested: ResearchBudgets, settings: Any) -> dict[str, int]:
    def cap(name: str, server: int) -> int:
        selected = getattr(requested, name)
        return min(server, selected) if selected is not None else server

    return {
        "max_queries": cap("max_queries", settings.research_max_queries),
        "max_candidates": cap("max_candidates", settings.research_max_candidates),
        "max_results": cap("max_results", settings.research_max_results),
        "max_results_per_query": cap(
            "max_results_per_query", settings.research_max_results_per_query
        ),
        "max_attempts": cap("max_attempts", settings.research_max_attempts),
        "deadline_seconds": cap("deadline_seconds", settings.research_deadline_seconds),
        "max_concurrent": cap("max_concurrent", settings.research_max_concurrent_searches),
    }


def _snapshot(project: ShoppingProject, command: ResearchCreate) -> dict[str, Any]:
    requirements = list(
        sorted(project.requirements, key=lambda item: (item.position, str(item.id)))
    )[:100]
    snapshot = {
        "objective": command.objective,
        "manual_queries": command.manual_queries,
        "project": {
            "id": str(project.id),
            "revision": project.revision,
            "title": project.title,
            "goal": project.goal,
            "category": project.category,
            "budget_target": _money(project.budget_target),
            "budget_maximum": _money(project.budget_maximum),
            "budget_currency": project.budget_currency,
        },
        "requirements": [
            {
                "id": str(item.id),
                "kind": item.kind,
                "label": item.label,
                "detail": item.detail,
                "attribute_key": item.attribute_key,
                "operator": item.operator,
                "value": item.value,
                "unit": item.unit,
            }
            for item in requirements
        ],
    }
    encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded) > 24_000:
        raise _invalid("Project discovery context exceeds its configured size limit")
    return snapshot


def _request_hash(command: ResearchCreate) -> str:
    encoded = json.dumps(
        command.model_dump(mode="json", exclude_none=False),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
