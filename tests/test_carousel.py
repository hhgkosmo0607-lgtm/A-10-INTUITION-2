"""Instagram carousel: fact lock, review and API with a fake writer. No network."""

from pathlib import Path

from fastapi.testclient import TestClient

from factlock.adapters.json_repo import JsonCompanyData
from factlock.adapters.sqlite_store import SqliteDraftStore
from factlock.adapters.stored_writer import StoredCarouselWriter, StoredDraftWriter
from factlock.adapters.xlsx_guideline import XlsxGuidelineReader
from factlock.application.service import FactLockService
from factlock.domain.models import Block, Carousel, DraftRequest, Slide
from factlock.web.app import create_app

DATA = Path(__file__).resolve().parents[1] / "data" / "tlink"


class FakeCarousel:
    def write_carousel(self, request: DraftRequest) -> Carousel:
        return Carousel(
            (
                Slide("고민", "외근 통화,\n회사는 알고 있나요", "통화가 어디에 남는지 살펴보세요."),
                Slide("비용", "A타입 월 30,000원", "상담원당 요금입니다.", ("PRICE-A",)),
                Slide("비용", "A타입 월 9,900원", "상담원당 요금입니다.", ("PRICE-A",)),
                Slide("해결", "이 제목은 스물두 글자를 훌쩍 넘기는 아주 긴 제목입니다", "본문"),
                Slide("해결", "휴대폰 녹취를 서버로", "티링크 모바일이 보관합니다."),
            ),
            (
                Block("sentence", "티링크가 제공한 자료로 만든 광고입니다."),
                Block("sentence", "전국 학교 200여 곳이 씁니다.", ("NUM-SCHOOL",)),
            ),
            ("티링크", "#통화 녹음", "#업계최고", "#티링크"),
            "fake",
        )


def client(tmp_path: Path, live: FakeCarousel | None) -> TestClient:
    company = JsonCompanyData(DATA)
    service = FactLockService(
        company.all(), company.targets(), company.current(), None, StoredDraftWriter(DATA / "drafts"),
        SqliteDraftStore(tmp_path / "t.db"), live_carousel=live,
        stored_carousel=StoredCarouselWriter(DATA / "carousels"),
    )  # fmt: skip
    return TestClient(create_app(service, XlsxGuidelineReader(), "fake"))


def test_ai_carousel_keeps_only_backed_cards_and_tags(tmp_path: Path) -> None:
    data = (
        client(tmp_path, FakeCarousel())
        .post("/api/carousel", json={"target_id": "field-sales", "include_price": True})
        .json()
    )
    assert [s["headline"] for s in data["slides"]] == [
        "외근 통화,\n회사는 알고 있나요",
        "A타입 월 30,000원",
        "이 제목은 스물두 글자를 훌쩍 넘기는 아주 긴 제목입니다",
    ]
    reasons = " / ".join(d["reason"] for d in data["dropped"])
    assert "9,900원" in reasons and "PROD-MOBILE" in reasons and "확인이 필요한" in reasons
    assert data["hashtags"] == ["#티링크", "#통화녹음"]
    verdicts = {r["rule"]: r["verdict"] for r in data["report"]["results"]}
    assert verdicts["C1"] == "pass"  # three cards left is still a workable carousel
    assert verdicts["C2"] == "fail"  # one headline is too long; the card stays so a person can shorten it
    assert verdicts["R7"] == "fail"  # price shown without its conditions


def test_stored_carousel_passes_lock_and_review(tmp_path: Path) -> None:
    data = client(tmp_path, None).post("/api/carousel", json={"target_id": "field-sales", "include_price": True}).json()
    assert data["source"] == "stored"
    assert len(data["slides"]) == 5 and data["dropped"] == []
    assert [r["rule"] for r in data["report"]["results"] if r["verdict"] != "pass"] == []


def test_edited_carousel_is_reviewed_again(tmp_path: Path) -> None:
    body = {
        "target_id": "field-sales",
        "slides": [{"kicker": "비용", "headline": "A타입 월 50,000원", "body": ""}] * 5,
        "caption": "티링크가 제공한 자료로 만든 광고입니다.",
        "hashtags": ["#티링크"],
    }
    data = client(tmp_path, None).post("/api/carousel/review", json=body).json()
    assert next(r for r in data["results"] if r["rule"] == "R4")["verdict"] == "fail"


