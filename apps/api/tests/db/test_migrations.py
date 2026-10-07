from datetime import UTC
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.db


def test_fresh_database_can_upgrade_downgrade_and_upgrade_again(postgres_schema):
    engine, _schema = postgres_schema
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    connection = engine.connect()
    config.attributes["connection"] = connection
    try:
        command.downgrade(config, "0007_catalog_versions")
        downgraded_offer_check = next(
            item["sqltext"]
            for item in inspect(connection).get_check_constraints("retail_offers")
            if item["name"] == "ck_offer_amount_currency"
        )
        assert "amount IS NOT NULL" not in downgraded_offer_check
        command.upgrade(config, "head")
        upgraded_offer_check = next(
            item["sqltext"]
            for item in inspect(connection).get_check_constraints("retail_offers")
            if item["name"] == "ck_offer_amount_currency"
        )
        assert "amount IS NOT NULL" in upgraded_offer_check
        command.check(config)

        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        command.check(config)
        tables = set(inspect(connection).get_table_names())
        assert {
            "shopping_projects",
            "project_requirements",
            "conversations",
            "conversation_messages",
            "project_update_proposals",
            "research_runs",
            "products",
            "product_variants",
            "product_identifiers",
            "project_products",
            "retail_offers",
            "catalog_observations",
            "entity_resolution_events",
            "owner_catalog_state",
            "search_queries",
            "search_attempts",
            "search_results",
            "discovery_candidates",
            "candidate_search_results",
            "sources",
            "source_snapshots",
            "research_run_sources",
            "claims",
            "claim_evidence",
            "claim_relations",
            "product_assessments",
            "assessment_citations",
            "shopping_profiles",
            "shopping_preferences",
            "preference_candidates",
            "firebase_owner_bindings",
            "owner_privacy_events",
            "owner_privacy_lifecycle",
            "alembic_version",
        } <= tables
        conversation_columns = {
            item["name"] for item in inspect(connection).get_columns("conversation_messages")
        }
        assert {
            "generation_owner",
            "generation_lease_token",
            "generation_lease_expires_at",
            "generation_heartbeat_at",
        } <= conversation_columns
        assert "ck_message_generation_lease_state" in {
            item["name"]
            for item in inspect(connection).get_check_constraints("conversation_messages")
        }
    finally:
        connection.close()


def test_legacy_long_revision_ids_upgrade_without_losing_existing_rows(postgres_schema):
    engine, _schema = postgres_schema
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    connection = engine.connect()
    config.attributes["connection"] = connection
    project_id = uuid4()
    owner_id = uuid4()
    try:
        connection.execute(
            text(
                "INSERT INTO shopping_projects (id, owner_id, title, goal, revision) "
                "VALUES (:id, :owner_id, 'Kept project', 'Upgrade aliases', 1)"
            ),
            {"id": project_id, "owner_id": owner_id},
        )
        connection.commit()

        legacy_revisions = [
            ("p9_shopping_preferences", "0019_explicit_shopping_preferences"),
            ("p9_monetary_preferences", "0020_explicit_monetary_preferences"),
            ("p9_identity_privacy_audit", "0021_cloud_identity_and_privacy_audit"),
        ]
        for compatible_revision, legacy_revision in legacy_revisions:
            command.downgrade(config, compatible_revision)
            connection.execute(
                text("UPDATE alembic_version SET version_num = :legacy"),
                {"legacy": legacy_revision},
            )
            connection.commit()
            command.upgrade(config, "head")
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "p9_conversation_generation_leases"
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM shopping_projects WHERE id = :id"),
                    {"id": project_id},
                )
                == 1
            )
    finally:
        connection.close()


def test_conversation_lease_migration_preserves_legacy_generating_message(postgres_schema):
    engine, _schema = postgres_schema
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    connection = engine.connect()
    config.attributes["connection"] = connection
    owner_id, project_id, conversation_id, message_id = (uuid4() for _ in range(4))
    try:
        command.downgrade(config, "p9_owner_privacy_lifecycle")
        connection.execute(
            text(
                "INSERT INTO shopping_projects (id, owner_id, title, goal, revision) "
                "VALUES (:id, :owner_id, 'Legacy conversation', 'Preserve active message', 1)"
            ),
            {"id": project_id, "owner_id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO conversations (id, project_id, owner_id) "
                "VALUES (:id, :project_id, :owner_id)"
            ),
            {"id": conversation_id, "project_id": project_id, "owner_id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO conversation_messages "
                "(id, conversation_id, project_id, owner_id, ordinal, role, content, status, "
                "sequence, input_snapshot) VALUES (:id, :conversation_id, :project_id, "
                ":owner_id, 1, 'assistant', '', 'generating', 0, CAST(:snapshot AS jsonb))"
            ),
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "project_id": project_id,
                "owner_id": owner_id,
                "snapshot": '{"saved":"context"}',
            },
        )
        connection.commit()

        command.upgrade(config, "head")
        row = connection.execute(
            text(
                "SELECT status, input_snapshot, generation_owner, generation_lease_token "
                "FROM conversation_messages WHERE id = :id"
            ),
            {"id": message_id},
        ).one()
        assert row.status == "generating"
        assert row.input_snapshot == {"saved": "context"}
        assert row.generation_owner is None
        assert row.generation_lease_token is None
    finally:
        connection.close()


