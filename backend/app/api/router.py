from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path

from fastapi import APIRouter

from app.modules.health.router import router as health_router

logger = logging.getLogger("platform.startup")
api_router = APIRouter()
api_router.include_router(health_router)


def _include_overlay_modules(router: APIRouter) -> None:
    """Mount every app/modules/<name>/router.py that defines a `router` object."""
    modules_dir = Path(__file__).resolve().parents[1] / "modules"

    for module_path in sorted(modules_dir.iterdir()):
        if not module_path.is_dir() or module_path.name.startswith("__") or module_path.name == "health":
            continue

        router_module = f"app.modules.{module_path.name}.router"
        try:
            module = import_module(router_module)
        except ModuleNotFoundError as error:
            if error.name != router_module:
                logger.exception(
                    "Could not import API module %s because dependency %s is missing",
                    module_path.name,
                    error.name,
                )
            continue

        child_router = getattr(module, "router", None)
        if isinstance(child_router, APIRouter):
            router.include_router(child_router)


_include_overlay_modules(api_router)