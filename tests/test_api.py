"""API tests with a fake live writer. No network."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from factlock.adapters.json_repo import JsonCompanyData
from factlock.adapters.sqlite_store import SqliteDraftStore
from factlock.adapters.stored_writer import StoredDraftWriter
from factlock.adapters.xlsx_guideline import XlsxGuidelineReader
from factlock.application.service import FactLockService
from factlock.domain.models import Block, Draft, DraftRequest
from factlock.ports import DraftWriterError
from factlock.web.app import create_app

DATA = Path(__file__).resolve().parents[1] / "data" / "tlink"


class FakeWriter:
    def __init__(self, fail: str = "") -> None:
        self.fail = fail
        self.seen: DraftRequest | None = None

    def write(self, request: DraftRequest) -> Draft:
        self.seen = request
        if self.fail:
            raise DraftWriterError(self.fail)
        return Draft(
            "통화요약 업무자동화 콜센터 프로그램",
            (
                Block("sentence", "A타입은 상담원당 월 30,000원입니다.", ("PRICE-A",)),
                Block("sentence", "A타입은 상담원당 월 9,900원입니다.", ("PRICE-A",)),
                Block("footer"),
            ),
            "claude",
        )


def make_client(tmp_path: Path, writer: FakeWriter | None) -> TestClient:
    company = JsonCompanyData(DATA)
    service = FactLockService(
        company.all(),
        company.targets(),
        company.current(),
        writer,
        StoredDraftWriter(DATA / "drafts"),
        SqliteDraftStore(tmp_path / "t.db"),
    )
    return TestClient(create_app(service, XlsxGuidelineReader()))


def test_state_lists_targets_and_counts(tmp_path: Path) -> None:
    data = make_client(tmp_path, None).get("/api/state").json()
    assert [t["id"] for t in data["targets"]] == ["field-sales", "remote-callcenter"]
    assert data["live"] is False
    assert data["fact_counts"]["conflict"] == 1


def test_bundle_returns_quote_with_conditions(tmp_path: Path) -> None:
    data = (
        make_client(tmp_path, None).post("/api/bundle", json={"target_id": "field-sales", "agents": 5}).json()
    )
    assert data["quote"]["monthly_total"] == 250_000
    assert data["quote"]["setup_total"] == 300_000
    assert any("아이폰" in c["statement"] for c in data["conditions"])


def test_bundle_below_minimum_explains_why(tmp_path: Path) -> None:
    data = (
        make_client(tmp_path, None).post("/api/bundle", json={"target_id": "field-sales", "agents": 2}).json()
    )
    assert data["quote"]["ok"] is False
    assert "최소 3명" in data["quote"]["reason"]


def test_unknown_target_is_404_with_code(tmp_path: Path) -> None:
    response = make_client(tmp_path, None).post("/api/bundle", json={"target_id": "nope", "agents": 5})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_target"


def test_live_draft_drops_unbacked_sentence(tmp_path: Path) -> None:
    writer = FakeWriter()
    data = make_client(tmp_path, writer).post("/api/drafts", json={"target_id": "field-sales"}).json()
    assert data["source"] == "claude"
    assert len(data["dropped"]) == 1
    assert "9,900원" in data["dropped"][0]["reason"]
    assert "9,900원" not in data["body"]
    assert writer.seen is not None
    assert all(fact.status.value != "conflict" for fact in writer.seen.facts)


def test_live_failure_falls_back_to_stored_draft(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeWriter(fail="claude_unreachable"))
    data = client.post("/api/drafts", json={"target_id": "field-sales"}).json()
    assert data["source"] == "stored"
    assert data["fallback_code"] == "claude_unreachable"
    assert data["dropped"] == []
    assert data["report"]["counts"]["fail"] == 1  # only the unfilled experience slot


@pytest.mark.parametrize("target", ["field-sales", "remote-callcenter"])
def test_stored_drafts_survive_the_fact_lock(tmp_path: Path, target: str) -> None:
    data = make_client(tmp_path, None).post("/api/drafts", json={"target_id": target}).json()
    assert data["dropped"] == []
    failed = [r["rule"] for r in data["report"]["results"] if r["verdict"] == "fail"]
    assert failed == ["R8"]


def test_review_flags_wrong_setup_fee(tmp_path: Path) -> None:
    body = "A타입 설정비는 20만 원입니다.\n[이미지 삽입: 화면]"
    data = make_client(tmp_path, None).post("/api/review", json={"title": "제목", "body": body}).json()
    verdicts = {r["rule"]: r["verdict"] for r in data["results"]}
    assert verdicts["R4"] == "fail"
    assert verdicts["R8"] == "fail"
    assert data["passed"] is False


def test_guideline_upload_keeps_confirmed_terms(tmp_path: Path) -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["필수", "알파, 베타"])
    sheet.append(["강조내용", "1. 첫째 항목\n\n2. 둘째 항목\n\n홈페이지(www.example.com)"])
    buffer = io.BytesIO()
    book.save(buffer)
    client = make_client(tmp_path, None)
    response = client.post("/api/guideline", files={"file": ("g.xlsx", buffer.getvalue())})
    data = response.json()
    assert data["required_keywords"] == ["알파", "베타"]
    assert len(data["emphasis"]) == 2
    assert data["emphasis"][0]["terms"]  # terms for item 1 carried over from the stored guideline


def test_bad_guideline_returns_fixed_code(tmp_path: Path) -> None:
    response = make_client(tmp_path, None).post(
        "/api/guideline", files={"file": ("g.xlsx", b"not a workbook")}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "guideline_unreadable"
    assert "not a workbook" not in response.text
