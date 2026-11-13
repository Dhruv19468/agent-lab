"""Publishing to Azure AI Foundry, against a fake Foundry (no network, no Azure account)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.foundry import (
    FoundryClient,
    FoundryError,
    agent_slug,
    function_tool,
    slug_with_suffix,
)

ENDPOINT = "https://lab.services.ai.azure.com/api/projects/lab"


def make_client(handler) -> tuple[FoundryClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    settings = Settings(
        _env_file=None,
        foundry_project_endpoint=ENDPOINT,
        foundry_auth_mode="api_key",
        foundry_api_key="secret",
    )
    return FoundryClient(settings, transport=httpx.MockTransport(record)), seen


PUBLISH = {
    "model": "gpt-4.1-mini",
    "instructions": "Write test plans.",
    "tools": [function_tool("read_file", "Read a file", {"type": "object", "properties": {}})],
    "metadata": {"agent_lab_id": "abc"},
    "temperature": 0.2,
}


def test_names() -> None:
    assert agent_slug("Test Plan Agent") == "test-plan-agent"
    assert agent_slug("  ##  ") == "agent"
    assert slug_with_suffix("Test Plan Agent", "1A2B3C4D-xyz") == "test-plan-agent-1a2b3c"
    assert len(agent_slug("x" * 100)) == 63


async def test_first_publish_creates_the_agent() -> None:
    client, seen = make_client(lambda request: httpx.Response(200, json={"name": "test-plan-agent", "versions": {"latest": {"version": "1"}}}))
    result = await client.publish(name="test-plan-agent", existing=False, **PUBLISH)

    assert (result.name, result.version) == ("test-plan-agent", "1")
    request = seen[0]
    assert request.url.path == "/api/projects/lab/agents" and request.url.params["api-version"] == "v1"
    assert request.headers["api-key"] == "secret"
    body = json.loads(request.content)
    assert body["name"] == "test-plan-agent"
    assert body["definition"]["kind"] == "prompt" and body["definition"]["model"] == "gpt-4.1-mini"
    assert body["definition"]["tools"][0] == {
        "type": "function", "name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {}},
    }


async def test_republish_creates_a_version() -> None:
    client, seen = make_client(lambda request: httpx.Response(200, json={"version": "4"}))
    result = await client.publish(name="test-plan-agent", existing=True, **PUBLISH)
    assert result.version == "4" and seen[0].url.path.endswith("/agents/test-plan-agent/versions")


async def test_taken_name_returns_none() -> None:
    client, _ = make_client(lambda request: httpx.Response(409, json={"error": {"message": "exists"}}))
    assert await client.publish(name="test-plan-agent", existing=False, **PUBLISH) is None


async def test_model_without_temperature_is_published_without_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "temperature" in json.loads(request.content)["definition"]:
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'temperature'"}})
        return httpx.Response(200, json={"version": "2"})

    client, seen = make_client(handler)
    result = await client.publish(name="test-plan-agent", existing=True, **{**PUBLISH, "model": "o4-mini"})
    assert len(seen) == 2 and result.version == "2"
    assert "does not accept a temperature" in result.warnings[0]


async def test_refusal_is_a_clear_error() -> None:
    client, _ = make_client(lambda request: httpx.Response(400, json={"error": {"message": "model 'gpt-9' not found"}}))
    with pytest.raises(FoundryError, match="gpt-9.*Is this model deployed"):
        await client.publish(name="test-plan-agent", existing=False, **PUBLISH)


async def test_list_deployments_skips_embeddings() -> None:
    deployments = {
        "value": [
            {"name": "gpt-4.1-mini", "modelName": "gpt-4.1-mini"},
            {"name": "text-embedding-3-small", "modelName": "text-embedding-3-small"},
            {"name": "o4-mini", "modelName": "o4-mini"},
        ]
    }
    client, seen = make_client(lambda request: httpx.Response(200, json=deployments))
    assert await client.list_deployments() == ["gpt-4.1-mini", "o4-mini"]
    assert seen[0].url.path.endswith("/deployments")


def test_settings_model_list() -> None:
    settings = Settings(_env_file=None, azure_openai_deployment="gpt-4.1-mini", azure_openai_deployments="gpt-4.1, o4-mini,gpt-4.1-mini")
    assert settings.configured_deployments == ["gpt-4.1-mini", "gpt-4.1", "o4-mini"]


async def test_delete_agent() -> None:
    client, seen = make_client(lambda request: httpx.Response(204))
    assert await client.delete_agent("test-plan-agent") is True
    assert seen[0].method == "DELETE" and seen[0].url.path.endswith("/agents/test-plan-agent")


async def test_delete_agent_already_gone() -> None:
    client, _ = make_client(lambda request: httpx.Response(404, json={"error": {"message": "not found"}}))
    assert await client.delete_agent("test-plan-agent") is False


async def test_delete_agent_refused() -> None:
    client, _ = make_client(lambda request: httpx.Response(403, json={"error": {"message": "PermissionDenied"}}))
    with pytest.raises(FoundryError, match="refused to delete.*PermissionDenied"):
        await client.delete_agent("test-plan-agent")
