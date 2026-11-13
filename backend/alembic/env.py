from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection

import app.models  # noqa: F401  (registers every model on Base.metadata)
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_database_engine, database_schema_search_path

# The Config object for alembic.ini.
config = context.config

# Only the `alembic` CLI applies alembic.ini's logging. When the API runs migrations at
# startup it has already set up logging, and fileConfig would silence the app's loggers.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

settings = get_settings()
# One source of truth for the URL: DATABASE_URL via Settings. "%" is escaped for the .ini parser.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# What the database SHOULD look like: every model registered on Base.
target_metadata = Base.metadata

def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to: object | None) -> bool:
    """Decide which database objects autogenerate may compare.

    Skip TABLES that exist only in the database (reflected, with no model). That covers
    alembic_version, which lives in our schema, and any table created by hand, so
    autogenerate never writes a drop_table for something it doesn't own.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it (no connection)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=settings.database_schema,
    )
    with context.begin_transaction():
        context.execute(f"CREATE SCHEMA IF NOT EXISTS {database_schema_search_path()}")
        context.execute(f"SET search_path TO {database_schema_search_path()}")
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Runs on a real connection. Called through run_sync, so the code inside is synchronous."""
    # Create our schema first, so the very first CREATE TABLE has somewhere to go.
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {database_schema_search_path()}"))
    connection.commit()

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        version_table_schema=settings.database_schema,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Normal mode: open one connection with our own engine and run the migrations."""
    connectable = create_database_engine(poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())