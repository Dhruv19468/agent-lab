from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.core.schemas import ApiModel


def _clean_phrases(phrases: list[str]) -> list[str]:
    """Strip spaces, drop blanks, drop duplicates (case-insensitive), keep the order given."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        text = phrase.strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)
    return cleaned


class SkillCreate(ApiModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    instructions: str = Field(min_length=1)
    trigger_phrases: list[str] = Field(default_factory=list)
    required_tool_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Tools the instructions call. Attaching the skill to an agent attaches these too.",
    )

    @field_validator("trigger_phrases")
    @classmethod
    def _clean(cls, value: list[str]) -> list[str]:
        return _clean_phrases(value)


class SkillUpdate(ApiModel):
    """Every field optional: only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    instructions: str | None = Field(default=None, min_length=1)
    trigger_phrases: list[str] | None = None
    required_tool_ids: list[uuid.UUID] | None = None

    @field_validator("trigger_phrases")
    @classmethod
    def _clean(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_phrases(value)


class SkillRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str | None
    instructions: str
    trigger_phrases: list[str]
    required_tool_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
