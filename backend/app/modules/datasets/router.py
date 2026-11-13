from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.modules.datasets.schemas import DatasetRead, ProjectRead
from app.runtime.dataset import find_projects
from app.runtime.storage import get_storage

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=DatasetRead)
async def list_projects() -> DatasetRead:
    """The practice projects found under raw/ in the data root (P00–P09): local folder or Blob."""
    storage = get_storage()
    projects = await asyncio.to_thread(find_projects, storage)  # Blob listing is network I/O
    return DatasetRead(
        data_dir=storage.describe(),
        projects=[
            ProjectRead(
                project=info.project,
                split=info.split,
                title=info.title,
                folder=info.folder,
                brd=info.brd,
                diagrams=info.diagrams,
                has_reference=info.reference_testplan is not None or info.gold is not None,
                has_gold=info.gold is not None,
                suggested_message=info.suggested_message,
            )
            for info in projects
        ],
    )
