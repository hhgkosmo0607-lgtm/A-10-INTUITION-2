"""Read facts from an internal document. The AI proposes; only what the document really says is kept."""

import datetime
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from factlock.application.catalog import FactCatalog, checked_values, short_hash
from factlock.application.results import DocumentView, Ingested, Unavailable, UnknownDocument
from factlock.domain.extract import contains, extract_values
from factlock.domain.models import Dropped, Fact, FactStatus, Source, StoredDocument
from factlock.ports import AiError, DocumentLibrary, DocumentReader, FactExtractor

DOC_KINDS = ("product", "feature", "number", "price", "condition", "company")
CHUNK_CHARS = 12_000
MAX_CHUNKS = 5
MIN_QUOTE = 4
MAX_QUOTE_KEPT = 300

Pages = Sequence[tuple[str, str]]  # (locator, text)


def split_into_chunks(pages: Pages) -> list[list[tuple[str, str]]]:
    chunks: list[list[tuple[str, str]]] = [[]]
    for locator, text in pages:
        if chunks[-1] and sum(len(t) for _, t in chunks[-1]) + len(text) > CHUNK_CHARS:
            chunks.append([])
        chunks[-1].append((locator, text[:CHUNK_CHARS]))
    return chunks


def link_for(document_id: str) -> str:
    """Where the original file of a stored document can be opened."""
    return f"/api/documents/{document_id}/file"


class DocumentIngestion:
    def __init__(
        self,
        catalog: FactCatalog,
        extractor: FactExtractor | None,
        reader: DocumentReader | None = None,
        library: DocumentLibrary | None = None,
    ) -> None:
        self._catalog = catalog
        self._extractor = extractor
        self._reader = reader
        self._library = library

    def _view(self, document: StoredDocument) -> DocumentView:
        facts = self._catalog.from_source(link_for(document.id))
        pending = sum(1 for fact in facts if fact.status is FactStatus.PENDING)
        return DocumentView(document, link_for(document.id), len(facts), pending)

    def stored(self) -> list[DocumentView]:
        return [self._view(document) for document in self._library.all()] if self._library else []

    def original(self, document_id: str) -> tuple[StoredDocument, Path]:
        found = self._library.get(document_id) if self._library else None
        if found is None:
            raise UnknownDocument(document_id)
        return found

    def add(self, filename: str, data: bytes) -> tuple[DocumentView, Ingested]:
        """Read the file, keep the original, then extract facts that point back to it."""
        if self._reader is None or self._library is None:
            raise Unavailable("documents_off")
        if self._extractor is None:
            raise Unavailable("ai_not_configured")
        pages = self._reader.read(filename, data)  # raises DocumentError before anything is stored
        document = self._library.add(filename, data, len(pages))
        result = self.ingest(document.filename, pages, link_for(document.id))
        return self._view(document), result

    def reanalyse(self, document_id: str) -> tuple[DocumentView, Ingested]:
        if self._reader is None:
            raise Unavailable("documents_off")
        document, path = self.original(document_id)
        pages = self._reader.read(document.filename, path.read_bytes())
        result = self.ingest(document.filename, pages, link_for(document.id))
        return self._view(document), result

    def remove(self, document_id: str) -> int:
        """Delete the original and every fact read from it. Returns the number of facts removed."""
        self.original(document_id)
        removed = self._catalog.discard_from_source(link_for(document_id))
        if self._library is not None:
            self._library.delete(document_id)
        return removed

    def ingest(self, filename: str, pages: Pages, link: str = "") -> Ingested:
        """Kept facts are 'pending': they cannot be used in copy until a person confirms them."""
        if self._extractor is None:
            raise Unavailable("ai_not_configured")
        chunks = split_into_chunks(pages)[:MAX_CHUNKS]
        pages_read = sum(len(chunk) for chunk in chunks)
        page_text = dict(pages)
        name = filename.rsplit("/", 1)[-1][:80]
        added: dict[str, Fact] = {}
        rejected: list[Dropped] = []
        for chunk in chunks:
            try:
                proposals = self._extractor.extract(chunk)
            except AiError as error:
                if not added and not rejected:
                    raise Unavailable(error.code) from None
                break
            for item in proposals:
                outcome = self._judge(item, page_text, name, link)
                if isinstance(outcome, Dropped):
                    rejected.append(outcome)
                elif outcome is not None and outcome.id not in added:
                    added[outcome.id] = outcome
        for fact in added.values():
            self._catalog.put(fact)
        return Ingested(tuple(added.values()), tuple(rejected), pages_read, len(pages) - pages_read)

    def _judge(self, item: dict[str, Any], page_text: dict[str, str], name: str, link: str) -> Fact | Dropped | None:
        """A pending fact, the reason it was rejected, or None when the catalog already has it."""
        statement, quote = item["statement"].strip(), item["quote"].strip()
        if not statement or len(quote) < MIN_QUOTE or item["kind"] not in DOC_KINDS:
            return Dropped(statement or quote, "문장이나 원문 인용이 비어 있습니다.")
        if not contains(page_text.get(item["locator"], ""), quote):
            return Dropped(statement, "인용한 원문을 문서에서 찾지 못했습니다.")
        values = checked_values(statement)
        quoted = {found.value for found in extract_values(quote)}
        if any(value not in quoted for value in values):
            return Dropped(statement, "문장의 숫자가 인용한 원문에 없습니다.")
        fact_id = "DOC-" + short_hash(statement)
        if self._catalog.get(fact_id) is not None:
            return None
        subject = tuple(word for word in item["subject_words"] if len(word) >= 2 and contains(statement, word))[:2]
        source = Source(f"{name} {item['locator']}", datetime.date.today().isoformat(), link, quote[:MAX_QUOTE_KEPT])
        return Fact(fact_id, item["kind"], statement, source, FactStatus.PENDING, values, subject if values else ())
