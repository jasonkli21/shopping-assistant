"""Persist bounded search retry scheduling and uncertain attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_bounded_search_retries"
down_revision: str | None = "0016_durable_research_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_queries", sa.Column("retry_not_before", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint("ck_search_attempt_status", "search_attempts", type_="check")
    op.create_check_constraint(
        "ck_search_attempt_status",
        "search_attempts",
        "status IN ('running', 'succeeded', 'failed', 'canceled', 'uncertain')",
    )
    op.execute(
        """
        UPDATE search_attempts
        SET status = 'uncertain', error_code = 'uncertain_completion', finished_at = now()
        WHERE status = 'running'
          AND query_id IN (
              SELECT q.id FROM search_queries q
              JOIN research_runs r ON r.id = q.run_id
              WHERE q.state = 'running' AND r.status IN ('queued', 'running')
          )
        """
    )
    op.execute(
        """
        UPDATE research_runs r
        SET queries_failed = r.queries_failed + pending.count
        FROM (
            SELECT q.run_id, count(*) AS count
            FROM search_queries q JOIN research_runs r ON r.id = q.run_id
            WHERE q.state = 'running' AND r.status IN ('queued', 'running')
            GROUP BY q.run_id
        ) AS pending
        WHERE r.id = pending.run_id
        """
    )
    op.execute(
        """
        UPDATE search_queries q
        SET state = 'failed', error_code = 'uncertain_completion',
            retry_not_before = NULL, completed_at = now()
        FROM research_runs r
        WHERE r.id = q.run_id AND q.state = 'running' AND r.status IN ('queued', 'running')
        """
    )
    op.execute(
        """
        UPDATE research_stage_attempts
        SET status = 'failed', error_code = 'uncertain_completion', finished_at = now()
        WHERE status = 'running'
          AND research_run_id IN (
              SELECT id FROM research_runs WHERE status IN ('queued', 'running')
          )
        """
    )
    op.execute(
        """
        UPDATE research_run_sources
        SET status = 'failed', reason = 'uncertain_completion'
        WHERE status = 'running'
          AND research_run_id IN (
              SELECT id FROM research_runs WHERE status IN ('queued', 'running')
          )
        """
    )


def downgrade() -> None:
    op.execute("UPDATE search_attempts SET status = 'failed' WHERE status = 'uncertain'")
    op.drop_constraint("ck_search_attempt_status", "search_attempts", type_="check")
    op.create_check_constraint(
        "ck_search_attempt_status",
        "search_attempts",
        "status IN ('running', 'succeeded', 'failed', 'canceled')",
    )
    op.drop_column("search_queries", "retry_not_before")
