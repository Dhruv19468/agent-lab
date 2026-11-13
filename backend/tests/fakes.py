"""A scripted stand-in for AzureOpenAIClient: returns prepared replies and records every request."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from app.integrations.azure_openai import ModelReply, ToolCall


def reply(
    content: str | None = None,
    calls: list[tuple[str, str]] | None = None,
    finish_reason: str = "stop",
    tokens: tuple[int, int] = (100, 10),
) -> ModelReply:
    return ModelReply(
        content=content,
        tool_calls=[
            ToolCall(id=f"call_{index}", name=name, arguments=args)
            for index, (name, args) in enumerate(calls or [])
        ],
        finish_reason="tool_calls" if calls else finish_reason,
        model="fake-model",
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
    )


class FakeLLM:
    def __init__(self, replies: list[ModelReply] | Callable[[dict[str, Any]], ModelReply]) -> None:
        self.replies = replies
        self.requests: list[dict[str, Any]] = []

    async def chat(self, **request: Any) -> ModelReply:
        self.requests.append(copy.deepcopy(request))
        if callable(self.replies):
            return self.replies(request)
        return self.replies.pop(0)
