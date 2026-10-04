"""Add durable bounded discovery runs, search lineage and provisional candidates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_bounded_discovery"
down_revision: str | None = "0004_proposal_applied_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("objective", sa.String(length=2000), nullable=False),
        sa.Column("run_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_revision", sa.Integer(), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effective_budgets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("task_name", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("ai_provider", sa.String(length=40), nullable=False),
        sa.Column("search_provider", sa.String(length=40), nullable=False),
        sa.Column("queries_planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queries_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queries_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("results_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidates_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.String(length=2000), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("run_type = 'discovery'", name="ck_research_run_type"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', "
            "'canceled', 'interrupted')",
            name="ck_research_run_status",
        ),
        sa.CheckConstraint(
            "char_length(objective) BETWEEN 1 AND 2000", name="ck_research_objective"
        ),
        sa.CheckConstraint("snapshot_revision >= 1", name="ck_research_snapshot_revision"),
        sa.CheckConstraint(
            "queries_planned >= 0 AND queries_completed >= 0 AND queries_failed >= 0",
            name="ck_research_query_counts",
        ),
        sa.CheckConstraint(
            "attempts_used >= 0 AND results_found >= 0 AND candidates_found >= 0 "
            "AND skipped_count >= 0",
            name="ck_research_work_counts",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "project_id", "request_key", name="uq_research_runs_request_key"
        ),
    )
    op.create_index(
        "ix_research_runs_project_queued", "research_runs", ["owner_id", "project_id", "queued_at"]
    )
    op.create_index(
        "uq_research_runs_one_active_project",
        "research_runs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "search_queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=False),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("results_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidates_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("ordinal >= 0", name="ck_search_query_ordinal"),
        sa.CheckConstraint("max_results BETWEEN 1 AND 20", name="ck_search_query_max_results"),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'succeeded', 'failed', 'skipped', 'canceled')",
            name="ck_search_query_state",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_search_query_run_ordinal"),
    )

    op.create_table(
        "search_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("provider_request_id", sa.String(length=200), nullable=True),
        sa.Column("results_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage_units", sa.Integer(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_number >= 1", name="ck_search_attempt_number"),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'canceled')",
            name="ck_search_attempt_status",
        ),
        sa.CheckConstraint(
            "usage_units IS NULL OR usage_units BETWEEN 0 AND 100000",
            name="ck_search_attempt_usage_units",
        ),
        sa.ForeignKeyConstraint(["query_id"], ["search_queries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query_id", "attempt_number", name="uq_search_attempt_query_number"),
    )

    op.create_table(
        "search_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("result_rank", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("snippet", sa.String(length=2000), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "provider_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint("result_rank >= 1", name="ck_search_result_rank"),
        sa.CheckConstraint("char_length(title) <= 300", name="ck_search_result_title_length"),
        sa.CheckConstraint("char_length(url) <= 2048", name="ck_search_result_url_length"),
        sa.CheckConstraint(
            "snippet IS NULL OR char_length(snippet) <= 2000",
            name="ck_search_result_snippet_length",
        ),
        sa.ForeignKeyConstraint(["query_id"], ["search_queries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["search_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query_id", "result_rank", name="uq_search_result_query_rank"),
    )

    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("provisional_name", sa.String(length=300), nullable=False),
        sa.Column("brand_clue", sa.String(length=200), nullable=True),
        sa.Column("model_clue", sa.String(length=200), nullable=True),
        sa.Column("category_clue", sa.String(length=100), nullable=True),
        sa.Column("discovery_reason", sa.String(length=300), nullable=False),
        sa.Column("indicative_price_text", sa.String(length=200), nullable=True),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("canonical_mapping_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "char_length(provisional_name) BETWEEN 1 AND 300", name="ck_candidate_name"
        ),
        sa.CheckConstraint(
            "char_length(normalized_url) <= 2048", name="ck_candidate_normalized_url"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "normalized_url", name="uq_candidate_run_normalized_url"),
    )
    op.create_index(
        "ix_candidates_project_created", "discovery_candidates", ["project_id", "created_at", "id"]
    )

    op.create_table(
        "candidate_search_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("search_result_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["discovery_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["search_result_id"], ["search_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "search_result_id", name="uq_candidate_search_result"),
    )


def downgrade() -> None:
    op.drop_table("candidate_search_results")
    op.drop_index("ix_candidates_project_created", table_name="discovery_candidates")
    op.drop_table("discovery_candidates")
    op.drop_table("search_results")
    op.drop_table("search_attempts")
    op.drop_table("search_queries")
    op.drop_index("uq_research_runs_one_active_project", table_name="research_runs")
    op.drop_index("ix_research_runs_project_queued", table_name="research_runs")
    op.drop_table("research_runs")
