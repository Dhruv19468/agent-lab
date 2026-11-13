from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.migrations import run_alembic_upgrade_head
from app.db.session import SessionLocal, engine
from app.models import AgentRun, Evaluation

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
# Newer Alembic logs every built-in plugin it loads at INFO; only show its warnings.
logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)
startup_logger = logging.getLogger("platform.startup")
error_logger = logging.getLogger("platform.error")


async def fail_interrupted_work() -> None:
    """Runs/evaluations still 'running' at startup were cut off by a restart: mark them failed."""
    message = "Interrupted: the server restarted while this was running. Start it again."
    async with SessionLocal() as session:
        for model in (AgentRun, Evaluation):
            result = await session.execute(
                update(model).where(model.status == "running").values(status="failed", error=message)
            )
            if result.rowcount:
                startup_logger.warning("Marked %d interrupted %s row(s) failed", result.rowcount, model.__tablename__)
        await session.commit()


async def prepare_database() -> None:
    await fail_interrupted_work()
    if settings.sync_catalog_on_startup:
        from app.catalog.sync import sync_catalog  # imported here: it pulls in the agents module

        async with SessionLocal() as session:
            await sync_catalog(session)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Code before `yield` runs once at startup; code after it runs once at shutdown."""
    startup_logger.info(
        "Starting %s: environment=%s database=%s schema=%s azure_openai=%s run_migrations=%s",
        settings.app_name,
        settings.environment,
        engine.url.render_as_string(hide_password=True),
        settings.database_schema,
        settings.azure_openai_deployment if settings.azure_openai_configured else "not configured",
        settings.run_alembic_on_startup,
    )

    if settings.run_alembic_on_startup:
        # env.py calls asyncio.run(), which can't run inside uvicorn's event loop,
        # so the migration runs in a separate worker thread.
        await asyncio.to_thread(run_alembic_upgrade_head)
    else:
        startup_logger.info("RUN_ALEMBIC_ON_STARTUP is false; skipping migrations")

    try:
        await prepare_database()
    except Exception:  # e.g. migrations not run yet: keep the API up so /api/health can say so
        startup_logger.exception("Startup database preparation failed")

    try:
        from app.runtime.storage import get_storage

        storage = get_storage()
        if await asyncio.to_thread(storage.is_dir, "raw"):
            startup_logger.info("Agent data (%s): %s", settings.agent_storage, storage.describe())
        else:
            startup_logger.warning("Agent data %s has no raw/ folder: agents will find no projects", storage.describe())
    except Exception:  # e.g. Blob role not active yet: the API still starts, runs will report it
        startup_logger.exception("Could not reach the agent data storage")

    yield

    await engine.dispose()
    startup_logger.info("Shutdown complete")


app = FastAPI(
    title=f"{settings.app_name} API",
    description=settings.project_description,
    docs_url=settings.docs_path if settings.include_openapi_docs else None,
    openapi_url=settings.openapi_path if settings.include_openapi_docs else None,
    root_path=settings.root_path.rstrip("/"),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
    """Services raise NotFoundError / ConflictError / BadRequestError; answer with their status."""
    if error.status_code >= 500:
        error_logger.error("%s %s failed: %s", request.method, request.url.path, error.message)
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})


@app.exception_handler(IntegrityError)
async def handle_integrity_error(request: Request, error: IntegrityError) -> JSONResponse:
    """Safety net: a database rule the service didn't check first (e.g. two requests at once)."""
    reason = str(error.orig).splitlines()[0] if error.orig else "constraint violated"
    error_logger.warning("%s %s rejected by the database: %s", request.method, request.url.path, reason)
    return JSONResponse(status_code=409, content={"detail": f"Rejected by the database: {reason}"})


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": settings.docs_path}
