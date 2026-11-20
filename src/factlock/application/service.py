"""Use cases: target plan, bundle and quote, draft with fact lock, review. Depends on domain and ports only."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from factlock.domain.extract import contains
from factlock.domain.lock import lock_draft, render_body
from factlock.domain.models import (
    Draft,
    DraftRequest,
    Dropped,
    EmphasisItem,
    Fact,
    FactStatus,
    Finding,
    Guideline,
    Quote,
    ReviewReport,
    RuleResult,
    Target,
    Verdict,
)
from factlock.domain.quote import build_quote
from factlock.domain.review import review
from factlock.ports import AiError, DraftStore, DraftWriter, DraftWriterError, MeaningReviewer, TargetPlanner

USABLE_KINDS_FOR_WRITING = ("product", "feature", "number", "price", "condition", "pain", "phrase", "company")
MAX_PRODUCTS = 4


@dataclass(frozen=True)
class Bundle:
    target: Target
    products: tuple[Fact, ...]
    pains: tuple[Fact, ...]
    conditions: tuple[Fact, ...]
    quote: Quote
    reason: str = ""


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


class Unavailable(Exception):
    """A step could not run. Carries a fixed code for the HTTP layer."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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
    ) -> None:
        self._facts = list(facts)
        self._by_id = {fact.id: fact for fact in facts}
        self._targets = {target.id: target for target in targets}
        self._reasons: dict[str, str] = {}
        self.guideline = guideline
        self._live = live_writer
        self._stored = stored_writer
        self._store = store
        self._planner = planner
        self._reviewer = reviewer

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

    def _pick(self, ids: Sequence[str], kind: str = "") -> tuple[Fact, ...]:
        """Known, usable facts for the ids, in order, without duplicates. Unknown ids are dropped."""
        picked: dict[str, Fact] = {}
        for fact_id in ids:
            fact = self._by_id.get(fact_id)
            if fact is None or fact.status is FactStatus.CONFLICT or (kind and fact.kind != kind):
                continue
            picked[fact.id] = fact
        return tuple(picked.values())

    def plan_target(self, description: str) -> Target:
        """Ask the AI which facts fit a free-text customer; keep only ids that exist in the fact list."""
        text = " ".join(description.split())
        if self._planner is None:
            raise Unavailable("ai_not_configured")
        try:
            plan = self._planner.plan(text, self.writable_facts())
        except AiError as error:
            raise Unavailable(error.code) from None
        products = self._pick(plan["product_ids"], "product")[:MAX_PRODUCTS]
        if not products:
            raise Unavailable("no_matching_products")
        conditions = dict.fromkeys(
            [
                *(f.id for f in self._pick(plan["condition_ids"], "condition")),
                *(c for p in products for c in p.requires),
            ]
        )
        target = Target(
            id="custom-" + hashlib.sha256(text.encode()).hexdigest()[:10],
            name=text[:40],
            pains=tuple(f.id for f in self._pick(plan["pain_ids"], "pain")[:3]),
            bundle=tuple(f.id for f in products),
            quote_items=tuple(f.id for f in self._pick(plan["price_ids"], "price")),
            must_conditions=tuple(c for c in conditions if c in self._by_id),
            status="ai",
        )
        self._targets[target.id] = target
        # The AI's explanation is shown only if it survives the same number check as any other text.
        reason = str(plan["reason"])
        report = review("", reason, self._facts, Guideline((), (), ()), None)
        clean = all(report.result(rule).verdict is Verdict.PASS for rule in ("R4", "R5", "R6", "R9"))
        self._reasons[target.id] = reason if clean else ""
        return target

    def bundle(self, target_id: str, agents: int) -> Bundle:
        target = self.target(target_id)
        products = self._pick(target.bundle)
        condition_ids = dict.fromkeys(
            [*target.must_conditions, *(cid for product in products for cid in product.requires)]
        )
        quote = build_quote(self._pick(target.quote_items), agents, self._facts)
        return Bundle(
            target,
            products,
            self._pick(target.pains),
            self._pick(list(condition_ids)),
            quote,
            self._reasons.get(target.id, ""),
        )

    def writable_facts(self) -> tuple[Fact, ...]:
        """Facts an AI step may use: never conflicting ones."""
        return tuple(
            fact
            for fact in self._facts
            if fact.status is not FactStatus.CONFLICT and fact.kind in USABLE_KINDS_FOR_WRITING
        )

    def make_draft(self, target_id: str, live: bool = True) -> DraftResult:
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
            try:
                raw = self._stored.write(request)
            except DraftWriterError:
                raise Unavailable(fallback_code or "stored_draft_missing") from None
        draft, dropped = lock_draft(raw, self._facts)
        body = render_body(draft, self.guideline, self._facts)
        report = review(draft.title, body, self._facts, self.guideline, target)
        draft_id = self._store.save(draft, report)
        return DraftResult(draft_id, draft, body, dropped, report, fallback_code)

    def _meaning(self, title: str, body: str) -> RuleResult:
        name = "AI 의미 검수"
        if self._reviewer is None:
            return RuleResult(
                "R11", name, Verdict.CHECK, (Finding("AI가 연결되어 있지 않아 의미 검수를 하지 못했습니다."),)
            )
        try:
            raw = self._reviewer.review(title, body, self.writable_facts())
        except AiError:
            return RuleResult(
                "R11", name, Verdict.CHECK, (Finding("AI 의미 검수를 하지 못했습니다. 다시 시도해 주세요."),)
            )
        text = f"{title}\n{body}"
        findings = []
        for item in raw[:8]:
            # Keep only findings that quote a sentence really present in the text.
            if not item["sentence"].strip() or not contains(text, item["sentence"]) or not item["problem"].strip():
                continue
            ids = (item["fact_id"],) if item["fact_id"] in self._by_id else ()
            findings.append(Finding(item["problem"], item["sentence"], ids))
        if not findings:
            return RuleResult("R11", name, Verdict.PASS)
        return RuleResult("R11", name, Verdict.CHECK, tuple(findings))

    def review_text(self, title: str, body: str, target_id: str | None, ai: bool = False) -> ReviewReport:
        target = self.target(target_id) if target_id else None
        report = review(title, body, self._facts, self.guideline, target)
        if not ai:
            return report
        return ReviewReport((*report.results, self._meaning(title, body)))

    def use_guideline(self, uploaded: Guideline) -> Guideline:
        """Adopt an uploaded guideline, keeping detection terms already confirmed for the same item."""
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
