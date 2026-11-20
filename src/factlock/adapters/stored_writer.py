"""Draft writer that returns a draft prepared ahead of time (data/<company>/drafts/<target>.json)."""

import json
from pathlib import Path
from typing import Any

from factlock.domain.models import Block, Draft, DraftRequest
from factlock.ports import DraftWriterError


def draft_from_json(raw: dict[str, Any], source: str) -> Draft:
    blocks = tuple(
        Block(str(b["type"]), str(b.get("text", "")), tuple(str(i) for i in b.get("fact_ids", [])))
        for b in raw["blocks"]
    )
    return Draft(str(raw["title"]), blocks, source)


class StoredDraftWriter:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def write(self, request: DraftRequest) -> Draft:
        path = self._folder / f"{request.target.id}.json"
        if not path.is_file():
            raise DraftWriterError("stored_draft_missing")
        return draft_from_json(json.loads(path.read_text(encoding="utf-8")), "stored")
