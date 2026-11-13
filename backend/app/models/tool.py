from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tool(Base):
    """A function an agent may call during a run.

    The LLM never runs code itself. It sees each tool's name, description and parameter
    schema, and replies "call read_file with {path: ...}". The backend then runs the
    matching Python function and sends the result back to the LLM.
    """

    __tablename__ = "tools"
    __table_args__ = (
        UniqueConstraint("name", name="uq_tools_name"),
        # OpenAI function names: letters, digits, _ and -, at most 64 characters.
        CheckConstraint("name ~ '^[a-zA-Z0-9_-]{1,64}$'", name="ck_tools_name_format"),
        CheckConstraint("tool_type IN ('builtin', 'http')", name="ck_tools_tool_type_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique tool identifier.",
    )
    name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Function name the LLM calls, e.g. read_file. Unique.",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="What the tool does and when to use it. The LLM reads this to decide when to call it.",
    )
    tool_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="builtin",
        comment="builtin = a Python function in this backend; http = an external HTTP endpoint (later).",
    )
    parameters: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="JSON Schema of the tool's arguments, sent to the LLM as the function's parameters.",
    )
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Extra settings for running the tool, e.g. a base folder or (for http) a URL.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the tool was created.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When the tool was last changed.",
    )

    def __repr__(self) -> str:
        return f"Tool(id={self.id!r}, name={self.name!r}, tool_type={self.tool_type!r})"