from __future__ import annotations

from pathlib import Path

from app.runtime.dataset import find_project, find_projects, project_in_text


def test_find_projects(data_root: Path) -> None:
    (project,) = find_projects(data_root)
    assert (project.project, project.split, project.title) == ("P06", "validation", "Demo")
    assert project.brd == "raw/validation/P06/P06_Demo_BRD.docx"
    assert project.diagrams == ["raw/validation/P06/P06_Demo_Architecture.png"]
    assert project.reference_testplan is not None and project.gold is not None
    assert "raw/validation/P06" in project.suggested_message


def test_find_project_and_message_parsing(data_root: Path, tmp_path: Path) -> None:
    assert find_project(data_root, "P07") is None
    assert find_projects(tmp_path / "empty") == []
    assert project_in_text("Create the master test plan for project p06 please") == "P06"
    assert project_in_text("no project here") is None


def test_long_folder_names(tmp_path: Path) -> None:
    """The real dataset names folders 'P06_Rebate_Validation', not 'P06'."""
    folder = tmp_path / "raw" / "validation" / "P06_Rebate_Validation"
    folder.mkdir(parents=True)
    (folder / "P06_Rebate_Validation_BRD.docx").write_bytes(b"x")
    (folder / "P06_Rebate_Validation_TestPlan.docx").write_bytes(b"x")
    gold = tmp_path / "gold" / "validation" / "P06_Rebate_Validation"
    gold.mkdir(parents=True)
    (gold / "gold_testplan.json").write_text("{}", encoding="utf-8")
    (tmp_path / "raw" / "validation" / "notes").mkdir()  # not a project folder

    (project,) = find_projects(tmp_path)
    assert (project.project, project.title) == ("P06", "Rebate Validation")
    assert project.folder == "raw/validation/P06_Rebate_Validation"
    assert project.gold is not None
    assert find_project(tmp_path, "P06") is not None
