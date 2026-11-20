"""Added guidelines kept in a local JSON file."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from factlock.adapters.json_repo import guideline_from_json
from factlock.domain.models import Guideline, GuidelineEntry


def guideline_to_json(guideline: Guideline) -> dict[str, Any]:
    return {
        "required_keywords": list(guideline.required_keywords),
        "title_keywords": list(guideline.title_keywords),
        "footer": list(guideline.footer),
        "targets": list(guideline.targets),
        "emphasis": [
            {"no": i.no, "text": i.text, "any_of": [list(g) for g in i.any_of], "terms_confirmed": i.terms_confirmed}
            for i in guideline.emphasis
        ],
    }


class JsonGuidelineStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _read(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"entries": [], "switches": {}}
        loaded: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        return loaded

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load(self) -> list[GuidelineEntry]:
        return [
            GuidelineEntry(raw["id"], raw["name"], guideline_from_json(raw["guideline"]))
            for raw in self._read()["entries"]
        ]

    def save(self, entries: Sequence[GuidelineEntry]) -> None:
        data = self._read()
        data["entries"] = [{"id": e.id, "name": e.name, "guideline": guideline_to_json(e.guideline)} for e in entries]
        self._write(data)

    def load_switches(self) -> dict[str, bool]:
        return {str(k): bool(v) for k, v in self._read()["switches"].items()}

    def save_switches(self, switches: dict[str, bool]) -> None:
        data = self._read()
        data["switches"] = switches
        self._write(data)
