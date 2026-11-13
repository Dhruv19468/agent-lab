from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.core.schemas import ApiModel

TOOL_NAME_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"  # the OpenAI function-name rule (same as the DB check)


def _check_parameters_schema(value: dict[str, Any]) -> dict[str, Any]:
    """OpenAI function parameters must be a JSON Schema object: {"type": "object", ...}."""
    if value.get("type") != "object":
        raise ValueError('parameters must be a JSON Schema with "type": "object"')
    properties = value.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("parameters.properties must be an object")
    required = value.get("required", [])
    if not isinstance(required, list) or any(name not in properties for name in required):
        raise ValueError("every name in parameters.required must be in parameters.properties")
    return value


class ToolCreate(ApiModel):
    name: str = Field(pattern=TOOL_NAME_PATTERN)
    description: str = Field(min_length=1)
    tool_type: Literal["builtin", "http"] = "builtin"
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def _check_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _check_parameters_schema(value)


class ToolUpdate(ApiModel):
    """Every field optional: only the fields sent are changed."""

    name: str | None = Field(default=None, pattern=TOOL_NAME_PATTERN)
    description: str | None = Field(default=None, min_length=1)
    tool_type: Literal["builtin", "http"] | None = None
    parameters: dict[str, Any] | None = None
    config: dict[str, Any] | None = None

    @field_validator("parameters")
    @classmethod
    def _check_parameters(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else _check_parameters_schema(value)


class ToolRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str
    tool_type: str
    parameters: dict[str, Any]
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
