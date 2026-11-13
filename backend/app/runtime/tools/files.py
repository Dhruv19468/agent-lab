"""The file tools an agent can call: list_files, read_file, view_image, create_document.

Every path the model sends is relative to the data root: the local data folder or the Azure
Blob container (see app/runtime/storage.py). These functions make sure the model can never:
  - leave the data root (no "../backend/.env"),
  - read the answer keys (gold/) or the human reference test plans (they are what we score against),
  - write anywhere except agent-output/, or overwrite an existing file.

A problem the model can fix (wrong path, file too big, name taken) raises ToolError. The agent
loop sends that message back to the model as the tool's result, so the model can try again.
"""

from __future__ import annotations

import base64
import io
import posixpath
from pathlib import Path, PurePosixPath
from typing import Any

from docx import Document
from docx.document import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.runtime import exporters
from app.runtime.storage import Storage, as_storage

TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv"}
WORD_SUFFIXES = {".docx"}
READABLE_SUFFIXES = TEXT_SUFFIXES | WORD_SUFFIXES
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
WRITABLE_SUFFIXES = {".md", ".docx", ".xlsx", ".pdf"}  # content is always Markdown; exporters.py converts it
OUTPUT_FOLDER = "agent-output"
PAGE_CHARS = 20_000  # most characters one read_file call returns
MAX_WRITE_CHARS = 400_000


class ToolError(Exception):
    """A tool call failed for a reason the model can understand and act on."""


def _hidden_reason(relative: PurePosixPath) -> str | None:
    """Why this path is off-limits to the agent, or None if it may be used."""
    parts = [part.lower() for part in relative.parts]
    if not parts:
        return None
    if parts[0] == "gold":
        return "gold/ holds the answer keys used to score your work; it is not available."
    if any(part.startswith(("_", ".")) for part in parts):
        return "internal files are not available."
    if parts[0] == OUTPUT_FOLDER:
        return None  # the agent's own documents, including the plans it writes
    name = parts[-1]
    if "testplan" in name.replace("_", "").replace("-", ""):
        return "reference test plans are what your work is scored against; they are not available."
    return None


def _normalise(raw_path: str) -> PurePosixPath | None:
    """The model's path as a clean relative path, or None if it points outside the data root."""
    text = (raw_path or "").strip().replace("\\", "/").lstrip("/")
    if ":" in text.split("/")[0]:  # "C:/…", "https://…"
        return None
    clean = posixpath.normpath(text) if text else "."
    if clean == ".." or clean.startswith("../"):
        return None
    return PurePosixPath(clean)


def _resolve(store: Storage, raw_path: str, *, must_exist: bool = True) -> str:
    """Check the model's path; return it as a relative "a/b/c" string ("" for the top), or raise ToolError."""
    relative = _normalise(raw_path)
    if relative is None:
        raise ToolError(f"'{raw_path}' is outside the data folder. Use paths like raw/validation/P06/P06_BRD.docx.")
    reason = _hidden_reason(relative)
    if reason:
        raise ToolError(f"'{relative}': {reason}")
    path = "" if str(relative) == "." else str(relative)
    if must_exist and not (store.is_file(path) or store.is_dir(path)):
        raise ToolError(f"'{relative}' does not exist. Call list_files to see what is there.")
    return path


def list_files(root: Storage | Path, folder: str = "") -> dict[str, Any]:
    """Folders and files directly inside `folder` (relative to the data root)."""
    store = as_storage(root)
    path = _resolve(store, folder)
    if store.is_file(path):
        raise ToolError(f"'{path}' is a file, not a folder. Use read_file to read it.")
    entries = []
    for entry in sorted(store.list(path), key=lambda e: (not e.is_dir, e.name.lower())):
        if _hidden_reason(PurePosixPath(entry.path)):
            continue  # hidden files are simply not listed
        if entry.is_dir:
            entries.append({"name": entry.name, "type": "folder", "path": entry.path})
        else:
            entries.append({"name": entry.name, "type": "file", "path": entry.path, "size_bytes": entry.size})
    return {"folder": path, "entries": entries}


def _table_to_markdown(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()).replace("|", "\\|") for cell in row.cells]
        rows.append("| " + " | ".join(cells) + " |")
    if len(rows) > 1:
        rows.insert(1, "|" + " --- |" * len(table.rows[0].cells))
    return "\n".join(rows)


def _paragraph_to_markdown(paragraph: Paragraph) -> str:
    text = paragraph.text.strip()
    if not text:
        return ""
    style = (paragraph.style.name if paragraph.style is not None else "").lower()
    if style == "title":
        return f"# {text}"
    if style.startswith("heading"):
        level = "".join(ch for ch in style if ch.isdigit()) or "1"
        return f"{'#' * min(int(level) + 1, 6)} {text}"
    if "list" in style:
        return f"- {text}"
    if _looks_like_bold_heading(paragraph, text):
        return f"**{text.rstrip(':')}**"
    return text


