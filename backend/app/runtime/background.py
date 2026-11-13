"""Run slow work (agent runs, evaluations) after the HTTP request has answered.

A test-plan run takes one to three minutes, longer than browsers, nginx and Azure Container
Apps (240 s) like to keep a request open. So POST /runs answers at once with status
"running", the work continues here, and the caller polls GET /runs/{id}.

The tasks live in this process only. If the container restarts mid-run, the startup hook
marks those rows failed (see `fail_interrupted_work` in app/main.py).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger("platform.background")
_tasks: set[asyncio.Task[Any]] = set()


def spawn(work: Coroutine[Any, Any, Any], name: str) -> None:
    task = asyncio.create_task(work, name=name)
    _tasks.add(task)  # keep a reference, or the task can be garbage-collected mid-run

    def _done(finished: asyncio.Task[Any]) -> None:
        _tasks.discard(finished)
        if not finished.cancelled() and finished.exception() is not None:
            logger.error("Background task %s crashed", name, exc_info=finished.exception())

    task.add_done_callback(_done)


def running_count() -> int:
    return len(_tasks)
