"""Markdown -> Word / Excel / PDF / tidy Markdown, laid out like the reference test plans."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook

from app.runtime.exporters import build_document, export, inline_spans, parse_markdown
from app.runtime.tools.files import ToolError, create_document

PLAN = """# Master Test Plan – Rebate Claim Validation

## Document Control
Version: 0.1
Test phase: MVP1

## References
P06_Rebate_Validation_BRD.docx

## 1. Test Objectives
- Verify **≥95%** extraction accuracy.
  - Including amendments.

## 5. Test Strategy
### 5.1 Test levels
1. Unit testing

## 7. Roles & Permissions
| Role | Can | Cannot |
|---|---|---|
| Rebate Analyst | Upload | Approve own claims |
"""


def test_parse_markdown_blocks() -> None:
    kinds = [(block.kind, block.level) for block in parse_markdown(PLAN)]
    assert ("bullet", 1) in kinds and ("number", 0) in kinds
    table = next(block for block in parse_markdown(PLAN) if block.kind == "table")
    assert table.rows == [["Role", "Can", "Cannot"], ["Rebate Analyst", "Upload", "Approve own claims"]]


def test_inline_spans() -> None:
    spans = inline_spans("Verify **≥95%** of *golden* `terms`")
    assert [(s.text, s.bold, s.italic) for s in spans] == [
        ("Verify ", False, False),
        ("≥95%", True, False),
        (" of ", False, False),
        ("golden", False, True),
        (" ", False, False),
        ("terms", False, False),
    ]


def test_reference_layout() -> None:
    doc = build_document(PLAN)
    assert (doc.title, doc.subtitle) == ("MASTER TEST PLAN", "Rebate Claim Validation")
    assert [section.heading for section in doc.sections] == [
        "Section 1 – Test Objectives",
        "Section 5 – Test Strategy",
        "Section 7 – Roles & Permissions",
    ]
    assert [block.text for block in doc.front] == ["Version: 0.1", "Test phase: MVP1"]
    assert doc.sections[1].blocks[0].text == "5.1 Test levels"  # the plan's own numbers are kept


def test_other_documents_keep_their_headings() -> None:
    doc = build_document("# Release notes\n\n## Changes\n- a\n\n## Fixes\n- b")
    assert not doc.test_plan and doc.title == "Release notes"
    assert [section.heading for section in doc.sections] == ["Changes", "Fixes"]


def test_word() -> None:
    document = Document(io.BytesIO(export(PLAN, "docx")))
    paragraphs = [(p.style.name, p.text) for p in document.paragraphs if p.text]
    assert paragraphs[0] == ("Normal", "MASTER TEST PLAN")
    assert ("Heading 1", "Section 1 – Test Objectives") in paragraphs
    assert ("Heading 2", "5.1 Test levels") in paragraphs
    assert ("List Bullet 2", "Including amendments.") in paragraphs
    assert document.tables[0].cell(1, 2).text == "Approve own claims"


def test_excel() -> None:
    workbook = load_workbook(io.BytesIO(export(PLAN, "xlsx")))
    assert workbook.sheetnames == ["Test Plan", "Document Control", "7. Roles & Permissions"]
    rows = list(workbook["Test Plan"].iter_rows(values_only=True))
    assert rows[0] == ("No.", "Section", "Content")
    assert rows[1][1] == "Test Objectives" and "• Verify ≥95% extraction accuracy." in rows[1][2]
    assert ("Version", "0.1") in list(workbook["Document Control"].iter_rows(values_only=True))
    assert list(workbook["7. Roles & Permissions"].iter_rows(values_only=True))[1][0] == "Rebate Analyst"


def test_pdf_and_markdown() -> None:
    assert export(PLAN, "pdf").startswith(b"%PDF")
    tidy = export(PLAN, "md").decode()
    assert "## Section 7 – Roles & Permissions" in tidy
    assert "| Rebate Analyst | Upload | Approve own claims |" in tidy
    assert export(tidy, "md").decode() == tidy  # stable: exporting twice changes nothing


def test_unknown_format() -> None:
    with pytest.raises(ValueError, match="Unknown format"):
        export(PLAN, "pptx")


@pytest.mark.parametrize("name", ["P06_test_plan.docx", "P06_test_plan.xlsx", "P06_test_plan.pdf", "P06_test_plan.md"])
def test_create_document_in_every_format(tmp_path: Path, name: str) -> None:
    saved = create_document(tmp_path, name, PLAN)
    assert saved["path"] == f"agent-output/{name}" and (tmp_path / saved["path"]).stat().st_size > 0


def test_create_document_rejects_other_formats(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="can be saved as"):
        create_document(tmp_path, "plan.pptx", PLAN)


def test_own_section_numbers_and_colon_title() -> None:
    plan = "Internal Use Only | Confidential\n\n# Test Plan: Contract Intelligence\n\n## 1. Document Control\nStatus: Draft\n\n## 2. Introduction and Objectives\nText.\n\n## 21. Assumptions, BRD Observations and Open Items\nSee section 21."
    doc = build_document(plan)
    assert doc.subtitle == "Contract Intelligence"
    assert [section.heading for section in doc.sections] == [
        "Section 2 – Introduction and Objectives",
        "Section 21 – Assumptions, BRD Observations and Open Items",
    ]
