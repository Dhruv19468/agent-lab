from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.dependencies import DbSession
from app.modules.tools.schemas import ToolCreate, ToolRead, ToolUpdate
from app.modules.tools.service import ToolService

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
async def create_tool(payload: ToolCreate, session: DbSession) -> ToolRead:
    return await ToolService(session).create_tool(payload)


@router.get("", response_model=list[ToolRead])
async def list_tools(session: DbSession) -> list[ToolRead]:
    return await ToolService(session).list_tools()


@router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(tool_id: uuid.UUID, session: DbSession) -> ToolRead:
    return await ToolService(session).read_tool(tool_id)


@router.put("/{tool_id}", response_model=ToolRead)
async def update_tool(tool_id: uuid.UUID, payload: ToolUpdate, session: DbSession) -> ToolRead:
    return await ToolService(session).update_tool(tool_id, payload)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(tool_id: uuid.UUID, session: DbSession) -> None:
    await ToolService(session).delete_tool(tool_id)
