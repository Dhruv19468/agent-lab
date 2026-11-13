from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.integrations.foundry import FoundryClient, FoundryError, agent_slug, function_tool, slug_with_suffix
from app.models import Agent, AgentConfiguration, AgentSkill, AgentTool, Skill, SkillTool, Tool
from app.modules.agents import skill_instructions
from app.modules.agents.schemas import (
    AgentConfigurationRead,
    AgentConfigurationUpdate,
    AgentCreate,
    AgentDetailRead,
    AgentRead,
    AgentSkillRead,
    AgentToolRead,
    AgentUpdate,
    PromptPreviewRead,
)


logger = logging.getLogger("platform.agents")


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- loading ---------------------------------------------------------------------

    async def get_agent(self, agent_id: uuid.UUID) -> Agent:
        agent = await self.session.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError(f"Agent {agent_id} not found.")
        return agent

    async def get_configuration(self, agent_id: uuid.UUID) -> AgentConfiguration:
        config = await self.session.scalar(
            select(AgentConfiguration).where(AgentConfiguration.agent_id == agent_id)
        )
        if config is None:  # every agent gets one at creation; recreate if it was removed by hand
            config = AgentConfiguration(agent_id=agent_id)
            self.session.add(config)
            await self.session.flush()
            await self.session.refresh(config)
        return config

    async def agent_skills(self, agent_id: uuid.UUID) -> list[Skill]:
        rows = await self.session.scalars(
            select(Skill)
            .join(AgentSkill, AgentSkill.skill_id == Skill.id)
            .where(AgentSkill.agent_id == agent_id)
            .order_by(Skill.name)
        )
        return list(rows)

    async def agent_tools(self, agent_id: uuid.UUID) -> list[tuple[Tool, str]]:
        rows = await self.session.execute(
            select(Tool, AgentTool.source)
            .join(AgentTool, AgentTool.tool_id == Tool.id)
            .where(AgentTool.agent_id == agent_id)
            .order_by(Tool.name)
        )
        return [(tool, source) for tool, source in rows]

    async def _ensure_name_free(self, name: str, *, except_id: uuid.UUID | None = None) -> None:
        query = select(Agent.id).where(Agent.name == name)
        if except_id is not None:
            query = query.where(Agent.id != except_id)
        if await self.session.scalar(query) is not None:
            raise ConflictError(f"An agent named '{name}' already exists.")

    async def _required_tools_of_attached_skills(self, agent_id: uuid.UUID) -> dict[uuid.UUID, list[str]]:
        """tool_id -> names of this agent's skills that require it."""
        rows = await self.session.execute(
            select(SkillTool.tool_id, Skill.name)
            .join(Skill, Skill.id == SkillTool.skill_id)
            .join(AgentSkill, AgentSkill.skill_id == SkillTool.skill_id)
            .where(AgentSkill.agent_id == agent_id)
        )
        required: dict[uuid.UUID, list[str]] = {}
        for tool_id, skill_name in rows:
            required.setdefault(tool_id, []).append(skill_name)
        return required

    async def detail(self, agent_id: uuid.UUID) -> AgentDetailRead:
        agent = await self.get_agent(agent_id)
        await self.session.refresh(agent)  # make sure server-filled values are loaded
        config = await self.get_configuration(agent_id)
        skills = await self.agent_skills(agent_id)
        tools = await self.agent_tools(agent_id)
        base = AgentRead.model_validate(agent)
        return AgentDetailRead(
            **base.model_dump(),
            configuration=AgentConfigurationRead.model_validate(config),
            skills=[AgentSkillRead.model_validate(skill) for skill in skills],
            tools=[
                AgentToolRead(id=tool.id, name=tool.name, description=tool.description, source=source)
                for tool, source in tools
            ],
            published_instructions=agent.published_instructions,
        )

    # --- agents ----------------------------------------------------------------------

    async def create_agent(self, payload: AgentCreate) -> AgentDetailRead:
        await self._ensure_name_free(payload.name)
        agent = Agent(name=payload.name, description=payload.description, owner=payload.owner)
        self.session.add(agent)
        await self.session.flush()  # agent row first: the configuration points at it

        settings = payload.configuration.model_dump(exclude_unset=True) if payload.configuration else {}
        if settings.get("max_tool_rounds", 0) is None:
            del settings["max_tool_rounds"]  # NOT NULL column: leave it to the database default
        self.session.add(AgentConfiguration(agent_id=agent.id, **settings))
        await self.session.commit()
        return await self.detail(agent.id)

    async def list_agents(self, status: str | None = None) -> list[AgentRead]:
        query = select(Agent).order_by(Agent.name)
        if status:
            query = query.where(Agent.status == status)
        return [AgentRead.model_validate(agent) for agent in await self.session.scalars(query)]

    async def update_agent(self, agent_id: uuid.UUID, payload: AgentUpdate) -> AgentDetailRead:
        agent = await self.get_agent(agent_id)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            await self._ensure_name_free(changes["name"], except_id=agent_id)
        if changes.get("status") == "ACTIVE" and agent.published_version == 0:
            raise ConflictError("Publish the agent before setting it ACTIVE.")
        for field, value in changes.items():
            setattr(agent, field, value)
        await self.session.commit()
        return await self.detail(agent_id)

    async def delete_agent(self, agent_id: uuid.UUID) -> None:
        """Delete the agent here and, if it was published to Foundry, there too (Foundry first).

        If Foundry refuses, nothing is deleted, so the two never drift apart. An agent Foundry
        no longer has (deleted in the portal) is fine: only the local copy is left to delete.
        """
        agent = await self.get_agent(agent_id)
        if agent.foundry_agent_name:
            settings = get_settings()
            if settings.foundry_enabled:
                await FoundryClient(settings).delete_agent(agent.foundry_agent_name)
            else:
                logger.warning(
                    "Agent '%s' is registered in Foundry as '%s', but FOUNDRY_PROJECT_ENDPOINT is not set: "
                    "deleting it in Agent Lab only", agent.name, agent.foundry_agent_name,
                )
        await self.session.delete(agent)  # configuration, links and runs go too (CASCADE)
        await self.session.commit()

    # --- configuration ---------------------------------------------------------------

    async def update_configuration(
        self, agent_id: uuid.UUID, payload: AgentConfigurationUpdate
    ) -> AgentConfigurationRead:
        await self.get_agent(agent_id)
        config = await self.get_configuration(agent_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field == "max_tool_rounds" and value is None:
                continue  # NOT NULL column: null means "keep the current value"
            setattr(config, field, value)
        await self.session.commit()
        await self.session.refresh(config)
        return AgentConfigurationRead.model_validate(config)

    async def read_configuration(self, agent_id: uuid.UUID) -> AgentConfigurationRead:
        await self.get_agent(agent_id)
        return AgentConfigurationRead.model_validate(await self.get_configuration(agent_id))

    # --- skills ----------------------------------------------------------------------

    async def attach_skill(self, agent_id: uuid.UUID, skill_id: uuid.UUID) -> AgentDetailRead:
        await self.get_agent(agent_id)
        skill = await self.session.get(Skill, skill_id)
        if skill is None:
            raise NotFoundError(f"Skill {skill_id} not found.")
        already = await self.session.scalar(
            select(AgentSkill.id).where(AgentSkill.agent_id == agent_id, AgentSkill.skill_id == skill_id)
        )
        if already is not None:
            raise ConflictError(f"Skill '{skill.name}' is already attached to this agent.")

        self.session.add(AgentSkill(agent_id=agent_id, skill_id=skill_id))

        # The skill's required tools come with it. A tool the agent already has keeps its source.
        required = set(await self.session.scalars(select(SkillTool.tool_id).where(SkillTool.skill_id == skill_id)))
        have = set(await self.session.scalars(select(AgentTool.tool_id).where(AgentTool.agent_id == agent_id)))
        for tool_id in required - have:
            self.session.add(AgentTool(agent_id=agent_id, tool_id=tool_id, source="skill"))

        await self.session.commit()
        return await self.detail(agent_id)

    async def detach_skill(self, agent_id: uuid.UUID, skill_id: uuid.UUID) -> AgentDetailRead:
        await self.get_agent(agent_id)
        link = await self.session.scalar(
            select(AgentSkill).where(AgentSkill.agent_id == agent_id, AgentSkill.skill_id == skill_id)
        )
        if link is None:
            raise NotFoundError("That skill is not attached to this agent.")
        await self.session.delete(link)
        await self.session.flush()

        # Remove tools that came with skills ('skill') and that no remaining skill needs.
        still_required = await self._required_tools_of_attached_skills(agent_id)
        skill_tools = await self.session.scalars(
            select(AgentTool).where(AgentTool.agent_id == agent_id, AgentTool.source == "skill")
        )
        for agent_tool in skill_tools:
            if agent_tool.tool_id not in still_required:
                await self.session.delete(agent_tool)

        await self.session.commit()
        return await self.detail(agent_id)

    # --- tools -----------------------------------------------------------------------

    async def attach_tool(self, agent_id: uuid.UUID, tool_id: uuid.UUID) -> AgentDetailRead:
        await self.get_agent(agent_id)
        tool = await self.session.get(Tool, tool_id)
        if tool is None:
            raise NotFoundError(f"Tool {tool_id} not found.")
        existing = await self.session.scalar(
            select(AgentTool).where(AgentTool.agent_id == agent_id, AgentTool.tool_id == tool_id)
        )
        if existing is not None:
            if existing.source == "manual":
                raise ConflictError(f"Tool '{tool.name}' is already attached to this agent.")
            existing.source = "manual"  # chosen by hand now: keep it even if its skill goes
        else:
            self.session.add(AgentTool(agent_id=agent_id, tool_id=tool_id, source="manual"))
        await self.session.commit()
        return await self.detail(agent_id)

    async def detach_tool(self, agent_id: uuid.UUID, tool_id: uuid.UUID) -> AgentDetailRead:
        await self.get_agent(agent_id)
        link = await self.session.scalar(
            select(AgentTool).where(AgentTool.agent_id == agent_id, AgentTool.tool_id == tool_id)
        )
        if link is None:
            raise NotFoundError("That tool is not attached to this agent.")
        needed_by = (await self._required_tools_of_attached_skills(agent_id)).get(tool_id)
        if needed_by:
            raise ConflictError(
                f"This tool is required by attached skill(s): {', '.join(sorted(needed_by))}. "
                "Detach those skills first."
            )
        await self.session.delete(link)
        await self.session.commit()
        return await self.detail(agent_id)

    # --- publish and preview -------------------------------------------------------------

    async def publish_agent(self, agent_id: uuid.UUID) -> AgentDetailRead:
        agent = await self.get_agent(agent_id)
        skills = await self.agent_skills(agent_id)
        if not skills:
            raise ConflictError("Attach at least one skill before publishing.")

        required = await self._required_tools_of_attached_skills(agent_id)
        have = {tool.id for tool, _ in await self.agent_tools(agent_id)}
        missing = [tool_id for tool_id in required if tool_id not in have]
        if missing:
            raise ConflictError(
                "The agent is missing tools its skills need. Detach and re-attach the skill "
                f"to restore them (missing tool ids: {', '.join(map(str, missing))})."
            )

        index = skill_instructions.build_skill_index(skills)
        warnings: list[str] = []
        settings = get_settings()
        if settings.foundry_enabled:
            # Publish = register in Foundry first. If Foundry refuses, nothing changes here either.
            warnings = await self._publish_to_foundry(agent, skills, index)

        agent.published_instructions = index
        agent.published_version = agent.published_version + 1
        agent.published_at = datetime.now(UTC)
        agent.status = "ACTIVE"
        await self.session.commit()
        detail = await self.detail(agent_id)
        return detail.model_copy(update={"publish_warnings": warnings})

    async def _publish_to_foundry(self, agent: Agent, skills: list[Skill], index: str) -> list[str]:
        """Create the agent in Foundry, or a new version of it. Fills agent.foundry_* (caller commits)."""
        settings = get_settings()
        config = await self.get_configuration(agent.id)
        model = config.model or settings.azure_openai_deployment
        if not model:
            raise ConflictError("Choose a model in Model settings (or set AZURE_OPENAI_DEPLOYMENT) before publishing.")
        # A Foundry agent has no per-message skill injection, so it gets the index plus every skill in full.
        instructions = "\n\n---\n\n".join(
            [index, *[f"## Skill: {skill.name}\n\n{skill.instructions}" for skill in skills]]
        )
        tools = [function_tool(tool.name, tool.description, tool.parameters) for tool, _ in await self.agent_tools(agent.id)]
        common = {
            "model": model,
            "instructions": instructions,
            "tools": tools,
            "metadata": {"agent_lab_id": str(agent.id), "agent_lab_version": str(agent.published_version + 1)},
            "temperature": config.temperature,
        }
        client = FoundryClient(settings)

        if agent.foundry_agent_name:  # published before: a new version of the same Foundry agent
            result = await client.publish(name=agent.foundry_agent_name, existing=True, **common)
        else:  # first publish: a readable name, or name + id suffix if another agent already has it
            result = None
            for name in (agent_slug(agent.name), slug_with_suffix(agent.name, str(agent.id))):
                result = await client.publish(name=name, existing=False, **common)
                if result is not None:
                    break
            if result is None:
                raise FoundryError(f"Foundry already has agents named like '{agent_slug(agent.name)}'; rename this agent.")
        assert result is not None
        agent.foundry_agent_name = result.name
        agent.foundry_agent_version = result.version
        agent.foundry_published_at = datetime.now(UTC)
        return result.warnings

    async def preview_prompt(self, agent_id: uuid.UUID, message: str) -> PromptPreviewRead:
        """What a run would send to the LLM: the published index plus the selected skills."""
        agent = await self.get_agent(agent_id)
        if agent.published_version == 0 or not agent.published_instructions:
            raise ConflictError("Publish the agent first: the system message is built at publish.")
        skills = await self.agent_skills(agent_id)
        selected = skill_instructions.select_skills_for_message(skills, message)
        tools = await self.agent_tools(agent_id)
        return PromptPreviewRead(
            matched_skills=[skill.name for skill in selected],
            system_message=agent.published_instructions,
            user_message=skill_instructions.inject_skills(selected, message),
            tools=[tool.name for tool, _ in tools],
        )
