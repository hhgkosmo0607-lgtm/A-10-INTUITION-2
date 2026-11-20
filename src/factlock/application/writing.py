"""Produce the two outputs: a blog post and an Instagram carousel. Each goes through the fact lock."""

from collections.abc import Callable

from factlock.application.briefing import WriterBrief
from factlock.application.catalog import FactCatalog
from factlock.application.guidelines import GuidelineBook
from factlock.application.results import CarouselResult, Choices, DraftResult, Unavailable
from factlock.application.reviewing import Reviewing
from factlock.domain.lock import lock_carousel, lock_draft, render_body
from factlock.domain.models import Target
from factlock.ports import CarouselWriter, DraftStore, DraftWriter, DraftWriterError


def write_with_fallback[T](
    live: bool, live_call: Callable[[], T] | None, stored_call: Callable[[], T] | None
) -> tuple[T, str]:
    """Try the live writer, then the stored copy. Returns the result and why the fallback was used, if it was."""
    code = "" if live else "stored_requested"
    if live and live_call is not None:
        try:
            return live_call(), ""
        except DraftWriterError as error:
            code = error.code
    elif live:
        code = "live_writer_not_configured"
    if stored_call is None:
        raise Unavailable(code or "stored_draft_missing")
    try:
        return stored_call(), code
    except DraftWriterError:
        raise Unavailable(code or "stored_draft_missing") from None


class BlogWriting:
    def __init__(
        self,
        catalog: FactCatalog,
        guidelines: GuidelineBook,
        brief: WriterBrief,
        reviewing: Reviewing,
        live: DraftWriter | None,
        stored: DraftWriter,
        store: DraftStore,
    ) -> None:
        self._catalog = catalog
        self._guidelines = guidelines
        self._brief = brief
        self._reviewing = reviewing
        self._live = live
        self._stored = stored
        self._store = store

    @property
    def live_available(self) -> bool:
        return self._live is not None

    def make(self, target: Target, choices: Choices) -> DraftResult:
        live, include_price, must_include = choices.live, choices.include_price, choices.must_include
        pick = self._catalog.must_include
        request = self._brief.request(target, include_price, pick(must_include), pick(choices.emphasize))
        live_writer = self._live
        raw, fallback_code = write_with_fallback(
            live,
            (lambda: live_writer.write(request)) if live_writer is not None else None,
            lambda: self._stored.write(request),
        )
        if not include_price:
            raw = self._brief.draft_without_prices(raw, target)
        facts = self._catalog.all()
        draft, dropped = lock_draft(raw, facts)
        body = render_body(draft, self._guidelines.current, facts)
        report = self._reviewing.text(draft.title, body, target, False, must_include, choices.emphasize)
        draft_id = self._store.save(draft, report)
        return DraftResult(draft_id, draft, body, dropped, report, fallback_code)


class CarouselWriting:
    def __init__(
        self,
        catalog: FactCatalog,
        brief: WriterBrief,
        reviewing: Reviewing,
        live: CarouselWriter | None,
        stored: CarouselWriter | None,
    ) -> None:
        self._catalog = catalog
        self._brief = brief
        self._reviewing = reviewing
        self._live = live
        self._stored = stored

    def make(self, target: Target, choices: Choices) -> CarouselResult:
        live, include_price, must_include = choices.live, choices.include_price, choices.must_include
        pick = self._catalog.must_include
        request = self._brief.request(target, include_price, pick(must_include), pick(choices.emphasize))
        live_writer, stored_writer = self._live, self._stored
        raw, fallback_code = write_with_fallback(
            live,
            (lambda: live_writer.write_carousel(request)) if live_writer is not None else None,
            (lambda: stored_writer.write_carousel(request)) if stored_writer is not None else None,
        )
        if not include_price:
            raw = self._brief.carousel_without_prices(raw, target)
        carousel, dropped = lock_carousel(raw, self._catalog.all())
        report = self._reviewing.carousel(carousel, target, must_include, choices.emphasize)
        return CarouselResult(carousel, dropped, report, fallback_code)
