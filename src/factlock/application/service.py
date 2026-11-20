"""Use cases: target plan, bundle and quote, draft with fact lock, review. Depends on domain and ports only."""

import datetime
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace

from factlock.domain.extract import contains, extract_values, is_checked
from factlock.domain.lock import BODY_MAX, HEADLINE_MAX, carousel_text, lock_carousel, lock_draft, render_body
from factlock.domain.models import (
    Block,
    Carousel,
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
    Source,
    Target,
    Verdict,
)
from factlock.domain.quote import build_quote
from factlock.domain.review import must_include_result, review
from factlock.ports import (
    AiError,
    CarouselWriter,
    DraftStore,
    DraftWriter,
    DraftWriterError,
    ExtraFactStore,
    FactExtractor,
    MeaningReviewer,
    TargetPlanner,
)

USABLE_KINDS_FOR_WRITING = ("product", "feature", "number", "price", "condition", "pain", "phrase", "company")
MAX_PRODUCTS = 4
ADDED = ("DOC-", "USER-")  # facts added on this computer: read from documents or typed by the marketer
DOC_KINDS = ("product", "feature", "number", "price", "condition", "company")
CHUNK_CHARS = 12_000
MAX_CHUNKS = 5


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


@dataclass(frozen=True)
class Ingested:
    added: tuple[Fact, ...]
    rejected: tuple[Dropped, ...]  # what the AI proposed and why it was not kept
    pages_read: int
    pages_skipped: int


@dataclass(frozen=True)
class CarouselResult:
    carousel: Carousel
    dropped: tuple[Dropped, ...]
    report: ReviewReport
    fallback_code: str


MIN_SLIDES = 3
MAX_SLIDES = 10  # Instagram shows at most ten cards the same way everywhere


class UnknownTarget(Exception):
    pass


