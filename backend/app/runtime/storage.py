"""Where the agent's data lives: a local folder (your laptop) or an Azure Blob container (Azure).

Everything that touches data files (the agent's four tools, project discovery, saved outputs,
the scorer and its cache) goes through `get_storage()`, so the same code works on both:

    AGENT_STORAGE=local   AGENT_DATA_DIR=../data                         (default)
    AGENT_STORAGE=blob    AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
                          AZURE_STORAGE_CONTAINER=agentdata

Paths are always relative and use "/": "raw/validation/P06_Rebate_Validation/P06_..._BRD.docx".
Blob Storage has no real folders; a "folder" is the shared start of blob names ("raw/validation/").

On Azure the backend signs in to Blob with its managed identity (role "Storage Blob Data
Contributor" on the storage account), so no storage key is stored anywhere. For testing Blob from
your laptop, `az login` works the same way, or set AZURE_STORAGE_CONNECTION_STRING.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True)
class Entry:
    name: str  # last part: "P06_Rebate_Validation_BRD.docx"
    path: str  # relative: "raw/validation/P06_Rebate_Validation/P06_Rebate_Validation_BRD.docx"
    is_dir: bool
    size: int | None = None


class Storage(Protocol):
    """What the rest of the code needs. Paths are relative, "/"-separated and already checked."""

    def describe(self) -> str: ...
    def list(self, folder: str) -> list[Entry]: ...
    def is_dir(self, path: str) -> bool: ...
    def is_file(self, path: str) -> bool: ...
    def size(self, path: str) -> int: ...
    def read_bytes(self, path: str) -> bytes: ...
    def write_bytes(self, path: str, data: bytes, *, overwrite: bool = False) -> None: ...


def _join(folder: str, name: str) -> str:
    return f"{folder.strip('/')}/{name}" if folder.strip("/") else name


# --- local folder ------------------------------------------------------------------------------


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def describe(self) -> str:
        return str(self.root)

    def _full(self, path: str) -> Path:
        full = (self.root / path).resolve() if path else self.root
        if not full.is_relative_to(self.root):  # e.g. a symlink pointing outside
            raise FileNotFoundError(path)
        return full

    def list(self, folder: str) -> list[Entry]:
        full = self._full(folder)
        if not full.is_dir():
            return []
        entries = []
        for child in full.iterdir():
            relative = _join(folder, child.name)
            if child.is_dir():
                entries.append(Entry(child.name, relative, True))
            elif child.is_file():
                entries.append(Entry(child.name, relative, False, child.stat().st_size))
        return entries

    def is_dir(self, path: str) -> bool:
        try:
            return self._full(path).is_dir()
        except FileNotFoundError:
            return False

    def is_file(self, path: str) -> bool:
        try:
            return self._full(path).is_file()
        except FileNotFoundError:
            return False

    def size(self, path: str) -> int:
        return self._full(path).stat().st_size

    def read_bytes(self, path: str) -> bytes:
        return self._full(path).read_bytes()

    def write_bytes(self, path: str, data: bytes, *, overwrite: bool = False) -> None:
        full = self._full(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        with full.open("wb" if overwrite else "xb") as handle:  # "x": fails if the file exists
            handle.write(data)


# --- Azure Blob container ----------------------------------------------------------------------


class BlobStorage:
    """One Blob container. `container` is an azure.storage.blob ContainerClient (tests pass a fake)."""

    def __init__(self, container: Any, description: str) -> None:
        self.container = container
        self._description = description

    @classmethod
    def from_settings(cls, account_url: str, container_name: str, connection_string: str = "") -> BlobStorage:
        from azure.storage.blob import BlobServiceClient

        if connection_string:
            service = BlobServiceClient.from_connection_string(connection_string)
        else:
            from azure.identity import DefaultAzureCredential

            # Managed identity on Azure; your `az login` on a laptop.
            credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            service = BlobServiceClient(account_url=account_url, credential=credential)
        return cls(service.get_container_client(container_name), f"{account_url or 'blob'}/{container_name}")

    def describe(self) -> str:
        return self._description

    def list(self, folder: str) -> list[Entry]:
        prefix = f"{folder.strip('/')}/" if folder.strip("/") else ""
        entries = []
        for item in self.container.walk_blobs(name_starts_with=prefix, delimiter="/"):
            name: str = item.name
            if name.endswith("/"):  # a "folder" (BlobPrefix)
                entries.append(Entry(name[len(prefix) :].rstrip("/"), name.rstrip("/"), True))
            else:
                entries.append(Entry(name[len(prefix) :], name, False, getattr(item, "size", None)))
        return entries

    def is_dir(self, path: str) -> bool:
        if not path.strip("/"):
            return True
        prefix = f"{path.strip('/')}/"
        return next(iter(self.container.list_blobs(name_starts_with=prefix, results_per_page=1)), None) is not None

    def is_file(self, path: str) -> bool:
        return bool(path) and self.container.get_blob_client(path).exists()

    def size(self, path: str) -> int:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return int(self.container.get_blob_client(path).get_blob_properties().size)
        except ResourceNotFoundError as error:
            raise FileNotFoundError(path) from error

    def read_bytes(self, path: str) -> bytes:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self.container.get_blob_client(path).download_blob().readall()
        except ResourceNotFoundError as error:
            raise FileNotFoundError(path) from error

    def write_bytes(self, path: str, data: bytes, *, overwrite: bool = False) -> None:
        from azure.core.exceptions import ResourceExistsError

        try:
            from azure.storage.blob import ContentSettings

            settings = ContentSettings(content_type=CONTENT_TYPES.get(Path(path).suffix.lower(), "application/octet-stream"))
        except ImportError:  # tests with a fake container
            settings = None
        try:
            self.container.upload_blob(path, data, overwrite=overwrite, content_settings=settings)
        except ResourceExistsError as error:
            raise FileExistsError(path) from error


# --- the configured storage --------------------------------------------------------------------


def as_storage(value: Storage | Path | str) -> Storage:
    """Tools and tests may pass a plain folder path; wrap it."""
    if isinstance(value, (str, Path)):
        return LocalStorage(Path(value))
    return value


@lru_cache
def get_storage() -> Storage:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.agent_storage.strip().lower() == "blob":
        return BlobStorage.from_settings(
            settings.azure_storage_account_url,
            settings.azure_storage_container,
            settings.azure_storage_connection_string.get_secret_value(),
        )
    return LocalStorage(settings.agent_data_path)
