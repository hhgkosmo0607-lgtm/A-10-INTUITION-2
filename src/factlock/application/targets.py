"""Targets: the ready-made ones, the ones an AI plans from a description, and what each brings."""

from collections.abc import Sequence

from factlock.application.catalog import FactCatalog, short_hash
from factlock.application.results import Bundle, Unavailable, UnknownTarget
from factlock.domain.models import Guideline, Target, Verdict
from factlock.domain.quote import build_quote
from factlock.domain.review import review
from factlock.ports import AiError, TargetPlanner

MAX_PRODUCTS = 4
MAX_PAINS = 3
NUMBER_RULES = ("R4", "R5", "R6", "R9")


class TargetBook:
    def __init__(self, targets: Sequence[Target], catalog: FactCatalog, planner: TargetPlanner | None) -> None:
        self._targets = {target.id: target for target in targets}
        self._reasons: dict[str, str] = {}
        self._catalog = catalog
        self._planner = planner

    def all(self) -> list[Target]:
        return list(self._targets.values())

    def get(self, target_id: str) -> Target:
        try:
            return self._targets[target_id]
        except KeyError:
            raise UnknownTarget(target_id) from None

    def plan(self, description: str) -> Target:
        """Ask the AI which facts fit a free-text customer; keep only ids that exist in the fact list."""
        text = " ".join(description.split())
        if self._planner is None:
            raise Unavailable("ai_not_configured")
        try:
            plan = self._planner.plan(text, self._catalog.writable())
        except AiError as error:
            raise Unavailable(error.code) from None
        pick = self._catalog.pick
        products = pick(plan["product_ids"], "product")[:MAX_PRODUCTS]
        if not products:
            raise Unavailable("no_matching_products")
        chosen = [fact.id for fact in pick(plan["condition_ids"], "condition")]
        conditions = dict.fromkeys([*chosen, *(cid for product in products for cid in product.requires)])
        target = Target(
            id="custom-" + short_hash(text, 10).lower(),
            name=text[:40],
            pains=tuple(fact.id for fact in pick(plan["pain_ids"], "pain")[:MAX_PAINS]),
            bundle=tuple(fact.id for fact in products),
            quote_items=tuple(fact.id for fact in pick(plan["price_ids"], "price")),
            must_conditions=tuple(cid for cid in conditions if self._catalog.get(cid) is not None),
            status="ai",
        )
        self._targets[target.id] = target
        self._reasons[target.id] = self._safe_reason(str(plan["reason"]))
        return target

    def _safe_reason(self, reason: str) -> str:
        """The AI's explanation is shown only if it survives the same number check as any other text."""
        report = review("", reason, self._catalog.all(), Guideline((), (), ()), None)
        clean = all(report.result(rule).verdict is Verdict.PASS for rule in NUMBER_RULES)
        return reason if clean else ""

    def bundle(self, target_id: str, agents: int) -> Bundle:
        target = self.get(target_id)
        pick = self._catalog.pick
        products = pick(target.bundle)
        condition_ids = dict.fromkeys(
            [*target.must_conditions, *(cid for product in products for cid in product.requires)]
        )
        quote = build_quote(pick(target.quote_items), agents, self._catalog.all())
        return Bundle(
            target,
            products,
            pick(target.pains),
            pick(list(condition_ids)),
            quote,
            self._reasons.get(target.id, ""),
        )
