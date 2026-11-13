from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.db.session import SessionLocal
from app.integrations.azure_openai import get_llm_client
from app.models import AgentRun, Evaluation
from app.modules.agents import skill_instructions
from app.modules.agents.service import AgentService
from app.modules.runs.schemas import RunCreate, RunRead, RunSummary
from app.runtime import background, exporters
from app.runtime.agent_runner import AgentToolSpec, run_agent
from app.runtime.dataset import project_in_text
from app.runtime.storage import get_storage
from app.runtime.tools.files import OUTPUT_FOLDER

logger = logging.getLogger("platform.runs")


class RunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_run(self, run_id: uuid.UUID) -> AgentRun:
        run = await self.session.get(AgentRun, run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found.")
        return run

    async def _latest_scores(self, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
        if not run_ids:
            return {}
        rows = await self.session.execute(
            select(Evaluation.run_id, Evaluation.overall)
            .where(Evaluation.run_id.in_(run_ids), Evaluation.status == "completed")
            .order_by(Evaluation.created_at)
        )
        return {run_id: overall for run_id, overall in rows}  # later rows win: the newest score

    async def read_run(self, run_id: uuid.UUID) -> RunRead:
        run = await self.get_run(run_id)
        scores = await self._latest_scores([run.id])
        return RunRead.model_validate(run).model_copy(update={"latest_overall": scores.get(run.id)})

    async def list_runs(self, agent_id: uuid.UUID, limit: int = 50) -> list[RunSummary]:
        await AgentService(self.session).get_agent(agent_id)
        runs = list(
            await self.session.scalars(
                select(AgentRun)
                .where(AgentRun.agent_id == agent_id)
                .order_by(AgentRun.created_at.desc())
                .limit(limit)
            )
        )
        scores = await self._latest_scores([run.id for run in runs])
        return [
            RunSummary.model_validate(run).model_copy(update={"latest_overall": scores.get(run.id)})
            for run in runs
        ]

    async def start_run(self, agent_id: uuid.UUID, payload: RunCreate) -> RunRead:
        """Save a 'running' row, start the agent loop in the background, answer at once."""
        agents = AgentService(self.session)
        agent = await agents.get_agent(agent_id)
        if agent.published_version == 0 or not agent.published_instructions:
            raise ConflictError("Publish the agent before running it.")
        if agent.status != "ACTIVE":
            raise ConflictError(f"The agent is {agent.status}; set it ACTIVE to run it.")

        get_llm_client()  # fail now (503) if Azure OpenAI isn't configured, not in the background
        settings = get_settings()
        config = await agents.get_configuration(agent_id)
        skills = await agents.agent_skills(agent_id)
        selected = skill_instructions.select_skills_for_message(skills, payload.message)
        tools = [
            AgentToolSpec(name=tool.name, description=tool.description, parameters=tool.parameters)
            for tool, _ in await agents.agent_tools(agent_id)
        ]
        deployment = (payload.model or "").strip() or config.model or settings.azure_openai_deployment

        run = AgentRun(
            agent_id=agent_id,
            agent_version=agent.published_version,
            model=deployment,
            status="running",
            prompt=payload.message,
            matched_skills=[skill.name for skill in selected],
            tool_calls=[],
            output_format=payload.output_format,
            created_by=payload.created_by,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)

        background.spawn(
            _execute_run(
                run_id=run.id,
                system_message=agent.published_instructions,
                user_message=skill_instructions.inject_skills(selected, payload.message),
                tools=tools,
                deployment=deployment,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                max_tool_rounds=config.max_tool_rounds,
                output_format=payload.output_format,
                file_stem=export_stem(payload.message, run.id),
            ),
            name=f"run-{run.id}",
        )
        logger.info("Run %s started for agent '%s' v%s", run.id, agent.name, agent.published_version)
        return RunRead.model_validate(run)

    async def export(self, run_id: uuid.UUID, fmt: str) -> tuple[bytes, str, str]:
        """(file bytes, media type, file name): the run's answer in the chosen format."""
        run = await self.get_run(run_id)
        if not run.answer:
            raise ConflictError("This run has no answer to download yet.")
        data = await asyncio.to_thread(exporters.export, run.answer, fmt)
        media_type, suffix = exporters.FORMATS[fmt]
        return data, media_type, f"{export_stem(run.prompt, run.id)}{suffix}"


def export_stem(message: str, run_id: uuid.UUID) -> str:
    """'P06_test_plan_1a2b3c4d': project from the message + the start of the run id (always unique)."""
    return f"{project_in_text(message) or 'run'}_test_plan_{str(run_id)[:8]}"


def _save_output(markdown: str, fmt: str, stem: str) -> str:
    """Write the answer to agent-output/<stem>.<ext> in the data root; return that relative path."""
    data = exporters.export(markdown, fmt)
    relative = f"{OUTPUT_FOLDER}/{stem}{exporters.FORMATS[fmt][1]}"
    get_storage().write_bytes(relative, data, overwrite=False)
    return relative


async def _execute_run(
    *,
    run_id: uuid.UUID,
    system_message: str,
    user_message: str,
    tools: list[AgentToolSpec],
    deployment: str,
    temperature: float | None,
    max_tokens: int | None,
    max_tool_rounds: int,
    output_format: str | None = None,
    file_stem: str = "run",
) -> None:
    """The background half of a run: the agent loop, the optional file, then one UPDATE."""
    started = time.perf_counter()
    values: dict[str, object]
    try:
        outcome = await run_agent(
            llm=get_llm_client(),
            system_message=system_message,
            user_message=user_message,
            tools=tools,
            data_root=get_storage(),
            deployment=deployment,
            temperature=temperature,
            max_tokens=max_tokens,
            max_tool_rounds=max_tool_rounds,
        )
        values = {
            "status": outcome.status,
            "answer": outcome.answer,
            "error": outcome.error,
            "tool_calls": outcome.tool_calls,
            "tool_rounds": outcome.tool_rounds,
            "prompt_tokens": outcome.prompt_tokens,
            "completion_tokens": outcome.completion_tokens,
        }
        if outcome.model:
            values["model"] = outcome.model
        if output_format and outcome.status == "completed" and outcome.answer:
            try:
                values["output_file"] = await asyncio.to_thread(_save_output, outcome.answer, output_format, file_stem)
            except Exception as error:  # the plan is safe in the database; only the file failed
                logger.exception("Run %s: saving the .%s file failed", run_id, output_format)
                values["error"] = f"The plan is saved, but writing the .{output_format} file failed: {error}"
    except Exception as error:  # LlmError (key, quota, timeout…) or a bug: record it on the run
        logger.exception("Run %s failed", run_id)
        values = {
            "status": "failed",
            "error": getattr(error, "message", None) or str(error) or type(error).__name__,
        }

    values["duration_ms"] = int((time.perf_counter() - started) * 1000)
    values["finished_at"] = datetime.now(UTC)
    async with SessionLocal() as session:
        await session.execute(update(AgentRun).where(AgentRun.id == run_id).values(**values))
        await session.commit()
    logger.info("Run %s %s in %d ms", run_id, values["status"], values["duration_ms"])
