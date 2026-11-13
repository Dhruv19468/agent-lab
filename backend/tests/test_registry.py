"""Checking the model's tool arguments before a tool runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime.tools.files import ToolError
from app.runtime.tools.registry import BUILTIN_TOOLS, execute, parse_arguments

READ = BUILTIN_TOOLS["read_file"]


def test_every_builtin_has_a_valid_schema() -> None:
    for tool in BUILTIN_TOOLS.values():
        assert tool.parameters["type"] == "object"
        assert set(tool.parameters.get("required", [])) <= set(tool.parameters["properties"])


def test_parse_arguments_keeps_known_fields_only() -> None:
    assert parse_arguments(READ, '{"path": "a.md", "offset": 5, "extra": 1}') == {"path": "a.md", "offset": 5}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not json", "not valid JSON"),
        ("[1, 2]", "JSON object"),
        ("{}", "Missing required argument"),
        ('{"path": 3}', "must be a string"),
        ('{"path": "a.md", "offset": true}', "not a boolean"),
    ],
)
def test_parse_arguments_errors(raw: str, message: str) -> None:
    with pytest.raises(ToolError, match=message):
        parse_arguments(READ, raw)


def test_execute_unknown_tool(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="no tool called"):
        execute("delete_everything", "{}", tmp_path)


def test_execute_runs_the_handler(data_root: Path) -> None:
    result = execute("list_files", '{"folder": "raw/validation"}', data_root)
    assert result["entries"][0]["name"] == "P06"
