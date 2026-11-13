"""Step 4 check: call the file tools directly on the raw dataset, the way the agent loop will.

Run from the backend/ folder:
    uv run python scripts/check_tools.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.runtime.tools.files import ToolError, create_document, list_files, read_file, view_image  # noqa: E402

root = get_settings().agent_data_path
print(f"Data folder: {root}\n")


def attempt(label: str, call) -> dict | None:
    try:
        result = call()
        print(f"OK   {label}")
        return result
    except ToolError as error:
        print(f"NO   {label}\n       -> {error}")
        return None


top = attempt("list_files('')", lambda: list_files(root, ""))
print("       " + ", ".join(entry["name"] for entry in top["entries"]) + "   (no gold/: hidden)")

projects = attempt("list_files('raw/validation')", lambda: list_files(root, "raw/validation"))
folders = [entry for entry in projects["entries"] if entry["type"] == "folder"]
if not folders:
    sys.exit("raw/validation has no project folders: copy the raw/ dataset into data/.")
project = folders[0]["path"]
files = attempt(f"list_files('{project}')", lambda: list_files(root, project))
names = [entry["name"] for entry in files["entries"]]
print("       " + ", ".join(names) + "   (reference TestPlan hidden)")

brd = next((e["path"] for e in files["entries"] if e["name"].lower().endswith(".docx")), None)
image = next((e["path"] for e in files["entries"] if e["name"].lower().endswith((".png", ".jpg", ".jpeg"))), None)

if brd:
    page = attempt(f"read_file('{brd}')", lambda: read_file(root, brd))
    print(f"       total_chars={page['total_chars']} next_offset={page['next_offset']}")
    print("       first lines:")
    for line in page["text"].splitlines()[:8]:
        print(f"         {line[:100]}")
if image:
    seen = attempt(f"view_image('{image}')", lambda: view_image(root, image))
    print(f"       media_type={seen['media_type']} size={seen['size_bytes']} bytes, "
          f"data URL of {len(seen['_image_data_url'])} characters (sent to the model, never to the log)")

print()
attempt("read gold answer key", lambda: read_file(root, "gold/validation"))
reference = next((p for p in (root / project).iterdir() if "testplan" in p.name.lower().replace("_", "")), None)
if reference:
    attempt("read the reference test plan", lambda: read_file(root, reference.relative_to(root).as_posix()))
attempt("escape the data folder", lambda: read_file(root, "../backend/.env"))
if image:
    attempt("read the diagram as text", lambda: read_file(root, image))
attempt("missing file", lambda: read_file(root, f"{project}/nothing_here.docx"))

print()
saved = attempt("create_document('check_tools_demo.md')", lambda: create_document(root, "check_tools_demo.md", "# Demo\n\nSaved by check_tools.py\n"))
print(f"       {saved}")
attempt("create the same file again", lambda: create_document(root, "check_tools_demo.md", "again"))
attempt("write outside agent-output", lambda: create_document(root, "../raw/hack.md", "x"))
(root / saved["path"]).unlink()  # tidy up
print("\nDemo document removed.")