def test_revision_and_notes_constraints_upgrade_downgrade_and_reupgrade(postgres_schema):
    engine, _schema = postgres_schema
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    connection = engine.connect()
    config.attributes["connection"] = connection
    project_id = uuid4()
    try:
        command.downgrade(config, "0001_projects_requirements")
        connection.execute(
            text(
                "INSERT INTO shopping_projects (id, owner_id, title, goal, revision) "
                "VALUES (:id, :owner_id, 'Existing project', 'Existing goal', 1)"
            ),
            {"id": project_id, "owner_id": uuid4()},
        )
        connection.commit()

        command.upgrade(config, "head")
        expected = {"ck_project_revision_positive", "ck_project_notes_length"}
        assert expected <= {
            item["name"] for item in inspect(connection).get_check_constraints("shopping_projects")
        }

        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE shopping_projects SET revision = 0 WHERE id = :id"),
                {"id": project_id},
            )
        connection.rollback()
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE shopping_projects SET notes = :notes WHERE id = :id"),
                {"id": project_id, "notes": "x" * 10001},
            )
        connection.rollback()

        command.downgrade(config, "0001_projects_requirements")
        assert not expected.intersection(
            item["name"] for item in inspect(connection).get_check_constraints("shopping_projects")
        )
        connection.execute(
            text("UPDATE shopping_projects SET revision = 0, notes = :notes WHERE id = :id"),
            {"id": project_id, "notes": "x" * 10001},
        )
        connection.execute(
            text("UPDATE shopping_projects SET revision = 1, notes = NULL WHERE id = :id"),
            {"id": project_id},
        )
        connection.commit()

        command.upgrade(config, "head")
        assert expected <= {
            item["name"] for item in inspect(connection).get_check_constraints("shopping_projects")
        }
        assert (
            connection.execute(
                text("SELECT count(*) FROM shopping_projects WHERE id = :id"),
                {"id": project_id},
            ).scalar_one()
            == 1
        )
    finally:
        connection.close()


def test_applied_at_migration_backfills_existing_applied_proposals(postgres_schema):
    engine, _schema = postgres_schema
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    connection = engine.connect()
    config.attributes["connection"] = connection
    project_id = uuid4()
    owner_id = uuid4()
    conversation_id = uuid4()
    assistant_id = uuid4()
    proposal_id = uuid4()
    try:
        command.downgrade(config, "0003_conversations_proposals")
        connection.execute(
            text(
                "INSERT INTO shopping_projects (id, owner_id, title, goal, revision) "
                "VALUES (:id, :owner_id, 'Existing project', 'Existing goal', 2)"
            ),
            {"id": project_id, "owner_id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO conversations (id, project_id, owner_id) "
                "VALUES (:id, :project_id, :owner_id)"
            ),
            {"id": conversation_id, "project_id": project_id, "owner_id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO conversation_messages "
                "(id, conversation_id, project_id, owner_id, ordinal, role, content, status) "
                "VALUES (:id, :conversation_id, :project_id, :owner_id, 1, "
                "'assistant', 'Saved', 'completed')"
            ),
            {
                "id": assistant_id,
                "conversation_id": conversation_id,
                "project_id": project_id,
                "owner_id": owner_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO project_update_proposals "
                "(id, project_id, owner_id, assistant_message_id, base_revision, schema_version, "
                "operations, status, applied_revision, applied_project) "
                "VALUES (:id, :project_id, :owner_id, :assistant_id, 1, 1, '{}'::jsonb, "
                "'applied', 2, '{}'::jsonb)"
            ),
            {
                "id": proposal_id,
                "project_id": project_id,
                "owner_id": owner_id,
                "assistant_id": assistant_id,
            },
        )
        connection.commit()

        command.upgrade(config, "head")
        timestamps = connection.execute(
            text("SELECT applied_at, updated_at FROM project_update_proposals WHERE id = :id"),
            {"id": proposal_id},
        ).one()
        assert timestamps.applied_at is not None
        assert timestamps.applied_at == timestamps.updated_at
        assert "applied_at" in {
            column["name"] for column in inspect(connection).get_columns("project_update_proposals")
        }
    finally:
        connection.close()


