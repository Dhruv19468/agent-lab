"""Finds the practice projects in the data root (local folder or Blob container).

Expected layout (the P00–P09 dummy dataset):

    raw/<split>/<Pxx_Name>/   Pxx_<Name>_BRD.docx, Pxx_<Name>_Architecture.png, Pxx_<Name>_TestPlan.docx
    gold/<split>/<Pxx_Name>/  gold_testplan.json   (optional: used for scoring when present)
    agent-output/             what agents save

The project folder may be called "P06" or "P06_Rebate_Validation"; the project id is "P06".
The agent's tools hide the TestPlan files and gold/; this module is for the platform itself
(the run screen and the scorer), which does need to know where the answers are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.runtime.storage import Storage, as_storage

SPLITS = ("train", "validation", "test")
PROJECT_PATTERN = re.compile(r"^(P\d{2})(?:[_\- ].*)?$", re.IGNORECASE)


@dataclass
class ProjectFiles:
    project: str
    split: str
    folder: str  # relative to the data root, as the agent's tools expect
    title: str
    brd: str | None = None
    diagrams: list[str] = field(default_factory=list)
    reference_testplan: str | None = None  # relative path; never shown to the agent
    gold: str | None = None  # relative path; never shown to the agent

    @property
    def suggested_message(self) -> str:
        return (
            f"Create the master test plan for project {self.project} ({self.title}). "
            f"Its documents are in the folder {self.folder}."
        )


def _is_testplan(name: str) -> bool:
    return "testplan" in name.lower().replace("_", "").replace("-", "")


def _title_from(name: str, project: str) -> str:
    stem = PurePosixPath(name).stem
    stem = re.sub(rf"^{project}_", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_(BRD|Architecture|TestPlan)$", "", stem, flags=re.IGNORECASE)
    return stem.replace("_", " ").strip() or project


def _describe(store: Storage, split: str, folder_name: str, folder: str) -> ProjectFiles:
    match = PROJECT_PATTERN.match(folder_name)
    project = match.group(1).upper() if match else folder_name.upper()  # "P06_Rebate_Validation" -> "P06"
    info = ProjectFiles(project=project, split=split, folder=folder, title=project)
    for entry in sorted(store.list(folder), key=lambda e: e.name.lower()):
        if entry.is_dir or entry.name.startswith((".", "_", "~")):
            continue
        suffix = PurePosixPath(entry.name).suffix.lower()
        if _is_testplan(entry.name):
            info.reference_testplan = entry.path
        elif suffix == ".docx" and info.brd is None:
            info.brd = entry.path
            info.title = _title_from(entry.name, project)
        elif suffix in {".png", ".jpg", ".jpeg"}:
            info.diagrams.append(entry.path)
    for gold_folder in (folder_name, project):  # gold/<split>/P06_Rebate_Validation/ or gold/<split>/P06/
        gold = f"gold/{split}/{gold_folder}/gold_testplan.json"
        if store.is_file(gold):
            info.gold = gold
            break
    return info


def find_projects(root: Storage | Path) -> list[ProjectFiles]:
    store = as_storage(root)
    projects: list[ProjectFiles] = []
    for split in SPLITS:
        for entry in sorted(store.list(f"raw/{split}"), key=lambda e: e.name):
            if entry.is_dir and PROJECT_PATTERN.match(entry.name):
                projects.append(_describe(store, split, entry.name, entry.path))
    return projects


def find_project(root: Storage | Path, project: str) -> ProjectFiles | None:
    wanted = project.strip().upper()
    return next((info for info in find_projects(root) if info.project == wanted), None)


def project_in_text(text: str) -> str | None:
    """'Create the test plan for project P06 …' -> 'P06'."""
    found = re.search(r"\bP\d{2}\b", text, flags=re.IGNORECASE)
    return found.group(0).upper() if found else None
