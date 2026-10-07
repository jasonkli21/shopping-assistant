from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, inspect, pool, text

from shopping.accounts import models as account_models  # noqa: F401
from shopping.catalog import models as catalog_models  # noqa: F401
from shopping.comparisons import models as comparison_models  # noqa: F401
from shopping.config import get_settings
from shopping.conversations import models as conversation_models  # noqa: F401
from shopping.db.base import Base
from shopping.evidence import models as evidence_models  # noqa: F401
from shopping.preferences import models as preference_models  # noqa: F401
from shopping.projects import models as project_models  # noqa: F401
from shopping.research import models as research_models  # noqa: F401

config = context.config
settings = get_settings()
# ConfigParser interprets percent signs in URL-encoded credentials.
migration_database_url = settings.migration_database_url or settings.database_url
config.set_main_option("sqlalchemy.url", migration_database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
LEGACY_REVISION_IDS = {
    "0019_explicit_shopping_preferences": "p9_shopping_preferences",
    "0020_explicit_monetary_preferences": "p9_monetary_preferences",
    "0021_cloud_identity_and_privacy_audit": "p9_identity_privacy_audit",
}


def _widen_alembic_version_column(connection) -> None:
    """Keep historical revision IDs readable in Alembic's default version table."""
    if connection.dialect.name != "postgresql":
        return
    if not inspect(connection).has_table("alembic_version"):
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(128) NOT NULL PRIMARY KEY)")
        )
    else:
        column = next(
            item
            for item in inspect(connection).get_columns("alembic_version")
            if item["name"] == "version_num"
        )
        if getattr(column["type"], "length", None) is not None and column["type"].length < 128:
            connection.execute(
                text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
            )
    for legacy_revision, compatible_revision in LEGACY_REVISION_IDS.items():
        connection.execute(
            text(
                "UPDATE alembic_version SET version_num = :compatible WHERE version_num = :legacy"
            ),
            {"compatible": compatible_revision, "legacy": legacy_revision},
        )


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        _widen_alembic_version_column(connection)
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=migration_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
