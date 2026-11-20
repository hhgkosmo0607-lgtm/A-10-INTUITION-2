"""Contracts the application layer depends on. Adapters implement them."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from factlock.domain.models import (
    Asset,
    Carousel,
    Draft,
    DraftRequest,
    Fact,
    Guideline,
    GuidelineEntry,
    ReviewReport,
    StoredDocument,
    Target,
)


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


class CarouselWriter(Protocol):
    """Writes Instagram carousel copy from allowed facts only. Raises DraftWriterError when unavailable."""

    def write_carousel(self, request: DraftRequest) -> Carousel: ...


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


class AiError(Exception):
    """An AI engine could not answer. Carries a fixed code, never prompt or answer text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JsonModel(Protocol):
    """Returns one JSON object shaped by the schema. Raises AiError when unavailable."""

    name: str

    def ask(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class TargetPlanner(Protocol):
    """Proposes fact ids for a free-text customer description. Raises AiError when unavailable."""

    def plan(self, description: str, facts: Sequence[Fact]) -> dict[str, Any]: ...


class MeaningReviewer(Protocol):
    """Finds meaning-level problems rules cannot see. Raises AiError when unavailable."""

    def review(self, title: str, body: str, facts: Sequence[Fact]) -> list[dict[str, str]]: ...


class DocumentError(Exception):
    """An uploaded document could not be read. Carries a fixed code, never the file content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FactExtractor(Protocol):
    """Proposes facts from document text, each with the exact supporting quote. Raises AiError."""

    def extract(self, pages: Sequence[tuple[str, str]]) -> list[dict[str, Any]]: ...


class ExtraFactStore(Protocol):
    def load(self) -> list[Fact]: ...

    def save(self, facts: list[Fact]) -> None: ...


class DocumentReader(Protocol):
    """Turns an uploaded document into (locator, text) pages. Raises DocumentError."""

    max_bytes: int

    def read(self, filename: str, data: bytes) -> list[tuple[str, str]]: ...


class AssetError(Exception):
    """A promo image could not be stored. Carries a fixed code, never file content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AssetLibrary(Protocol):
    max_bytes: int

    def all(self) -> list[Asset]: ...

    def add(self, filename: str, data: bytes, caption: str) -> Asset: ...

    def get(self, asset_id: str) -> tuple[Asset, Path] | None: ...

    def delete(self, asset_id: str) -> bool: ...


class DocumentLibrary(Protocol):
    """Keeps the original files of analysed documents."""

    def all(self) -> list[StoredDocument]: ...

    def add(self, filename: str, data: bytes, pages: int) -> StoredDocument: ...

    def get(self, document_id: str) -> tuple[StoredDocument, Path] | None: ...

    def delete(self, document_id: str) -> bool: ...


class GuidelineStore(Protocol):
    """Keeps added guidelines and which ones are switched on."""

    def load(self) -> list[GuidelineEntry]: ...

    def save(self, entries: Sequence[GuidelineEntry]) -> None: ...

    def load_switches(self) -> dict[str, bool]: ...

    def save_switches(self, switches: dict[str, bool]) -> None: ...
