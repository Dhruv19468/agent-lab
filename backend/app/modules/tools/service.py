from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import Skill, SkillTool, Tool
from app.modules.tools.schemas import ToolCreate, ToolRead, ToolUpdate


class ToolService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_tool(self, tool_id: uuid.UUID) -> Tool:
        tool = await self.session.get(Tool, tool_id)
        if tool is None:
            raise NotFoundError(f"Tool {tool_id} not found.")
        return tool

    async def _ensure_name_free(self, name: str, *, except_id: uuid.UUID | None = None) -> None:
        query = select(Tool.id).where(Tool.name == name)
        if except_id is not None:
            query = query.where(Tool.id != except_id)
        if await self.session.scalar(query) is not None:
            raise ConflictError(f"A tool named '{name}' already exists.")

    async def create_tool(self, payload: ToolCreate) -> ToolRead:
        await self._ensure_name_free(payload.name)
        tool = Tool(**payload.model_dump())
        self.session.add(tool)
        await self.session.commit()
        await self.session.refresh(tool)  # load created_at/updated_at that Postgres filled in
        return ToolRead.model_validate(tool)

    async def list_tools(self) -> list[ToolRead]:
        tools = await self.session.scalars(select(Tool).order_by(Tool.name))
        return [ToolRead.model_validate(tool) for tool in tools]

    async def read_tool(self, tool_id: uuid.UUID) -> ToolRead:
        return ToolRead.model_validate(await self.get_tool(tool_id))

    async def update_tool(self, tool_id: uuid.UUID, payload: ToolUpdate) -> ToolRead:
        tool = await self.get_tool(tool_id)
        changes = payload.model_dump(exclude_unset=True)  # only the fields the caller sent
        if "name" in changes:
            await self._ensure_name_free(changes["name"], except_id=tool_id)
        for field, value in changes.items():
            setattr(tool, field, value)
        await self.session.commit()
        await self.session.refresh(tool)
        return ToolRead.model_validate(tool)

    async def delete_tool(self, tool_id: uuid.UUID) -> None:
        tool = await self.get_tool(tool_id)
        # Refuse while a skill's instructions still call it; detach it from those skills first.
        skill_names = (
            await self.session.scalars(
                select(Skill.name)
                .join(SkillTool, SkillTool.skill_id == Skill.id)
                .where(SkillTool.tool_id == tool_id)
                .order_by(Skill.name)
            )
        ).all()
        if skill_names:
            raise ConflictError(
                f"Tool '{tool.name}' is required by skill(s): {', '.join(skill_names)}. "
                "Remove it from those skills first."
            )
        await self.session.delete(tool)  # agent_tools rows go with it (ON DELETE CASCADE)
        await self.session.commit()
