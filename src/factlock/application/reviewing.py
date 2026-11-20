"""Review of blog text and carousel copy: the rules decide, the AI only adds things to look at."""

from collections.abc import Sequence

from factlock.application.catalog import FactCatalog
from factlock.application.guidelines import GuidelineBook
from factlock.domain.extract import contains
from factlock.domain.lock import BODY_MAX, HEADLINE_MAX, carousel_text
from factlock.domain.models import Carousel, Finding, Guideline, ReviewReport, RuleResult, Target, Verdict
from factlock.domain.review import must_include_result, review
from factlock.ports import AiError, MeaningReviewer

MIN_SLIDES = 3
MAX_SLIDES = 10  # Instagram shows at most ten cards the same way everywhere
CAROUSEL_RULES = ("R4", "R5", "R6", "R7", "R8", "R9", "R10")
MAX_AI_FINDINGS = 8
AI_RULE = "AI 의미 검수"


class Reviewing:
    def __init__(self, catalog: FactCatalog, guidelines: GuidelineBook, meaning: MeaningReviewer | None) -> None:
        self._catalog = catalog
        self._guidelines = guidelines
        self._meaning = meaning

    def text(
        self, title: str, body: str, target: Target | None, ai: bool = False, must_include: Sequence[str] = ()
    ) -> ReviewReport:
        results = list(review(title, body, self._catalog.all(), self._guidelines.current, target).results)
        if must_include:
            results.append(must_include_result(f"{title}\n{body}", self._catalog.must_include(must_include)))
        if ai:
            results.append(self._ask_ai(title, body))
        return ReviewReport(tuple(results))

    def carousel(self, carousel: Carousel, target: Target | None, must_include: Sequence[str] = ()) -> ReviewReport:
        """Card count and length, then the number, condition, leftover and wording rules on all the words."""
        words = carousel_text(carousel)
        base = review("", words, self._catalog.all(), Guideline((), (), ()), target)
        kept = tuple(result for result in base.results if result.rule in CAROUSEL_RULES)
        extra = (must_include_result(words, self._catalog.must_include(must_include)),) if must_include else ()
        return ReviewReport((self._card_count(carousel), self._card_length(carousel), *kept, *extra))

    @staticmethod
    def _card_count(carousel: Carousel) -> RuleResult:
        count = len(carousel.slides)
        if MIN_SLIDES <= count <= MAX_SLIDES:
            return RuleResult("C1", "카드 장 수", Verdict.PASS)
        note = Finding(f"카드가 {count}장입니다. {MIN_SLIDES}~{MAX_SLIDES}장이 알맞습니다.")
        return RuleResult("C1", "카드 장 수", Verdict.FAIL, (note,))

    @staticmethod
    def _card_length(carousel: Carousel) -> RuleResult:
        findings = []
        for number, slide in enumerate(carousel.slides, 1):
            if len(slide.headline.replace("\n", "")) > HEADLINE_MAX:
                headline = slide.headline.replace("\n", " ")
                findings.append(Finding(f"카드 {number}의 제목이 {HEADLINE_MAX}자를 넘습니다.", headline))
            if len(slide.body) > BODY_MAX:
                findings.append(Finding(f"카드 {number}의 본문이 {BODY_MAX}자를 넘습니다.", slide.body))
        return RuleResult("C2", "카드 글자 수", Verdict.FAIL if findings else Verdict.PASS, tuple(findings))

    def _ask_ai(self, title: str, body: str) -> RuleResult:
        if self._meaning is None:
            note = Finding("AI가 연결되어 있지 않아 의미 검수를 하지 못했습니다.")
            return RuleResult("R11", AI_RULE, Verdict.CHECK, (note,))
        try:
            raw = self._meaning.review(title, body, self._catalog.writable())
        except AiError:
            note = Finding("AI 의미 검수를 하지 못했습니다. 다시 시도해 주세요.")
            return RuleResult("R11", AI_RULE, Verdict.CHECK, (note,))
        text = f"{title}\n{body}"
        findings = []
        for item in raw[:MAX_AI_FINDINGS]:
            quoted = item["sentence"].strip()
            # Keep only findings that quote a sentence really present in the text.
            if not quoted or not item["problem"].strip() or not contains(text, quoted):
                continue
            ids = (item["fact_id"],) if self._catalog.get(item["fact_id"]) is not None else ()
            findings.append(Finding(item["problem"], item["sentence"], ids))
        return RuleResult("R11", AI_RULE, Verdict.CHECK if findings else Verdict.PASS, tuple(findings))
