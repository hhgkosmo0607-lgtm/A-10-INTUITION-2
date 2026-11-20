"""The fact list: the single place that knows which facts exist and which may be used."""

import datetime
import hashlib
from collections.abc import Sequence
from dataclasses import replace

from factlock.application.results import UnknownFact
from factlock.domain.extract import extract_values, is_checked
from factlock.domain.models import Fact, FactStatus, Source, Value
from factlock.ports import ExtraFactStore

USABLE = (FactStatus.CONFIRMED, FactStatus.CLAIM)
WRITABLE_KINDS = ("product", "feature", "number", "price", "condition", "pain", "phrase", "company")
ADDED = ("DOC-", "USER-")  # facts added on this computer: read from documents or typed by the marketer
MAX_MUST_INCLUDE = 10


def checked_values(text: str) -> tuple[Value, ...]:
    return tuple(dict.fromkeys(found.value for found in extract_values(text) if is_checked(found.value)))


def short_hash(text: str, length: int = 8) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:length].upper()


class FactCatalog:
    def __init__(self, facts: Sequence[Fact], extra_store: ExtraFactStore | None = None) -> None:
        self._extra_store = extra_store
        extra = extra_store.load() if extra_store else []
        built_in = {fact.id for fact in facts}
        self._facts = [*facts, *(fact for fact in extra if fact.id not in built_in)]
        self._by_id = {fact.id: fact for fact in self._facts}

    def all(self) -> list[Fact]:
        return list(self._facts)

    def get(self, fact_id: str) -> Fact | None:
        return self._by_id.get(fact_id)

    def pick(self, ids: Sequence[str], kind: str = "") -> tuple[Fact, ...]:
        """Known, usable facts for the ids, in order, without duplicates. Unknown ids are dropped."""
        picked: dict[str, Fact] = {}
        for fact_id in ids:
            fact = self._by_id.get(fact_id)
            if fact is None or fact.status not in USABLE or (kind and fact.kind != kind):
                continue
            picked[fact.id] = fact
        return tuple(picked.values())

    def must_include(self, ids: Sequence[str]) -> tuple[Fact, ...]:
        return self.pick(list(ids))[:MAX_MUST_INCLUDE]

    def writable(self) -> tuple[Fact, ...]:
        """Facts an AI step may see: confirmed or claimed, never conflicting or pending."""
        return tuple(f for f in self._facts if f.status in USABLE and f.kind in WRITABLE_KINDS)

    def put(self, fact: Fact) -> None:
        self._facts = [f for f in self._facts if f.id != fact.id] + [fact]
        self._sync()

    def _sync(self) -> None:
        self._by_id = {fact.id: fact for fact in self._facts}
        if self._extra_store is not None:
            self._extra_store.save([fact for fact in self._facts if fact.id.startswith(ADDED)])

    def from_source(self, link: str) -> list[Fact]:
        return [fact for fact in self._facts if fact.source.url == link]

    def discard_from_source(self, link: str) -> int:
        """Remove every fact read from one document. Returns how many were removed."""
        gone = [fact for fact in self._facts if fact.source.url == link and fact.id.startswith("DOC-")]
        self._facts = [fact for fact in self._facts if fact not in gone]
        self._sync()
        return len(gone)

    def add_from_marketer(self, statement: str) -> Fact:
        """A fact the marketer vouches for. Recorded with 'typed by the marketer' as its source."""
        text = " ".join(statement.split())
        fact_id = "USER-" + short_hash(text)
        existing = self._by_id.get(fact_id)
        if existing is not None:
            return existing
        source = Source("담당자가 직접 입력", datetime.date.today().isoformat())
        fact = Fact(fact_id, "feature", text, source, FactStatus.CONFIRMED, checked_values(text))
        self.put(fact)
        return fact

    def _added(self, fact_id: str) -> Fact:
        fact = self._by_id.get(fact_id)
        if fact is None or not fact_id.startswith(ADDED):
            raise UnknownFact(fact_id)
        return fact

    def confirm(self, fact_id: str) -> Fact:
        confirmed = replace(self._added(fact_id), status=FactStatus.CONFIRMED)
        self.put(confirmed)
        return confirmed

    def discard(self, fact_id: str) -> None:
        self._added(fact_id)
        self._facts = [fact for fact in self._facts if fact.id != fact_id]
        self._sync()
