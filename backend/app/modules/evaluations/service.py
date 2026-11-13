from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.db.session import SessionLocal
from app.evaluation.judge import Judge
from app.evaluation.scorer import ReferenceMissingError, load_reference, load_sources, score_plan
from app.integrations.azure_openai import get_llm_client
from app.models import AgentRun, Evaluation
from app.modules.evaluations.schemas import EvaluationCreate, EvaluationRead, EvaluationRow
from app.runtime import background
from app.runtime.dataset import find_project, project_in_text
from app.runtime.storage import get_storage

logger = logging.getLogger("platform.evaluation")


class EvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(self, run_id: uuid.UUID, payload: EvaluationCreate) -> EvaluationRead:
        run = await self.session.get(AgentRun, run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found.")
        if run.status != "completed" or not run.answer:
            raise ConflictError("Only a completed run with an answer can be scored.")

        project_id = (payload.project or project_in_text(run.prompt) or "").upper()
        if not project_id:
            raise BadRequestError(
                "Say which project this run was for (e.g. P06): the message doesn't name one."
            )
        settings = get_settings()
        storage = get_storage()
        project = await asyncio.to_thread(find_project, storage, project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} is not in {storage.describe()}/raw.")
        try:
            reference, source = await asyncio.to_thread(load_reference, storage, project)
            brd_text, diagrams = await asyncio.to_thread(load_sources, storage, project)
        except ReferenceMissingError as error:
            raise ConflictError(str(error)) from error
        get_llm_client()  # 503 now if Azure OpenAI isn't configured

        evaluation = Evaluation(
            run_id=run_id,
            project=project.project,
            split=project.split,
            reference_source=source,
            judge_model=settings.judge_deployment,
            status="running",
            details={},
        )
        self.session.add(evaluation)
        await self.session.commit()
        await self.session.refresh(evaluation)

        background.spawn(
            _execute(evaluation.id, project.project, run.answer, reference, brd_text, diagrams),
            name=f"evaluation-{evaluation.id}",
        )
        return EvaluationRead.model_validate(evaluation)

    async def read(self, evaluation_id: uuid.UUID) -> EvaluationRead:
        evaluation = await self.session.get(Evaluation, evaluation_id)
        if evaluation is None:
            raise NotFoundError(f"Evaluation {evaluation_id} not found.")
        return EvaluationRead.model_validate(evaluation)

    async def for_run(self, run_id: uuid.UUID) -> list[EvaluationRead]:
        rows = await self.session.scalars(
            select(Evaluation).where(Evaluation.run_id == run_id).order_by(Evaluation.created_at.desc())
        )
        return [EvaluationRead.model_validate(row) for row in rows]

    async def for_agent(self, agent_id: uuid.UUID, limit: int = 200) -> list[EvaluationRow]:
        rows = await self.session.execute(
            select(Evaluation, AgentRun.agent_version, AgentRun.model)
            .join(AgentRun, AgentRun.id == Evaluation.run_id)
            .where(AgentRun.agent_id == agent_id)
            .order_by(Evaluation.created_at.desc())
            .limit(limit)
        )
        return [
            EvaluationRow.model_validate(
                {
                    **EvaluationRead.model_validate(evaluation).model_dump(),
                    "agent_version": version,
                    "run_model": model,
                }
            )
            for evaluation, version, model in rows
        ]


async def _execute(
    evaluation_id: uuid.UUID,
    project: str,
    candidate: str,
    reference: dict[str, str],
    brd_text: str,
    diagrams: list[str],
) -> None:
    settings = get_settings()
    judge = Judge(llm=get_llm_client(), deployment=settings.judge_deployment)
    started = time.perf_counter()
    values: dict[str, object]
    try:
        result = await score_plan(
            judge=judge,
            project=project,
            candidate=candidate,
            reference=reference,
            brd_text=brd_text,
            diagrams=diagrams,
            cache_dir=get_storage(),
            cache_prefix="_cache/evaluation",
        )
        values = {
            "status": "completed",
            "structure": result.structure,
            "coverage": result.coverage,
            "similarity": result.similarity,
            "faithfulness": result.faithfulness,
            "overall": result.overall,
            "details": result.details,
        }
    except Exception as error:
        logger.exception("Evaluation %s failed", evaluation_id)
        values = {
            "status": "failed",
            "error": getattr(error, "message", None) or str(error) or type(error).__name__,
        }

    values.update(
        prompt_tokens=judge.tokens.prompt,
        completion_tokens=judge.tokens.completion,
        duration_ms=int((time.perf_counter() - started) * 1000),
        finished_at=datetime.now(UTC),
    )
    async with SessionLocal() as session:
        await session.execute(update(Evaluation).where(Evaluation.id == evaluation_id).values(**values))
        await session.commit()
