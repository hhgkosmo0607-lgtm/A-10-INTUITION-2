"""Synthetic workbook coverage for guideline extraction and safe input errors."""

from io import BytesIO

import pytest
from openpyxl import Workbook

from factlock.adapters.xlsx_guideline import XlsxGuidelineReader
from factlock.domain.models import EmphasisItem, Guideline
from factlock.ports import GuidelineError


def workbook_bytes(rows: list[tuple[str, str]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    other = workbook.create_sheet("Ignored")
    other.append(("필수", "wrong sheet"))
    workbook.active = other
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_reads_first_sheet_keywords_items_quotes_and_footer() -> None:
    data = workbook_bytes(
        [
            (" 필수 \n", "alpha, beta phrase, , gamma "),
            ("서브", "ignored"),
            ("태그", "ignored"),
            ("Other", "ignored"),
            (
                " 강조내용 ",
                "1. Use ‘Title alpha’ and 'Title beta'.\n\n"
                "  Continue   here.\n"
                "2. Second item.\n\n"
                "3. Third\n item.\n"
                "홈페이지(www.example.test)\n"
                "블로그 (https://blog.example.test/synthetic)\n"
                "상담 문의 : 0000-0000  https://www.example.test/help.php\n"
                "리뷰 하단 https://www.example.test 0000-0000",
            ),
        ]
    )

    assert XlsxGuidelineReader().read(data) == Guideline(
        required_keywords=("alpha", "beta phrase", "gamma"),
        emphasis=(
            EmphasisItem(1, "Use ‘Title alpha’ and 'Title beta'. Continue here.", ()),
            EmphasisItem(2, "Second item.", ()),
            EmphasisItem(3, "Third item.", ()),
        ),
        title_keywords=("Title alpha", "Title beta"),
        footer=("example.test", "blog.example.test/synthetic", "0000-0000", "example.test/help.php"),
    )


@pytest.mark.parametrize("label", ["홈페이지", "블로그", "상담 문의", "리뷰 하단"])
def test_footer_lines_end_item_text(label: str) -> None:
    data = workbook_bytes([("필수", "alpha"), ("강조내용", f"1. First item.\n{label} ignored footer")])
    assert XlsxGuidelineReader().read(data).emphasis == (EmphasisItem(1, "First item.", ()),)


def test_accepts_item_numbers_above_nine_and_contacts_anywhere_in_cell() -> None:
    data = workbook_bytes(
        [
            ("필수", "alpha"),
            (
                "강조내용",
                "1. First https://www.example.test/path?ignored=yes#fragment\n12. Second 000-000-0000\n100. Last item.",
            ),
        ]
    )
    guideline = XlsxGuidelineReader().read(data)
    assert tuple(item.no for item in guideline.emphasis) == (1, 12, 100)
    assert guideline.footer == ("example.test/path", "000-000-0000")


@pytest.mark.parametrize(
    ("rows", "code"),
    [
        ([("강조내용", "1. Synthetic item")], "guideline_missing_required"),
        ([("필수", " , \n"), ("강조내용", "1. Synthetic item")], "guideline_missing_required"),
        ([("필수", "alpha")], "guideline_missing_emphasis"),
        ([("필수", "alpha"), ("강조내용", "")], "guideline_missing_emphasis"),
        ([("필수", "alpha"), ("강조내용", "Synthetic item without a number")], "guideline_missing_emphasis"),
    ],
)
def test_rejects_missing_or_empty_required_rows(rows: list[tuple[str, str]], code: str) -> None:
    with pytest.raises(GuidelineError) as error:
        XlsxGuidelineReader().read(workbook_bytes(rows))
    assert error.value.code == code
    assert str(error.value) == code


@pytest.mark.parametrize("data", [b"", b"synthetic private content", b"PK\x03\x04broken archive"])
def test_rejects_unreadable_workbooks_without_content(data: bytes) -> None:
    with pytest.raises(GuidelineError) as error:
        XlsxGuidelineReader().read(data)
    assert error.value.code == "guideline_unreadable"
    assert str(error.value) == "guideline_unreadable"


def test_rejects_more_than_two_megabytes_before_parsing() -> None:
    with pytest.raises(GuidelineError) as error:
        XlsxGuidelineReader().read(b"x" * (2 * 1024 * 1024 + 1))
    assert error.value.code == "guideline_too_large"
    assert str(error.value) == "guideline_too_large"


def test_two_megabytes_is_not_too_large() -> None:
    with pytest.raises(GuidelineError) as error:
        XlsxGuidelineReader().read(b"x" * (2 * 1024 * 1024))
    assert error.value.code == "guideline_unreadable"
