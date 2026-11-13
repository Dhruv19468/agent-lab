from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentTool(Base):
    """Which tools an agent may call.

    `source` records why a tool is attached:
    - 'skill'  : it came with a skill (via skill_tools). It is removed again when no attached
                 skill needs it any more, and can't be detached by hand while one does.
    - 'manual' : someone attached it directly. It stays until someone detaches it.
    """

    __tablename__ = "agent_tools"
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_agent_tools_agent_id_tool_id"),
        CheckConstraint("source IN ('manual', 'skill')", name="ck_agent_tools_source_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique agent-tool attachment identifier.",
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        comment="Agent the tool is attached to.",
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tool attached to the agent.",
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="manual",
        comment="Why the tool is attached: 'manual' (by hand) or 'skill' (required by an attached skill).",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Who attached the tool.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the tool was attached.",
    )

    def __repr__(self) -> str:
        return f"AgentTool(agent_id={self.agent_id!r}, tool_id={self.tool_id!r}, source={self.source!r})"