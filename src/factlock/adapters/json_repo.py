"""Read facts, targets and the guideline from a company's data folder (data/<company>/*.json)."""

import json
from pathlib import Path
from typing import Any

from factlock.domain.models import (
    EmphasisItem,
    Fact,
    FactStatus,
    Guideline,
    Pricing,
    Source,
    Target,
    Value,
)


def _value(raw: dict[str, Any]) -> Value:
    # Percent is stored per-mille so "93.4%" stays an integer.
    if raw["unit"] == "%":
        return Value(round(float(raw["amount"]) * 10), "‰")
    return Value(int(raw["amount"]), str(raw["unit"]))


def fact_from_json(raw: dict[str, Any]) -> Fact:
    pricing = raw.get("pricing")
    return Fact(
        id=raw["id"],
        kind=raw["kind"],
        statement=raw["statement"],
        source=Source(raw["source"]["where"], raw["source"]["checked"]),
        status=FactStatus(raw.get("status", "confirmed")),
        values=tuple(_value(v) for v in raw.get("values", [])),
        anchors=tuple(raw.get("anchors", [])),
        requires=tuple(raw.get("requires", [])),
        markers=tuple(raw.get("markers", [])),
        scope=raw.get("scope", ""),
        pricing=Pricing(**pricing) if pricing else None,
    )


def guideline_from_json(raw: dict[str, Any]) -> Guideline:
    return Guideline(
        required_keywords=tuple(raw["required_keywords"]),
        emphasis=tuple(
            EmphasisItem(
                item["no"],
                item["text"],
                tuple(tuple(group) for group in item.get("any_of", [])),
                bool(item.get("terms_confirmed", False)),
            )
            for item in raw["emphasis"]
        ),
        footer=tuple(raw["footer"]),
        title_keywords=tuple(raw.get("title_keywords", [])),
    )


class JsonCompanyData:
    """Implements FactRepository, TargetRepository and GuidelineRepository for one company folder."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder
        self._facts = [fact_from_json(raw) for raw in self._load("facts")]
        self._targets = [
            Target(
                id=raw["id"],
                name=raw["name"],
                pains=tuple(raw["pains"]),
                bundle=tuple(raw["bundle"]),
                quote_items=tuple(raw["quote_items"]),
                must_conditions=tuple(raw.get("must_conditions", [])),
                status=raw.get("status", "proposed"),
            )
            for raw in self._load("targets")
        ]
        self._guideline = guideline_from_json(self._load("guideline"))

    def _load(self, name: str) -> Any:
        return json.loads((self._folder / f"{name}.json").read_text(encoding="utf-8"))

    def all(self) -> list[Fact]:
        return list(self._facts)

    def get(self, fact_id: str) -> Fact | None:
        return next((fact for fact in self._facts if fact.id == fact_id), None)

    def targets(self) -> list[Target]:
        return list(self._targets)

    def target(self, target_id: str) -> Target | None:
        return next((target for target in self._targets if target.id == target_id), None)

    def current(self) -> Guideline:
        return self._guideline
