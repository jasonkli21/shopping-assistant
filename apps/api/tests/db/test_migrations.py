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
