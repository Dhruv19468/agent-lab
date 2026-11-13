from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.models import AgentSkill, AgentTool, Skill, SkillTool, Tool
from app.modules.skills.schemas import SkillCreate, SkillRead, SkillUpdate


class SkillService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- helpers ---------------------------------------------------------------------

    async def get_skill(self, skill_id: uuid.UUID) -> Skill:
        skill = await self.session.get(Skill, skill_id)
        if skill is None:
            raise NotFoundError(f"Skill {skill_id} not found.")
        return skill

    async def required_tool_ids(self, skill_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.session.scalars(
            select(SkillTool.tool_id).where(SkillTool.skill_id == skill_id)
        )
        return list(rows)

    async def _ensure_name_free(self, name: str, *, except_id: uuid.UUID | None = None) -> None:
        query = select(Skill.id).where(Skill.name == name)
        if except_id is not None:
            query = query.where(Skill.id != except_id)
        if await self.session.scalar(query) is not None:
            raise ConflictError(f"A skill named '{name}' already exists.")

    async def _ensure_tools_exist(self, tool_ids: list[uuid.UUID]) -> None:
        if not tool_ids:
            return
        found = set(await self.session.scalars(select(Tool.id).where(Tool.id.in_(tool_ids))))
        missing = [str(tool_id) for tool_id in tool_ids if tool_id not in found]
        if missing:
            raise BadRequestError(f"Unknown tool id(s): {', '.join(missing)}")

    async def _to_read(self, skill: Skill) -> SkillRead:
        await self.session.refresh(skill)  # load values Postgres filled in (timestamps)
        read = SkillRead.model_validate(skill)
        read.required_tool_ids = await self.required_tool_ids(skill.id)
        return read

    async def _give_required_tools_to_agents(self, skill_id: uuid.UUID) -> None:
        """Agents that already have this skill get any newly required tool (source='skill')."""
        agent_ids = list(
            await self.session.scalars(select(AgentSkill.agent_id).where(AgentSkill.skill_id == skill_id))
        )
        tool_ids = await self.required_tool_ids(skill_id)
        for agent_id in agent_ids:
            have = set(
                await self.session.scalars(select(AgentTool.tool_id).where(AgentTool.agent_id == agent_id))
            )
            for tool_id in tool_ids:
                if tool_id not in have:
                    self.session.add(AgentTool(agent_id=agent_id, tool_id=tool_id, source="skill"))

    # --- operations --------------------------------------------------------------

    async def create_skill(self, payload: SkillCreate) -> SkillRead:
        await self._ensure_name_free(payload.name)
        tool_ids = list(dict.fromkeys(payload.required_tool_ids))  # remove duplicates, keep order
        await self._ensure_tools_exist(tool_ids)

        skill = Skill(**payload.model_dump(exclude={"required_tool_ids"}))
        self.session.add(skill)
        await self.session.flush()  # skill row first: skill_tools rows point at it
        self.session.add_all(SkillTool(skill_id=skill.id, tool_id=tool_id) for tool_id in tool_ids)
        await self.session.commit()
        return await self._to_read(skill)

    async def list_skills(self) -> list[SkillRead]:
        skills = list(await self.session.scalars(select(Skill).order_by(Skill.name)))
        links = await self.session.execute(select(SkillTool.skill_id, SkillTool.tool_id))
        tools_by_skill: dict[uuid.UUID, list[uuid.UUID]] = {}
        for skill_id, tool_id in links:
            tools_by_skill.setdefault(skill_id, []).append(tool_id)
        result = []
        for skill in skills:
            read = SkillRead.model_validate(skill)
            read.required_tool_ids = tools_by_skill.get(skill.id, [])
            result.append(read)
        return result

    async def read_skill(self, skill_id: uuid.UUID) -> SkillRead:
        return await self._to_read(await self.get_skill(skill_id))

    async def update_skill(self, skill_id: uuid.UUID, payload: SkillUpdate) -> SkillRead:
        skill = await self.get_skill(skill_id)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            await self._ensure_name_free(changes["name"], except_id=skill_id)

        new_tool_ids = changes.pop("required_tool_ids", None)
        for field, value in changes.items():
            setattr(skill, field, value)

        if new_tool_ids is not None:  # replace the skill's tool list
            new_tool_ids = list(dict.fromkeys(new_tool_ids))
            await self._ensure_tools_exist(new_tool_ids)
            await self.session.execute(delete(SkillTool).where(SkillTool.skill_id == skill_id))
            self.session.add_all(SkillTool(skill_id=skill_id, tool_id=tool_id) for tool_id in new_tool_ids)
            await self.session.flush()
            await self._give_required_tools_to_agents(skill_id)

        await self.session.commit()
        return await self._to_read(skill)

    async def delete_skill(self, skill_id: uuid.UUID) -> None:
        skill = await self.get_skill(skill_id)
        # agent_skills and skill_tools rows go with it (ON DELETE CASCADE). Tools the skill brought
        # to agents stay attached as 'skill' tools; detach them from the agent if no longer wanted.
        await self.session.delete(skill)
        await self.session.commit()