def _looks_like_bold_heading(paragraph: Paragraph, text: str) -> bool:
    """Many BRDs use bold 'Normal' paragraphs instead of Word heading styles ("Section 3 – Objectives").

    A short paragraph whose every run is bold is treated as a heading, so the structure
    survives into the text the model (and the scorer) reads.
    """
    if len(text) > 120 or text.endswith((".", ";", ",")):
        return False
    runs = [run for run in paragraph.runs if run.text.strip()]
    return bool(runs) and all(run.bold for run in runs)


def docx_to_text(source: Path | bytes) -> str:
    """A Word document (a file path or its bytes) as Markdown: headings, paragraphs, lists and tables, in order."""
    document: DocxDocument = Document(io.BytesIO(source) if isinstance(source, bytes) else str(source))
    blocks: list[str] = []
    for element in document.element.body.iterchildren():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "p":
            block = _paragraph_to_markdown(Paragraph(element, document))
        elif tag == "tbl":
            block = _table_to_markdown(Table(element, document))
        else:
            continue
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def read_file(root: Storage | Path, path: str, offset: int = 0) -> dict[str, Any]:
    """Up to PAGE_CHARS characters of a text file, starting at `offset`."""
    store = as_storage(root)
    relative = _resolve(store, path)
    if not store.is_file(relative):
        raise ToolError(f"'{relative}' is a folder. Use list_files to see inside it.")
    suffix = PurePosixPath(relative).suffix.lower()
    if suffix not in READABLE_SUFFIXES:
        raise ToolError(
            f"'{relative}' is a {suffix or 'file without extension'}; only "
            f"{', '.join(sorted(READABLE_SUFFIXES))} files can be read. For a diagram (.png/.jpg) use view_image."
        )
    data = store.read_bytes(relative)
    text = docx_to_text(data) if suffix in WORD_SUFFIXES else data.decode("utf-8", errors="replace")
    offset = max(0, int(offset or 0))
    if offset > len(text):
        raise ToolError(f"offset {offset} is past the end of '{relative}' ({len(text)} characters).")
    chunk = text[offset : offset + PAGE_CHARS]
    end = offset + len(chunk)
    return {
        "path": relative,
        "text": chunk,
        "offset": offset,
        "total_chars": len(text),
        "next_offset": end if end < len(text) else None,  # not None: call again with this offset
    }


def view_image(root: Storage | Path, path: str) -> dict[str, Any]:
    """Load an image so the model can look at it.

    The image itself can't travel inside a tool result (tool results are text), so it is
    returned under the private key "_image_data_url"; the agent loop removes that key and
    shows the image to the model in a separate message.
    """
    store = as_storage(root)
    relative = _resolve(store, path)
    media_type = IMAGE_TYPES.get(PurePosixPath(relative).suffix.lower())
    if not store.is_file(relative) or media_type is None:
        raise ToolError(f"'{relative}' is not an image; view_image takes {', '.join(sorted(IMAGE_TYPES))} files.")
    size = store.size(relative)
    if size > MAX_IMAGE_BYTES:
        raise ToolError(f"'{relative}' is {size // 1024} KB; images up to {MAX_IMAGE_BYTES // (1024 * 1024)} MB can be viewed.")
    data = store.read_bytes(relative)
    return {
        "path": relative,
        "media_type": media_type,
        "size_bytes": len(data),
        "note": "The image is attached in the next message. Describe only what you can actually see in it.",
        "_image_data_url": f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}",
    }


def create_document(root: Storage | Path, path: str, content: str) -> dict[str, Any]:
    """Save a new document under agent-output/. Never overwrites.

    `content` is always Markdown. The file name's extension picks the format:
    .md as is, .docx (Word), .xlsx (Excel) or .pdf, built by app/runtime/exporters.py.
    """
    store = as_storage(root)
    text = (path or "").strip().replace("\\", "/").lstrip("/")
    if not text.startswith(f"{OUTPUT_FOLDER}/"):
        text = f"{OUTPUT_FOLDER}/{text}"  # "P06_test_plan.docx" -> "agent-output/P06_test_plan.docx"
    relative = _resolve(store, text, must_exist=False)
    if PurePosixPath(relative).parts[:1] != (OUTPUT_FOLDER,):  # e.g. "agent-output/../processed/x.md"
        raise ToolError(f"Documents can only be saved inside {OUTPUT_FOLDER}/.")
    pure = PurePosixPath(relative)
    suffix = pure.suffix.lower()
    if suffix not in WRITABLE_SUFFIXES:
        raise ToolError(f"'{relative}': documents can be saved as {', '.join(sorted(WRITABLE_SUFFIXES))}.")
    exists_message = f"'{relative}' already exists. Choose a new name, e.g. {pure.stem}_v2{suffix}."
    if store.is_file(relative):
        raise ToolError(exists_message)
    if not content or not content.strip():
        raise ToolError("content is empty; write the document first, then save it.")
    if len(content) > MAX_WRITE_CHARS:
        raise ToolError(f"content is {len(content)} characters; the limit is {MAX_WRITE_CHARS}.")
    data = exporters.export(content, exporters.SUFFIX_TO_FORMAT[suffix])
    try:
        store.write_bytes(relative, data)  # never overwrites, even if two runs race for the name
    except FileExistsError as error:
        raise ToolError(exists_message) from error
    return {"path": relative, "format": suffix.lstrip("."), "bytes": len(data), "saved": True}
