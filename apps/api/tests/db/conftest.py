import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def postgres_schema() -> Iterator[tuple[Engine, str]]:
    """Migrate an isolated schema inside a deliberately named disposable test DB."""
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for -m db tests; no fallback database is used")

    database_name = (make_url(database_url).database or "").lower()
    application_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://shopping:shopping@localhost:5432/shopping"
    )
    test_parts = make_url(database_url)
    app_parts = make_url(application_url)
    if (
        test_parts.host,
        test_parts.port,
        test_parts.database,
    ) == (app_parts.host, app_parts.port, app_parts.database):
        pytest.fail("Refusing to run database tests against the configured application database")
    if not re.search(r"(^test[_-]|[_-]test$|[_-]tests$)", database_name):
        pytest.fail(
            "Refusing destructive PostgreSQL tests: TEST_DATABASE_URL database name must "
            "start with 'test_' or end in '_test'/'_tests'"
        )
    if database_name in {"shopping", "production", "prod", "postgres"}:
        pytest.fail("Refusing to run database tests against a known application/system database")

    admin_engine = create_engine(database_url, pool_pre_ping=True)
    schema = f"shopping_test_{uuid.uuid4().hex}"
    quoted_schema = admin_engine.dialect.identifier_preparer.quote(schema)
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))

        schema_engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        repository_root = Path(__file__).resolve().parents[4]
        api_root = repository_root / "apps" / "api"
        config = Config(str(api_root / "alembic.ini"))
        config.attributes["connection"] = schema_engine.connect()
        try:
            command.upgrade(config, "head")
            yield schema_engine, schema
        finally:
            config.attributes["connection"].close()
            schema_engine.dispose()
    finally:
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE"))
        admin_engine.dispose()


@pytest.fixture
def db_engine(postgres_schema: tuple[Engine, str]) -> Engine:
    return postgres_schema[0]
