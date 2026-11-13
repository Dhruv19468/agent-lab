from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.core.dependencies import DbSession
from app.modules.evaluations.schemas import EvaluationCreate, EvaluationRead, EvaluationRow
from app.modules.evaluations.service import EvaluationService

router = APIRouter(tags=["evaluations"])


@router.post(
    "/runs/{run_id}/evaluations", response_model=EvaluationRead, status_code=status.HTTP_202_ACCEPTED
)
async def evaluate_run(run_id: uuid.UUID, payload: EvaluationCreate, session: DbSession) -> EvaluationRead:
    """Score a completed run against its project's reference plan. Poll GET /evaluations/{id}."""
    return await EvaluationService(session).start(run_id, payload)


@router.get("/runs/{run_id}/evaluations", response_model=list[EvaluationRead])
async def run_evaluations(run_id: uuid.UUID, session: DbSession) -> list[EvaluationRead]:
    return await EvaluationService(session).for_run(run_id)


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationRead)
async def get_evaluation(evaluation_id: uuid.UUID, session: DbSession) -> EvaluationRead:
    return await EvaluationService(session).read(evaluation_id)


@router.get("/agents/{agent_id}/evaluations", response_model=list[EvaluationRow])
async def agent_evaluations(
    agent_id: uuid.UUID, session: DbSession, limit: int = Query(default=200, ge=1, le=1000)
) -> list[EvaluationRow]:
    """Every score of this agent's runs, newest first: the prompt-engineering scoreboard."""
    return await EvaluationService(session).for_agent(agent_id, limit)
