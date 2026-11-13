"""Step 2 check: insert linked rows, test the constraints, and watch ON DELETE CASCADE.

Run from the backend/ folder (after `alembic upgrade head`):
    uv run python scripts/check_models.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Agent,
    AgentConfiguration,
    AgentRun,
    AgentSkill,
    AgentTool,
    Skill,
    SkillTool,
    Tool,
)


async def count(session, model, **filters) -> int:
    """SELECT count(*) FROM <model's table> WHERE <column> = <value> ..."""
    query = select(func.count()).select_from(model)
    for column, value in filters.items():
        query = query.where(getattr(model, column) == value)
    return await session.scalar(query)


async def expect_rejected(label: str, *rows) -> None:
    """Try to insert rows that break a rule; the database must refuse them."""
    async with SessionLocal() as session:
        session.add_all(rows)
        try:
            await session.commit()
        except IntegrityError as error:
            await session.rollback()
            reason = str(error.orig).splitlines()[0]
            print(f"  OK  {label}: rejected -> {reason}")
        else:
            print(f"  !!  {label}: was NOT rejected")


async def main() -> None:
    suffix = uuid.uuid4().hex[:6]  # unique names, so the script can run again

    # 1) Create an agent, a skill and a tool, then link them.
    async with SessionLocal() as session:
        agent = Agent(name=f"Demo Agent {suffix}", description="Created by check_models.py")
        skill = Skill(
            name=f"Demo Skill {suffix}",
            description="Says hello. Demo only.",
            instructions="# Demo skill\n\nAnswer with a friendly hello.",
            trigger_phrases=["say hello"],
        )
        tool = Tool(
            name=f"demo_tool_{suffix}",
            description="Does nothing. Demo only.",
            parameters={"type": "object", "properties": {}},
        )
        session.add_all([agent, skill, tool])
        await session.flush()  # send these INSERTs first: the links below point at them

        session.add_all(
            [
                AgentConfiguration(agent_id=agent.id, model="gpt-4.1-mini", temperature=0.2),
                SkillTool(skill_id=skill.id, tool_id=tool.id),
                AgentSkill(agent_id=agent.id, skill_id=skill.id),
                AgentTool(agent_id=agent.id, tool_id=tool.id, source="skill"),
                AgentRun(agent_id=agent.id, agent_version=0, model="gpt-4.1-mini", prompt="say hello"),
            ]
        )
        await session.commit()

        await session.refresh(agent)  # read back what Postgres filled in (server defaults)
        print("1) Created:")
        print(f"  {agent!r}")
        print(f"  published_version={agent.published_version}  created_at={agent.created_at}")
        print(f"  {skill!r}  trigger_phrases={skill.trigger_phrases}")
        print(f"  {tool!r}")

    agent_id, skill_id, tool_id = agent.id, skill.id, tool.id

    # 2) Rules the database enforces.
    print("2) Constraints:")
    await expect_rejected(
        "same skill attached twice", AgentSkill(agent_id=agent_id, skill_id=skill_id)
    )
    await expect_rejected("invalid status", Agent(name=f"Bad Agent {suffix}", status="FOO"))
    await expect_rejected(
        "temperature 5", AgentConfiguration(agent_id=agent_id, temperature=5.0)
    )
    await expect_rejected(
        "tool name with a space",
        Tool(name="bad name", description="x", parameters={}),
    )
    await expect_rejected(
        "link to an agent that doesn't exist",
        AgentSkill(agent_id=uuid.uuid4(), skill_id=skill_id),
    )

    # 3) Delete the agent and let ON DELETE CASCADE clean up.
    async with SessionLocal() as session:
        before = {
            "agent_configurations": await count(session, AgentConfiguration, agent_id=agent_id),
            "agent_skills": await count(session, AgentSkill, agent_id=agent_id),
            "agent_tools": await count(session, AgentTool, agent_id=agent_id),
            "agent_runs": await count(session, AgentRun, agent_id=agent_id),
        }
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()
        after = {
            "agent_configurations": await count(session, AgentConfiguration, agent_id=agent_id),
            "agent_skills": await count(session, AgentSkill, agent_id=agent_id),
            "agent_tools": await count(session, AgentTool, agent_id=agent_id),
            "agent_runs": await count(session, AgentRun, agent_id=agent_id),
        }
        print("3) Delete the agent (ON DELETE CASCADE):")
        for table in before:
            print(f"  {table:22} {before[table]} -> {after[table]}")
        print(f"  skill still exists: {await count(session, Skill, id=skill_id) == 1}")
        print(f"  tool still exists:  {await count(session, Tool, id=tool_id) == 1}")

        # 4) Clean up the demo skill and tool (skill_tools goes with them).
        await session.execute(delete(Skill).where(Skill.id == skill_id))
        await session.execute(delete(Tool).where(Tool.id == tool_id))
        await session.commit()
        print(f"4) Cleanup done. skill_tools rows left: {await count(session, SkillTool, skill_id=skill_id)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())