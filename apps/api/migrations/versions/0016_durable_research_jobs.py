"""Add durable research job leases and execution attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_durable_research_jobs"
down_revision: str | None = "0015_research_modes_and_refresh"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_runs", sa.Column("active_job_token", sa.Uuid(), nullable=True))
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("stage_type", sa.String(length=20), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "not_before", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("lease_owner", sa.String(length=100), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "stage_type IN ('plan', 'search', 'retrieve', 'extract', 'assess', 'refresh_offer')",
            name="ck_research_job_stage_type",
        ),
        sa.CheckConstraint("payload_version >= 1", name="ck_research_job_payload_version"),
        sa.CheckConstraint(
            "octet_length(payload::text) <= 16000", name="ck_research_job_payload_size"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name="ck_research_job_status",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_research_job_ordinal"),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 5", name="ck_research_job_attempt_count"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 5", name="ck_research_job_max_attempts"),
        sa.CheckConstraint(
            "(status = 'running' AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL) OR status <> 'running'",
            name="ck_research_job_lease_state",
        ),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "research_run_id", "stage_type", "ordinal", name="uq_research_job_stage"
        ),
    )
    op.create_index(
        "ix_research_jobs_dispatch",
        "research_jobs",
        ["status", "not_before", "lease_expires_at"],
    )
    op.create_index("ix_research_jobs_run_order", "research_jobs", ["research_run_id", "ordinal"])
    op.create_index(
        "uq_research_jobs_run_running",
        "research_jobs",
        ["research_run_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "research_job_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("provider_request_id", sa.String(length=200), nullable=True),
        sa.Column(
            "budget_consumed",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("number BETWEEN 1 AND 5", name="ck_research_job_attempt_number"),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'canceled', 'uncertain')",
            name="ck_research_job_attempt_status",
        ),
        sa.CheckConstraint(
            "octet_length(budget_consumed::text) <= 4000",
            name="ck_research_job_attempt_budget_size",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "number", name="uq_research_job_attempt_number"),
        sa.UniqueConstraint("lease_token"),
    )
    op.execute(
        """
        INSERT INTO research_jobs (
            id, research_run_id, stage_type, ordinal, payload_version, payload, status,
            attempt_count, max_attempts, not_before, created_at
        )
        SELECT gen_random_uuid(), id,
               CASE WHEN run_type = 'product_research' THEN 'plan' ELSE 'search' END,
               0, 1, jsonb_build_object('research_run_id', id::text), 'queued', 0, 3,
               now(), now()
        FROM research_runs
        WHERE status IN ('queued', 'running')
        """
    )


def downgrade() -> None:
    op.drop_table("research_job_attempts")
    op.drop_index("uq_research_jobs_run_running", table_name="research_jobs")
    op.drop_index("ix_research_jobs_run_order", table_name="research_jobs")
    op.drop_index("ix_research_jobs_dispatch", table_name="research_jobs")
    op.drop_table("research_jobs")
    op.drop_column("research_runs", "active_job_token")
