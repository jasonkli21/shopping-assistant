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
            "alembic_version",
        } <= tables
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
