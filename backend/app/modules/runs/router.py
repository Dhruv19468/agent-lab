from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query, Response, status

from app.core.dependencies import DbSession
from app.modules.runs.schemas import RunCreate, RunRead, RunSummary
from app.modules.runs.service import RunService

router = APIRouter(tags=["runs"])


@router.post("/agents/{agent_id}/runs", response_model=RunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_run(agent_id: uuid.UUID, payload: RunCreate, session: DbSession) -> RunRead:
    """Start a run. It answers at once with status 'running'; poll GET /runs/{id} until it isn't."""
    return await RunService(session).start_run(agent_id, payload)


@router.get("/agents/{agent_id}/runs", response_model=list[RunSummary])
async def list_runs(
    agent_id: uuid.UUID, session: DbSession, limit: int = Query(default=50, ge=1, le=200)
) -> list[RunSummary]:
    return await RunService(session).list_runs(agent_id, limit)


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(run_id: uuid.UUID, session: DbSession) -> RunRead:
    return await RunService(session).read_run(run_id)


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: uuid.UUID,
    session: DbSession,
    format: Literal["md", "docx", "xlsx", "pdf"] = Query(default="docx"),  # noqa: A002 (the URL says ?format=)
) -> Response:
    """Download the run's answer as Markdown, Word, Excel or PDF (built now, from the saved Markdown)."""
    data, media_type, file_name = await RunService(session).export(run_id, format)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )
