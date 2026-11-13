from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentConfiguration(Base):
    """How one agent calls the model. Exactly one row per agent (1-to-1 with agents).

    Blank (NULL) values mean "use the platform default" from Settings at run time.
    """

    __tablename__ = "agent_configurations"
    __table_args__ = (
        CheckConstraint(
            "temperature IS NULL OR (temperature >= 0 AND temperature <= 2)",
            name="ck_agent_configurations_temperature_range",
        ),
        CheckConstraint(
            "max_tokens IS NULL OR max_tokens > 0",
            name="ck_agent_configurations_max_tokens_positive",
        ),
        CheckConstraint(
            "max_tool_rounds > 0",
            name="ck_agent_configurations_max_tool_rounds_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique configuration identifier.",
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="The agent this configuration belongs to (one configuration per agent).",
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Azure OpenAI deployment name. NULL = AZURE_OPENAI_DEPLOYMENT from Settings.",
    )
    temperature: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Sampling temperature 0-2. NULL = the model's default.",
    )
    max_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Most tokens one model reply may contain. NULL = the model's default.",
    )
    max_tool_rounds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="10",
        comment="Most model -> tool -> model rounds in one run before it is stopped.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the configuration was created.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When the configuration was last changed.",
    )

    def __repr__(self) -> str:
        return (
            f"AgentConfiguration(agent_id={self.agent_id!r}, model={self.model!r}, "
            f"temperature={self.temperature!r})"
        )