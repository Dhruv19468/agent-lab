"""The one place that talks to Azure OpenAI.

Everything else (the agent loop, scripts) calls `get_llm_client().chat(...)` and gets back a
plain `ModelReply`. Endpoint, key, retries and error translation live here only, the way
Wesco keeps all Foundry calls in app/integrations/foundry_*.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)

from app.core.config import Settings, get_settings
from app.core.errors import AppError


class LlmError(AppError):
    """Azure OpenAI could not answer (502: the upstream service failed, not our request)."""

    status_code = 502


class LlmNotConfiguredError(LlmError):
    """The three AZURE_OPENAI_* settings are not all set (503: service unavailable)."""

    status_code = 503


@dataclass
class ToolCall:
    """The model asking us to run one tool. `arguments` is a JSON string the model wrote."""

    id: str
    name: str
    arguments: str


@dataclass
class ModelReply:
    """One answer from the model: either text, or a request to call tools (or both)."""

    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str | None
    model: str
    prompt_tokens: int
    completion_tokens: int

    def as_assistant_message(self) -> dict[str, Any]:
        """This reply as a message for the conversation, so the model later sees what it asked for."""
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
                for call in self.tool_calls
            ]
        return message


def _short(error: Exception, limit: int = 300) -> str:
    text = getattr(error, "message", None) or str(error)
    return text if len(text) <= limit else text[:limit] + "..."


class AzureOpenAIClient:
    def __init__(self, settings: Settings) -> None:
        self.default_deployment = settings.azure_openai_deployment
        self._client = AsyncOpenAI(
            api_key=settings.azure_openai_api_key.get_secret_value(),
            base_url=settings.azure_openai_endpoint,
            timeout=settings.azure_openai_timeout_seconds,
            max_retries=settings.azure_openai_max_retries,
        )

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        deployment: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_output: bool = False,
    ) -> ModelReply:
        """Send the conversation so far; return the model's next reply.

        json_output=True asks for a single JSON object (used by the evaluation judge).
        """
        model = deployment or self.default_deployment
        request: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            request["tools"] = tools
        if temperature is not None:
            request["temperature"] = temperature
        if max_tokens is not None:
            request["max_completion_tokens"] = max_tokens
        if json_output:
            request["response_format"] = {"type": "json_object"}

        try:
            try:
                response = await self._client.chat.completions.create(**request)
            except BadRequestError as error:
                # Reasoning models (o-series, gpt-5) refuse a temperature: drop it and ask again.
                if "temperature" not in request or "temperature" not in str(error).lower():
                    raise
                request.pop("temperature")
                response = await self._client.chat.completions.create(**request)
        except AuthenticationError as error:
            raise LlmError("Azure OpenAI rejected the API key (401). Check AZURE_OPENAI_API_KEY.") from error
        except NotFoundError as error:
            raise LlmError(
                f"Deployment '{model}' was not found (404). Check the agent's model setting "
                "or AZURE_OPENAI_DEPLOYMENT, and that the endpoint ends with /openai/v1/."
            ) from error
        except RateLimitError as error:
            raise LlmError(
                "Azure OpenAI rate limit reached (429), even after retrying. Wait a minute, "
                "or raise the deployment's tokens-per-minute limit in the Foundry portal."
            ) from error
        except BadRequestError as error:
            raise LlmError(f"Azure OpenAI refused the request (400): {_short(error)}") from error
        except APITimeoutError as error:
            raise LlmError("Azure OpenAI did not answer in time. Try again, or raise AZURE_OPENAI_TIMEOUT_SECONDS.") from error
        except APIConnectionError as error:
            raise LlmError("Could not connect to Azure OpenAI. Check the endpoint and your network.") from error
        except APIStatusError as error:
            raise LlmError(f"Azure OpenAI returned {error.status_code}: {_short(error)}") from error

        choice = response.choices[0]
        message = choice.message
        usage = response.usage
        calls = [
            ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments or "{}")
            for call in (message.tool_calls or [])
            if getattr(call, "function", None) is not None  # only function tools; we offer no others
        ]
        return ModelReply(
            content=message.content,
            tool_calls=calls,
            finish_reason=choice.finish_reason,
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


@lru_cache
def get_llm_client() -> AzureOpenAIClient:
    """One shared client for the whole app (it keeps a pool of HTTP connections)."""
    settings = get_settings()
    if not settings.azure_openai_configured:
        raise LlmNotConfiguredError(
            "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY "
            "and AZURE_OPENAI_DEPLOYMENT in backend/.env."
        )
    return AzureOpenAIClient(settings)
