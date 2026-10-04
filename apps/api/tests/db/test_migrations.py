from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

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
        tables = set(inspect(connection).get_table_names())
        assert {"shopping_projects", "project_requirements", "alembic_version"} <= tables
    finally:
        connection.close()
