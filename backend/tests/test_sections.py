"""Mapping test-plan headings to the 24 standard sections."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.sections import (
    REQUIRED_KEYS,
    clean_heading,
    match_heading,
    sections_from_gold,
    split_sections,
)
from app.runtime.tools.files import docx_to_text


@pytest.mark.parametrize(
    ("heading", "key"),
    [
        ("Section 1 – Test Objectives", "objectives"),
        ("Section 2 – In Scope / Out of Scope", "scope_in"),
        ("Out of scope", "scope_out"),
        ("4.1 Test levels", "test_strategy"),
        ("Section 5 – Test Coverage – Functional", "functional_coverage"),
        ("Section 9 – NFR Testing", "nfr_performance"),
        ("9.2 Reliability and recovery", "nfr_reliability"),
        ("Section 8 – AI and Data Quality Validation", "ai_data_quality"),
        ("Section 11 – Environments and Test Data", "test_data_environment"),
        ("Section 12 – Suspension, Entry and Exit Criteria", "entry_exit_criteria"),
        ("Section 16 – Recommended MVP1 Traceability and Metrics", "traceability_metrics"),
        ("21. End-to-End Scenario", "e2e_scenario"),
        ("MASTER TEST PLAN", None),
    ],
)
def test_match_heading(heading: str, key: str | None) -> None:
    assert match_heading(heading) == key


def test_clean_heading_strips_numbering() -> None:
    assert clean_heading("Section 9 – NFR Testing") == "nfr testing"
    assert clean_heading("**4.1 Test levels:**") == "test levels"


def test_subheadings_stay_in_their_section() -> None:
    plan = "\n".join(
        [
            "# Master Test Plan – Demo",
            "## 6. Test Coverage – Functional",
            "### 6.5 Worksheet and approval",  # 'approval' must not start the Approvals section
            "Claims above USD 50,000 need a Finance Manager.",
            "## 10. Performance and Scalability",
            "Supplier-year within 2 minutes.",
            "### 10.1 Reliability",  # NFR siblings may start as sub-headings
            "Re-runs are identical.",
        ]
    )
    sections = split_sections(plan)
    assert "USD 50,000" in sections["functional_coverage"]
    assert "approvals" not in sections
    assert "Re-runs" in sections["nfr_reliability"]
    assert sections["document_control"] == "Master Test Plan – Demo"


def test_reference_docx_splits_like_the_real_plans(data_root: Path) -> None:
    text = docx_to_text(data_root / "raw/validation/P06/P06_Demo_TestPlan.docx")
    sections = split_sections(text)
    assert set(sections) == {
        "document_control",
        "objectives",
        "scope_in",
        "scope_out",
        "nfr_performance",
        "nfr_reliability",
    }
    assert "Supplier portal submission" in sections["scope_out"]


def test_gold_json_uses_present_sections_only(data_root: Path) -> None:
    sections = sections_from_gold(data_root / "gold/validation/P06/gold_testplan.json")
    assert sections == {"objectives": "Verify tiers."}


def test_twenty_required_sections() -> None:
    assert len(REQUIRED_KEYS) == 20


def test_reference_title_block_and_unnamed_first_section() -> None:
    """Learned from P03's reference: 'Test Strategy & Plan' is the title, section 1 is the objectives."""
    reference = "\n".join(
        [
            "**Test Strategy & Plan**",
            "**Contract Intelligence**",
            "Version: 1.0",
            "## 1. Contract Extraction and RAG Scoring Validation",
            "- Verify extraction of metadata and clauses with page references.",
            "## 3. Quality Risks, Assumptions and Dependencies",
            "- SBU/customer mappings seeded before testing.",
            "## 4. Approach",
            "Unit testing with 85% coverage.",
            "## 14. Risks and Mitigations",
            "Poor scan quality: OCR tests.",
        ]
    )
    sections = split_sections(reference)
    assert "Version: 1.0" in sections["document_control"]
    assert "page references" in sections["objectives"]
    assert "mappings seeded" in sections["assumptions_dependencies"]
    assert "85% coverage" in sections["test_strategy"] and "Version" not in sections["test_strategy"]
    assert sections["risks"].startswith("14. Risks")