class UnknownFact(Exception):
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
        extractor: FactExtractor | None = None,
        extra_store: ExtraFactStore | None = None,
        live_carousel: CarouselWriter | None = None,
        stored_carousel: CarouselWriter | None = None,
    ) -> None:
        self._live_carousel = live_carousel
        self._stored_carousel = stored_carousel
        self._extra_store = extra_store
        self._extractor = extractor
        extra = extra_store.load() if extra_store else []
        self._facts = [*facts, *(f for f in extra if f.id not in {x.id for x in facts})]
        self._by_id = {fact.id: fact for fact in self._facts}
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
            if (
                fact is None
                or fact.status not in (FactStatus.CONFIRMED, FactStatus.CLAIM)
                or (kind and fact.kind != kind)
            ):
                continue
            picked[fact.id] = fact
        return tuple(picked.values())

    def _replace_fact(self, fact: Fact | None, fact_id: str) -> None:
        self._facts = [f for f in self._facts if f.id != fact_id]
        if fact is not None:
            self._facts.append(fact)
        self._by_id = {f.id: f for f in self._facts}
        if self._extra_store is not None:
            self._extra_store.save([f for f in self._facts if f.id.startswith(ADDED)])

    def ingest_document(self, filename: str, pages: Sequence[tuple[str, str]]) -> Ingested:
        """Ask the AI for facts in a document; keep only those whose quote is really in the text.

        Kept facts are 'pending': they cannot be used in copy until a person confirms them.
        """
        if self._extractor is None:
            raise Unavailable("ai_not_configured")
        chunks: list[list[tuple[str, str]]] = [[]]
        for locator, text in pages:
            if chunks[-1] and sum(len(t) for _, t in chunks[-1]) + len(text) > CHUNK_CHARS:
                chunks.append([])
            chunks[-1].append((locator, text[:CHUNK_CHARS]))
        used = chunks[:MAX_CHUNKS]
        pages_read = sum(len(chunk) for chunk in used)
        by_locator = dict(pages)
        added: list[Fact] = []
        rejected: list[Dropped] = []
        today = datetime.date.today().isoformat()
        name = filename.rsplit("/", 1)[-1][:80]
        for chunk in used:
            try:
                proposals = self._extractor.extract(chunk)
            except AiError as error:
                if not added and not rejected:
                    raise Unavailable(error.code) from None
                break
            for item in proposals:
                statement, quote = item["statement"].strip(), item["quote"].strip()
                page_text = by_locator.get(item["locator"], "")
                if not statement or len(quote) < 4 or item["kind"] not in DOC_KINDS:
                    rejected.append(Dropped(statement or quote, "문장이나 원문 인용이 비어 있습니다."))
                    continue
                if not contains(page_text, quote):
                    rejected.append(Dropped(statement, "인용한 원문을 문서에서 찾지 못했습니다."))
                    continue
                values = tuple(dict.fromkeys(f.value for f in extract_values(statement) if is_checked(f.value)))
                quoted = {f.value for f in extract_values(quote)}
                if any(value not in quoted for value in values):
                    rejected.append(Dropped(statement, "문장의 숫자가 인용한 원문에 없습니다."))
                    continue
                fact_id = "DOC-" + hashlib.sha256(statement.encode()).hexdigest()[:8].upper()
                if fact_id in self._by_id or any(f.id == fact_id for f in added):
                    continue
                anchors = tuple(w for w in item["subject_words"] if len(w) >= 2 and contains(statement, w))[:2]
                source = Source(f"{name} {item['locator']}", today, "", quote[:300])
                added.append(
                    Fact(
                        fact_id, item["kind"], statement, source, FactStatus.PENDING, values, anchors if values else ()
                    )
                )
        for fact in added:
            self._replace_fact(fact, fact.id)
        return Ingested(tuple(added), tuple(rejected), pages_read, len(pages) - pages_read)

    def add_user_fact(self, statement: str) -> Fact:
        """A fact the marketer vouches for. Recorded with 'typed by the marketer' as its source."""
        text = " ".join(statement.split())
        fact_id = "USER-" + hashlib.sha256(text.encode()).hexdigest()[:8].upper()
        existing = self._by_id.get(fact_id)
        if existing is not None:
            return existing
        values = tuple(dict.fromkeys(f.value for f in extract_values(text) if is_checked(f.value)))
        source = Source("담당자가 직접 입력", datetime.date.today().isoformat())
        fact = Fact(fact_id, "feature", text, source, FactStatus.CONFIRMED, values)
        self._replace_fact(fact, fact_id)
        return fact

    def _must(self, ids: Sequence[str]) -> tuple[Fact, ...]:
        return self._pick(list(ids))[:10]

    def confirm_fact(self, fact_id: str) -> Fact:
        fact = self._by_id.get(fact_id)
        if fact is None or not fact_id.startswith(ADDED):
            raise UnknownFact(fact_id)
        confirmed = replace(fact, status=FactStatus.CONFIRMED)
        self._replace_fact(confirmed, fact_id)
        return confirmed

    def discard_fact(self, fact_id: str) -> None:
        if fact_id not in self._by_id or not fact_id.startswith(ADDED):
            raise UnknownFact(fact_id)
        self._replace_fact(None, fact_id)

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
            if fact.status in (FactStatus.CONFIRMED, FactStatus.CLAIM) and fact.kind in USABLE_KINDS_FOR_WRITING
        )

    def _request(self, target: Target, include_price: bool, must: Sequence[Fact] = ()) -> DraftRequest:
        """What a writer may see. Without prices, price facts and conditions only prices need are withheld."""
        facts = self.writable_facts()
        if include_price:
            return DraftRequest(target, self.guideline, facts, True, tuple(f.id for f in must))
        hidden = self._price_only_ids(target) - {f.id for f in must}
        visible = tuple(f for f in facts if f.id not in hidden)
        return DraftRequest(replace(target, quote_items=()), self.guideline, visible, False, tuple(f.id for f in must))

    def _price_only_ids(self, target: Target) -> set[str]:
        prices = [f for f in self._facts if f.kind == "price"]
        needed_elsewhere = {c for f in self._facts if f.kind != "price" for c in f.requires} | set(
            target.must_conditions
        )
        return {f.id for f in prices} | ({c for f in prices for c in f.requires} - needed_elsewhere)

    def _without_price_blocks(self, blocks: Sequence[Block], hidden: set[str]) -> tuple[Block, ...]:
        kept = [b for b in blocks if not set(b.fact_ids) & hidden]
        # Drop a heading left with nothing under it.
        out: list[Block] = []
        for i, block in enumerate(kept):
            nxt = kept[i + 1].type if i + 1 < len(kept) else "end"
            if block.type == "heading" and nxt in ("heading", "footer", "end") and "비용" in block.text:
                continue
            out.append(block)
        return tuple(out)

    def make_draft(
        self, target_id: str, live: bool = True, include_price: bool = True, must_include: Sequence[str] = ()
    ) -> DraftResult:
        target = self.target(target_id)
        must = self._must(must_include)
        request = self._request(target, include_price, must)
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
        if not include_price:
            raw = Draft(raw.title, self._without_price_blocks(raw.blocks, self._price_only_ids(target)), raw.source)
        draft, dropped = lock_draft(raw, self._facts)
        body = render_body(draft, self.guideline, self._facts)
        report = self.review_text(draft.title, body, target.id, False, must_include)
        draft_id = self._store.save(draft, report)
        return DraftResult(draft_id, draft, body, dropped, report, fallback_code)

    def review_carousel(
        self, carousel: Carousel, target: Target | None, must_include: Sequence[str] = ()
    ) -> ReviewReport:
        """Number, condition, leftover and wording rules on the card and caption text, plus a card count."""
        base = review("", carousel_text(carousel), self._facts, Guideline((), (), ()), target)
        kept = tuple(r for r in base.results if r.rule in ("R4", "R5", "R6", "R7", "R8", "R9", "R10"))
        count = len(carousel.slides)
        fits = MIN_SLIDES <= count <= MAX_SLIDES
        note = Finding(f"카드가 {count}장입니다. {MIN_SLIDES}~{MAX_SLIDES}장이 알맞습니다.")
        cards = RuleResult("C1", "카드 장 수", Verdict.PASS if fits else Verdict.FAIL, () if fits else (note,))
        long = [
            Finding(f"카드 {i}의 제목이 {HEADLINE_MAX}자를 넘습니다.", s.headline.replace("\n", " "))
            for i, s in enumerate(carousel.slides, 1)
            if len(s.headline.replace("\n", "")) > HEADLINE_MAX
        ] + [
            Finding(f"카드 {i}의 본문이 {BODY_MAX}자를 넘습니다.", s.body)
            for i, s in enumerate(carousel.slides, 1)
            if len(s.body) > BODY_MAX
        ]
        length = RuleResult("C2", "카드 글자 수", Verdict.FAIL if long else Verdict.PASS, tuple(long))
        extra = (must_include_result(carousel_text(carousel), self._must(must_include)),) if must_include else ()
        return ReviewReport((cards, length, *kept, *extra))

    def make_carousel(
        self, target_id: str, live: bool = True, include_price: bool = True, must_include: Sequence[str] = ()
    ) -> CarouselResult:
        target = self.target(target_id)
        must = self._must(must_include)
        request = self._request(target, include_price, must)
        fallback_code = "" if live else "stored_requested"
        raw: Carousel | None = None
        if live and self._live_carousel is not None:
            try:
                raw = self._live_carousel.write_carousel(request)
            except DraftWriterError as error:
                fallback_code = error.code
        elif live:
            fallback_code = "live_writer_not_configured"
        if raw is None:
            if self._stored_carousel is None:
                raise Unavailable(fallback_code or "stored_draft_missing")
            try:
                raw = self._stored_carousel.write_carousel(request)
            except DraftWriterError:
                raise Unavailable(fallback_code or "stored_draft_missing") from None
        if not include_price:
            hidden = self._price_only_ids(target)
            slides = [s for s in raw.slides if not set(s.fact_ids) & hidden]
            if raw.offer_without_price is not None and len(slides) < len(raw.slides):
                slides.append(raw.offer_without_price)
            caption = tuple(b for b in raw.caption if not set(b.fact_ids) & hidden)
            raw = Carousel(tuple(slides), caption, raw.hashtags, raw.source)
        carousel, dropped = lock_carousel(raw, self._facts)
        return CarouselResult(carousel, dropped, self.review_carousel(carousel, target, must_include), fallback_code)

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

    def review_text(
        self, title: str, body: str, target_id: str | None, ai: bool = False, must_include: Sequence[str] = ()
    ) -> ReviewReport:
        target = self.target(target_id) if target_id else None
        results = list(review(title, body, self._facts, self.guideline, target).results)
        if must_include:
            results.append(must_include_result(f"{title}\n{body}", self._must(must_include)))
        if ai:
            results.append(self._meaning(title, body))
        return ReviewReport(tuple(results))

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
