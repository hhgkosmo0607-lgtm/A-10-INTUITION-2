"""Promo material library: images the company owns (product screens, photos) kept in a local folder."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from factlock.domain.models import Asset
from factlock.ports import AssetError

MAX_BYTES = 10 * 1024 * 1024
MAX_ITEMS = 200


def _kind(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise AssetError("asset_type_unsupported")


class FileAssetStore:
    max_bytes = MAX_BYTES

    def __init__(self, folder: Path) -> None:
        self._folder = folder
        self._index = folder / "index.json"

    def all(self) -> list[Asset]:
        if not self._index.is_file():
            return []
        return [Asset(**raw) for raw in json.loads(self._index.read_text(encoding="utf-8"))]

    def _save(self, items: list[Asset]) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2)
        self._index.write_text(payload + "\n", encoding="utf-8")

    def add(self, filename: str, data: bytes, caption: str) -> Asset:
        if len(data) > MAX_BYTES:
            raise AssetError("asset_too_large")
        caption = " ".join(caption.split())[:120]
        if len(caption) < 2:
            raise AssetError("asset_caption_missing")
        content_type, extension = _kind(data)
        items = self.all()
        if len(items) >= MAX_ITEMS:
            raise AssetError("asset_library_full")
        asset_id = hashlib.sha256(data).hexdigest()[:12]
        asset = Asset(asset_id, caption, filename.rsplit("/", 1)[-1][:80], content_type, f"{asset_id}.{extension}")
        self._folder.mkdir(parents=True, exist_ok=True)
        (self._folder / asset.stored_as).write_bytes(data)
        self._save([*(item for item in items if item.id != asset_id), asset])
        return asset

    def get(self, asset_id: str) -> tuple[Asset, Path] | None:
        asset = next((item for item in self.all() if item.id == asset_id), None)
        if asset is None:
            return None
        path = self._folder / asset.stored_as
        return (asset, path) if path.is_file() else None

    def delete(self, asset_id: str) -> bool:
        found = self.get(asset_id)
        if found is None:
            return False
        found[1].unlink(missing_ok=True)
        self._save([item for item in self.all() if item.id != asset_id])
        return True
