"""Stable research-service facade over command, execution, and read modules."""

from shopping.research.commands import create_run, effective_budgets, exact_replay
from shopping.research.common import _decode_cursor, normalize_candidate_url
from shopping.research.execution import (
    cancel_run,
    complete_attempt,
    fail_attempt,
    fail_run,
    finalize,
    interrupt_all_unfinished,
    interrupt_project_runs,
    interrupt_run,
    list_run_queries,
    load_execution_input,
    mark_running,
    run_started_at,
    save_plan,
    start_attempt,
)
from shopping.research.reads import get_run, list_candidates, list_runs

__all__ = [
    "cancel_run",
    "complete_attempt",
    "create_run",
    "effective_budgets",
    "exact_replay",
    "fail_attempt",
    "fail_run",
    "finalize",
    "get_run",
    "interrupt_all_unfinished",
    "interrupt_project_runs",
    "interrupt_run",
    "list_candidates",
    "list_run_queries",
    "list_runs",
    "load_execution_input",
    "mark_running",
    "normalize_candidate_url",
    "run_started_at",
    "save_plan",
    "start_attempt",
    "_decode_cursor",
]
