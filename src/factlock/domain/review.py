"""Review rules R1-R10. Deterministic: the same text and facts always give the same report."""

import re
from collections.abc import Iterable, Sequence

from factlock.domain.extract import Found, contains, extract_values, is_checked, split_sentences
from factlock.domain.models import (
    Fact,
    FactStatus,
    Finding,
    Guideline,
    ReviewReport,
    RuleResult,
    Target,
    Value,
    Verdict,
)

SUPERLATIVES = ("최고", "최초", "유일", "업계 최저", "100%", "완벽", "무조건", "1위", "독보적", "압도적")
HEDGES = ("회사 설명", "티링크에 따르면", "티링크 측", "회사 측 설명", "회사에 따르면")
DISCLOSURES = ("협찬", "제공받아", "제공 받아", "원고료", "유료 광고", "#광고", "광고입니다", "체험단")
_LEFTOVER = re.compile(
    r"\[[^\]\n]*(?:삽입|이미지|체험 내용|작성|입력|TODO)[^\]\n]*\]|TODO|\{\{[^}]*\}\}|○○|XXX", re.IGNORECASE
)


def _anchored(sentence: str, facts: Iterable[Fact]) -> list[Fact]:
    return [fact for fact in facts if any(contains(sentence, anchor) for anchor in fact.anchors)]


def used_facts(text: str, facts: Sequence[Fact]) -> list[Fact]:
    """Facts a text relies on: an anchor is present and, for facts with values, a value appears nearby."""
    used: dict[str, Fact] = {}
    for sentence in split_sentences(text):
        values = {item.value for item in extract_values(sentence)}
        for fact in _anchored(sentence, facts):
            if not fact.values or values & set(fact.values) or fact.kind in ("product", "feature"):
                used[fact.id] = fact
    return list(used.values())


def _result(rule: str, name: str, findings: list[Finding], verdict: Verdict = Verdict.FAIL) -> RuleResult:
    return RuleResult(rule, name, verdict if findings else Verdict.PASS, tuple(findings))


def _keywords(title: str, body: str, guideline: Guideline) -> RuleResult:
    findings = []
    for keyword in guideline.required_keywords:
        if not contains(title, keyword):
            findings.append(Finding(f"제목에 필수 키워드 '{keyword}'가 없습니다."))
        if not contains(body, keyword):
            findings.append(Finding(f"본문에 필수 키워드 '{keyword}'가 없습니다."))
    return _result("R1", "필수 키워드", findings)


def _emphasis(text: str, guideline: Guideline) -> RuleResult:
    findings = []
    unconfirmed = False
    for item in guideline.emphasis:
        if not item.any_of:
            unconfirmed = True
            findings.append(
                Finding(f"강조 {item.no}번을 알아볼 낱말이 정해지지 않았습니다. 낱말 확인이 필요합니다.")
            )
            continue
        missing = [group for group in item.any_of if not any(contains(text, term) for term in group)]
        if missing:
            wanted = " / ".join(" 또는 ".join(group) for group in missing)
            findings.append(Finding(f"강조 {item.no}번이 빠졌습니다. 필요한 낱말: {wanted}"))
        elif not item.terms_confirmed:
            unconfirmed = True
    only_unconfirmed = unconfirmed and all("낱말 확인" in f.message for f in findings)
    if not findings and unconfirmed:
        return RuleResult(
            "R2",
            "강조 항목",
            Verdict.CHECK,
            (Finding("강조 항목의 낱말을 담당자가 아직 확인하지 않았습니다."),),
        )
    return _result("R2", "강조 항목", findings, Verdict.CHECK if only_unconfirmed else Verdict.FAIL)


def _footer(text: str, guideline: Guideline) -> RuleResult:
    plain = text.replace("https://", "").replace("http://", "").replace("www.", "")
    findings = [
        Finding(f"하단 정보 '{item}'가 없습니다.") for item in guideline.footer if not contains(plain, item)
    ]
    return _result("R3", "하단 정보", findings)


def _same_unit(found: Iterable[Found], units: set[str]) -> list[Found]:
    return [item for item in found if item.value.unit in units and is_checked(item.value)]


