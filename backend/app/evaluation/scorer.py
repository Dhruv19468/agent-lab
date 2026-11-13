"""Scores one generated test plan against the project's reference plan and its BRD.

    overall = (0.25 * structure + 0.45 * coverage + 0.30 * similarity) * faithfulness

  structure     share of the 20 required sections the plan has           (code, no LLM)
  coverage      share of the reference plan's checkable points it covers (LLM, quote-verified)
  similarity    word-overlap F1 with the reference, section by section    (code, no LLM)
  faithfulness  share of its project-specific claims the BRD/diagram back (LLM, quote-verified)

Faithfulness multiplies everything: a plan that invents facts loses points everywhere.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.evaluation import judge as judging
from app.evaluation.sections import REQUIRED_KEYS, SECTIONS, sections_from_gold, split_sections
from app.evaluation.text import overlap_f1
from app.runtime.dataset import ProjectFiles
from app.runtime.storage import Storage, as_storage
from app.runtime.tools.files import IMAGE_TYPES, docx_to_text

WEIGHTS = {"structure": 0.25, "coverage": 0.45, "similarity": 0.30}
MIN_SECTION_CHARS = 40  # a heading with (almost) nothing under it doesn't count as a section


class ReferenceMissingError(Exception):
    pass


@dataclass
class ScoreResult:
    structure: float
    coverage: float
    similarity: float
    faithfulness: float
    overall: float
    details: dict[str, Any] = field(default_factory=dict)


def load_reference(root: Storage | Path, project: ProjectFiles) -> tuple[dict[str, str], str]:
    """(section key -> text, 'gold' | 'testplan'). gold_testplan.json wins when it exists."""
    store = as_storage(root)
    if project.gold is not None:
        sections = sections_from_gold(store.read_bytes(project.gold).decode("utf-8"))
        if sections:
            return sections, "gold"
    if project.reference_testplan is not None:
        return split_sections(docx_to_text(store.read_bytes(project.reference_testplan))), "testplan"
    raise ReferenceMissingError(
        f"{project.project} has no reference test plan (no *TestPlan.docx in {project.folder}, no gold json)."
    )


def load_sources(root: Storage | Path, project: ProjectFiles) -> tuple[str, list[str]]:
    """The BRD as text and the diagrams as data URLs: what the agent itself was given."""
    store = as_storage(root)
    if project.brd is None:
        raise ReferenceMissingError(f"{project.project} has no BRD .docx in {project.folder}.")
    brd_text = docx_to_text(store.read_bytes(project.brd))
    diagrams = []
    for relative in project.diagrams:
        media = IMAGE_TYPES.get(Path(relative).suffix.lower())
        if media and store.size(relative) <= 8 * 1024 * 1024:
            data = store.read_bytes(relative)
            diagrams.append(f"data:{media};base64,{base64.b64encode(data).decode('ascii')}")
    return brd_text, diagrams


def score_structure(candidate_sections: dict[str, str]) -> tuple[float, dict[str, bool]]:
    present = {key: len(candidate_sections.get(key, "")) >= MIN_SECTION_CHARS for key in SECTIONS}
    required_present = sum(present[key] for key in REQUIRED_KEYS)
    return required_present / len(REQUIRED_KEYS), present


def score_similarity(
    candidate_sections: dict[str, str], reference: dict[str, str]
) -> tuple[float, dict[str, float]]:
    per_section = {
        key: round(overlap_f1(candidate_sections.get(key, ""), text), 4) for key, text in reference.items()
    }
    return (sum(per_section.values()) / len(per_section) if per_section else 0.0), per_section


def combine(structure: float, coverage: float, similarity: float, faithfulness: float) -> float:
    weighted = (
        WEIGHTS["structure"] * structure + WEIGHTS["coverage"] * coverage + WEIGHTS["similarity"] * similarity
    )
    return weighted * faithfulness


async def score_plan(
    *,
    judge: judging.Judge,
    project: str,
    candidate: str,
    reference: dict[str, str],
    brd_text: str,
    diagrams: list[str],
    cache_dir: Storage | Path | None,
    cache_prefix: str = "",
) -> ScoreResult:
    candidate_sections = split_sections(candidate)

    structure, present = score_structure(candidate_sections)
    similarity, similarity_by_section = score_similarity(candidate_sections, reference)

    points = await judging.extract_points(judge, project, reference, cache_dir, cache_prefix)
    checked = await judging.check_coverage(judge, points, candidate)
    coverage = sum(item["covered"] for item in checked) / len(checked) if checked else 0.0

    claims = await judging.check_faithfulness(judge, brd_text, candidate, diagrams)
    supported = sum(claim["support"] != "none" for claim in claims)
    faithfulness = supported / len(claims) if claims else 1.0

    coverage_by_section: dict[str, dict[str, int]] = {}
    for item in checked:
        counts = coverage_by_section.setdefault(item["section"], {"covered": 0, "total": 0})
        counts["total"] += 1
        counts["covered"] += int(item["covered"])

    sections_table = [
        {
            "key": key,
            "title": title,
            "required": required,
            "inPlan": present[key],
            "inReference": key in reference,
            "similarity": similarity_by_section.get(key),
            "covered": coverage_by_section.get(key, {}).get("covered"),
            "points": coverage_by_section.get(key, {}).get("total"),
        }
        for key, (title, required) in SECTIONS.items()
    ]
    return ScoreResult(
        structure=round(structure, 4),
        coverage=round(coverage, 4),
        similarity=round(similarity, 4),
        faithfulness=round(faithfulness, 4),
        overall=round(combine(structure, coverage, similarity, faithfulness), 4),
        details={
            "weights": WEIGHTS,
            "sections": sections_table,
            "missingRequired": [key for key in REQUIRED_KEYS if not present[key]],
            "points": checked,
            "claims": claims,
            "counts": {
                "points": len(checked),
                "covered": sum(item["covered"] for item in checked),
                "claims": len(claims),
                "supported": supported,
            },
        },
    )
