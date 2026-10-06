"""Durable run dispatch, lease ownership, and fencing for research workers."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from shopping.evidence.models import ResearchRunSource
from shopping.research.models import (
    ResearchJob,
    ResearchJobAttempt,
    ResearchRun,
    ResearchStageAttempt,
    SearchAttempt,
    SearchQueryRecord,
)

ACTIVE_RESEARCH_JOB_TOKEN: ContextVar[UUID | None] = ContextVar(
    "active_research_job_token", default=None
)


@dataclass(frozen=True)
class ResearchJobClaim:
    job_id: UUID
    run_id: UUID
    owner_id: UUID
    project_id: UUID
    token: UUID
    stage_type: str
    payload: dict
    attempt_number: int


def enqueue_run_job(session: Session, run: ResearchRun) -> ResearchJob:
    """Create the initial serializable dispatch record in the run's transaction."""
    job = ResearchJob(
        research_run_id=run.id,
        stage_type=(
            "refresh_offer"
            if run.run_type == "product_research"
            and run.input_snapshot.get("refresh_targets") == ["offers"]
            else "plan"
            if run.run_type == "product_research"
            else "search"
        ),
        ordinal=0,
        payload_version=1,
        payload={"research_run_id": str(run.id)},
        status="queued",
        attempt_count=0,
        max_attempts=3,
    )
    session.add(job)
    return job


def claim_job(
    session: Session,
    *,
    worker_id: str,
    now: datetime | None = None,
    lease_seconds: int = 60,
    run_id: UUID | None = None,
) -> ResearchJobClaim | None:
    now = _utc(now or datetime.now(UTC))
    worker_id = worker_id.strip()[:100]
    if not worker_id:
        raise ValueError("worker_id must not be blank")

    eligible = or_(
        (ResearchJob.status == "queued") & (ResearchJob.not_before <= now),
        (ResearchJob.status == "running") & (ResearchJob.lease_expires_at <= now),
    )
    candidate_query = (
        select(ResearchJob.research_run_id)
        .where(eligible)
        .order_by(ResearchJob.not_before, ResearchJob.created_at, ResearchJob.id)
        .limit(1)
    )
    if run_id is not None:
        candidate_query = candidate_query.where(ResearchJob.research_run_id == run_id)
    candidate_run_id = session.scalar(candidate_query)
    if candidate_run_id is None:
        return None

    run = session.scalar(
        select(ResearchRun)
        .where(ResearchRun.id == candidate_run_id)
        .with_for_update(skip_locked=True)
    )
    if run is None or run.status not in {"queued", "running"}:
        return None
    job = session.scalar(
        select(ResearchJob)
        .where(ResearchJob.research_run_id == run.id, eligible)
        .order_by(ResearchJob.ordinal, ResearchJob.created_at, ResearchJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None

    if job.status == "running":
        _recover_expired_attempt(session, job, run, now)
    if _run_deadline_expired(run, now):
        if job.status == "queued":
            _mark_run_deadline_expired(run, job, now)
            session.commit()
            return None
        if job.attempt_count >= job.max_attempts:
            job.status = "failed"
            job.error_code = "lease_recovery_exhausted"
            job.finished_at = now
            run.status = "interrupted"
            run.error_code = job.error_code
            run.summary = "Research stopped after repeated worker lease expiry."
            run.finished_at = now
            run.active_job_token = None
            session.commit()
            return None

    token = uuid4()
    number = job.attempt_count + 1
    job.status = "running"
    job.attempt_count = number
    job.lease_owner = worker_id
    job.lease_token = token
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.heartbeat_at = now
    job.started_at = job.started_at or now
    job.finished_at = None
    job.error_code = None
    run.active_job_token = token
    attempt = ResearchJobAttempt(
        job_id=job.id,
        number=number,
        lease_token=token,
        status="running",
        budget_consumed={},
        started_at=now,
    )
    session.add(attempt)
    session.commit()
    return ResearchJobClaim(
        job_id=job.id,
        run_id=run.id,
        owner_id=run.owner_id,
        project_id=run.project_id,
        token=token,
        stage_type=job.stage_type,
        payload=job.payload,
        attempt_number=number,
    )


def heartbeat_job(
    session: Session,
    *,
    job_id: UUID,
    token: UUID,
    now: datetime | None = None,
    lease_seconds: int = 60,
) -> bool:
    now = _utc(now or datetime.now(UTC))
    run, job = _lock_run_then_job(session, job_id)
    if (
        run is None
        or job is None
        or job.status != "running"
        or job.lease_token != token
        or job.lease_expires_at is None
        or _utc(job.lease_expires_at) <= now
    ):
        return False
    if run is None or run.active_job_token != token or run.status not in {"queued", "running"}:
        return False
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    session.commit()
    return True


def complete_job(
    session: Session,
    *,
    job_id: UUID,
    token: UUID,
    status: str,
    error_code: str | None = None,
    provider_request_id: str | None = None,
    budget_consumed: dict | None = None,
    now: datetime | None = None,
) -> bool:
    if status not in {"succeeded", "failed", "canceled"}:
        raise ValueError("invalid research job terminal status")
    now = _utc(now or datetime.now(UTC))
    run, job = _lock_run_then_job(session, job_id)
    if (
        run is None
        or job is None
        or job.status != "running"
        or job.lease_token != token
        or job.lease_expires_at is None
        or _utc(job.lease_expires_at) <= now
    ):
        return False
    if run is None or run.active_job_token != token:
        return False
    attempt = session.scalar(
        select(ResearchJobAttempt)
        .where(ResearchJobAttempt.job_id == job.id, ResearchJobAttempt.lease_token == token)
        .with_for_update()
    )
    if attempt is None or attempt.status != "running":
        return False
    job.status = status
    job.error_code = _safe_code(error_code)
    job.finished_at = now
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    job.heartbeat_at = now
    attempt.status = status
    attempt.error_code = _safe_code(error_code)
    attempt.provider_request_id = (
        provider_request_id[:200] if isinstance(provider_request_id, str) else None
    )
    attempt.budget_consumed = budget_consumed or {}
    attempt.finished_at = now
    run.active_job_token = None
    session.commit()
    return True


def cancel_run_jobs(
    session: Session,
    run_id: UUID,
    *,
    now: datetime | None = None,
    error_code: str = "user_canceled",
    job_status: str = "canceled",
    attempt_status: str = "canceled",
) -> None:
    now = _utc(now or datetime.now(UTC))
    run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id).with_for_update())
    if run is None:
        return
    jobs = list(
        session.scalars(
            select(ResearchJob)
            .where(
                ResearchJob.research_run_id == run_id, ResearchJob.status.in_(["queued", "running"])
            )
            .with_for_update()
        ).all()
    )
    for job in jobs:
        job.status = job_status
        job.error_code = error_code
        job.finished_at = now
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        attempts = list(
            session.scalars(
                select(ResearchJobAttempt)
                .where(ResearchJobAttempt.job_id == job.id, ResearchJobAttempt.status == "running")
                .with_for_update()
            ).all()
        )
        for attempt in attempts:
            attempt.status = attempt_status
            attempt.error_code = error_code
            attempt.finished_at = now
    run.active_job_token = None
    session.flush()


