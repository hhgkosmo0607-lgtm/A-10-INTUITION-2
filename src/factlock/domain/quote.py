"""Example quote from price facts. Integer won only; conditions always travel with the result."""

from collections.abc import Sequence

from factlock.domain.models import Fact, FactStatus, Quote, QuoteLine


def build_quote(items: Sequence[Fact], agents: int, facts: Sequence[Fact]) -> Quote:
    by_id = {fact.id: fact for fact in facts}
    priced = [fact for fact in items if fact.pricing is not None and fact.status is FactStatus.CONFIRMED]
    minimum = max((fact.pricing.min_agents for fact in priced if fact.pricing), default=1)
    if agents < minimum:
        return Quote(False, agents, reason=f"상담원 수는 최소 {minimum}명부터 계산할 수 있습니다.")
    lines = []
    for fact in priced:
        pricing = fact.pricing
        assert pricing is not None
        if pricing.per_agent:
            monthly = pricing.monthly * agents
            formula = f"{pricing.monthly:,}원 × {agents}명 = {monthly:,}원"
        else:
            monthly = pricing.monthly
            formula = f"{monthly:,}원 (정액)"
        lines.append(QuoteLine(fact.id, fact.statement, monthly, pricing.setup, formula))
    condition_ids = dict.fromkeys(cid for fact in priced for cid in fact.requires)
    conditions = tuple(by_id[cid].statement for cid in condition_ids if cid in by_id)
    notes = tuple(
        f"계산에 넣지 않았습니다(확인 필요): {fact.statement} {fact.scope}".strip()
        for fact in items
        if fact.pricing is None or fact.status is not FactStatus.CONFIRMED
    )
    return Quote(
        True,
        agents,
        tuple(lines),
        sum(line.monthly for line in lines),
        sum(line.setup for line in lines),
        conditions,
        notes,
    )
