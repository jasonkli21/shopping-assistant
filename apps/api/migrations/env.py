from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

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


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
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
