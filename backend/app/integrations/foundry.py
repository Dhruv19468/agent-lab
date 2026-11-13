"""Azure AI Foundry: register (publish) an agent in a Foundry project and list its models.

Publish in Agent Lab = build the agent's instructions, then create the agent in Foundry, or a
new version of it if it already exists, using Foundry's agent control plane (the same API
the work framework uses):

    POST {project}/agents?api-version=v1                  {"name", "definition"}  first publish
    POST {project}/agents/{name}/versions?api-version=v1  {"definition"}          every later one
    DELETE {project}/agents/{name}?api-version=v1          delete it, all versions
    GET  {project}/deployments?api-version=v1             the models deployed in the project

The definition carries the model, instructions, temperature and the tools as function
definitions. Runs still use Agent Lab's own loop (app/runtime/agent_runner.py); Foundry holds
the registered, versioned agent you can open in the portal.

Sign-in: FOUNDRY_AUTH_MODE=entra uses DefaultAzureCredential: your `az login` on your laptop,
the Container App's managed identity on Azure. Either needs the "Azure AI User" role on the
Foundry resource.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import AppError

logger = logging.getLogger("platform.foundry")

API_VERSION = "v1"
NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")  # Foundry: <=63, alnum + inner hyphens
_EMBEDDING = re.compile(r"embed", re.IGNORECASE)


class FoundryError(AppError):
    """Foundry refused or could not be reached (502: the upstream service failed)."""

    status_code = 502


@dataclass
class FoundryPublishResult:
    name: str
    version: str
    warnings: list[str] = field(default_factory=list)


def agent_slug(name: str) -> str:
    """'Test Plan Agent' -> 'test-plan-agent' (Foundry's naming rule)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:63].strip("-")
    return slug or "agent"


def slug_with_suffix(name: str, agent_id: str) -> str:
    """'test-plan-agent-1a2b3c': used when the plain name is taken by something else."""
    suffix = re.sub(r"[^a-z0-9]", "", agent_id.lower())[:6]
    return f"{agent_slug(name)[: 63 - len(suffix) - 1].strip('-')}-{suffix}"


def function_tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """A tool as a Foundry agent definition expects it (Responses-style function tool)."""
    return {"type": "function", "name": name, "description": description, "parameters": parameters}


def _version_of(body: dict[str, Any]) -> str:
    """POST /versions returns {"version"}; POST /agents nests it under versions.latest."""
    version = body.get("version") or ((body.get("versions") or {}).get("latest") or {}).get("version")
    return str(version or "1")


class FoundryClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.base_url = settings.foundry_project_endpoint.rstrip("/")
        self._transport = transport  # tests pass a fake transport
        self._credential: Any = None

    @property
    def enabled(self) -> bool:
        return self.settings.foundry_enabled

    async def _headers(self) -> dict[str, str]:
        if self.settings.foundry_auth_mode.strip().lower() == "api_key":
            return {"api-key": self.settings.foundry_api_key.get_secret_value()}
        if self._credential is None:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as error:
                raise FoundryError("Foundry sign-in needs azure-identity: run `uv add azure-identity`.") from error
            self._credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        try:
            token = await asyncio.to_thread(self._credential.get_token, self.settings.foundry_entra_scope)
        except Exception as error:
            raise FoundryError(
                "Could not sign in to Foundry. Locally run `az login`; on Azure check the Container App's "
                f"managed identity has the 'Azure AI User' role. ({type(error).__name__}: {str(error)[:200]})"
            ) from error
        return {"Authorization": f"Bearer {token.token}"}

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> tuple[int, Any]:
        headers = await self._headers()
        try:
            async with httpx.AsyncClient(timeout=self.settings.foundry_timeout_seconds, transport=self._transport) as client:
                response = await client.request(
                    method, f"{self.base_url}{path}", params={"api-version": API_VERSION}, json=json, headers=headers
                )
        except httpx.HTTPError as error:
            raise FoundryError(f"Could not reach Foundry at {self.base_url}: {type(error).__name__}: {error}") from error
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return response.status_code, body

    @staticmethod
    def _problem(status: int, body: Any) -> str:
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)[:500]
        return str(body)[:500]

    # --- models ---------------------------------------------------------------------------

    async def list_deployments(self) -> list[str]:
        """Names of the chat models deployed in the project (embeddings left out)."""
        status, body = await self._request("GET", "/deployments")
        if status >= 400:
            raise FoundryError(f"Foundry would not list deployments ({status}): {self._problem(status, body)}")
        names = []
        for entry in (body or {}).get("value", []) if isinstance(body, dict) else []:
            name = str(entry.get("name") or "").strip()
            model_name = str(entry.get("modelName") or (entry.get("properties") or {}).get("model", {}).get("name") or "")
            if name and not _EMBEDDING.search(name) and not _EMBEDDING.search(model_name):
                names.append(name)
        return sorted(names)

    # --- publish --------------------------------------------------------------------------

    @staticmethod
    def definition(
        model: str, instructions: str, tools: list[dict[str, Any]], metadata: dict[str, str], temperature: float | None
    ) -> dict[str, Any]:
        definition: dict[str, Any] = {"kind": "prompt", "model": model, "instructions": instructions}
        if temperature is not None:
            definition["temperature"] = temperature
        if tools:
            definition["tools"] = tools
        if metadata:
            definition["metadata"] = metadata
        return definition

    async def _post_definition(self, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
        """POST, retrying once without temperature if the model refuses one (reasoning models)."""
        status, body = await self._request("POST", path, payload)
        definition = payload["definition"]
        if status == 400 and "temperature" in definition and "temperature" in str(body).lower():
            definition = {key: value for key, value in definition.items() if key != "temperature"}
            status, body = await self._request("POST", path, {**payload, "definition": definition})
            if status < 400 and isinstance(body, dict):
                body["_dropped_temperature"] = True
        return status, body

    async def publish(
        self,
        *,
        name: str,
        existing: bool,
        model: str,
        instructions: str,
        tools: list[dict[str, Any]],
        metadata: dict[str, str],
        temperature: float | None,
    ) -> FoundryPublishResult | None:
        """Create agent `name` (existing=False) or a new version of it (existing=True).

        Returns None when creating and the name is already taken (409), so the caller can try
        another name: a taken name may belong to a different agent in the project.
        """
        if not NAME_PATTERN.match(name):
            raise FoundryError(f"'{name}' is not a valid Foundry agent name.")
        definition = self.definition(model, instructions, tools, metadata, temperature)
        if existing:
            status, body = await self._post_definition(f"/agents/{name}/versions", {"definition": definition})
        else:
            status, body = await self._post_definition("/agents", {"name": name, "definition": definition})
            if status == 409:
                return None
        if status >= 400:
            hint = " Is this model deployed in the Foundry project?" if "model" in str(body).lower() else ""
            raise FoundryError(f"Foundry refused to publish '{name}' ({status}): {self._problem(status, body)}{hint}")
        result = FoundryPublishResult(name=name, version=_version_of(body if isinstance(body, dict) else {}))
        if isinstance(body, dict) and body.get("_dropped_temperature"):
            result.warnings.append(f"{model} does not accept a temperature, so it was published without one.")
        logger.info("Published agent '%s' to Foundry as version %s", name, result.version)
        return result

    # --- delete ---------------------------------------------------------------------------

    async def delete_agent(self, name: str) -> bool:
        """Delete agent `name` and all its versions. False if Foundry has no such agent (404)."""
        status, body = await self._request("DELETE", f"/agents/{name}")
        if status == 404:
            logger.info("Foundry agent '%s' was already gone", name)
            return False
        if status >= 400:
            raise FoundryError(f"Foundry refused to delete '{name}' ({status}): {self._problem(status, body)}")
        logger.info("Deleted agent '%s' from Foundry", name)
        return True
