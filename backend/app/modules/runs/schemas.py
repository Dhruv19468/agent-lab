from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.core.schemas import ApiModel

OutputFormat = Literal["md", "docx", "xlsx", "pdf"]


class RunCreate(ApiModel):
    message: str = Field(min_length=1, max_length=20_000)
    output_format: OutputFormat | None = Field(
        default=None, description="Also save the answer as a file in agent-output/ when the run finishes."
    )
    model: str | None = Field(
        default=None, max_length=100, description="Deployment for this run only. Empty: the agent's model."
    )
    created_by: str | None = Field(default=None, max_length=100)


class RunSummary(ApiModel):
    """A row in the run history (no answer text, so the list stays small)."""

    id: uuid.UUID
    agent_id: uuid.UUID
    agent_version: int
    model: str
    status: str
    prompt: str
    error: str | None
    tool_rounds: int
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int | None
    output_format: str | None = None
    output_file: str | None = None
    created_at: datetime
    finished_at: datetime | None
    latest_overall: float | None = None  # newest completed evaluation's score, if any


class RunRead(RunSummary):
    answer: str | None
    matched_skills: list[str]
    tool_calls: list[dict[str, Any]]
