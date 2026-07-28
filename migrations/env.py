from alembic import context
from sqlalchemy import engine_from_config, pool

from rag.config import get_settings
from rag.storage.migrations import metadata

config = context.config
target_metadata = metadata


def run_migrations_offline() -> None:
    settings = get_settings()
    context.configure(
        url=settings.postgres_dsn.replace("+asyncpg", ""),
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = get_settings()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = settings.postgres_dsn.replace("+asyncpg", "")
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

