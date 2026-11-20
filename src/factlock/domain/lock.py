"""Fact lock: keep only AI sentences whose values and product names are backed by the cited facts."""

from collections.abc import Sequence

from factlock.domain.extract import contains, extract_values, is_checked
from factlock.domain.models import Block, Carousel, Draft, Dropped, Fact, FactStatus, Guideline, Slide
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
        if fact.status is FactStatus.PENDING:
            return f"근거 {fact_id}는 담당자가 아직 확정하지 않은 사실이라 쓸 수 없습니다."
        if fact.status is FactStatus.CLAIM and not any(h in block.text for h in HEDGES):
            return f"근거 {fact_id}는 회사 주장입니다. 주장임이 드러나는 표현이 필요합니다."
        refs.append(fact)
    allowed = {value for fact in refs for value in fact.values}
    for item in extract_values(block.text):
        if is_checked(item.value) and item.value not in allowed:
            return f"근거 사실에 없는 값입니다: {item.text}"
    cited = set(block.fact_ids)
    for fact in named:
        # Only the product's own name (its first anchor) forces a citation; looser search words do not.
        if fact.id not in cited and contains(block.text, fact.anchors[0]):
            return f"제품을 말하지만 근거 번호 {fact.id}가 붙어 있지 않습니다: {fact.anchors[0]}"
    for word in SUPERLATIVES:
        if word in block.text and not any(word in fact.statement for fact in refs):
            return f"근거 없는 표현이 있습니다: {word}"
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


HEADLINE_MAX = 24
BODY_MAX = 90
MAX_HASHTAGS = 5


def lock_carousel(carousel: Carousel, facts: Sequence[Fact]) -> tuple[Carousel, tuple[Dropped, ...]]:
    """Keep only cards, caption sentences and hashtags that the cited facts back."""
    by_id = {fact.id: fact for fact in facts}
    named = [fact for fact in facts if fact.kind == "product" and fact.anchors]
    known = {v for f in facts if f.status in (FactStatus.CONFIRMED, FactStatus.CLAIM) for v in f.values}
    dropped: list[Dropped] = []
    slides: list[Slide] = []
    for slide in carousel.slides:
        reason = _check(Block("sentence", slide.text, slide.fact_ids), by_id, named)
        if reason:
            dropped.append(Dropped(slide.text, reason))
        else:
            slides.append(slide)
    caption: list[Block] = []
    for block in carousel.caption:
        reason = _check(block, by_id, named)
        if reason:
            dropped.append(Dropped(block.text, reason))
        else:
            caption.append(block)
    tags: list[str] = []
    for raw in carousel.hashtags:
        tag = "#" + raw.strip().lstrip("#").replace(" ", "")
        values = [i.value for i in extract_values(tag) if is_checked(i.value)]
        if len(tag) < 3 or tag in tags:
            continue
        if any(word in tag for word in SUPERLATIVES) or any(v not in known for v in values):
            dropped.append(Dropped(tag, "근거 없는 표현이나 숫자가 든 해시태그입니다."))
            continue
        tags.append(tag)
    return Carousel(tuple(slides), tuple(caption), tuple(tags[:MAX_HASHTAGS]), carousel.source), tuple(dropped)


def carousel_text(carousel: Carousel) -> str:
    """All words a reader sees, for review: cards, then caption, then hashtags."""
    cards = [f"{s.kicker}. {s.headline.replace(chr(10), ' ')}. {s.body}" for s in carousel.slides]
    return "\n".join([*cards, *(b.text for b in carousel.caption), " ".join(carousel.hashtags)])


def footer_text(guideline: Guideline, facts: Sequence[Fact]) -> str:
    lines = [fact.statement for fact in facts if fact.kind == "contact" and fact.status is FactStatus.CONFIRMED]
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
