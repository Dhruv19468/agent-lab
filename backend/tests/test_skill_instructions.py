"""How skills reach the model (needs SQLAlchemy for the Skill model; no database)."""

from __future__ import annotations

from app.models import Skill
from app.modules.agents.skill_instructions import (
    build_skill_index,
    inject_skills,
    select_skills_for_message,
)


def make(name: str, phrases: list[str]) -> Skill:
    return Skill(
        name=name, description=f"{name} description", instructions=f"{name} steps", trigger_phrases=phrases
    )


def test_one_skill_is_always_selected() -> None:
    plan = make("BRD to Test Plan", ["test plan"])
    assert select_skills_for_message([plan], "hello") == [plan]


def test_trigger_phrases_pick_skills() -> None:
    plan, summary = make("Plan", ["test plan"]), make("Summary", ["summarise"])
    assert select_skills_for_message([plan, summary], "Write the TEST PLAN for P06") == [plan]
    assert select_skills_for_message([plan, summary], "hello") == []


def test_index_and_injection() -> None:
    plan = make("Plan", ["test plan"])
    index = build_skill_index([plan])
    assert "## Plan" in index and "Trigger phrases: test plan" in index and "Plan steps" not in index
    message = inject_skills([plan], "P06 please")
    assert message.startswith("## Active skill: Plan") and message.endswith("## User message\n\nP06 please")