def recover_expired_jobs(session: Session, *, now: datetime | None = None) -> list[UUID]:
    now = _utc(now or datetime.now(UTC))
    expired_ids = list(
        session.scalars(
            select(ResearchJob.id)
            .where(
                ResearchJob.status == "running",
                ResearchJob.lease_expires_at <= now,
            )
            .order_by(ResearchJob.lease_expires_at, ResearchJob.id)
        ).all()
    )
    recovered: list[UUID] = []
    for job_id in expired_ids:
        run, job = _lock_run_then_job(session, job_id, skip_locked=True)
        if job is None or run is None or job.status != "running" or job.lease_expires_at is None:
            continue
        if _utc(job.lease_expires_at) > now:
            continue
        if run.status not in {"queued", "running"}:
            _reconcile_terminal_run_job(session, job, run, now)
            recovered.append(run.id)
            continue
        if _run_deadline_expired(run, now):
            _recover_expired_attempt(session, job, run, now)
            _mark_run_deadline_expired(run, job, now)
            recovered.append(run.id)
            continue
        if job.attempt_count >= job.max_attempts:
            _recover_expired_attempt(session, job, run, now)
            job.status = "failed"
            job.error_code = "lease_recovery_exhausted"
            job.finished_at = now
            run.status = "interrupted"
            run.error_code = job.error_code
            run.summary = "Research stopped after repeated worker lease expiry."
            run.finished_at = now
            run.active_job_token = None
            recovered.append(run.id)
            continue
        _recover_expired_attempt(session, job, run, now)
        recovered.append(run.id)
    session.commit()
    return recovered


def dispatchable_run_ids(session: Session, *, now: datetime | None = None) -> list[UUID]:
    now = _utc(now or datetime.now(UTC))
    return list(
        session.scalars(
            select(ResearchJob.research_run_id)
            .join(ResearchRun, ResearchRun.id == ResearchJob.research_run_id)
            .where(
                ResearchJob.status == "queued",
                ResearchJob.not_before <= now,
                ResearchRun.status.in_(["queued", "running"]),
            )
            .order_by(ResearchJob.research_run_id)
            .distinct()
        ).all()
    )


def reconcile_terminal_run_jobs(session: Session, *, now: datetime | None = None) -> int:
    """Settle dispatch rows left running after a run's terminal commit."""
    now = _utc(now or datetime.now(UTC))
    run_ids = list(
        session.scalars(
            select(ResearchJob.research_run_id)
            .join(ResearchRun, ResearchRun.id == ResearchJob.research_run_id)
            .where(
                ResearchJob.status == "running",
                ResearchRun.status.not_in(["queued", "running"]),
            )
            .distinct()
        ).all()
    )
    settled = 0
    for run_id in run_ids:
        run = session.scalar(
            select(ResearchRun).where(ResearchRun.id == run_id).with_for_update(skip_locked=True)
        )
        if run is None or run.status in {"queued", "running"}:
            continue
        jobs = list(
            session.scalars(
                select(ResearchJob)
                .where(ResearchJob.research_run_id == run_id, ResearchJob.status == "running")
                .with_for_update(skip_locked=True)
            ).all()
        )
        for job in jobs:
            _reconcile_terminal_run_job(session, job, run, now)
            settled += 1
    session.commit()
    return settled