def test_carousel_without_ai_or_stored_copy_is_503(tmp_path: Path) -> None:
    response = client(tmp_path, None).post("/api/carousel", json={"target_id": "school"})
    assert response.status_code == 503


def test_prices_are_left_out_unless_asked_for(tmp_path: Path) -> None:
    c = client(tmp_path, None)
    car = c.post("/api/carousel", json={"target_id": "field-sales"}).json()
    words = " ".join(s["headline"] + s["body"] for s in car["slides"]) + " ".join(b["text"] for b in car["caption"])
    assert "30,000원" not in words and "부가세" not in words
    assert len(car["slides"]) == 5 and car["slides"][-1]["kicker"] == "문의"
    assert [r["rule"] for r in car["report"]["results"] if r["verdict"] == "fail"] == []
    blog = c.post("/api/drafts", json={"target_id": "field-sales"}).json()
    assert "30,000원" not in blog["body"] and "■ 비용" not in blog["body"]
    assert "아이폰은 사용할 수 없습니다" in blog["body"]  # non-price conditions stay


def test_writer_is_not_shown_price_facts_when_prices_are_off(tmp_path: Path) -> None:
    seen: list[DraftRequest] = []

    class Spy(FakeCarousel):
        def write_carousel(self, request: DraftRequest) -> Carousel:
            seen.append(request)
            return super().write_carousel(request)

    client(tmp_path, Spy()).post("/api/carousel", json={"target_id": "field-sales"})
    assert seen[0].target.quote_items == ()
    assert not [f.id for f in seen[0].facts if f.kind == "price" or f.id in ("COND-VAT", "COND-MIN3")]
    assert any(f.id == "COND-ANDROID" for f in seen[0].facts)


def test_hashtags_are_capped_at_five(tmp_path: Path) -> None:
    data = client(tmp_path, None).post("/api/carousel", json={"target_id": "field-sales"}).json()
    assert len(data["hashtags"]) == 5


def test_too_few_cards_fail_review(tmp_path: Path) -> None:
    body = {"slides": [{"kicker": "", "headline": "한 장", "body": ""}] * 2, "caption": "광고입니다.", "hashtags": []}
    data = client(tmp_path, None).post("/api/carousel/review", json=body).json()
    assert next(r for r in data["results"] if r["rule"] == "C1")["verdict"] == "fail"


def test_marketer_can_add_content_and_review_checks_it_is_there(tmp_path: Path) -> None:
    company = JsonCompanyData(DATA)
    seen: list[DraftRequest] = []

    class Spy(FakeCarousel):
        def write_carousel(self, request: DraftRequest) -> Carousel:
            seen.append(request)
            return super().write_carousel(request)

    from factlock.adapters.extra_facts import JsonExtraFacts

    service = FactLockService(
        company.all(), company.targets(), company.current(), None, StoredDraftWriter(DATA / "drafts"),
        SqliteDraftStore(tmp_path / "t.db"), extra_store=JsonExtraFacts(tmp_path / "extra.json"),
        live_carousel=Spy(), stored_carousel=StoredCarouselWriter(DATA / "carousels"),
    )  # fmt: skip
    c = TestClient(create_app(service, XlsxGuidelineReader(), "fake"))
    added = c.post("/api/facts", json={"statement": "12월 한 달 동안 설치 상담을 무료로 진행합니다."}).json()
    assert (
        added["id"].startswith("USER-") and added["status"] == "confirmed" and added["source"] == "담당자가 직접 입력"
    )
    must = [added["id"], "FEAT-SECURITY"]
    data = c.post("/api/carousel", json={"target_id": "field-sales", "must_include": must}).json()
    assert seen[0].must_include == tuple(must)
    m1 = next(r for r in data["report"]["results"] if r["rule"] == "M1")
    assert m1["verdict"] == "fail" and len(m1["findings"]) == 2  # the fake writer ignored both

    body = "녹취파일은 AES256으로, 비밀번호는 SHA256으로 암호화합니다.\n12월 한 달 동안 설치 상담을 무료로 진행합니다."
    ok = c.post("/api/review", json={"title": "t", "body": body, "must_include": must}).json()
    assert next(r for r in ok["results"] if r["rule"] == "M1")["verdict"] == "pass"
    assert next(r for r in ok["results"] if r["rule"] == "R5")["verdict"] == "pass"  # "12월" is a date, not a value
