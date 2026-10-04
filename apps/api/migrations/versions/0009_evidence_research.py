"""Add immutable source snapshots, grounded claims and assessment history."""
# Generated PostgreSQL DDL is kept verbatim to make this migration independent of ORM drift.
# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_evidence_research"
down_revision: str | None = "0008_offer_amount_currency_pair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE sources (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tnormalized_url VARCHAR(2048) NOT NULL, \n\ttitle VARCHAR(300), \n\tpublisher VARCHAR(200), \n\tdomain VARCHAR(253) NOT NULL, \n\tclassification VARCHAR(40) NOT NULL, \n\tclassification_basis VARCHAR(500), \n\tclassification_actor VARCHAR(24) NOT NULL, \n\tclassification_version VARCHAR(80) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_source_url CHECK (char_length(normalized_url) BETWEEN 1 AND 2048), \n\tCONSTRAINT ck_source_title CHECK (char_length(title) <= 300), \n\tCONSTRAINT ck_source_publisher CHECK (char_length(publisher) <= 200), \n\tCONSTRAINT ck_source_domain CHECK (char_length(domain) <= 253), \n\tCONSTRAINT ck_source_classification CHECK (classification IN ('manufacturer_specification', 'manufacturer_claim', 'retailer_listing', 'independent_measurement', 'editorial_assessment', 'community_observation', 'individual_anecdote', 'unknown')), \n\tCONSTRAINT uq_source_owner_url UNIQUE (owner_id, normalized_url)\n)"
    )
    op.execute("CREATE INDEX ix_sources_owner_domain ON sources (owner_id, domain)")
    op.execute(
        "CREATE TABLE source_snapshots (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tsource_id UUID NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tmedia_type VARCHAR(200), \n\ttitle VARCHAR(300), \n\tpublished_at TIMESTAMP WITH TIME ZONE, \n\tretrieved_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\trelevant_text TEXT NOT NULL, \n\texcerpts JSONB NOT NULL, \n\textractor_version VARCHAR(80) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_source_snapshot_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'), \n\tCONSTRAINT ck_source_snapshot_media_type CHECK (char_length(media_type) <= 200), \n\tCONSTRAINT ck_source_snapshot_title CHECK (char_length(title) <= 300), \n\tCONSTRAINT ck_source_snapshot_text_size CHECK (octet_length(relevant_text) <= 12000), \n\tCONSTRAINT ck_source_snapshot_excerpts_size CHECK (octet_length(excerpts::text) <= 12000), \n\tCONSTRAINT uq_source_snapshot_content UNIQUE (source_id, content_hash), \n\tCONSTRAINT uq_source_snapshot_owner UNIQUE (id, owner_id), \n\tFOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE RESTRICT\n)"
    )
    op.execute(
        "CREATE INDEX ix_source_snapshots_source_time ON source_snapshots (source_id, retrieved_at)"
    )
    op.execute(
        "CREATE TABLE claims (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tsnapshot_id UUID NOT NULL, \n\tsubject_product_id UUID NOT NULL, \n\tsubject_variant_id UUID NOT NULL, \n\tattribute_key VARCHAR(100) NOT NULL, \n\tassertion_text VARCHAR(800) NOT NULL, \n\tnormalized_value JSONB, \n\tqualifiers JSONB NOT NULL, \n\tevidence_category VARCHAR(32) NOT NULL, \n\textracted_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\ttask_name VARCHAR(80) NOT NULL, \n\tprompt_version VARCHAR(80) NOT NULL, \n\tschema_version INTEGER NOT NULL, \n\textraction_confidence VARCHAR(24), \n\tvalidation_warnings JSONB NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_claim_attribute CHECK (char_length(attribute_key) BETWEEN 1 AND 100), \n\tCONSTRAINT ck_claim_text CHECK (char_length(assertion_text) BETWEEN 1 AND 800), \n\tCONSTRAINT ck_claim_category CHECK (evidence_category IN ('manufacturer_specification', 'manufacturer_claim', 'retailer_listing', 'independent_measurement', 'editorial_assessment', 'community_observation', 'individual_anecdote')), \n\tCONSTRAINT ck_claim_qualifiers_size CHECK (octet_length(qualifiers::text) <= 6000), \n\tCONSTRAINT ck_claim_warnings_size CHECK (octet_length(validation_warnings::text) <= 4000), \n\tCONSTRAINT uq_claim_owner UNIQUE (id, owner_id), \n\tCONSTRAINT uq_claim_extraction_fingerprint UNIQUE (snapshot_id, subject_variant_id, prompt_version, fingerprint), \n\tFOREIGN KEY(snapshot_id) REFERENCES source_snapshots (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(subject_product_id) REFERENCES products (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(subject_variant_id) REFERENCES product_variants (id) ON DELETE RESTRICT\n)"
    )
    op.execute(
        "CREATE INDEX ix_claims_subject_attribute ON claims (owner_id, subject_variant_id, attribute_key)"
    )
    op.execute(
        "CREATE TABLE claim_evidence (\n\tid UUID NOT NULL, \n\tclaim_id UUID NOT NULL, \n\texcerpt VARCHAR(1000) NOT NULL, \n\tlocator JSONB NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tmeasurement_details JSONB NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_claim_evidence_excerpt CHECK (char_length(excerpt) BETWEEN 1 AND 1000), \n\tCONSTRAINT ck_claim_evidence_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'), \n\tCONSTRAINT uq_claim_evidence_quote UNIQUE (claim_id, content_hash, excerpt), \n\tFOREIGN KEY(claim_id) REFERENCES claims (id) ON DELETE RESTRICT\n)"
    )
    op.execute("CREATE INDEX ix_claim_evidence_claim ON claim_evidence (claim_id)")
    op.execute(
        "CREATE TABLE claim_relations (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tclaim_id UUID NOT NULL, \n\trelated_claim_id UUID NOT NULL, \n\trelation VARCHAR(24) NOT NULL, \n\tbasis VARCHAR(500) NOT NULL, \n\torigin VARCHAR(8) NOT NULL, \n\ttask_version VARCHAR(80) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_claim_relation_type CHECK (relation IN ('supports', 'contradicts', 'different_context', 'duplicate')), \n\tCONSTRAINT ck_claim_relation_origin CHECK (origin IN ('system', 'ai', 'user')), \n\tCONSTRAINT ck_claim_relation_order CHECK (claim_id < related_claim_id), \n\tCONSTRAINT uq_claim_relation UNIQUE (claim_id, related_claim_id, relation), \n\tFOREIGN KEY(claim_id) REFERENCES claims (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(related_claim_id) REFERENCES claims (id) ON DELETE RESTRICT\n)"
    )
    op.execute(
        "CREATE TABLE product_assessments (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tproject_id UUID NOT NULL, \n\tproject_product_id UUID NOT NULL, \n\tresearch_run_id UUID NOT NULL, \n\tproject_revision INTEGER NOT NULL, \n\trequirements_snapshot JSONB NOT NULL, \n\tproduct_revision INTEGER NOT NULL, \n\tvariant_revision INTEGER NOT NULL, \n\tclaim_ids JSONB NOT NULL, \n\tsnapshot_ids JSONB NOT NULL, \n\tconclusions JSONB NOT NULL, \n\tsummary VARCHAR(1200) NOT NULL, \n\tstrengths JSONB NOT NULL, \n\tconcerns JSONB NOT NULL, \n\tuncertainties JSONB NOT NULL, \n\tgenerated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\ttask_name VARCHAR(80) NOT NULL, \n\ttask_version VARCHAR(80) NOT NULL, \n\tai_provider VARCHAR(40) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_assessment_summary CHECK (char_length(summary) <= 1200), \n\tCONSTRAINT ck_assessment_requirements_size CHECK (octet_length(requirements_snapshot::text) <= 24000), \n\tCONSTRAINT ck_assessment_conclusions_size CHECK (octet_length(conclusions::text) <= 12000), \n\tCONSTRAINT uq_assessment_run_target_task UNIQUE (owner_id, research_run_id, project_product_id, task_version), \n\tFOREIGN KEY(project_id) REFERENCES shopping_projects (id) ON DELETE CASCADE, \n\tFOREIGN KEY(project_product_id) REFERENCES project_products (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(research_run_id) REFERENCES research_runs (id) ON DELETE CASCADE\n)"
    )
    op.execute(
        "CREATE INDEX ix_assessments_project_product_time ON product_assessments (owner_id, project_product_id, generated_at)"
    )
    op.execute(
        "CREATE TABLE assessment_citations (\n\tid UUID NOT NULL, \n\tassessment_id UUID NOT NULL, \n\tclaim_id UUID NOT NULL, \n\trequirement_id UUID, \n\trationale VARCHAR(500) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_assessment_citation UNIQUE (assessment_id, claim_id, requirement_id), \n\tFOREIGN KEY(assessment_id) REFERENCES product_assessments (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(claim_id) REFERENCES claims (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(requirement_id) REFERENCES project_requirements (id) ON DELETE SET NULL\n)"
    )
    op.execute("CREATE INDEX ix_assessment_citations_claim ON assessment_citations (claim_id)")
    op.execute(
        "CREATE TABLE research_run_sources (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tresearch_run_id UUID NOT NULL, \n\tproject_product_id UUID NOT NULL, \n\tsearch_result_id UUID, \n\tsource_id UUID NOT NULL, \n\tsnapshot_id UUID, \n\trequested_url VARCHAR(2048) NOT NULL, \n\tfinal_url VARCHAR(2048) NOT NULL, \n\tretrieved_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\treason VARCHAR(80), \n\tbytes_read INTEGER, \n\tattempt_number INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_research_run_source_status CHECK (status IN ('retrieved', 'blocked', 'timeout', 'unsupported', 'failed', 'skipped')), \n\tCONSTRAINT ck_research_run_source_attempt CHECK (attempt_number >= 1), \n\tCONSTRAINT ck_research_run_source_bytes CHECK (bytes_read IS NULL OR bytes_read BETWEEN 0 AND 20000000), \n\tCONSTRAINT ck_research_run_source_urls CHECK (char_length(requested_url) <= 2048 AND char_length(final_url) <= 2048), \n\tCONSTRAINT uq_research_run_source_attempt UNIQUE (research_run_id, project_product_id, source_id, attempt_number), \n\tFOREIGN KEY(research_run_id) REFERENCES research_runs (id) ON DELETE CASCADE, \n\tFOREIGN KEY(project_product_id) REFERENCES project_products (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(search_result_id) REFERENCES search_results (id) ON DELETE SET NULL, \n\tFOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(snapshot_id) REFERENCES source_snapshots (id) ON DELETE RESTRICT\n)"
    )
    op.execute(
        "CREATE INDEX ix_research_run_sources_target_time ON research_run_sources (research_run_id, project_product_id, retrieved_at)"
    )
    op.drop_constraint("ck_research_run_type", "research_runs", type_="check")
    op.create_check_constraint(
        "ck_research_run_type",
        "research_runs",
        "run_type IN ('discovery', 'product_research')",
    )
    op.add_column(
        "search_queries", sa.Column("target_project_product_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_search_queries_target_project_product",
        "search_queries",
        "project_products",
        ["target_project_product_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("catalog_observations", sa.Column("snapshot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_catalog_observations_snapshot",
        "catalog_observations",
        "source_snapshots",
        ["snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    _backfill_catalog_snapshots()


def _backfill_catalog_snapshots() -> None:
    # Only provenance already recorded by Phase 4 is copied. No page body, title,
    # publication date, or missing hash is inferred during migration.
    op.execute("""
        INSERT INTO sources (
            id, owner_id, normalized_url, domain, classification,
            classification_actor, classification_version
        )
        SELECT
            md5(owner_id::text || ':' || normalized_url)::uuid,
            owner_id,
            normalized_url,
            left(lower(regexp_replace(
                substring(normalized_url from '^[a-zA-Z]+://([^/?#]+)'),
                ':[0-9]+$', ''
            )), 253),
            'unknown', 'system', 'source-classifier.v1'
        FROM (
            SELECT DISTINCT owner_id,
                regexp_replace(final_url, '#.*$', '') AS normalized_url
            FROM catalog_observations
            WHERE content_hash IS NOT NULL
        ) AS observed_sources
        ON CONFLICT (owner_id, normalized_url) DO NOTHING
    """)
    op.execute("""
        INSERT INTO source_snapshots (
            id, owner_id, source_id, content_hash, media_type, retrieved_at,
            relevant_text, excerpts, extractor_version
        )
        SELECT
            md5(source.id::text || ':' || legacy.content_hash)::uuid,
            legacy.owner_id,
            source.id,
            legacy.content_hash,
            legacy.content_type,
            legacy.retrieved_at,
            legacy.relevant_text,
            legacy.excerpts,
            legacy.extractor_version
        FROM (
            SELECT DISTINCT ON (owner_id, final_url, content_hash)
                owner_id, regexp_replace(final_url, '#.*$', '') AS normalized_url,
                content_hash, content_type, retrieved_at, extractor_version,
                coalesce((
                    SELECT jsonb_agg(left(item.value, 500) ORDER BY item.ordinality)
                    FROM jsonb_array_elements_text(catalog_observations.excerpts)
                        WITH ORDINALITY AS item(value, ordinality)
                    WHERE item.ordinality <= 5
                ), '[]'::jsonb) AS excerpts,
                coalesce((
                    SELECT string_agg(item.value, ' ' ORDER BY item.ordinality)
                    FROM jsonb_array_elements_text(catalog_observations.excerpts)
                        WITH ORDINALITY AS item(value, ordinality)
                    WHERE item.ordinality <= 5
                ), '') AS relevant_text
            FROM catalog_observations
            WHERE content_hash IS NOT NULL
            ORDER BY owner_id, final_url, content_hash, retrieved_at, id
        ) AS legacy
        JOIN sources AS source
          ON source.owner_id = legacy.owner_id
         AND source.normalized_url = legacy.normalized_url
        ON CONFLICT (source_id, content_hash) DO NOTHING
    """)
    op.execute("""
        UPDATE catalog_observations AS observation
        SET snapshot_id = snapshot.id
        FROM sources AS source
        JOIN source_snapshots AS snapshot ON snapshot.source_id = source.id
        WHERE source.owner_id = observation.owner_id
          AND source.normalized_url = regexp_replace(observation.final_url, '#.*$', '')
          AND snapshot.content_hash = observation.content_hash
          AND observation.content_hash IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_constraint(
        "fk_catalog_observations_snapshot", "catalog_observations", type_="foreignkey"
    )
    op.drop_column("catalog_observations", "snapshot_id")
    op.drop_constraint(
        "fk_search_queries_target_project_product", "search_queries", type_="foreignkey"
    )
    op.drop_column("search_queries", "target_project_product_id")
    op.drop_constraint("ck_research_run_type", "research_runs", type_="check")
    op.create_check_constraint("ck_research_run_type", "research_runs", "run_type = 'discovery'")
    op.drop_table("assessment_citations")
    op.drop_table("product_assessments")
    op.drop_table("claim_relations")
    op.drop_table("claim_evidence")
    op.drop_table("claims")
    op.drop_table("research_run_sources")
    op.drop_table("source_snapshots")
    op.drop_table("sources")