def test_catalog_migration_preserves_phase_three_candidate_and_search_lineage(postgres_schema):
    engine, _schema = postgres_schema
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    connection = engine.connect()
    config.attributes["connection"] = connection
    owner_id, project_id, run_id, query_id = uuid4(), uuid4(), uuid4(), uuid4()
    attempt_id, result_id, candidate_id = uuid4(), uuid4(), uuid4()
    try:
        command.downgrade(config, "0005_bounded_discovery")
        connection.execute(
            text(
                "INSERT INTO shopping_projects (id, owner_id, title, goal, revision) "
                "VALUES (:id, :owner_id, 'Vacuum', 'Find a vacuum', 1)"
            ),
            {"id": project_id, "owner_id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO research_runs (id, project_id, owner_id, objective, run_type, "
                "status, request_key, request_hash, snapshot_revision, input_snapshot, "
                "effective_budgets, task_name, prompt_version, schema_version, ai_provider, "
                "search_provider) VALUES (:id, :project_id, :owner_id, 'Find vacuum', "
                "'discovery', 'succeeded', 'request-0001', 'hash', 1, '{}'::jsonb, "
                "'{}'::jsonb, 'plan_discovery.v1', 'v1', 1, 'fake', 'fake')"
            ),
            {"id": run_id, "project_id": project_id, "owner_id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO search_queries "
                "(id, run_id, ordinal, text, purpose, max_results, state) "
                "VALUES (:id, :run_id, 0, 'vacuum pet hair', 'identify products', 1, 'succeeded')"
            ),
            {"id": query_id, "run_id": run_id},
        )
        connection.execute(
            text(
                "INSERT INTO search_attempts (id, query_id, attempt_number, provider, status) "
                "VALUES (:id, :query_id, 1, 'fake', 'succeeded')"
            ),
            {"id": attempt_id, "query_id": query_id},
        )
        connection.execute(
            text(
                "INSERT INTO search_results (id, query_id, attempt_id, result_rank, title, url) "
                "VALUES (:id, :query_id, :attempt_id, 1, 'Example Vacuum', "
                "'https://shop.example/vacuum')"
            ),
            {"id": result_id, "query_id": query_id, "attempt_id": attempt_id},
        )
        connection.execute(
            text(
                "INSERT INTO discovery_candidates (id, project_id, run_id, provisional_name, "
                "discovery_reason, normalized_url) VALUES (:id, :project_id, :run_id, "
                "'Example Vacuum', 'Search result', 'https://shop.example/vacuum')"
            ),
            {"id": candidate_id, "project_id": project_id, "run_id": run_id},
        )
        connection.execute(
            text(
                "INSERT INTO candidate_search_results (id, candidate_id, search_result_id) "
                "VALUES (:id, :candidate_id, :result_id)"
            ),
            {"id": uuid4(), "candidate_id": candidate_id, "result_id": result_id},
        )
        connection.commit()

        command.upgrade(config, "head")
        assert connection.execute(
            text(
                "SELECT c.provisional_name, c.canonical_mapping_id, r.owner_id, "
                "s.title FROM discovery_candidates c "
                "JOIN research_runs r ON r.id = c.run_id "
                "JOIN candidate_search_results csr ON csr.candidate_id = c.id "
                "JOIN search_results s ON s.id = csr.search_result_id WHERE c.id = :id"
            ),
            {"id": candidate_id},
        ).one() == ("Example Vacuum", None, owner_id, "Example Vacuum")

        command.downgrade(config, "0005_bounded_discovery")
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM candidate_search_results csr "
                    "JOIN discovery_candidates c ON c.id = csr.candidate_id "
                    "WHERE c.id = :id"
                ),
                {"id": candidate_id},
            ).scalar_one()
            == 1
        )
        command.upgrade(config, "head")
        assert (
            connection.execute(
                text("SELECT count(*) FROM discovery_candidates WHERE id = :id"),
                {"id": candidate_id},
            ).scalar_one()
            == 1
        )
    finally:
        connection.close()


