"""Persist selected-product targets and bounded research stage attempts."""
# Generated PostgreSQL DDL is kept verbatim to make this migration independent of ORM drift.
# ruff: noqa: E501

from collections.abc import Sequence

from alembic import op

revision: str = "0010_research_stage_progress"
down_revision: str | None = "0009_evidence_research"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_research_run_source_status", "research_run_sources", type_="check")
    op.create_check_constraint(
        "ck_research_run_source_status",
        "research_run_sources",
        "status IN ('running', 'retrieved', 'blocked', 'timeout', 'unsupported', 'failed', 'skipped')",
    )
    op.execute(
        "CREATE TABLE research_run_targets (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tresearch_run_id UUID NOT NULL, \n\tproject_product_id UUID NOT NULL, \n\tproduct_id UUID NOT NULL, \n\tvariant_id UUID NOT NULL, \n\tproduct_revision INTEGER NOT NULL, \n\tvariant_revision INTEGER NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\tsources_attempted INTEGER NOT NULL, \n\tsources_retrieved INTEGER NOT NULL, \n\tclaims_created INTEGER NOT NULL, \n\terror_code VARCHAR(60), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_research_run_target_status CHECK (status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'skipped')), \n\tCONSTRAINT ck_research_run_target_counts CHECK (sources_attempted >= 0 AND sources_retrieved >= 0 AND claims_created >= 0), \n\tCONSTRAINT uq_research_run_target UNIQUE (research_run_id, project_product_id), \n\tFOREIGN KEY(research_run_id) REFERENCES research_runs (id) ON DELETE CASCADE, \n\tFOREIGN KEY(project_product_id) REFERENCES project_products (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(variant_id) REFERENCES product_variants (id) ON DELETE RESTRICT\n)"
    )
    op.execute(
        "CREATE INDEX ix_research_run_targets_status ON research_run_targets (research_run_id, status)"
    )
    op.execute(
        "CREATE TABLE research_stage_attempts (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tresearch_run_id UUID NOT NULL, \n\ttarget_project_product_id UUID, \n\tstage VARCHAR(16) NOT NULL, \n\tattempt_number INTEGER NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\ttask_name VARCHAR(80) NOT NULL, \n\tprompt_version VARCHAR(80) NOT NULL, \n\terror_code VARCHAR(60), \n\tprovider_request_id VARCHAR(200), \n\tinput_chars INTEGER NOT NULL, \n\toutput_chars INTEGER NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_research_stage_attempt_stage CHECK (stage IN ('planning', 'extraction', 'relations', 'assessment')), \n\tCONSTRAINT ck_research_stage_attempt_status CHECK (status IN ('running', 'succeeded', 'failed', 'skipped', 'canceled')), \n\tCONSTRAINT ck_research_stage_attempt_number CHECK (attempt_number BETWEEN 1 AND 3), \n\tCONSTRAINT ck_research_stage_attempt_chars CHECK (input_chars BETWEEN 0 AND 24000 AND output_chars BETWEEN 0 AND 16000), \n\tFOREIGN KEY(research_run_id) REFERENCES research_runs (id) ON DELETE CASCADE, \n\tFOREIGN KEY(target_project_product_id) REFERENCES project_products (id) ON DELETE SET NULL\n)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_research_stage_attempt_global ON research_stage_attempts (research_run_id, stage, attempt_number) WHERE target_project_product_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_research_stage_attempt_target ON research_stage_attempts (research_run_id, target_project_product_id, stage, attempt_number) WHERE target_project_product_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("research_stage_attempts")
    op.drop_table("research_run_targets")
    op.drop_constraint("ck_research_run_source_status", "research_run_sources", type_="check")
    op.create_check_constraint(
        "ck_research_run_source_status",
        "research_run_sources",
        "status IN ('retrieved', 'blocked', 'timeout', 'unsupported', 'failed', 'skipped')",
    )