def _numbers(text: str, facts: Sequence[Fact]) -> tuple[RuleResult, RuleResult, RuleResult]:
    usable = [f for f in facts if f.status is not FactStatus.CONFLICT]
    conflicts = [f for f in facts if f.status is FactStatus.CONFLICT]
    known: set[Value] = {value for fact in usable for value in fact.values}
    mismatch: list[Finding] = []
    unknown: list[Finding] = []
    locked: list[Finding] = []
    for sentence in split_sentences(text):
        found = extract_values(sentence)
        if not found:
            continue
        settled: set[int] = set()
        for fact in _anchored(sentence, conflicts):
            for item in _same_unit(found, {v.unit for v in fact.values}):
                settled.add(item.start)
                locked.append(
                    Finding(
                        f"'{item.text}'는 자료끼리 값이 달라 확인이 필요한 내용입니다. ({fact.statement})",
                        sentence,
                        (fact.id,),
                    )
                )
        anchored = [fact for fact in _anchored(sentence, usable) if fact.values]
        allowed = {value for fact in anchored for value in fact.values}
        for item in _same_unit(found, {value.unit for value in allowed}):
            if item.start in settled:
                continue
            settled.add(item.start)
            if item.value not in allowed:
                refs = [f for f in anchored if any(v.unit == item.value.unit for v in f.values)]
                detail = "; ".join(fact.statement for fact in refs)
                mismatch.append(
                    Finding(
                        f"'{item.text}'가 자료와 다릅니다. 자료: {detail}",
                        sentence,
                        tuple(f.id for f in refs),
                    )
                )
        for item in found:
            if item.start in settled or not is_checked(item.value) or item.value in known:
                continue
            unknown.append(Finding(f"'{item.text}'는 사실 목록에 없는 값입니다.", sentence))
    return (
        _result("R4", "자료와 다른 값", mismatch),
        _result("R5", "목록에 없는 값", unknown),
        _result("R6", "확인 필요 값", locked),
    )


def _conditions(text: str, facts: Sequence[Fact], target: Target | None) -> RuleResult:
    by_id = {fact.id: fact for fact in facts}
    needed: dict[str, list[str]] = {}
    for fact in used_facts(text, [f for f in facts if f.status is not FactStatus.CONFLICT]):
        for condition_id in fact.requires:
            needed.setdefault(condition_id, []).append(fact.id)
    if target is not None:
        for condition_id in target.must_conditions:
            needed.setdefault(condition_id, []).append(f"타깃 {target.name}")
    findings = []
    for condition_id, reasons in needed.items():
        condition = by_id.get(condition_id)
        if condition is None or any(contains(text, marker) for marker in condition.markers):
            continue
        findings.append(
            Finding(
                f"조건이 빠졌습니다: {condition.statement} (필요한 이유: {', '.join(sorted(set(reasons)))})",
                fact_ids=(condition_id,),
            )
        )
    return _result("R7", "필수 조건", findings)


def _leftovers(text: str) -> RuleResult:
    findings = [Finding(f"작업 메모가 남아 있습니다: {match.group(0)}") for match in _LEFTOVER.finditer(text)]
    return _result("R8", "남은 작업 메모", findings)


def _superlatives(text: str, facts: Sequence[Fact]) -> RuleResult:
    findings = []
    for sentence in split_sentences(text):
        for word in SUPERLATIVES:
            if word not in sentence:
                continue
            backing = [f for f in _anchored(sentence, facts) if word in f.statement]
            confirmed = any(f.status is FactStatus.CONFIRMED for f in backing)
            hedged = any(f.status is FactStatus.CLAIM for f in backing) and any(h in sentence for h in HEDGES)
            if not (confirmed or hedged):
                findings.append(Finding(f"근거 없는 표현 '{word}'가 있습니다.", sentence))
    return _result("R9", "최상급·비교", findings)


def _disclosure(text: str) -> RuleResult:
    if any(marker in text for marker in DISCLOSURES):
        return RuleResult("R10", "광고 표시", Verdict.PASS)
    note = Finding("협찬·광고 표시 문구가 보이지 않습니다. 필요한 글인지 담당자가 확인해 주세요.")
    return RuleResult("R10", "광고 표시", Verdict.CHECK, (note,))


def review(
    title: str, body: str, facts: Sequence[Fact], guideline: Guideline, target: Target | None = None
) -> ReviewReport:
    text = f"{title}\n{body}"
    r4, r5, r6 = _numbers(text, facts)
    return ReviewReport(
        (
            _keywords(title, body, guideline),
            _emphasis(text, guideline),
            _footer(text, guideline),
            r4,
            r5,
            r6,
            _conditions(text, facts, target),
            _leftovers(text),
            _superlatives(text, facts),
            _disclosure(text),
        )
    )
