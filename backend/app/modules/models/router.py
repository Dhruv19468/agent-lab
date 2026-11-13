"""GET /api/models: the model deployments the dropdowns offer."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.schemas import ApiModel
from app.integrations.foundry import FoundryClient, FoundryError

router = APIRouter(prefix="/models", tags=["models"])
logger = logging.getLogger("platform.models")


class ModelList(ApiModel):
    default: str | None  # AZURE_OPENAI_DEPLOYMENT: used when an agent has no model chosen
    models: list[str]
    foundry_enabled: bool
    foundry_error: str | None = None  # why the Foundry list couldn't be read (the dropdown still works)


@router.get("", response_model=ModelList)
async def list_models() -> ModelList:
    """The project's chat deployments from Foundry (when configured) plus the ones in .env."""
    settings = get_settings()
    models = list(settings.configured_deployments)
    problem = None
    if settings.foundry_enabled:
        try:
            models += await FoundryClient(settings).list_deployments()
        except FoundryError as error:
            logger.warning("Could not list Foundry deployments: %s", error.message)
            problem = error.message
    return ModelList(
        default=settings.azure_openai_deployment or None,
        models=list(dict.fromkeys(models)),
        foundry_enabled=settings.foundry_enabled,
        foundry_error=problem,
    )
