"""Use cases: bundle and quote, draft with fact lock, review. Depends on domain and ports only."""

from collections.abc import Sequence
from dataclasses import dataclass

from factlock.domain.lock import lock_draft, render_body
from factlock.domain.models import Draft, Dropped, Fact, FactStatus, Guideline, Quote, ReviewReport, Target
from factlock.domain.quote import build_quote
from factlock.domain.review import review
from factlock.ports import DraftStore, DraftWriter, DraftWriterError

USABLE_KINDS_FOR_WRITING = ("product", "feature", "number", "price", "condition", "pain", "phrase", "company")


@dataclass(frozen=True)
class Bundle:
    target: Target
    products: tuple[Fact, ...]
    pains: tuple[Fact, ...]
    conditions: tuple[Fact, ...]
    quote: Quote


@dataclass(frozen=True)
class DraftResult:
    draft_id: str
    draft: Draft
    body: str
    dropped: tuple[Dropped, ...]
    report: ReviewReport
    fallback_code: str  # empty when the live writer answered


class UnknownTarget(Exception):
    pass


class FactLockService:
    def __init__(
        self,
        facts: Sequence[Fact],
        targets: Sequence[Target],
        guideline: Guideline,
        live_writer: DraftWriter | None,
        stored_writer: DraftWriter,
        store: DraftStore,
    ) -> None:
        self._facts = list(facts)
        self._by_id = {fact.id: fact for fact in facts}
        self._targets = {target.id: target for target in targets}
        self.guideline = guideline
        self._live = live_writer
        self._stored = stored_writer
        self._store = store

    @property
    def facts(self) -> list[Fact]:
        return list(self._facts)

    @property
    def targets(self) -> list[Target]:
        return list(self._targets.values())

    @property
    def live_available(self) -> bool:
        return self._live is not None

    def target(self, target_id: str) -> Target:
        try:
            return self._targets[target_id]
        except KeyError:
            raise UnknownTarget(target_id) from None

    def _pick(self, ids: Sequence[str]) -> tuple[Fact, ...]:
        return tuple(self._by_id[i] for i in ids if i in self._by_id)

    def bundle(self, target_id: str, agents: int) -> Bundle:
        target = self.target(target_id)
        products = self._pick(target.bundle)
        condition_ids = dict.fromkeys(
            [*target.must_conditions, *(cid for product in products for cid in product.requires)]
        )
        quote = build_quote(self._pick(target.quote_items), agents, self._facts)
        return Bundle(target, products, self._pick(target.pains), self._pick(list(condition_ids)), quote)

    def writable_facts(self) -> tuple[Fact, ...]:
        """Facts a writer may use: never conflicting ones."""
        return tuple(
            fact
            for fact in self._facts
            if fact.status is not FactStatus.CONFLICT and fact.kind in USABLE_KINDS_FOR_WRITING
        )

    def make_draft(self, target_id: str, live: bool = True) -> DraftResult:
        from factlock.domain.models import DraftRequest

        target = self.target(target_id)
        request = DraftRequest(target, self.guideline, self.writable_facts())
        fallback_code = "" if live else "stored_requested"
        raw: Draft | None = None
        if live and self._live is not None:
            try:
                raw = self._live.write(request)
            except DraftWriterError as error:
                fallback_code = error.code
        elif live:
            fallback_code = "live_writer_not_configured"
        if raw is None:
            raw = self._stored.write(request)
        draft, dropped = lock_draft(raw, self._facts)
        body = render_body(draft, self.guideline, self._facts)
        report = review(draft.title, body, self._facts, self.guideline, target)
        draft_id = self._store.save(draft, report)
        return DraftResult(draft_id, draft, body, dropped, report, fallback_code)

    def review_text(self, title: str, body: str, target_id: str | None) -> ReviewReport:
        target = self.target(target_id) if target_id else None
        return review(title, body, self._facts, self.guideline, target)

    def use_guideline(self, uploaded: Guideline) -> Guideline:
        """Adopt an uploaded guideline, keeping detection terms already confirmed for the same item."""
        from factlock.domain.models import EmphasisItem

        known = {item.no: item for item in self.guideline.emphasis}
        merged = tuple(
            EmphasisItem(item.no, item.text, known[item.no].any_of, known[item.no].terms_confirmed)
            if item.no in known and not item.any_of
            else item
            for item in uploaded.emphasis
        )
        footer = uploaded.footer or self.guideline.footer
        self.guideline = Guideline(
            uploaded.required_keywords, merged, footer, uploaded.title_keywords, self.guideline.targets
        )
        return self.guideline
