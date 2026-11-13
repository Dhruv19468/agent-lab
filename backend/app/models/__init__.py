"""Import every model here so Base.metadata (and therefore Alembic) knows all tables."""

from app.models.agent import Agent
from app.models.agent_configuration import AgentConfiguration
from app.models.agent_run import AgentRun
from app.models.agent_skill import AgentSkill
from app.models.agent_tool import AgentTool
from app.models.evaluation import Evaluation
from app.models.skill import Skill, SkillTool
from app.models.tool import Tool

__all__ = [
    "Agent",
    "AgentConfiguration",
    "AgentRun",
    "AgentSkill",
    "AgentTool",
    "Evaluation",
    "Skill",
    "SkillTool",
    "Tool",
]
