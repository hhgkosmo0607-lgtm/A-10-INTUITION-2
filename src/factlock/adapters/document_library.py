"""Internal document library: original files kept in a local folder, outside the repository data."""

import datetime
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from factlock.domain.models import StoredDocument


class FileDocumentLibrary:
    def __init__(self, folder: Path) -> None:
        self._folder = folder
        self._index = folder / "index.json"

    def all(self) -> list[StoredDocument]:
        if not self._index.is_file():
            return []
        return [StoredDocument(**raw) for raw in json.loads(self._index.read_text(encoding="utf-8"))]

    def _save(self, items: list[StoredDocument]) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2)
        self._index.write_text(payload + "\n", encoding="utf-8")

    def add(self, filename: str, data: bytes, pages: int) -> StoredDocument:
        document_id = hashlib.sha256(data).hexdigest()[:12]
        name = filename.rsplit("/", 1)[-1][:80]
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else "bin"
        today = datetime.date.today().isoformat()
        document = StoredDocument(document_id, name, pages, today, f"{document_id}.{extension}")
        self._folder.mkdir(parents=True, exist_ok=True)
        (self._folder / document.stored_as).write_bytes(data)
        self._save([*(item for item in self.all() if item.id != document_id), document])
        return document

    def get(self, document_id: str) -> tuple[StoredDocument, Path] | None:
        document = next((item for item in self.all() if item.id == document_id), None)
        if document is None:
            return None
        path = self._folder / document.stored_as
        return (document, path) if path.is_file() else None

    def delete(self, document_id: str) -> bool:
        found = self.get(document_id)
        if found is None:
            return False
        found[1].unlink(missing_ok=True)
        self._save([item for item in self.all() if item.id != document_id])
        return True
