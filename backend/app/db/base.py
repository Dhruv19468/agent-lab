from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Parent class of every table model. Alembic reads Base.metadata to know all tables."""