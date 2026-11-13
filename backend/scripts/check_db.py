"""Step 1 check: can the app's own session code reach PostgreSQL?

Run from the backend/ folder:
    uv run python scripts/check_db.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make `import app...` work when running a file from scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402


async def main() -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            text("select current_database(), current_user, current_setting('search_path')")
        )
        database, user, search_path = result.one()

    print(f"Connected to : {database} as {user}")
    print(f"search_path  : {search_path}")

    # Close the pool's connections cleanly before the event loop ends.
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())