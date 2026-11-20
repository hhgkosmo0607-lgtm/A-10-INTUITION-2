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
    assert [t["id"] for t in data["targets"]][:2] == ["field-sales", "remote-callcenter"]
    assert len(data["targets"]) == 6
    assert data["live"] is False
    assert data["fact_counts"]["conflict"] == 1


def test_bundle_returns_quote_with_conditions(tmp_path: Path) -> None:
    data = make_client(tmp_path, None).post("/api/bundle", json={"target_id": "field-sales", "agents": 5}).json()
    assert data["quote"]["monthly_total"] == 250_000
    assert data["quote"]["setup_total"] == 300_000
    assert any("아이폰" in c["statement"] for c in data["conditions"])


def test_bundle_below_minimum_explains_why(tmp_path: Path) -> None:
    data = make_client(tmp_path, None).post("/api/bundle", json={"target_id": "field-sales", "agents": 2}).json()
    assert data["quote"]["ok"] is False
    assert "최소 3명" in data["quote"]["reason"]


def test_unknown_target_is_404_with_code(tmp_path: Path) -> None:
    response = make_client(tmp_path, None).post("/api/bundle", json={"target_id": "nope", "agents": 5})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_target"


def test_live_draft_drops_unbacked_sentence(tmp_path: Path) -> None:
    writer = FakeWriter()
    data = (
        make_client(tmp_path, writer)
        .post("/api/drafts", json={"target_id": "field-sales", "include_price": True})
        .json()
    )
    assert data["source"] == "claude"
    assert len(data["dropped"]) == 1
    assert "9,900원" in data["dropped"][0]["reason"]
    assert "9,900원" not in data["body"]
    assert writer.seen is not None
    assert all(fact.status.value != "conflict" for fact in writer.seen.facts)


def test_live_failure_falls_back_to_stored_draft(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeWriter(fail="claude_unreachable"))
    data = client.post("/api/drafts", json={"target_id": "field-sales", "include_price": True}).json()
    assert data["source"] == "stored"
    assert data["fallback_code"] == "claude_unreachable"
    assert data["dropped"] == []
    assert data["report"]["counts"]["fail"] == 1  # only the unfilled experience slot


@pytest.mark.parametrize("target", ["field-sales", "remote-callcenter"])
def test_stored_drafts_survive_the_fact_lock(tmp_path: Path, target: str) -> None:
    data = make_client(tmp_path, None).post("/api/drafts", json={"target_id": target, "include_price": True}).json()
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
    response = make_client(tmp_path, None).post("/api/guideline", files={"file": ("g.xlsx", b"not a workbook")})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "guideline_unreadable"
    assert "not a workbook" not in response.text


class FakePlanner:
    def plan(self, description, facts):  # type: ignore[no-untyped-def]
        return {
            "name": "병원",
            "product_ids": ("PROD-RECORDING", "PROD-NOPE", "NUM-SCHOOL", "FEAT-STT"),
            "pain_ids": ("PAIN-FIND",),
            "price_ids": ("PRICE-C",),
            "condition_ids": (),
            "reason": "병원은 통화 기록이 중요합니다. 도입 병원은 9,999곳입니다.",
        }


class FakeReviewer:
    def review(self, title, body, facts):  # type: ignore[no-untyped-def]
        return [
            {
                "sentence": "아이폰에서도 잘 됩니다.",
                "problem": "자료에는 아이폰을 쓸 수 없다고 되어 있습니다.",
                "fact_id": "COND-ANDROID",
            },
            {"sentence": "글에 없는 문장입니다.", "problem": "지어낸 지적", "fact_id": ""},
        ]


def make_ai_client(tmp_path: Path) -> TestClient:
    company = JsonCompanyData(DATA)
    service = FactLockService(
        company.all(), company.targets(), company.current(), None,
        StoredDraftWriter(DATA / "drafts"), SqliteDraftStore(tmp_path / "t.db"), FakePlanner(), FakeReviewer(),
    )  # fmt: skip
    return TestClient(create_app(service, XlsxGuidelineReader(), "fake"))


def test_planned_target_keeps_only_real_product_facts(tmp_path: Path) -> None:
    client = make_ai_client(tmp_path)
    target = client.post("/api/targets/plan", json={"description": "동네 병원 원무과"}).json()
    assert target["status"] == "ai"
    data = client.post("/api/bundle", json={"target_id": target["id"], "agents": 3}).json()
    assert [p["id"] for p in data["products"]] == ["PROD-RECORDING"]  # unknown, conflicting and non-product ids dropped
    assert data["quote"]["monthly_total"] == 30_000
    assert data["reason"] == ""  # the AI's reason had a number that is not in the fact list


