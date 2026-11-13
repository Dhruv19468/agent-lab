"""Shared test fixtures. The tests need no database, no network and no Azure account.

`data_root` builds a tiny copy of the real dataset layout in a temp folder:

    raw/validation/P06/P06_Demo_BRD.docx            (bold 'Normal' headings, like the real BRDs)
    raw/validation/P06/P06_Demo_Architecture.png
    raw/validation/P06/P06_Demo_TestPlan.docx       (Heading 1 sections, like the real plans)
    gold/validation/P06/gold_testplan.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from docx import Document

# Settings are read from the environment; make sure no developer .env value leaks into tests.
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT", "")

# A real 1x1 PNG.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082"
)

BRD_SECTIONS = [
    ("Section 1 – Purpose", ["Rebate Claim Validation calculates supplier rebates."]),
    (
        "Section 7 – Functional Requirements",
        ["1. MVP1: Upload of agreement PDFs.", "2. MVP2 – Dispute tracking."],
    ),
    (
        "Section 8 – Quality Attributes",
        ["1. Performance: Calculation for one supplier-year within 2 minutes."],
    ),
    ("Section 10 – Data Requirements", ["RBAC – Approval above USD 50,000 by Finance Manager."]),
]

PLAN_SECTIONS = [
    ("Section 1 – Test Objectives", ["Verify extraction of tiers with page references."]),
    ("Section 2 – In Scope / Out of Scope", ["In scope: agreement upload and calculation."]),
    ("Section 9 – NFR Testing", []),
    ("9.1 Performance and scalability", ["Supplier-year calculation within 2 minutes."]),
    ("9.2 Reliability and recovery", ["Re-run with the same snapshot gives identical results."]),
]


def make_brd(path: Path) -> None:
    document = Document()
    title = document.add_paragraph()
    title.add_run("Business Requirement Specification – Demo").bold = True
    document.add_paragraph("Version: 1.0")
    for heading, lines in BRD_SECTIONS:
        paragraph = document.add_paragraph()
        paragraph.add_run(heading).bold = True
        for line in lines:
            document.add_paragraph(line)
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Role", "Rights"
    table.cell(1, 0).text, table.cell(1, 1).text = "Finance Manager", "Approve claims"
    document.save(str(path))


def make_reference_plan(path: Path) -> None:
    document = Document()
    title = document.add_paragraph()
    title.add_run("MASTER TEST PLAN").bold = True
    for heading, lines in PLAN_SECTIONS:
        document.add_heading(heading, level=2 if heading[0].isdigit() else 1)
        for line in lines:
            document.add_paragraph(line)
    out = document.add_paragraph()
    out.add_run("Out of scope:").bold = True
    document.add_paragraph("Supplier portal submission (MVP2).", style="List Bullet")
    document.save(str(path))


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    project = tmp_path / "raw" / "validation" / "P06"
    project.mkdir(parents=True)
    make_brd(project / "P06_Demo_BRD.docx")
    (project / "P06_Demo_Architecture.png").write_bytes(PNG_BYTES)
    make_reference_plan(project / "P06_Demo_TestPlan.docx")

    gold = tmp_path / "gold" / "validation" / "P06"
    gold.mkdir(parents=True)
    (gold / "gold_testplan.json").write_text(
        json.dumps(
            {
                "project": "P06",
                "sections": {
                    "objectives": {
                        "present": True,
                        "source_headings": ["Test Objectives"],
                        "text": "Verify tiers.",
                    },
                    "approvals": {"present": False, "source_headings": [], "text": ""},
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "processed").mkdir()
    return tmp_path.resolve()
