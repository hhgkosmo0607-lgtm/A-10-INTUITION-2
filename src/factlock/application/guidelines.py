"""Guidelines pile up: each added one is kept, and the ones switched on are applied together."""

import hashlib
from dataclasses import replace

from factlock.domain.extract import squash
from factlock.domain.models import EmphasisItem, Guideline, GuidelineEntry
from factlock.ports import GuidelineStore


class UnknownGuideline(Exception):
    pass


def merge(guidelines: list[Guideline]) -> Guideline:
    """One guideline that asks for everything the given ones ask for, without repeats."""
    keywords: dict[str, None] = {}
    title: dict[str, None] = {}
    footer: dict[str, None] = {}
    items: dict[str, EmphasisItem] = {}
    for guideline in guidelines:
        keywords.update(dict.fromkeys(guideline.required_keywords))
        title.update(dict.fromkeys(guideline.title_keywords))
        footer.update(dict.fromkeys(guideline.footer))
        for item in guideline.emphasis:
            items.setdefault(squash(item.text), item)
    emphasis = tuple(replace(item, no=number) for number, item in enumerate(items.values(), 1))
    # A merged guideline is tied to targets only when every part is.
    scoped = bool(guidelines) and all(guideline.targets for guideline in guidelines)
    targets = tuple(dict.fromkeys(t for g in guidelines for t in g.targets)) if scoped else ()
    return Guideline(tuple(keywords), emphasis, tuple(footer), tuple(title), targets)


class GuidelineBook:
    def __init__(self, builtin: Guideline, store: GuidelineStore | None = None) -> None:
        self._store = store
        saved = store.load() if store else []
        switches = store.load_switches() if store else {}
        entries = [GuidelineEntry("builtin", "기본 가이드라인", builtin, True, True), *saved]
        self._entries = [replace(entry, enabled=switches.get(entry.id, entry.enabled)) for entry in entries]

    @property
    def current(self) -> Guideline:
        return merge([entry.guideline for entry in self._entries if entry.enabled])

    def all(self) -> list[GuidelineEntry]:
        return list(self._entries)

    def _save(self) -> None:
        if self._store is not None:
            self._store.save([entry for entry in self._entries if not entry.builtin])
            self._store.save_switches({entry.id: entry.enabled for entry in self._entries})

    @staticmethod
    def _with_known_terms(item: EmphasisItem, known: dict[str, EmphasisItem]) -> EmphasisItem:
        same = known.get(squash(item.text))
        if item.any_of or same is None:
            return item
        return replace(item, any_of=same.any_of, terms_confirmed=same.terms_confirmed)

    def add(self, name: str, uploaded: Guideline) -> GuidelineEntry:
        """Keep an uploaded guideline next to the others, reusing detection terms known for the same item."""
        known = {squash(item.text): item for entry in self._entries for item in entry.guideline.emphasis}
        emphasis = tuple(self._with_known_terms(item, known) for item in uploaded.emphasis)
        guideline = replace(uploaded, emphasis=emphasis)
        digest = hashlib.sha256(repr(guideline).encode()).hexdigest()[:10]
        entry = GuidelineEntry(f"g-{digest}", name.rsplit("/", 1)[-1][:80] or "가이드라인", guideline)
        self._entries = [e for e in self._entries if e.id != entry.id] + [entry]
        self._save()
        return entry

    def _find(self, entry_id: str) -> GuidelineEntry:
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        raise UnknownGuideline(entry_id)

    def switch(self, entry_id: str, enabled: bool) -> GuidelineEntry:
        switched = replace(self._find(entry_id), enabled=enabled)
        self._entries = [switched if e.id == entry_id else e for e in self._entries]
        self._save()
        return switched

    def remove(self, entry_id: str) -> None:
        if self._find(entry_id).builtin:
            raise UnknownGuideline(entry_id)
        self._entries = [e for e in self._entries if e.id != entry_id]
        self._save()
