from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.schemas import ApiModel


class EvaluationCreate(ApiModel):
    project: str | None = Field(
        default=None, pattern=r"^[Pp]\d{2}$", description="e.g. P06. Empty: read it from the run's message."
    )


class EvaluationSummary(ApiModel):
    id: uuid.UUID
    run_id: uuid.UUID
    project: str
    split: str | None
    reference_source: str | None
    judge_model: str
    status: str
    structure: float | None
    coverage: float | None
    similarity: float | None
    faithfulness: float | None
    overall: float | None
    error: str | None
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int | None
    created_at: datetime
    finished_at: datetime | None


class EvaluationRead(EvaluationSummary):
    details: dict[str, Any]


class EvaluationRow(EvaluationSummary):
    """One line of an agent's score history: the evaluation plus the run it scored."""

    agent_version: int
    run_model: str
