"""The built-in tools, in one table: name -> description, JSON Schema parameters, Python function.

The database `tools` table says which tools an agent may use. This registry says what a
builtin tool actually *does*. At startup the catalog sync copies each entry's description and
parameters into the database (so the UI shows them), and the agent loop calls `execute`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.runtime.storage import Storage
from app.runtime.tools import files
from app.runtime.tools.files import ToolError


@dataclass(frozen=True)
class BuiltinTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]  # handler(root, **arguments)


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


BUILTIN_TOOLS: dict[str, BuiltinTool] = {
    tool.name: tool
    for tool in [
        BuiltinTool(
            name="list_files",
            description=(
                "List the folders and files inside a folder of the project data. Start with "
                "folder '' (the top) and go down, e.g. 'raw/validation/P06'."
            ),
            parameters={
                "type": "object",
                "properties": {"folder": _string("Folder path relative to the data root; '' for the top.")},
                "required": [],
            },
            handler=files.list_files,
        ),
        BuiltinTool(
            name="read_file",
            description=(
                "Read a .docx, .md, .txt, .json or .csv file as text (Word documents come back "
                "as Markdown with headings and tables). Long files are paged: if next_offset is "
                "not null, call again with that offset to read the rest."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": _string(
                        "File path relative to the data root, e.g. 'raw/validation/P06/P06_BRD.docx'."
                    ),
                    "offset": {
                        "type": "integer",
                        "description": "Character to start from (default 0).",
                        "minimum": 0,
                    },
                },
                "required": ["path"],
            },
            handler=files.read_file,
        ),
        BuiltinTool(
            name="view_image",
            description=(
                "Look at a .png or .jpg image, such as an architecture diagram. The image is "
                "shown to you in the next message."
            ),
            parameters={
                "type": "object",
                "properties": {"path": _string("Image path relative to the data root.")},
                "required": ["path"],
            },
            handler=files.view_image,
        ),
        BuiltinTool(
            name="create_document",
            description=(
                "Save a document under agent-output/. Write the content in Markdown; the file "
                "name's extension picks the format: .md, .docx (Word), .xlsx (Excel) or .pdf. "
                "Use this when the user asks for a file or a format. It never overwrites: pick a "
                "new name if the file exists."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": _string(
                        "File name with extension, e.g. 'P06_test_plan.docx' (saved as agent-output/P06_test_plan.docx)."
                    ),
                    "content": _string("The full document in Markdown."),
                },
                "required": ["path", "content"],
            },
            handler=files.create_document,
        ),
    ]
}

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def parse_arguments(tool: BuiltinTool, raw: str) -> dict[str, Any]:
    """The model's JSON argument string -> checked keyword arguments, or ToolError."""
    try:
        arguments = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        raise ToolError(f"The arguments are not valid JSON ({error.msg}). Send a JSON object.") from error
    if not isinstance(arguments, dict):
        raise ToolError("The arguments must be a JSON object.")

    properties: dict[str, Any] = tool.parameters.get("properties", {})
    missing = [name for name in tool.parameters.get("required", []) if name not in arguments]
    if missing:
        raise ToolError(f"Missing required argument(s): {', '.join(missing)}.")

    checked: dict[str, Any] = {}
    for name, value in arguments.items():
        schema = properties.get(name)
        if schema is None:
            continue  # ignore arguments the tool doesn't take
        expected = _JSON_TYPES.get(schema.get("type", ""), (object,))
        if isinstance(value, bool) and bool not in expected:
            raise ToolError(f"Argument '{name}' must be a {schema['type']}, not a boolean.")
        if not isinstance(value, expected):
            raise ToolError(f"Argument '{name}' must be a {schema.get('type')}.")
        checked[name] = value
    return checked


def execute(name: str, raw_arguments: str, root: Storage | Path) -> dict[str, Any]:
    """Run one builtin tool. Raises ToolError for anything the model can correct."""
    tool = BUILTIN_TOOLS.get(name)
    if tool is None:
        raise ToolError(f"There is no tool called '{name}'.")
    return tool.handler(root, **parse_arguments(tool, raw_arguments))
