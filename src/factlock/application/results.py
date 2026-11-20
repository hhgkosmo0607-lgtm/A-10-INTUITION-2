"""What the use cases return, and the errors they raise."""

from dataclasses import dataclass

from factlock.domain.models import Carousel, Draft, Dropped, Fact, Quote, ReviewReport, StoredDocument, Target


@dataclass(frozen=True)
class Choices:
    """What the marketer decided in the content step. None means 'use the target's defaults'."""

    live: bool = True
    include_price: bool = False
    must_include: tuple[str, ...] = ()
    emphasize: tuple[str, ...] = ()
    pains: tuple[str, ...] | None = None
    conditions: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Bundle:
    target: Target
    products: tuple[Fact, ...]
    pains: tuple[Fact, ...]
    conditions: tuple[Fact, ...]
    quote: Quote
    reason: str = ""
    saved_pains: tuple[Fact, ...] = ()  # typed by the marketer earlier, offered for reuse
    saved_conditions: tuple[Fact, ...] = ()
    saved_content: tuple[Fact, ...] = ()


@dataclass(frozen=True)
class DraftResult:
    draft_id: str
    draft: Draft
    body: str
    dropped: tuple[Dropped, ...]
    report: ReviewReport
    fallback_code: str  # empty when the live writer answered


@dataclass(frozen=True)
class CarouselResult:
    carousel: Carousel
    dropped: tuple[Dropped, ...]
    report: ReviewReport
    fallback_code: str


@dataclass(frozen=True)
class Ingested:
    added: tuple[Fact, ...]
    rejected: tuple[Dropped, ...]  # what the AI proposed and why it was not kept
    pages_read: int
    pages_skipped: int


@dataclass(frozen=True)
class DocumentView:
    document: StoredDocument
    link: str
    facts: int
    pending: int


class UnknownDocument(Exception):
    pass


class UnknownTarget(Exception):
    pass


class UnknownFact(Exception):
    pass


class Unavailable(Exception):
    """A step could not run. Carries a fixed code for the HTTP layer."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
