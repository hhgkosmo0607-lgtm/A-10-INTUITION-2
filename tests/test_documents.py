"""Document reading and fact extraction with a fake AI. All document content is synthetic."""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from factlock.adapters.doc_text import MAX_BYTES, read_document
from factlock.adapters.extra_facts import JsonExtraFacts
from factlock.adapters.json_repo import JsonCompanyData
from factlock.adapters.sqlite_store import SqliteDraftStore
from factlock.adapters.stored_writer import StoredDraftWriter
from factlock.adapters.xlsx_guideline import XlsxGuidelineReader
from factlock.application.service import FactLockService
from factlock.ports import DocumentError
from factlock.web.app import create_app

DATA = Path(__file__).resolve().parents[1] / "data" / "tlink"
DOC = "가나다 상품 안내\n프리미엄 요금제는 월 77,000원입니다.\n설치는 영업일 기준 3일 안에 끝납니다."
SLIDE = (
    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>둘째 </a:t></a:r>'
    "<a:r><a:t>슬라이드</a:t></a:r></a:p></p:sld>"
)


class FakeExtractor:
    def extract(self, pages):  # type: ignore[no-untyped-def]
        return [
            {"statement": "프리미엄 요금제는 월 77,000원입니다.", "quote": "프리미엄 요금제는 월 77,000원입니다.",
             "locator": "본문", "kind": "price", "subject_words": ("프리미엄 요금제",)},
            {"statement": "프리미엄 요금제는 월 55,000원입니다.", "quote": "프리미엄 요금제는 월 77,000원입니다.",
             "locator": "본문", "kind": "price", "subject_words": ("프리미엄 요금제",)},
            {"statement": "24시간 상담을 제공합니다.", "quote": "24시간 상담을 제공합니다.",
             "locator": "본문", "kind": "feature", "subject_words": ()},
        ]  # fmt: skip


def client(tmp_path: Path, extractor: FakeExtractor | None = None) -> TestClient:
    company = JsonCompanyData(DATA)
    service = FactLockService(
        company.all(), company.targets(), company.current(), None, StoredDraftWriter(DATA / "drafts"),
        SqliteDraftStore(tmp_path / "t.db"), None, None, extractor, JsonExtraFacts(tmp_path / "extra.json"),
    )  # fmt: skip
    return TestClient(create_app(service, XlsxGuidelineReader(), "fake"))


def test_reads_text_pptx_and_xlsx() -> None:
    assert read_document("a.txt", DOC.encode())[0].text.startswith("가나다")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/slides/slide2.xml", SLIDE)
        archive.writestr("ppt/slides/slide10.xml", SLIDE.replace("둘째", "열째"))
    pages = read_document("deck.PPTX", buffer.getvalue())
    assert [(p.locator, p.text) for p in pages] == [("슬라이드 1", "둘째 슬라이드"), ("슬라이드 2", "열째 슬라이드")]
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["요금", 77000])
    out = io.BytesIO()
    book.save(out)
    assert "요금 | 77000" in read_document("p.xlsx", out.getvalue())[0].text


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("a.hwp", b"x", "document_type_unsupported"),
        ("a.pdf", b"not a pdf", "document_unreadable"),
        ("a.txt", b"   ", "document_has_no_text"),
        ("a.txt", b"x" * (MAX_BYTES + 1), "document_too_large"),
    ],
)
def test_unreadable_documents_give_fixed_codes(name: str, data: bytes, code: str) -> None:
    with pytest.raises(DocumentError) as error:
        read_document(name, data)
    assert error.value.code == code


def test_only_facts_quoted_from_the_document_are_kept_and_stay_pending(tmp_path: Path) -> None:
    c = client(tmp_path, FakeExtractor())
    data = c.post("/api/documents", files={"file": ("안내.txt", DOC.encode())}).json()
    assert [f["statement"] for f in data["added"]] == ["프리미엄 요금제는 월 77,000원입니다."]
    assert data["added"][0]["status"] == "pending"
    assert data["added"][0]["source"] == "안내.txt 본문"
    assert data["added"][0]["quote"] == "프리미엄 요금제는 월 77,000원입니다."
    reasons = [r["reason"] for r in data["rejected"]]
    assert reasons == ["문장의 숫자가 인용한 원문에 없습니다.", "인용한 원문을 문서에서 찾지 못했습니다."]

    body = "프리미엄 요금제는 월 77,000원입니다."
    before = c.post("/api/review", json={"title": "t", "body": body}).json()
    assert next(r for r in before["results"] if r["rule"] == "R5")["verdict"] == "fail"  # pending is not usable

    fact_id = data["added"][0]["id"]
    assert c.post(f"/api/facts/{fact_id}/confirm").json()["status"] == "confirmed"
    after = c.post("/api/review", json={"title": "t", "body": body}).json()
    assert next(r for r in after["results"] if r["rule"] == "R5")["verdict"] == "pass"
    wrong = c.post("/api/review", json={"title": "t", "body": "프리미엄 요금제는 월 88,000원입니다."}).json()
    assert next(r for r in wrong["results"] if r["rule"] == "R4")["verdict"] == "fail"


def test_confirmed_document_facts_survive_a_restart_and_can_be_discarded(tmp_path: Path) -> None:
    c = client(tmp_path, FakeExtractor())
    fact_id = c.post("/api/documents", files={"file": ("안내.txt", DOC.encode())}).json()["added"][0]["id"]
    c.post(f"/api/facts/{fact_id}/confirm")
    again = client(tmp_path)
    assert any(f["id"] == fact_id and f["status"] == "confirmed" for f in again.get("/api/facts").json())
    assert again.delete(f"/api/facts/{fact_id}").status_code == 200
    assert again.delete("/api/facts/PRICE-A").status_code == 404  # built-in facts cannot be deleted here


def test_document_upload_without_ai_explains(tmp_path: Path) -> None:
    response = client(tmp_path).post("/api/documents", files={"file": ("안내.txt", DOC.encode())})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_not_configured"
