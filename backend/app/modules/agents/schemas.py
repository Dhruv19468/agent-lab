from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.schemas import ApiModel

AgentStatus = Literal["DRAFT", "ACTIVE", "INACTIVE", "ARCHIVED"]


# --- configuration ----------------------------------------------------------------------


class AgentConfigurationUpdate(ApiModel):
    """Only the fields sent are changed. Send null to go back to the default."""

    model: str | None = Field(default=None, max_length=100)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    max_tool_rounds: int | None = Field(default=None, ge=1, le=50)


class AgentConfigurationRead(ApiModel):
    model: str | None
    temperature: float | None
    max_tokens: int | None
    max_tool_rounds: int


# --- agents -----------------------------------------------------------------------------


class AgentCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    owner: str | None = Field(default=None, max_length=100)
    configuration: AgentConfigurationUpdate | None = None


class AgentUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    owner: str | None = Field(default=None, max_length=100)
    status: AgentStatus | None = None


class AgentRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str | None
    owner: str | None
    status: str
    published_version: int
    published_at: datetime | None
    foundry_agent_name: str | None = None
    foundry_agent_version: str | None = None
    foundry_published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentSkillRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str | None
    trigger_phrases: list[str]


class AgentToolRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str
    source: str  # 'manual' or 'skill'


class AgentDetailRead(AgentRead):
    configuration: AgentConfigurationRead
    skills: list[AgentSkillRead]
    tools: list[AgentToolRead]
    published_instructions: str | None
    publish_warnings: list[str] = []  # said once, in the answer to a publish


# --- attach / publish / preview ---------------------------------------------------------


class AttachSkillRequest(ApiModel):
    skill_id: uuid.UUID


class AttachToolRequest(ApiModel):
    tool_id: uuid.UUID


class PromptPreviewRequest(ApiModel):
    message: str = Field(min_length=1)


class PromptPreviewRead(ApiModel):
    """Exactly what Step 4 will send to the LLM for this message (before any tool calls)."""

    matched_skills: list[str]
    system_message: str
    user_message: str
    tools: list[str]
