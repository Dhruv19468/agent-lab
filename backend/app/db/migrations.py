from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)


def run_alembic_upgrade_head() -> None:
    """Run Alembic migrations up to head (same as `alembic upgrade head` in the terminal)."""
    # cwd, not __file__: inside the Docker image the app is installed into site-packages,
    # but both the image (WORKDIR /app) and local dev (run from backend/) start in the
    # folder that holds alembic.ini and alembic/.
    repo_root = Path.cwd()
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "alembic"))
    # Keep the app's own logging; alembic/env.py checks this flag before calling fileConfig.
    config.attributes["configure_logger"] = False

    logger.info("Running Alembic migrations to head (script_location=%s)", repo_root / "alembic")
    started_at = perf_counter()
    try:
        command.upgrade(config, "head")
    except Exception:
        logger.exception("Alembic migrations failed")
        raise
    logger.info("Alembic migrations complete in %d ms", int((perf_counter() - started_at) * 1000))