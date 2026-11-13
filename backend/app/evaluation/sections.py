"""Split a test plan into the 24 standard sections, whatever the headings are called.

Both sides of the comparison go through this module:
  - the agent's plan (Markdown: '## 3. Test Assumptions', '**Out of scope**'),
  - the human reference plan (Word: 'Section 3 – Test Assumptions', converted to Markdown by
    the same docx_to_text the agent's read_file uses).

A heading is mapped to a section key by keyword rules (first rule that matches wins). Text
under a heading that matches nothing stays in the section above it, so '5.1 Agreement
extraction' remains part of functional coverage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# The 24 sections of templates/test_plan_schema.json, in order. True = required.
SECTIONS: dict[str, tuple[str, bool]] = {
    "document_control": ("Document control", True),
    "references": ("References", False),
    "objectives": ("Test objectives", True),
    "scope_in": ("In scope", True),
    "scope_out": ("Out of scope", True),
    "assumptions_dependencies": ("Assumptions and dependencies", True),
    "test_strategy": ("Test strategy", True),
    "functional_coverage": ("Functional test coverage", True),
    "rbac_testing": ("Roles and permissions", True),
    "security_compliance": ("Security, privacy and compliance", True),
    "ai_data_quality": ("AI and data quality validation", True),
    "nfr_performance": ("Performance and scalability", True),
    "nfr_reliability": ("Reliability and recovery", True),
    "nfr_accessibility_compat": ("Accessibility and compatibility", True),
    "observability_audit": ("Logging, monitoring and audit", True),
    "test_data_environment": ("Test data and environments", True),
    "entry_exit_criteria": ("Entry and exit criteria", True),
    "defect_management": ("Defect management", True),
    "risks": ("Risks and mitigations", True),
    "deliverables_reporting": ("Deliverables and reporting", False),
    "traceability_metrics": ("Traceability and metrics", True),
    "schedule": ("Schedule", False),
    "e2e_scenario": ("End-to-end scenario", True),
    "approvals": ("Approvals", False),
}
REQUIRED_KEYS = [key for key, (_, required) in SECTIONS.items() if required]

# (key, pattern). Order matters: specific rules before general ones.
RULES: list[tuple[str, str]] = [
    ("e2e_scenario", r"end[- ]to[- ]end|\be2e\b"),
    ("traceability_metrics", r"traceab|\brtm\b"),
    ("entry_exit_criteria", r"entry|exit criteria|suspension"),
    ("defect_management", r"defect|\bbug"),
    ("assumptions_dependencies", r"assumption"),  # "Quality Risks, Assumptions and Dependencies" is about assumptions
    ("risks", r"\brisk"),
    ("deliverables_reporting", r"deliverable|reporting"),
    ("schedule", r"timeline|schedule|milestone"),
    ("approvals", r"approval|sign[- ]?off"),
    ("nfr_accessibility_compat", r"accessib|compatib|browser"),
    ("nfr_reliability", r"reliab|recovery|availability|resilien|disaster"),
    ("nfr_performance", r"performance|scalab|non[- ]functional|\bnfr|\bload\b"),
    ("observability_audit", r"logging|monitoring|observab|audit"),
    ("security_compliance", r"security|privacy|compliance"),
    ("ai_data_quality", r"\bai\b|data quality|\bmodel\b|\bml\b"),
    ("rbac_testing", r"\broles?\b|permission|rbac|access control"),
    ("test_data_environment", r"environment|test data"),
    ("functional_coverage", r"functional|coverage|feature"),
    ("test_strategy", r"strategy|approach|levels? of testing|test levels|technique"),
    ("assumptions_dependencies", r"assumption|dependenc|constraint"),
    ("scope_in", r"\bin[- ]scope"),
    ("scope_out", r"out[- ]of[- ]scope|exclusion|not in scope"),
    ("scope_in", r"\bscope\b"),
    ("objectives", r"objective|purpose|goal"),
    ("references", r"reference"),
    ("document_control", r"document control|revision|version history|document history"),
]
# A sub-heading (deeper than the current section's heading) may only start one of these;
# any other sub-heading stays inside its parent ('5.5 Worksheet and approval' is functional).
SUBSECTION_KEYS = {"scope_in", "scope_out", "nfr_performance", "nfr_reliability", "nfr_accessibility_compat", "e2e_scenario"}
BOLD_LEVEL = 9  # a bold line ('**Out of scope**') is the weakest kind of heading

_NUMBERING = re.compile(r"^(section\s+)?[\dA-Za-z]{0,3}(\.\d+)*[.)]?\s*[–—:-]?\s*", re.IGNORECASE)
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BOLD_LINE = re.compile(r"^\*\*(.+?)\*\*:?\s*$|^__(.+?)__:?\s*$")


def clean_heading(text: str) -> str:
    """'Section 9 – NFR Testing' -> 'nfr testing'; '4.1 Test levels' -> 'test levels'."""
    text = text.strip().strip("*_ ").rstrip(":")
    if re.match(r"^(section\s+\d+|\d+(\.\d+)*[.)]?)\s", text, re.IGNORECASE):
        text = _NUMBERING.sub("", text, count=1)
    return text.strip().lower()


def match_heading(text: str) -> str | None:
    cleaned = clean_heading(text)
    for key, pattern in RULES:
        if re.search(pattern, cleaned):
            return key
    return None


@dataclass
class _Line:
    heading_level: int | None  # None = body text
    text: str


def _parse(markdown: str) -> list[_Line]:
    lines = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        heading = _MD_HEADING.match(line)
        if heading:
            lines.append(_Line(len(heading.group(1)), heading.group(2)))
            continue
        bold = _BOLD_LINE.match(line.strip())
        if bold and len(line) <= 120:
            lines.append(_Line(BOLD_LEVEL, bold.group(1) or bold.group(2)))
            continue
        lines.append(_Line(None, line))
    return lines


_TITLE_WORDS = re.compile(r"\b(test\s+)?plan\b|\bstrategy\s*(&|and)\s*plan\b", re.IGNORECASE)
_FIRST_SECTION = re.compile(r"^\s*(section\s+)?1(\.0)?[.)]?\s", re.IGNORECASE)


def split_sections(markdown: str) -> dict[str, str]:
    """Section key -> its text (headings included). Text before the first match = document control.

    Two rules for the title block, learned from the reference plans:
    - a heading before any section that names the document ("Master Test Plan", "Test Strategy &
      Plan") is the title, not the Test strategy section;
    - an unnamed first numbered section ("1. Contract Extraction and RAG Scoring Validation")
      is the objectives.
    """
    collected: dict[str, list[str]] = {}
    current_key = "document_control"
    current_level = 0  # the title block: any heading may start a new section
    started = False  # has any real section begun?
    for line in _parse(markdown):
        if line.heading_level is not None:
            if not started and _TITLE_WORDS.search(clean_heading(line.text)):
                key = None  # the document's title
            else:
                key = match_heading(line.text)
                if key is None and not started and _FIRST_SECTION.match(line.text.strip("*_ ")):
                    key = "objectives"
            deeper = current_key != "document_control" and line.heading_level > current_level
            if key and key != current_key and (not deeper or key in SUBSECTION_KEYS):
                current_key = key
                current_level = line.heading_level
                started = started or key not in {"document_control", "references"}
            elif key == current_key and line.heading_level < current_level:
                current_level = line.heading_level
            collected.setdefault(current_key, []).append(line.text)
            continue
        if line.text.strip():
            collected.setdefault(current_key, []).append(line.text)
    return {key: "\n".join(lines).strip() for key, lines in collected.items() if "\n".join(lines).strip()}


def sections_from_gold(source: Path | str) -> dict[str, str]:
    """gold_testplan.json (a file path, or its JSON text) -> section key -> text (sections marked present)."""
    text = source.read_text(encoding="utf-8") if isinstance(source, Path) else source
    data = json.loads(text)
    sections: dict[str, str] = {}
    for key, value in (data.get("sections") or {}).items():
        if isinstance(value, dict) and value.get("present") and (value.get("text") or "").strip():
            sections[key] = value["text"].strip()
    return sections
