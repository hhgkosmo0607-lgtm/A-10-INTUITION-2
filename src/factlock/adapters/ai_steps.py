"""The three AI steps, each built on a JsonModel: write a draft, plan a target, review meaning."""

from collections.abc import Sequence
from typing import Any

from factlock.adapters import prompts
from factlock.adapters.stored_writer import carousel_from_json, draft_from_json
from factlock.domain.models import Carousel, Draft, DraftRequest, Fact
from factlock.ports import AiError, DraftWriterError, JsonModel


def _strings(raw: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in raw) if isinstance(raw, list) else ()


class AiDraftWriter:
    def __init__(self, model: JsonModel) -> None:
        self._model = model

    def write(self, request: DraftRequest) -> Draft:
        try:
            answer = self._model.ask(prompts.SYSTEM, prompts.build_prompt(request), prompts.SCHEMA)
        except AiError as error:
            raise DraftWriterError(error.code) from None
        source = getattr(self._model, "last_used", "") or self._model.name
        try:
            return draft_from_json(answer, source)
        except (KeyError, TypeError, ValueError):
            raise DraftWriterError("ai_bad_output") from None


class AiCarouselWriter:
    def __init__(self, model: JsonModel) -> None:
        self._model = model

    def write_carousel(self, request: DraftRequest) -> Carousel:
        try:
            answer = self._model.ask(prompts.CAROUSEL_SYSTEM, prompts.carousel_prompt(request), prompts.CAROUSEL_SCHEMA)
        except AiError as error:
            raise DraftWriterError(error.code) from None
        source = getattr(self._model, "last_used", "") or self._model.name
        try:
            return carousel_from_json(answer, source)
        except (KeyError, TypeError, ValueError):
            raise DraftWriterError("ai_bad_output") from None


class AiTargetPlanner:
    def __init__(self, model: JsonModel) -> None:
        self._model = model

    def plan(self, description: str, facts: Sequence[Fact]) -> dict[str, Any]:
        answer = self._model.ask(prompts.PLAN_SYSTEM, prompts.plan_prompt(description, facts), prompts.PLAN_SCHEMA)
        return {
            "name": str(answer.get("name", "")),
            "product_ids": _strings(answer.get("product_ids")),
            "pain_ids": _strings(answer.get("pain_ids")),
            "price_ids": _strings(answer.get("price_ids")),
            "condition_ids": _strings(answer.get("condition_ids")),
            "reason": str(answer.get("reason", "")),
        }


class AiMeaningReviewer:
    def __init__(self, model: JsonModel) -> None:
        self._model = model

    def review(self, title: str, body: str, facts: Sequence[Fact]) -> list[dict[str, str]]:
        answer = self._model.ask(
            prompts.REVIEW_SYSTEM, prompts.review_prompt(title, body, facts), prompts.REVIEW_SCHEMA
        )
        raw = answer.get("findings")
        if not isinstance(raw, list):
            raise AiError("ai_bad_output")
        return [
            {
                "sentence": str(i.get("sentence", "")),
                "problem": str(i.get("problem", "")),
                "fact_id": str(i.get("fact_id", "")),
            }
            for i in raw
            if isinstance(i, dict)
        ]


class AiFactExtractor:
    def __init__(self, model: JsonModel) -> None:
        self._model = model

    def extract(self, pages: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
        answer = self._model.ask(prompts.EXTRACT_SYSTEM, prompts.extract_prompt(pages), prompts.EXTRACT_SCHEMA)
        raw = answer.get("facts")
        if not isinstance(raw, list):
            raise AiError("ai_bad_output")
        return [
            {
                "statement": str(i.get("statement", "")),
                "quote": str(i.get("quote", "")),
                "locator": str(i.get("locator", "")),
                "kind": str(i.get("kind", "")),
                "subject_words": _strings(i.get("subject_words")),
            }
            for i in raw
            if isinstance(i, dict)
        ]
