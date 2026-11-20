"""Core data shapes. Pure Python: no web, database or AI imports here."""

from dataclasses import dataclass, field
from enum import StrEnum


class FactStatus(StrEnum):
    CONFIRMED = "confirmed"
    CONFLICT = "conflict"
    CLAIM = "claim"


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    CHECK = "check"


@dataclass(frozen=True)
class Value:
    """A checkable quantity normalised to an integer amount and a unit (원, %, 개, ...)."""

    amount: int
    unit: str


@dataclass(frozen=True)
class Source:
    where: str
    checked: str


@dataclass(frozen=True)
class Pricing:
    monthly: int
    per_agent: bool
    setup: int = 0
    min_agents: int = 1


@dataclass(frozen=True)
class Fact:
    id: str
    kind: str
    statement: str
    source: Source
    status: FactStatus = FactStatus.CONFIRMED
    values: tuple[Value, ...] = ()
    anchors: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    markers: tuple[str, ...] = ()
    scope: str = ""
    pricing: Pricing | None = None


@dataclass(frozen=True)
class Target:
    id: str
    name: str
    pains: tuple[str, ...]
    bundle: tuple[str, ...]
    quote_items: tuple[str, ...]
    must_conditions: tuple[str, ...] = ()
    status: str = "proposed"


@dataclass(frozen=True)
class EmphasisItem:
    no: int
    text: str
    any_of: tuple[tuple[str, ...], ...]
    terms_confirmed: bool = False


@dataclass(frozen=True)
class Guideline:
    required_keywords: tuple[str, ...]
    emphasis: tuple[EmphasisItem, ...]
    footer: tuple[str, ...]
    title_keywords: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()  # target ids this guideline was written for; empty means all


@dataclass(frozen=True)
class Block:
    """One piece of a draft: an AI sentence, a slot a person must fill, or the rule-made footer."""

    type: str  # "sentence" | "heading" | "experience_slot" | "footer"
    text: str = ""
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Draft:
    title: str
    blocks: tuple[Block, ...]
    source: str = "stored"  # "claude" | "stored"


@dataclass(frozen=True)
class DraftRequest:
    target: Target
    guideline: Guideline
    facts: tuple[Fact, ...]


@dataclass(frozen=True)
class Dropped:
    text: str
    reason: str


@dataclass(frozen=True)
class Finding:
    message: str
    sentence: str = ""
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleResult:
    rule: str
    name: str
    verdict: Verdict
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True)
class ReviewReport:
    results: tuple[RuleResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.verdict is not Verdict.FAIL for r in self.results)

    def result(self, rule: str) -> RuleResult:
        return next(r for r in self.results if r.rule == rule)


@dataclass(frozen=True)
class QuoteLine:
    fact_id: str
    label: str
    monthly: int
    setup: int
    formula: str


@dataclass(frozen=True)
class Quote:
    ok: bool
    agents: int
    lines: tuple[QuoteLine, ...] = ()
    monthly_total: int = 0
    setup_total: int = 0
    conditions: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default=())
    reason: str = ""
