"""The agent loop: send the conversation to the model, run the tools it asks for, repeat.

This module knows nothing about the database or HTTP. It takes the two messages the agent
starts with plus the tools it may use, and returns a `RunOutcome`. The runs service
(app/modules/runs/service.py) loads those inputs from the database and saves the outcome,
and the unit tests drive this loop with a fake model.

One run, step by step:
  1. messages = [system: the agent's published skill index, user: skills + the user's message]
  2. ask the model; it answers with text, or with tool calls
  3. for each tool call: run the tool, append its result as a "tool" message
     (an image from view_image is added afterwards as a user message: tool results are text only)
  4. go back to 2, until the model answers without tool calls or max_tool_rounds is used up
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.integrations.azure_openai import ModelReply
from app.runtime.storage import Storage
from app.runtime.tools import registry
from app.runtime.tools.files import ToolError

logger = logging.getLogger("platform.runner")

IMAGE_KEY = "_image_data_url"
LOG_ARGUMENT_CHARS = 400  # tool arguments kept in the run log (create_document content can be huge)
LOG_RESULT_CHARS = 300


class ChatModel(Protocol):
    """What the loop needs from the LLM client (AzureOpenAIClient fits; tests pass a fake)."""

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        deployment: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelReply: ...


@dataclass
class RunOutcome:
    status: str  # "completed" or "failed"
    answer: str | None
    error: str | None = None
    model: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_rounds: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class AgentToolSpec:
    """One tool as the agent's database row describes it (editable in the UI)."""

    name: str
    description: str
    parameters: dict[str, Any]


def tool_specs(tools: list[AgentToolSpec]) -> list[dict[str, Any]]:
    """OpenAI function definitions for the agent's tools that have a builtin implementation.

    The description and parameters come from the database, so editing a tool's description in
    the UI changes what the model sees (that is prompt engineering too).
    """
    specs = []
    for tool in tools:
        if tool.name not in registry.BUILTIN_TOOLS:
            logger.warning("Tool '%s' is attached but has no builtin implementation; skipping it", tool.name)
            continue
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
        )
    return specs


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}… ({len(text)} chars)"


async def _run_tool(name: str, raw_arguments: str, data_root: Storage | Path) -> tuple[dict[str, Any], bool]:
    """(result, ok). A ToolError becomes {"error": ...} so the model can read it and try again."""
    try:
        result = await asyncio.to_thread(registry.execute, name, raw_arguments, data_root)
        return result, True
    except ToolError as error:
        return {"error": str(error)}, False
    except Exception as error:  # a bug in a tool must not kill the whole run
        logger.exception("Tool %s crashed", name)
        return {"error": f"The tool failed unexpectedly: {type(error).__name__}."}, False


async def run_agent(
    *,
    llm: ChatModel,
    system_message: str,
    user_message: str,
    tools: list[AgentToolSpec],
    data_root: Storage | Path,  # the local data folder or the Blob container
    deployment: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    max_tool_rounds: int = 10,
) -> RunOutcome:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]
    specs = tool_specs(tools)
    outcome = RunOutcome(status="failed", answer=None)

    for round_number in range(max_tool_rounds + 1):
        # Last allowed round: no tools on offer, so the model has to answer.
        offer_tools = specs if round_number < max_tool_rounds else None
        reply = await llm.chat(
            messages=messages,
            tools=offer_tools or None,
            deployment=deployment,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        outcome.model = reply.model
        outcome.prompt_tokens += reply.prompt_tokens
        outcome.completion_tokens += reply.completion_tokens

        if not reply.tool_calls:
            outcome.answer = reply.content or ""
            if reply.finish_reason == "length":
                outcome.error = (
                    "The answer was cut off at max_tokens. Raise the agent's max tokens "
                    "(the model's output limit) and run again."
                )
                return outcome
            if not outcome.answer.strip():
                outcome.error = "The model returned an empty answer."
                return outcome
            outcome.status = "completed"
            return outcome

        outcome.tool_rounds += 1
        messages.append(reply.as_assistant_message())
        images: list[tuple[str, str]] = []

        for call in reply.tool_calls:
            started = time.perf_counter()
            result, ok = await _run_tool(call.name, call.arguments, data_root)
            image = result.pop(IMAGE_KEY, None)
            if image:
                images.append((result.get("path", "image"), image))
            content = json.dumps(result, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
            outcome.tool_calls.append(
                {
                    "round": outcome.tool_rounds,
                    "name": call.name,
                    "arguments": _clip(call.arguments, LOG_ARGUMENT_CHARS),
                    "ok": ok,
                    "result": _clip(content, LOG_RESULT_CHARS),
                    "durationMs": int((time.perf_counter() - started) * 1000),
                }
            )

        # Every tool message must directly follow the assistant message that asked for it,
        # so images go in one user message after all of them.
        if images:
            parts: list[dict[str, Any]] = []
            for path, data_url in images:
                parts.append({"type": "text", "text": f"Image returned by view_image for {path}:"})
                parts.append({"type": "image_url", "image_url": {"url": data_url}})
            messages.append({"role": "user", "content": parts})

    outcome.error = "The agent used every tool round without giving a final answer."  # pragma: no cover
    return outcome  # pragma: no cover
