from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()


def database_schema_search_path() -> str:
    """The schema name, quoted for SQL, so every table lands in DATABASE_SCHEMA."""
    escaped_schema = settings.database_schema.replace('"', '""')
    return f'"{escaped_schema}"'


def create_database_engine(poolclass: type[object] | None = None) -> AsyncEngine:
    """Build the async engine. Alembic passes NullPool; the app uses the default pool."""
    options: dict[str, object] = {"future": True, "echo": False}
    if poolclass is not None:
        options["poolclass"] = poolclass

    return create_async_engine(
        settings.database_url,
        connect_args={"server_settings": {"search_path": database_schema_search_path()}},
        **options,
    )


engine = create_database_engine()
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed afterwards."""
    async with SessionLocal() as session:
        yield session