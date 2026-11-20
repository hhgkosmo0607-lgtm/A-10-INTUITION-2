"""Read text from internal documents, page by page: PDF, PowerPoint, Excel, Word, plain text."""

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

from openpyxl import load_workbook
from pypdf import PdfReader

from factlock.ports import DocumentError

MAX_BYTES = 30 * 1024 * 1024
_SPACE = re.compile(r"[ \t ]+")
_DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class Page:
    locator: str  # "3쪽", "슬라이드 2", "시트 Sheet1"
    text: str


def _clean(text: str) -> str:
    lines = (_SPACE.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _pdf(data: bytes) -> list[Page]:
    reader = PdfReader(io.BytesIO(data))
    return [Page(f"{number}쪽", _clean(page.extract_text() or "")) for number, page in enumerate(reader.pages, 1)]


def _paragraphs(xml: bytes, namespace: str) -> str:
    root = ElementTree.fromstring(xml)  # noqa: S314 - office files are zip members, parsed without network access
    lines = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            lines.append(text)
    return _clean("\n".join(lines))


def _pptx(data: bytes) -> list[Page]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        names.sort(key=lambda n: int(re.findall(r"\d+", n)[-1]))
        return [Page(f"슬라이드 {i}", _paragraphs(archive.read(n), _DRAWING)) for i, n in enumerate(names, 1)]


def _docx(data: bytes) -> list[Page]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return [Page("본문", _paragraphs(archive.read("word/document.xml"), _WORD))]


def _xlsx(data: bytes) -> list[Page]:
    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    pages = []
    for sheet in book.worksheets:
        rows = (" | ".join(str(c) for c in row if c is not None) for row in sheet.iter_rows(values_only=True))
        pages.append(Page(f"시트 {sheet.title}", _clean("\n".join(rows))))
    return pages


def _text(data: bytes) -> list[Page]:
    return [Page("본문", _clean(data.decode("utf-8")))]


READERS = {"pdf": _pdf, "pptx": _pptx, "docx": _docx, "xlsx": _xlsx, "txt": _text, "md": _text}


def read_document(filename: str, data: bytes) -> list[Page]:
    """Return non-empty pages. Raises DocumentError with a fixed code, never file content."""
    if len(data) > MAX_BYTES:
        raise DocumentError("document_too_large")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    reader = READERS.get(extension)
    if reader is None:
        raise DocumentError("document_type_unsupported")
    try:
        pages = [page for page in reader(data) if page.text]
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("document_unreadable") from None
    if not pages:
        raise DocumentError("document_has_no_text")
    return pages


class OfficeDocumentReader:
    """Implements ports.DocumentReader for PDF, PowerPoint, Word, Excel and text files."""

    max_bytes = MAX_BYTES

    def read(self, filename: str, data: bytes) -> list[tuple[str, str]]:
        return [(page.locator, page.text) for page in read_document(filename, data)]
