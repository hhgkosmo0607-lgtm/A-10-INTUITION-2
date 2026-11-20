"""One entry point for the HTTP layer. It only wires the use cases together and passes calls on."""

from collections.abc import Sequence
from pathlib import Path

from factlock.application.briefing import WriterBrief
from factlock.application.catalog import FactCatalog
from factlock.application.documents import DocumentIngestion
from factlock.application.guidelines import GuidelineBook
from factlock.application.results import (
    Bundle,
    CarouselResult,
    Choices,
    DocumentView,
    DraftResult,
    Ingested,
    Unavailable,
    UnknownDocument,
    UnknownFact,
    UnknownTarget,
)
from factlock.application.reviewing import Reviewing
from factlock.application.targets import TargetBook
from factlock.application.writing import BlogWriting, CarouselWriting
from factlock.domain.models import Carousel, Fact, Guideline, ReviewReport, StoredDocument, Target
from factlock.ports import (
    CarouselWriter,
    DocumentLibrary,
    DocumentReader,
    DraftStore,
    DraftWriter,
    ExtraFactStore,
    FactExtractor,
    MeaningReviewer,
    TargetPlanner,
)

__all__ = [
    "Bundle",
    "CarouselResult",
    "Choices",
    "DocumentView",
    "DraftResult",
    "FactLockService",
    "Ingested",
    "Unavailable",
    "UnknownDocument",
    "UnknownFact",
    "UnknownTarget",
]


class FactLockService:
    def __init__(
        self,
        facts: Sequence[Fact],
        targets: Sequence[Target],
        guideline: Guideline,
        live_writer: DraftWriter | None,
        stored_writer: DraftWriter,
        store: DraftStore,
        planner: TargetPlanner | None = None,
        reviewer: MeaningReviewer | None = None,
        extractor: FactExtractor | None = None,
        extra_store: ExtraFactStore | None = None,
        live_carousel: CarouselWriter | None = None,
        stored_carousel: CarouselWriter | None = None,
        document_reader: DocumentReader | None = None,
        document_library: DocumentLibrary | None = None,
    ) -> None:
        self._catalog = FactCatalog(facts, extra_store)
        self._guidelines = GuidelineBook(guideline)
        self._targets = TargetBook(targets, self._catalog, planner)
        self._reviewing = Reviewing(self._catalog, self._guidelines, reviewer)
        brief = WriterBrief(self._catalog, self._guidelines)
        self._blog = BlogWriting(
            self._catalog, self._guidelines, brief, self._reviewing, live_writer, stored_writer, store
        )
        self._carousel = CarouselWriting(self._catalog, brief, self._reviewing, live_carousel, stored_carousel)
        self._documents = DocumentIngestion(self._catalog, extractor, document_reader, document_library)

    # facts
    @property
    def facts(self) -> list[Fact]:
        return self._catalog.all()

    def add_user_fact(self, statement: str, kind: str = "feature") -> Fact:
        return self._catalog.add_from_marketer(statement, kind)

    def confirm_fact(self, fact_id: str) -> Fact:
        return self._catalog.confirm(fact_id)

    def discard_fact(self, fact_id: str) -> None:
        self._catalog.discard(fact_id)

    # documents
    def documents(self) -> list[DocumentView]:
        return self._documents.stored()

    def add_document(self, filename: str, data: bytes) -> tuple[DocumentView, Ingested]:
        return self._documents.add(filename, data)

    def reanalyse_document(self, document_id: str) -> tuple[DocumentView, Ingested]:
        return self._documents.reanalyse(document_id)

    def remove_document(self, document_id: str) -> int:
        return self._documents.remove(document_id)

    def document_file(self, document_id: str) -> tuple[StoredDocument, Path]:
        return self._documents.original(document_id)

    # targets
    @property
    def targets(self) -> list[Target]:
        return self._targets.all()

    def target(self, target_id: str) -> Target:
        return self._targets.get(target_id)

    def plan_target(self, description: str) -> Target:
        return self._targets.plan(description)

    def bundle(self, target_id: str, agents: int) -> Bundle:
        return self._targets.bundle(target_id, agents)

    # guideline
    @property
    def guideline(self) -> Guideline:
        return self._guidelines.current

    def use_guideline(self, uploaded: Guideline) -> Guideline:
        return self._guidelines.adopt(uploaded)

    # outputs
    @property
    def live_available(self) -> bool:
        return self._blog.live_available

    def make_draft(self, target_id: str, choices: Choices) -> DraftResult:
        target = self._targets.tailored(target_id, choices.pains, choices.conditions)
        return self._blog.make(target, choices)

    def make_carousel(self, target_id: str, choices: Choices) -> CarouselResult:
        target = self._targets.tailored(target_id, choices.pains, choices.conditions)
        return self._carousel.make(target, choices)

    # review
    def review_text(self, title: str, body: str, target_id: str | None, ai: bool, choices: Choices) -> ReviewReport:
        target = self._targets.tailored(target_id, None, choices.conditions) if target_id else None
        return self._reviewing.text(title, body, target, ai, choices.must_include, choices.emphasize)

    def review_carousel(self, carousel: Carousel, target_id: str | None, choices: Choices) -> ReviewReport:
        target = self._targets.tailored(target_id, None, choices.conditions) if target_id else None
        return self._reviewing.carousel(carousel, target, choices.must_include, choices.emphasize)
