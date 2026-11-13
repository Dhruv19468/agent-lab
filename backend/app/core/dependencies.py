"""Shared FastAPI dependencies. Routes declare what they need; FastAPI provides it per request."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session

# A route parameter typed `session: DbSession` gets one database session per request,
# closed automatically when the request ends.
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
