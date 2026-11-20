"""Read guideline labels and numbered emphasis items from an uploaded workbook."""

import re
from io import BytesIO
from urllib.parse import urlsplit

from openpyxl import load_workbook

from factlock.domain.models import EmphasisItem, Guideline
from factlock.ports import GuidelineError, GuidelineReader

_MAX_BYTES = 2 * 1024 * 1024
_ITEM = re.compile(r"^\s*(\d+)\.\s*", re.MULTILINE)
_FOOTER_LINE = re.compile(r"^.*(?:홈페이지|블로그|상담 문의|리뷰 하단).*$", re.MULTILINE)
_QUOTE = re.compile(r"‘([^’]+)’|'([^']+)'")
_CONTACT = re.compile(
    r"(?P<url>(?:https?://|www\.)[^\s<>()\[\]{}\"'‘’]+)"
    r"|(?P<phone>(?<!\d)\d{2,4}-\d{3,4}-?\d{0,4}(?!\d))",
    re.IGNORECASE,
)


def _read_labels(data: bytes) -> dict[str, str]:
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        labels = {}
        for label, value in workbook.worksheets[0].iter_rows(max_col=2, values_only=True):
            if isinstance(label, str) and label.strip() in {"필수", "강조내용"}:
                labels[label.strip()] = value if isinstance(value, str) else ""
        return labels
    finally:
        workbook.close()


def _footer(text: str) -> tuple[str, ...]:
    contacts = []
    for match in _CONTACT.finditer(text):
        if match.group("url"):
            url = match.group("url").rstrip(".,;:!?")
            parts = urlsplit(url if "://" in url else f"https://{url}")
            contact = parts.netloc.removeprefix("www.") + parts.path
        else:
            contact = match.group("phone")
        if contact not in contacts:
            contacts.append(contact)
    return tuple(contacts)


class XlsxGuidelineReader(GuidelineReader):
    def read(self, data: bytes) -> Guideline:
        if len(data) > _MAX_BYTES:
            raise GuidelineError("guideline_too_large")
        try:
            labels = _read_labels(data)
        except Exception:
            raise GuidelineError("guideline_unreadable") from None

        required = tuple(word.strip() for word in labels.get("필수", "").split(",") if word.strip())
        if not required:
            raise GuidelineError("guideline_missing_required")

        text = labels.get("강조내용", "")
        footer_start = _FOOTER_LINE.search(text)
        body = text[: footer_start.start()] if footer_start else text
        markers = list(_ITEM.finditer(body))
        items = []
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
            items.append(
                EmphasisItem(
                    no=int(marker.group(1)),
                    text=" ".join(body[marker.end() : end].split()),
                    any_of=(),
                    terms_confirmed=False,
                )
            )
        if not items:
            raise GuidelineError("guideline_missing_emphasis")

        first = next((item.text for item in items if item.no == 1), "")
        titles = tuple(match.group(1) or match.group(2) for match in _QUOTE.finditer(first))
        return Guideline(required_keywords=required, emphasis=tuple(items), footer=_footer(text), title_keywords=titles)
