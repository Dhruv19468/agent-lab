from __future__ import annotations

from app.core.schemas import ApiModel


class ProjectRead(ApiModel):
    project: str
    split: str
    title: str
    folder: str
    brd: str | None
    diagrams: list[str]
    has_reference: bool  # the human TestPlan.docx is there, so runs can be scored
    has_gold: bool  # gold/<split>/<project>/gold_testplan.json is there (preferred for scoring)
    suggested_message: str


class DatasetRead(ApiModel):
    data_dir: str
    projects: list[ProjectRead]
