"""Turns an agent's skills into what the LLM receives. Adapted from Wesco's skill_instructions.py.

Agents have no hand-written system prompt. Skills reach the model in two places:

1. At publish (`build_skill_index`): the agent's instructions become a short index of its
   skills (name, description, trigger phrases), saved in agents.published_instructions and
   sent as the system message on every run.
2. Per message (`select_skills_for_message` + `inject_skills`): skills whose trigger phrase
   appears in the message have their full instructions put in front of that one message.
   An agent with exactly one skill always gets it, phrase or not.
"""

from __future__ import annotations

from app.models import Skill

SKILL_INDEX_PREAMBLE = (
    "You are an AI agent whose behaviour comes entirely from the skills below; there is "
    "no separate system prompt. Each skill describes when to use it and how. When the "
    "user's message matches one, its full instructions are provided ahead of the message; "
    "follow those precisely. If none were provided for this message, use the descriptions "
    "below to judge whether one of these skills still applies, or ask a clarifying question "
    "if it is genuinely ambiguous."
)


def build_skill_index(skills: list[Skill]) -> str:
    """The agent's published instructions: one short entry per skill, not the full text."""
    sections = [SKILL_INDEX_PREAMBLE]
    for skill in skills:
        lines = [f"## {skill.name}", skill.description or "(no description)"]
        phrases = ", ".join(skill.trigger_phrases or [])
        if phrases:
            lines.append(f"Trigger phrases: {phrases}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def match_skills(skills: list[Skill], message: str) -> list[Skill]:
    """Skills with a trigger phrase contained in the message (case-insensitive)."""
    lowered = message.lower()
    return [
        skill
        for skill in skills
        if any(phrase and phrase.lower() in lowered for phrase in (skill.trigger_phrases or []))
    ]


def select_skills_for_message(skills: list[Skill], message: str) -> list[Skill]:
    """The skills whose full instructions go with this message."""
    if len(skills) == 1:
        return skills  # one skill: always send it, so "run this" just works
    return match_skills(skills, message)


def inject_skills(selected: list[Skill], message: str) -> str:
    """Put each selected skill's full instructions in front of the message, for this turn only."""
    if not selected:
        return message
    sections = [f"## Active skill: {skill.name}\n\n{skill.instructions}" for skill in selected]
    sections.append(f"## User message\n\n{message}")
    return "\n\n---\n\n".join(sections)
