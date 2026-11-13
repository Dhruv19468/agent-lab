"""The storage layer: a local folder and an Azure Blob container behave the same for the tools.

BlobStorage is tested against a small fake ContainerClient that behaves like the real SDK:
"folders" are name prefixes, walk_blobs(delimiter="/") returns prefixes ending in "/", and
uploading to an existing name raises ResourceExistsError unless overwrite=True.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

from app.runtime.dataset import find_projects
from app.runtime.storage import BlobStorage, LocalStorage
from app.runtime.tools.files import ToolError, create_document, list_files, read_file, view_image


@dataclass
class _Props:
    name: str
    size: int


class _Prefix:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeBlob:
    def __init__(self, container: FakeContainer, name: str) -> None:
        self.container, self.name = container, name

    def exists(self) -> bool:
        return self.name in self.container.blobs

    def get_blob_properties(self) -> _Props:
        if not self.exists():
            raise ResourceNotFoundError("missing")
        return _Props(self.name, len(self.container.blobs[self.name]))

    def download_blob(self):
        if not self.exists():
            raise ResourceNotFoundError("missing")
        data = self.container.blobs[self.name]
        return type("Downloader", (), {"readall": lambda _self: data})()


class FakeContainer:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def walk_blobs(self, name_starts_with: str = "", delimiter: str = "/"):
        seen = set()
        for name in sorted(self.blobs):
            if not name.startswith(name_starts_with):
                continue
            rest = name[len(name_starts_with) :]
            if delimiter in rest:
                prefix = name_starts_with + rest.split(delimiter)[0] + delimiter
                if prefix not in seen:
                    seen.add(prefix)
                    yield _Prefix(prefix)
            else:
                yield _Props(name, len(self.blobs[name]))

    def list_blobs(self, name_starts_with: str = "", results_per_page: int | None = None):
        return iter([_Props(n, len(b)) for n, b in sorted(self.blobs.items()) if n.startswith(name_starts_with)])

    def get_blob_client(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)

    def upload_blob(self, name: str, data: bytes, overwrite: bool = False, content_settings=None) -> None:
        if name in self.blobs and not overwrite:
            raise ResourceExistsError("exists")
        self.blobs[name] = bytes(data)


@pytest.fixture
def blob_root(data_root: Path) -> BlobStorage:
    """The conftest dataset copied into a fake Blob container."""
    container = FakeContainer()
    for file in data_root.rglob("*"):
        if file.is_file():
            container.blobs[file.relative_to(data_root).as_posix()] = file.read_bytes()
    return BlobStorage(container, "fake/agentdata")


@pytest.fixture(params=["local", "blob"])
def store(request, data_root: Path, blob_root: BlobStorage):
    return LocalStorage(data_root) if request.param == "local" else blob_root


def test_tools_behave_the_same_on_both(store) -> None:
    top = [entry["name"] for entry in list_files(store, "")["entries"]]
    assert "raw" in top and "gold" not in top

    project = [entry["name"] for entry in list_files(store, "raw/validation/P06")["entries"]]
    assert project == ["P06_Demo_Architecture.png", "P06_Demo_BRD.docx"]  # TestPlan hidden

    page = read_file(store, "raw/validation/P06/P06_Demo_BRD.docx")
    assert "**Section 1 – Purpose**" in page["text"]
    assert view_image(store, "raw/validation/P06/P06_Demo_Architecture.png")["media_type"] == "image/png"

    for path, reason in [
        ("gold/validation/P06/gold_testplan.json", "answer keys"),
        ("raw/validation/P06/P06_Demo_TestPlan.docx", "reference test plans"),
        ("../outside.txt", "outside the data folder"),
        ("C:/Windows/win.ini", "outside the data folder"),
        ("raw/validation/P06/missing.docx", "does not exist"),
    ]:
        with pytest.raises(ToolError, match=reason):
            read_file(store, path)


def test_create_document_on_both(store) -> None:
    saved = create_document(store, "P06_plan.docx", "# Test Plan\n\n## 1. Objectives\nText")
    assert saved["path"] == "agent-output/P06_plan.docx" and store.is_file(saved["path"])
    with pytest.raises(ToolError, match="already exists"):
        create_document(store, "P06_plan.docx", "again")
    with pytest.raises(ToolError, match="inside agent-output"):
        create_document(store, "agent-output/../raw/hack.md", "x")
    assert [e["name"] for e in list_files(store, "agent-output")["entries"]] == ["P06_plan.docx"]


def test_projects_found_on_both(store) -> None:
    (project,) = find_projects(store)
    assert project.project == "P06" and project.brd == "raw/validation/P06/P06_Demo_BRD.docx"
    assert project.reference_testplan == "raw/validation/P06/P06_Demo_TestPlan.docx"
    assert project.gold == "gold/validation/P06/gold_testplan.json"


def test_storage_basics(store) -> None:
    assert store.is_dir("") and store.is_dir("raw/validation") and not store.is_dir("raw/nothing")
    assert store.is_file("raw/validation/P06/P06_Demo_BRD.docx") and not store.is_file("raw")
    store.write_bytes("_cache/x.json", b"1")
    with pytest.raises(FileExistsError):
        store.write_bytes("_cache/x.json", b"2")
    store.write_bytes("_cache/x.json", b"3", overwrite=True)
    assert store.read_bytes("_cache/x.json") == b"3"
    with pytest.raises(FileNotFoundError):
        store.read_bytes("_cache/missing.json")
