from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Skill(Base):
    """A reusable, named procedure an agent can be given.

    Agents have no hand-written system prompt: their behaviour comes from their skills.
    At publish, the agent's instructions become a short index of its skills (name,
    description, trigger phrases). Per message, a skill whose trigger phrase appears in
    the text has its full `instructions` sent along for that turn only.
    """

    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("name", name="uq_skills_name"),
        CheckConstraint("name <> ''", name="ck_skills_name_not_empty"),
        CheckConstraint("instructions <> ''", name="ck_skills_instructions_not_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique skill identifier.",
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Human-readable, unique skill name.",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="One or two sentences: what the skill produces and from what. Shown in the skill index.",
    )
    instructions: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The full procedure in Markdown (the SKILL.md text). Sent only on a matching message.",
    )
    trigger_phrases: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment='Short phrases that select this skill, e.g. ["test plan", "generate test plan"].',
    )
    created_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Who created the skill.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the skill was created.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When the skill was last changed.",
    )

    def __repr__(self) -> str:
        return f"Skill(id={self.id!r}, name={self.name!r})"


class SkillTool(Base):
    """A tool this skill is built around.

    Attaching the skill to an agent attaches these tools too, and they can't be
    detached while the skill stays attached: the skill's instructions call them.
    """

    __tablename__ = "skill_tools"
    __table_args__ = (
        UniqueConstraint("skill_id", "tool_id", name="uq_skill_tools_skill_id_tool_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        comment="Skill that requires the tool.",
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
        comment="Tool the skill's instructions call.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"SkillTool(skill_id={self.skill_id!r}, tool_id={self.tool_id!r})"