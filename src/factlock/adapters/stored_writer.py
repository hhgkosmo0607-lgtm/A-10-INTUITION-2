"""Draft writer that returns a draft prepared ahead of time (data/<company>/drafts/<target>.json)."""

import json
from pathlib import Path
from typing import Any

from factlock.domain.models import Block, Carousel, Draft, DraftRequest, Slide
from factlock.ports import DraftWriterError


def draft_from_json(raw: dict[str, Any], source: str) -> Draft:
    blocks = tuple(
        Block(str(b["type"]), str(b.get("text", "")), tuple(str(i) for i in b.get("fact_ids", [])))
        for b in raw["blocks"]
    )
    return Draft(str(raw["title"]), blocks, source)


def carousel_from_json(raw: dict[str, Any], source: str) -> Carousel:
    slides = tuple(
        Slide(
            str(s.get("kicker", "")),
            str(s["headline"]),
            str(s.get("body", "")),
            tuple(str(i) for i in s.get("fact_ids", [])),
        )
        for s in raw["slides"]
    )
    caption = tuple(
        Block("sentence", str(b["text"]), tuple(str(i) for i in b.get("fact_ids", []))) for b in raw["caption"]
    )
    alt = raw.get("offer_without_price")
    offer = (
        Slide(
            str(alt.get("kicker", "")), str(alt["headline"]), str(alt.get("body", "")), tuple(alt.get("fact_ids", []))
        )
        if isinstance(alt, dict)
        else None
    )
    return Carousel(slides, caption, tuple(str(t) for t in raw.get("hashtags", [])), source, offer)


class StoredCarouselWriter:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def write_carousel(self, request: DraftRequest) -> Carousel:
        path = self._folder / f"{request.target.id}.json"
        if not path.is_file():
            raise DraftWriterError("stored_draft_missing")
        return carousel_from_json(json.loads(path.read_text(encoding="utf-8")), "stored")


class StoredDraftWriter:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def write(self, request: DraftRequest) -> Draft:
        path = self._folder / f"{request.target.id}.json"
        if not path.is_file():
            raise DraftWriterError("stored_draft_missing")
        return draft_from_json(json.loads(path.read_text(encoding="utf-8")), "stored")
