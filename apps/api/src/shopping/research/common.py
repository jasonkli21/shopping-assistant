from __future__ import annotations

import base64
import ipaddress
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.projects.errors import ProjectError
from shopping.projects.models import ShoppingProject
from shopping.research.jobs import ACTIVE_RESEARCH_JOB_TOKEN
from shopping.research.models import ResearchJob, ResearchRun

ACTIVE_STATES = {"queued", "running"}


TERMINAL_STATES = {"succeeded", "partial", "failed", "canceled", "interrupted"}


SAFE_ERROR_CODES = {
    "ai_call_budget_exhausted",
    "attempt_budget_exhausted",
    "blocked_address",
    "blocked_port",
    "byte_budget_exhausted",
    "deadline_exceeded",
    "discovery_failed",
    "discovery_stopped",
    "uncertain_completion",
    "execution_fenced",
    "invalid_plan",
    "invalid_redirect",
    "malformed_response",
    "no_grounded_claims",
    "no_product_data",
    "no_sources_retrieved",
    "page_budget_exhausted",
    "page_too_large",
    "planner_failed",
    "planner_timeout",
    "process_restarted",
    "project_deleted",
    "provider_auth",
    "provider_error",
    "provider_refused",
    "provider_rejected",
    "provider_timeout",
    "provider_unavailable",
    "ambiguous_products",
    "missing_product_name",
    "invalid_structured_data",
    "unsupported_extraction",
    "unrelated_offer",
    "invalid_offer_origin",
    "variant_identity_mismatch",
    "target_missing",
    "refresh_failed",
    "quota_exceeded",
    "rate_limited",
    "result_budget_exhausted",
    "source_budget_exhausted",
    "source_class_mismatch",
    "source_domain_excluded",
    "server_error",
    "stage_attempt_budget_exhausted",
    "unsupported_content_type",
    "url_too_long",
    "user_canceled",
    "worker_interrupted",
}


def _live_project(
    session: Session, owner_id: UUID, project_id: UUID, *, lock: bool = False
) -> ShoppingProject:
    statement = select(ShoppingProject).where(
        ShoppingProject.id == project_id,
        ShoppingProject.owner_id == owner_id,
        ShoppingProject.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    project = session.scalar(statement)
    if project is None:
        raise _not_found("Project not found")
    return project


def _lock_live_run(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID
) -> tuple[ShoppingProject, ResearchRun]:
    project = _live_project(session, owner_id, project_id, lock=True)
    run = _owned_run(session, owner_id, project_id, run_id, lock=True)
    if run is None:
        raise _not_found("Research run not found")
    worker_token = ACTIVE_RESEARCH_JOB_TOKEN.get()
    if worker_token is not None and run.active_job_token != worker_token:
        raise _conflict(
            "execution_fenced",
            "This research worker no longer owns the active job lease.",
        )
    if worker_token is not None:
        now = datetime.now(UTC)
        job = session.scalar(
            select(ResearchJob)
            .where(
                ResearchJob.research_run_id == run.id,
                ResearchJob.status == "running",
                ResearchJob.lease_token == worker_token,
                ResearchJob.lease_expires_at > now,
            )
            .with_for_update()
        )
        if job is None:
            raise _conflict(
                "execution_fenced",
                "This research worker no longer owns a live job lease.",
            )
    return project, run


def _owned_run(
    session: Session, owner_id: UUID, project_id: UUID, run_id: UUID, *, lock: bool = False
) -> ResearchRun | None:
    statement = select(ResearchRun).where(
        ResearchRun.owner_id == owner_id,
        ResearchRun.project_id == project_id,
        ResearchRun.id == run_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _safe_http_url(value: str) -> str | None:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not host
            or parsed.username
            or parsed.password
        ):
            return None
        port = parsed.port
        if port is not None and not (1 <= port <= 65535):
            return None
        lowered = host.lower().rstrip(".")
        if lowered == "localhost" or lowered.endswith((".localhost", ".local")):
            return None
        try:
            address = ipaddress.ip_address(lowered)
            if not address.is_global:
                return None
        except ValueError:
            if not re.fullmatch(r"[a-z0-9.-]+", lowered) or "." not in lowered:
                return None
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc,
                parsed.path or "/",
                parsed.query,
                parsed.fragment,
            )
        )
    except ValueError:
        return None


def normalize_candidate_url(url: str) -> str:
    safe = _safe_http_url(url)
    if safe is None:
        raise ValueError("search result URL is not safe HTTP/S")
    parsed = urlsplit(safe)
    host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
    port = parsed.port
    netloc = (
        host
        if port is None
        or (parsed.scheme == "http" and port == 80)
        or (parsed.scheme == "https" and port == 443)
        else f"{host}:{port}"
    )
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))


def _clean_text(value: str | None, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = "".join(char for char in value[:limit] if char in "\n\t" or ord(char) >= 32)
    return cleaned.strip()[:limit]


def _money(value: Any) -> str | None:
    return None if value is None else format(value, "f")


def _encode_cursor(created_at: datetime, candidate_id: UUID) -> str:
    value = json.dumps([created_at.isoformat(), str(candidate_id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        if not isinstance(cursor, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", cursor):
            raise ValueError("invalid cursor encoding")
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
        value = json.loads(decoded.decode("utf-8"))
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not isinstance(value[0], str)
            or not isinstance(value[1], str)
        ):
            raise ValueError("invalid cursor payload")
        timestamp = datetime.fromisoformat(value[0])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("cursor timestamp must be timezone-aware")
        return timestamp.astimezone(UTC), UUID(value[1])
    except (ValueError, TypeError, UnicodeError, OverflowError) as error:
        raise _invalid("Pagination cursor is invalid") from error


def _validate_page_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise _invalid("Pagination limit must be between 1 and 100")


def _safe_error_code(value: object) -> str:
    return value if isinstance(value, str) and value in SAFE_ERROR_CODES else "provider_error"


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _invalid(message: str) -> ProjectError:
    return ProjectError(422, "validation_error", message)


def _conflict(code: str, message: str, details: dict | None = None) -> ProjectError:
    return ProjectError(409, code, message, details)