def test_phase_four_observation_backfills_only_saved_snapshot_provenance(postgres_schema):
    engine, _schema = postgres_schema
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    connection = engine.connect()
    config.attributes["connection"] = connection
    owner_id, project_id, run_id, candidate_id = uuid4(), uuid4(), uuid4(), uuid4()
    product_id, variant_id, project_product_id = uuid4(), uuid4(), uuid4()
    observation_id = uuid4()
    content_hash = "a" * 64
    retrieved_at = "2026-10-04T18:00:00+00:00"
    try:
        command.downgrade(config, "0008_offer_amount_currency_pair")
        connection.execute(
            text(
                "INSERT INTO shopping_projects (id, owner_id, title, goal, revision) "
                "VALUES (:id, :owner_id, 'Vacuum', 'Find a vacuum', 1)"
            ),
            {"id": project_id, "owner_id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO research_runs (id, project_id, owner_id, objective, run_type, "
                "status, request_key, request_hash, snapshot_revision, input_snapshot, "
                "effective_budgets, task_name, prompt_version, schema_version, ai_provider, "
                "search_provider) VALUES (:id, :project_id, :owner_id, 'Normalize product', "
                "'discovery', 'succeeded', 'request-0001', :hash, 1, '{}'::jsonb, "
                "'{}'::jsonb, 'plan_discovery.v1', 'v1', 1, 'fake', 'fake')"
            ),
            {
                "id": run_id,
                "project_id": project_id,
                "owner_id": owner_id,
                "hash": "b" * 64,
            },
        )
        connection.execute(
            text(
                "INSERT INTO discovery_candidates "
                "(id, project_id, run_id, provisional_name, discovery_reason, normalized_url) "
                "VALUES (:id, :project_id, :run_id, 'Example Vacuum', 'Search result', "
                "'https://shop.example/vacuum')"
            ),
            {"id": candidate_id, "project_id": project_id, "run_id": run_id},
        )
        connection.execute(
            text(
                "INSERT INTO products (id, owner_id, canonical_name) "
                "VALUES (:id, :owner_id, 'Example Vacuum')"
            ),
            {"id": product_id, "owner_id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO product_variants "
                "(id, product_id, display_name, identity_key, identity_attributes, "
                "category_attributes) "
                "VALUES (:id, :product_id, 'Unspecified', 'unspecified', '{}'::jsonb, '{}'::jsonb)"
            ),
            {"id": variant_id, "product_id": product_id},
        )
        connection.execute(
            text(
                "INSERT INTO project_products (id, project_id, variant_id, discovery_reason) "
                "VALUES (:id, :project_id, :variant_id, 'Search result')"
            ),
            {"id": project_product_id, "project_id": project_id, "variant_id": variant_id},
        )
        connection.execute(
            text(
                "INSERT INTO catalog_observations "
                "(id, owner_id, project_id, candidate_id, run_id, idempotency_key, request_hash, "
                "requested_url, final_url, retrieved_at, content_hash, content_type, status, "
                "extractor_version, task_version, extraction, excerpts, warnings) "
                "VALUES (:id, :owner_id, :project_id, :candidate_id, :run_id, 'request-0001', "
                ":request_hash, 'https://shop.example/vacuum', 'https://shop.example/vacuum', "
                "CAST(:retrieved_at AS timestamptz), :content_hash, 'text/html', 'succeeded', "
                "'httpx-page-retriever.v1', 'normalize_catalog_candidate.v1', '{}'::jsonb, "
                "CAST(:excerpts AS jsonb), '[]'::jsonb)"
            ),
            {
                "id": observation_id,
                "owner_id": owner_id,
                "project_id": project_id,
                "candidate_id": candidate_id,
                "run_id": run_id,
                "request_hash": "c" * 64,
                "retrieved_at": retrieved_at,
                "content_hash": content_hash,
                "excerpts": '["Example Vacuum", "Runtime up to 60 minutes"]',
            },
        )
        connection.commit()

        command.upgrade(config, "head")
        linked = connection.execute(
            text(
                "SELECT source.domain, source.classification, snapshot.content_hash, "
                "snapshot.published_at, snapshot.retrieved_at, snapshot.excerpts, "
                "snapshot.relevant_text FROM catalog_observations observation "
                "JOIN source_snapshots snapshot ON snapshot.id = observation.snapshot_id "
                "JOIN sources source ON source.id = snapshot.source_id "
                "WHERE observation.id = :id"
            ),
            {"id": observation_id},
        ).one()
        assert linked.domain == "shop.example"
        assert linked.classification == "unknown"
        assert linked.content_hash == content_hash
        assert linked.published_at is None
        assert linked.retrieved_at.astimezone(UTC).isoformat() == retrieved_at
        assert linked.excerpts == ["Example Vacuum", "Runtime up to 60 minutes"]
        assert "Runtime up to 60 minutes" in linked.relevant_text
        assert (
            connection.execute(
                text("SELECT count(*) FROM sources WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            ).scalar_one()
            == 1
        )
    finally:
        connection.close()