def _recover_expired_attempt(
    session: Session, job: ResearchJob, run: ResearchRun, now: datetime
) -> None:
    token = job.lease_token
    if token is not None:
        attempt = session.scalar(
            select(ResearchJobAttempt)
            .where(ResearchJobAttempt.job_id == job.id, ResearchJobAttempt.lease_token == token)
            .with_for_update()
        )
        if attempt is not None and attempt.status == "running":
            attempt.status = "uncertain"
            attempt.error_code = "worker_lease_expired"
            attempt.finished_at = now
    _reopen_inflight_stages(session, run, now)
    job.status = "queued"
    job.error_code = "worker_lease_expired"
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    job.heartbeat_at = now
    job.not_before = now
    run.active_job_token = None


def _lock_run_then_job(
    session: Session, job_id: UUID, *, skip_locked: bool = False
) -> tuple[ResearchRun | None, ResearchJob | None]:
    """Lock every dispatch mutation in the shared run -> job order."""
    run_id = session.scalar(select(ResearchJob.research_run_id).where(ResearchJob.id == job_id))
    if run_id is None:
        return None, None
    run_stmt = (
        select(ResearchRun).where(ResearchRun.id == run_id).with_for_update(skip_locked=skip_locked)
    )
    run = session.scalar(run_stmt)
    if run is None:
        return None, None
    job_stmt = (
        select(ResearchJob).where(ResearchJob.id == job_id).with_for_update(skip_locked=skip_locked)
    )
    return run, session.scalar(job_stmt)


def _run_deadline_expired(run: ResearchRun, now: datetime) -> bool:
    if run.started_at is None:
        return False
    started = _utc(run.started_at)
    return now >= started + timedelta(seconds=run.effective_budgets["deadline_seconds"])


def _mark_run_deadline_expired(run: ResearchRun, job: ResearchJob, now: datetime) -> None:
    job.status = "failed"
    job.error_code = "deadline_exceeded"
    job.finished_at = now
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    run.status = "interrupted"
    run.error_code = "deadline_exceeded"
    run.summary = "Research stopped when its saved deadline expired."
    run.finished_at = now
    run.active_job_token = None


def _reconcile_terminal_run_job(
    session: Session, job: ResearchJob, run: ResearchRun, now: datetime
) -> None:
    terminal_status = (
        "canceled"
        if run.status == "canceled"
        else "succeeded"
        if run.status in {"succeeded", "partial"}
        else "failed"
    )
    attempt = session.scalar(
        select(ResearchJobAttempt)
        .where(ResearchJobAttempt.job_id == job.id, ResearchJobAttempt.status == "running")
        .order_by(ResearchJobAttempt.number.desc())
        .limit(1)
        .with_for_update()
    )
    if attempt is not None:
        attempt.status = terminal_status
        attempt.error_code = _safe_code(run.error_code)
        attempt.finished_at = now
    job.status = terminal_status
    job.error_code = _safe_code(run.error_code)
    job.finished_at = now
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    job.heartbeat_at = now
    run.active_job_token = None


def _reopen_inflight_stages(session: Session, run: ResearchRun, now: datetime) -> None:
    queries = list(
        session.scalars(
            select(SearchQueryRecord)
            .where(SearchQueryRecord.run_id == run.id, SearchQueryRecord.state == "running")
            .with_for_update()
        ).all()
    )
    for query in queries:
        query.state = "failed"
        query.error_code = "uncertain_completion"
        query.retry_not_before = None
        query.completed_at = now
        run.queries_failed += 1
        run.error_code = run.error_code or "uncertain_completion"
        attempts = list(
            session.scalars(
                select(SearchAttempt)
                .where(SearchAttempt.query_id == query.id, SearchAttempt.status == "running")
                .with_for_update()
            ).all()
        )
        for attempt in attempts:
            attempt.status = "uncertain"
            attempt.error_code = "uncertain_completion"
            attempt.finished_at = now
    stage_attempts = list(
        session.scalars(
            select(ResearchStageAttempt)
            .where(
                ResearchStageAttempt.research_run_id == run.id,
                ResearchStageAttempt.status == "running",
            )
            .with_for_update()
        ).all()
    )
    for attempt in stage_attempts:
        attempt.status = "failed"
        attempt.error_code = "uncertain_completion"
        attempt.finished_at = now
    sources = list(
        session.scalars(
            select(ResearchRunSource)
            .where(
                ResearchRunSource.research_run_id == run.id,
                ResearchRunSource.status == "running",
            )
            .with_for_update()
        ).all()
    )
    for source in sources:
        source.status = "failed"
        source.reason = "uncertain_completion"


def _safe_code(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = "".join(char if char.isalnum() or char == "_" else "_" for char in value.lower())
    return normalized[:60] or None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