def test_plan_without_ai_is_503_with_code(tmp_path: Path) -> None:
    response = make_client(tmp_path, None).post("/api/targets/plan", json={"description": "동네 병원"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_not_configured"


def test_ai_review_keeps_only_findings_that_quote_the_text(tmp_path: Path) -> None:
    body = "휴대폰 통화도 녹음합니다. 아이폰에서도 잘 됩니다."
    data = make_ai_client(tmp_path).post("/api/review", json={"title": "제목", "body": body, "ai": True}).json()
    r11 = next(r for r in data["results"] if r["rule"] == "R11")
    assert r11["verdict"] == "check"
    assert len(r11["findings"]) == 1
    assert r11["findings"][0]["fact_ids"] == ["COND-ANDROID"]


def test_draft_for_target_without_stored_draft_is_503(tmp_path: Path) -> None:
    response = make_client(tmp_path, None).post("/api/drafts", json={"target_id": "school"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "live_writer_not_configured"


def test_facts_link_only_to_public_pages(tmp_path: Path) -> None:
    facts = {f["id"]: f for f in make_client(tmp_path, None).get("/api/facts").json()}
    assert facts["COND-ANDROID"]["url"].startswith("https://www.tlinkcrm.com/mobile.php#:~:text=")
    assert facts["COND-ANDROID"]["quote"] == "아이폰 사용 불가"
    assert facts["PROD-NAME"]["url"] == ""  # the guideline is a received file, not an online page
    assert all(f["url"] == "" or f["url"].startswith("https://") for f in facts.values())


class SeeingWriter(FakeWriter):
    def write(self, request: DraftRequest) -> Draft:
        self.seen = request
        return super().write(request)


def test_marketer_chooses_problems_and_notices_and_can_reuse_typed_ones(tmp_path: Path) -> None:
    writer = SeeingWriter()
    c = make_client(tmp_path, writer)
    pain = c.post(
        "/api/facts", json={"statement": "외근 뒤 일일 보고서를 쓰느라 퇴근이 늦어집니다.", "kind": "pain"}
    ).json()
    note = c.post("/api/facts", json={"statement": "설치는 평일에만 진행합니다.", "kind": "condition"}).json()
    assert pain["kind"] == "pain" and note["kind"] == "condition"

    saved = c.post("/api/bundle", json={"target_id": "field-sales", "agents": 5}).json()["saved"]
    assert [f["id"] for f in saved["pains"]] == [pain["id"]]  # offered again next time
    assert [f["id"] for f in saved["conditions"]] == [note["id"]]

    body = {"target_id": "field-sales", "pains": [pain["id"]], "conditions": [], "must_include": [note["id"]]}
    c.post("/api/drafts", json=body)
    assert writer.seen is not None
    assert writer.seen.target.pains == (pain["id"],)  # only the checked problem is sent
    assert writer.seen.target.must_conditions == ()  # the unchecked default notice is left out
    assert writer.seen.must_include == (note["id"],)
    shown = {fact.id for fact in writer.seen.facts}
    assert pain["id"] in shown and note["id"] in shown
    assert "PAIN-MOBILE" not in shown  # an unchecked customer problem is not even shown to the writer

    c.post("/api/drafts", json={"target_id": "field-sales"})
    shown = {fact.id for fact in writer.seen.facts}
    assert pain["id"] not in shown and note["id"] not in shown  # typed earlier but not ticked this time
    assert "PAIN-MOBILE" in shown and "PAIN-SCHOOL" not in shown  # only this target's problems


def test_unchecked_notice_is_still_caught_when_its_product_is_mentioned(tmp_path: Path) -> None:
    body = "티링크 모바일은 휴대폰 녹취 파일을 중앙 서버로 전송해 보관합니다."
    data = (
        make_client(tmp_path, None)
        .post("/api/review", json={"title": "t", "body": body, "target_id": "field-sales", "conditions": []})
        .json()
    )
    r7 = next(r for r in data["results"] if r["rule"] == "R7")
    assert r7["verdict"] == "fail" and "COND-ANDROID" in r7["findings"][0]["fact_ids"]


def test_emphasized_items_reach_the_writer_and_a_miss_is_only_a_note(tmp_path: Path) -> None:
    writer = SeeingWriter()
    c = make_client(tmp_path, writer)
    body = {"target_id": "field-sales", "emphasize": ["PROD-REPORT", "PAIN-MOBILE"]}
    data = c.post("/api/drafts", json=body).json()
    assert writer.seen is not None and writer.seen.emphasize == ("PROD-REPORT", "PAIN-MOBILE")
    e1 = next(r for r in data["report"]["results"] if r["rule"] == "E1")
    assert e1["verdict"] == "check"  # the fake draft ignores them: shown to the marketer, not a failure
    assert data["report"]["passed"] is True or all(
        r["rule"] != "E1" for r in data["report"]["results"] if r["verdict"] == "fail"
    )

    said = {"title": "t", "body": "종합리포트를 소개합니다.", "emphasize": ["PROD-REPORT"]}
    ok = c.post("/api/review", json=said).json()
    assert next(r for r in ok["results"] if r["rule"] == "E1")["verdict"] == "pass"
