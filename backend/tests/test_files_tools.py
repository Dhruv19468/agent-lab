"""The agent's file tools: what they show, and what they refuse."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime.tools.files import ToolError, create_document, list_files, read_file, view_image

BRD = "raw/validation/P06/P06_Demo_BRD.docx"


def test_list_files_hides_gold_and_reference_plans(data_root: Path) -> None:
    top = [entry["name"] for entry in list_files(data_root, "")["entries"]]
    assert "gold" not in top and "raw" in top

    project = [entry["name"] for entry in list_files(data_root, "raw/validation/P06")["entries"]]
    assert project == ["P06_Demo_Architecture.png", "P06_Demo_BRD.docx"]  # no TestPlan


def test_read_docx_keeps_bold_headings_and_tables(data_root: Path) -> None:
    page = read_file(data_root, BRD)
    assert "**Section 1 – Purpose**" in page["text"]
    assert "Version: 1.0" in page["text"]  # plain paragraphs stay plain
    assert "| Finance Manager | Approve claims |" in page["text"]
    assert page["next_offset"] is None and page["total_chars"] == len(page["text"])


def test_read_file_pages_long_text(data_root: Path) -> None:
    (data_root / "processed" / "long.txt").write_text("x" * 25_000, encoding="utf-8")
    first = read_file(data_root, "processed/long.txt")
    assert len(first["text"]) == 20_000 and first["next_offset"] == 20_000
    second = read_file(data_root, "processed/long.txt", offset=first["next_offset"])
    assert len(second["text"]) == 5_000 and second["next_offset"] is None


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("gold/validation/P06/gold_testplan.json", "answer keys"),
        ("raw/validation/P06/P06_Demo_TestPlan.docx", "reference test plans"),
        ("../outside.txt", "outside the data folder"),
        ("raw/validation/P06/missing.docx", "does not exist"),
        ("raw/validation/P06/P06_Demo_Architecture.png", "view_image"),
    ],
)
def test_read_file_refusals(data_root: Path, path: str, reason: str) -> None:
    with pytest.raises(ToolError, match=reason):
        read_file(data_root, path)


def test_view_image_returns_a_data_url(data_root: Path) -> None:
    seen = view_image(data_root, "raw/validation/P06/P06_Demo_Architecture.png")
    assert seen["media_type"] == "image/png"
    assert seen["_image_data_url"].startswith("data:image/png;base64,")


def test_create_document_only_in_agent_output_and_never_overwrites(data_root: Path) -> None:
    saved = create_document(data_root, "P06_test_plan.md", "# Plan\n")
    assert saved["path"] == "agent-output/P06_test_plan.md"
    assert (data_root / "agent-output" / "P06_test_plan.md").read_text(encoding="utf-8") == "# Plan\n"

    with pytest.raises(ToolError, match="already exists"):
        create_document(data_root, "P06_test_plan.md", "again")
    with pytest.raises(ToolError, match="inside agent-output"):
        create_document(data_root, "agent-output/../raw/hack.md", "x")
    with pytest.raises(ToolError, match="can be saved as"):
        create_document(data_root, "plan.pptx", "x")

    # the agent may read back its own plan, even though the name contains "test_plan"
    assert read_file(data_root, "agent-output/P06_test_plan.md")["text"] == "# Plan\n"
