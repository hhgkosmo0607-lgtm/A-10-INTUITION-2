"""Keep facts read from internal documents in a local JSON file (outside the repository data)."""

import json
from pathlib import Path
from typing import Any

from factlock.adapters.json_repo import fact_from_json
from factlock.domain.models import Fact


def fact_to_json(fact: Fact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "kind": fact.kind,
        "statement": fact.statement,
        "status": fact.status.value,
        "source": {
            "where": fact.source.where,
            "checked": fact.source.checked,
            "url": fact.source.url,
            "quote": fact.source.quote,
        },
        "values": [
            {"amount": v.amount / 10, "unit": "%"} if v.unit == "‰" else {"amount": v.amount, "unit": v.unit}
            for v in fact.values
        ],
        "anchors": list(fact.anchors),
    }


class JsonExtraFacts:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[Fact]:
        if not self._path.is_file():
            return []
        return [fact_from_json(raw) for raw in json.loads(self._path.read_text(encoding="utf-8"))]

    def save(self, facts: list[Fact]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([fact_to_json(f) for f in facts], ensure_ascii=False, indent=2)
        self._path.write_text(payload + "\n", encoding="utf-8")
