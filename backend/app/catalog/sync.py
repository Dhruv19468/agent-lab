"""The standard catalogue: what a fresh database gets at startup (SYNC_CATALOG_ON_STARTUP=true).

- Built-in tools: created if missing; their description and parameters are overwritten from
  the code registry unless the tool row says config.managed = false. Set
  "managed": false on a tool (Tools page) to experiment with its description yourself.
- Skill "BRD to Test Plan": created if missing, with prompts/v2_structured.md. Never
  overwritten: your edits in the UI (or scripts/run_experiment.py --prompt) stay.
- Agent "Test Plan Agent": created if missing, with the skill attached and published.

Running it again is harmless: it only fills in what isn't there.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Skill, SkillTool, Tool
from app.modules.agents.schemas import AgentConfigurationUpdate, AgentCreate
from app.modules.agents.service import AgentService
from app.runtime.tools.registry import BUILTIN_TOOLS

logger = logging.getLogger("platform.catalog")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
TEST_PLAN_SKILL = "BRD to Test Plan"
TEST_PLAN_AGENT = "Test Plan Agent"
DEFAULT_PROMPT = "v2_structured.md"
SKILL_TOOLS = ["list_files", "read_file", "view_image", "create_document"]


def prompt_text(file_name: str) -> str:
    return (PROMPTS_DIR / file_name).read_text(encoding="utf-8").strip()


async def _sync_tools(session: AsyncSession) -> dict[str, Tool]:
    existing = {tool.name: tool for tool in await session.scalars(select(Tool))}
    for name, builtin in BUILTIN_TOOLS.items():
        tool = existing.get(name)
        if tool is None:
            tool = Tool(
                name=name,
                description=builtin.description,
                tool_type="builtin",
                parameters=builtin.parameters,
                config={"managed": True},
            )
            session.add(tool)
            existing[name] = tool
            logger.info("Catalog: created tool %s", name)
        elif (tool.config or {}).get("managed", True):
            # A builtin tool must match its code, so a row made by hand is adopted (managed).
            tool.config = {**(tool.config or {}), "managed": True}
            tool.description = builtin.description
            tool.parameters = builtin.parameters
            tool.tool_type = "builtin"
    await session.flush()
    return existing


async def _sync_skill(session: AsyncSession, tools: dict[str, Tool]) -> Skill:
    skill = await session.scalar(select(Skill).where(Skill.name == TEST_PLAN_SKILL))
    if skill is not None:
        return skill
    skill = Skill(
        name=TEST_PLAN_SKILL,
        description=(
            "Writes a master test plan for a project from its BRD (.docx) and architecture "
            "diagram (.png), with the 24 standard sections."
        ),
        instructions=prompt_text(DEFAULT_PROMPT),
        trigger_phrases=["test plan", "master test plan", "test strategy"],
    )
    session.add(skill)
    await session.flush()
    for name in SKILL_TOOLS:
        session.add(SkillTool(skill_id=skill.id, tool_id=tools[name].id))
    await session.flush()
    logger.info("Catalog: created skill '%s' from %s", TEST_PLAN_SKILL, DEFAULT_PROMPT)
    return skill


async def _sync_agent(session: AsyncSession, skill: Skill) -> None:
    if await session.scalar(select(Agent.id).where(Agent.name == TEST_PLAN_AGENT)) is not None:
        return
    agents = AgentService(session)
    detail = await agents.create_agent(
        AgentCreate(
            name=TEST_PLAN_AGENT,
            description="Reads a project's BRD and architecture diagram and writes its master test plan.",
            owner="catalog",
            configuration=AgentConfigurationUpdate(temperature=0.2, max_tokens=16000, max_tool_rounds=12),
        )
    )
    await agents.attach_skill(detail.id, skill.id)
    await agents.publish_agent(detail.id)
    logger.info("Catalog: created and published agent '%s'", TEST_PLAN_AGENT)


async def sync_catalog(session: AsyncSession) -> None:
    tools = await _sync_tools(session)
    skill = await _sync_skill(session, tools)
    await session.commit()
    await _sync_agent(session, skill)
