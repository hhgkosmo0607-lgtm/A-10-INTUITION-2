"""Fact lock: keep only AI sentences whose values and product names are backed by the cited facts."""

from collections.abc import Sequence

from factlock.domain.extract import contains, extract_values, is_checked
from factlock.domain.models import Block, Draft, Dropped, Fact, FactStatus, Guideline
from factlock.domain.review import HEDGES, SUPERLATIVES

SLOT_PREFIX = "[체험 내용: "


def _check(block: Block, by_id: dict[str, Fact], named: Sequence[Fact]) -> str:
    refs = []
    for fact_id in block.fact_ids:
        fact = by_id.get(fact_id)
        if fact is None:
            return f"근거 번호 {fact_id}가 사실 목록에 없습니다."
        if fact.status is FactStatus.CONFLICT:
            return f"근거 {fact_id}는 확인이 필요한 사실이라 쓸 수 없습니다."
        if fact.status is FactStatus.CLAIM and not any(h in block.text for h in HEDGES):
            return f"근거 {fact_id}는 회사 주장입니다. 주장임이 드러나는 표현이 필요합니다."
        refs.append(fact)
    allowed = {value for fact in refs for value in fact.values}
    for item in extract_values(block.text):
        if is_checked(item.value) and item.value not in allowed:
            return f"'{item.text}'가 근거 사실에 없는 값입니다."
    cited = set(block.fact_ids)
    for fact in named:
        if fact.id not in cited and any(contains(block.text, anchor) for anchor in fact.anchors):
            return f"'{fact.anchors[0]}'을(를) 말하지만 근거 번호 {fact.id}가 붙어 있지 않습니다."
    for word in SUPERLATIVES:
        if word in block.text and not any(word in fact.statement for fact in refs):
            return f"근거 없는 표현 '{word}'가 있습니다."
    return ""


def lock_draft(draft: Draft, facts: Sequence[Fact]) -> tuple[Draft, tuple[Dropped, ...]]:
    """Return the draft without unbacked sentences, plus what was dropped and why."""
    by_id = {fact.id: fact for fact in facts}
    named = [fact for fact in facts if fact.kind == "product" and fact.anchors]
    kept: list[Block] = []
    dropped: list[Dropped] = []
    for block in draft.blocks:
        if block.type not in ("sentence", "heading"):
            kept.append(block)
            continue
        reason = _check(block, by_id, named)
        if reason:
            dropped.append(Dropped(block.text, reason))
        else:
            kept.append(block)
    title_reason = _check(Block("heading", draft.title), by_id, [])
    title = draft.title if not title_reason else ""
    if title_reason:
        dropped.append(Dropped(draft.title, title_reason))
    return Draft(title, tuple(kept), draft.source), tuple(dropped)


def footer_text(guideline: Guideline, facts: Sequence[Fact]) -> str:
    lines = [
        fact.statement for fact in facts if fact.kind == "contact" and fact.status is FactStatus.CONFIRMED
    ]
    return "\n".join(lines)


def render_body(draft: Draft, guideline: Guideline, facts: Sequence[Fact]) -> str:
    """Plain text of the draft body. Unfilled experience slots stay visible so review can catch them."""
    parts: list[str] = []
    for block in draft.blocks:
        if block.type == "heading":
            parts.append(f"\n■ {block.text}\n")
        elif block.type == "experience_slot":
            parts.append(f"\n{SLOT_PREFIX}{block.text}]\n")
        elif block.type == "footer":
            parts.append("\n" + footer_text(guideline, facts))
        else:
            parts.append(block.text)
    return "\n".join(parts).strip()
