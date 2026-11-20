"""Contracts the application layer depends on. Adapters implement them."""

from typing import Protocol

from factlock.domain.models import Draft, DraftRequest, Fact, Guideline, ReviewReport, Target


class FactRepository(Protocol):
    def all(self) -> list[Fact]: ...

    def get(self, fact_id: str) -> Fact | None: ...


class TargetRepository(Protocol):
    def all(self) -> list[Target]: ...

    def get(self, target_id: str) -> Target | None: ...


class GuidelineRepository(Protocol):
    def current(self) -> Guideline: ...


class GuidelineReader(Protocol):
    """Reads an uploaded guideline spreadsheet. Raises GuidelineError on unreadable input."""

    def read(self, data: bytes) -> Guideline: ...


class DraftWriter(Protocol):
    """Writes a draft from allowed facts only. Raises DraftWriterError when unavailable."""

    def write(self, request: DraftRequest) -> Draft: ...


class DraftStore(Protocol):
    def save(self, draft: Draft, report: ReviewReport) -> str: ...

    def load(self, draft_id: str) -> tuple[Draft, ReviewReport] | None: ...


class GuidelineError(Exception):
    """The uploaded guideline could not be read. Carries a fixed code, never the file content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DraftWriterError(Exception):
    """The draft writer is unavailable (no key, network failure, bad response)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
