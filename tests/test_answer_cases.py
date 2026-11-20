"""Answer cases C1-C10 from docs/DESIGN.md. All texts are synthetic."""

from factlock.adapters.json_repo import JsonCompanyData
from factlock.domain.lock import lock_draft, render_body
from factlock.domain.models import Block, Draft, Verdict
from factlock.domain.quote import build_quote
from factlock.domain.review import review

TITLE = "티링크 비즈레코딩 후기: 통화요약과 업무자동화가 되는 콜센터 프로그램, 영업사원 통화관리"
GOOD = """협찬: 이 글은 티링크의 자료를 제공받아 작성했습니다.
티링크 비즈레코딩은 휴대폰 통화녹음과 인터넷전화 자동녹취를 한곳에 모으는 콜센터 프로그램입니다.
휴대폰, 인터넷전화, PC폰 통화가 하나의 녹취 서버에 모이고 KT, SK, LG 회선을 모두 녹취할 수 있습니다.
티링크 모바일은 안드로이드에서 쓸 수 있고 아이폰은 사용할 수 없습니다.
통화가 끝나면 STT 문자변환과 AI 통화요약, 키워드, 후속 조치 내용이 기록되어 업무자동화에 도움이 됩니다.
직원별 통화량과 평균 통화시간, 상담 이력, 미결 건을 볼 수 있습니다.
통화 기록은 CRM에 연결되어 담당자가 변경되어도 이전 이력을 확인할 수 있습니다.
종합리포트와 경영 대시보드에서 미결 업무와 해지 위험 고객을 확인합니다.
일일 보고서를 쓰는 시간을 줄이고 통화 데이터로 코칭과 성과관리를 할 수 있습니다.
직접 통화 한 건을 녹음하니 AI 요약 화면이 만들어졌습니다.
녹취파일은 AES256, 비밀번호는 SHA256으로 암호화하고 권한을 나눕니다.
A타입은 상담원당 월 30,000원이고 설정비는 300,000원입니다.
가격은 부가세 별도의 예시 견적이며 상담원 최소 3명부터입니다.
단순한 녹음이 아니라 기업용 영업관리 솔루션입니다.
홈페이지: www.tlinkcrm.com
블로그: https://blog.naver.com/mobilecrm
상담 문의: 1877-3836
"""


def run(company: JsonCompanyData, body: str, title: str = TITLE):
    return review(title, body, company.all(), company.current(), company.target("field-sales"))


def verdicts(report) -> dict[str, Verdict]:
    return {r.rule: r.verdict for r in report.results}


def test_c1_text_within_facts_passes(company: JsonCompanyData) -> None:
    report = run(company, GOOD)
    got = verdicts(report)
    failed = {
        rule: [f.message for f in report.result(rule).findings]
        for rule, v in got.items()
        if v is Verdict.FAIL
    }
    assert failed == {}
    assert got["R2"] is Verdict.CHECK  # emphasis terms are not confirmed by a person yet
    assert got["R10"] is Verdict.PASS


def test_c2_wrong_setup_fee_is_a_mismatch(company: JsonCompanyData) -> None:
    body = GOOD.replace("설정비는 300,000원", "설정비는 20만 원")
    result = run(company, body).result("R4")
    assert result.verdict is Verdict.FAIL
    assert "PRICE-SETUP" in result.findings[0].fact_ids
    assert "20만 원" in result.findings[0].sentence


def test_c3_leftover_memos_are_counted(company: JsonCompanyData) -> None:
    body = (
        GOOD
        + "\n[이미지 삽입: 고객 조회 화면]\n[이미지 삽입: 문자 발송 화면]\n[이미지 삽입: 상담 관리 화면]\n"
    )
    result = run(company, body).result("R8")
    assert result.verdict is Verdict.FAIL
    assert len(result.findings) == 3


def test_c4_price_without_vat_condition_fails(company: JsonCompanyData) -> None:
    body = GOOD.replace("가격은 부가세 별도의 예시 견적이며", "가격은 예시 견적이며")
    result = run(company, body).result("R7")
    assert result.verdict is Verdict.FAIL
    assert any("COND-VAT" in f.fact_ids for f in result.findings)


def test_c5_conflicting_school_count_is_locked(company: JsonCompanyData) -> None:
    result = run(company, GOOD + "\n전국 학교 200여 곳에 납품했습니다.\n").result("R6")
    assert result.verdict is Verdict.FAIL
    assert result.findings[0].fact_ids == ("NUM-SCHOOL",)


def test_c6_mobile_recording_without_iphone_condition_fails(company: JsonCompanyData) -> None:
    body = GOOD.replace("티링크 모바일은 안드로이드에서 쓸 수 있고 아이폰은 사용할 수 없습니다.\n", "")
    result = run(company, body).result("R7")
    assert result.verdict is Verdict.FAIL
    assert any("COND-ANDROID" in f.fact_ids for f in result.findings)


def test_c7_ai_sentence_with_wrong_value_is_dropped(company: JsonCompanyData) -> None:
    draft = Draft(
        "제목",
        (
            Block("sentence", "A타입은 상담원당 월 30,000원입니다.", ("PRICE-A",)),
            Block("sentence", "A타입은 상담원당 월 25,000원입니다.", ("PRICE-A",)),
            Block("sentence", "도입 기업은 5,000여 개입니다.", ()),
            Block("sentence", "전국 학교 200여 곳에 납품했습니다.", ("NUM-SCHOOL",)),
            Block("sentence", "이제 화면을 살펴보겠습니다.", ()),
        ),
    )
    locked, dropped = lock_draft(draft, company.all())
    assert [b.text for b in locked.blocks] == [
        "A타입은 상담원당 월 30,000원입니다.",
        "이제 화면을 살펴보겠습니다.",
    ]
    assert len(dropped) == 3
    assert "25,000원" in dropped[0].reason
    assert "확인이 필요한" in dropped[2].reason


def test_c8_quote_for_five_agents_with_report(company: JsonCompanyData) -> None:
    items = [company.get("PRICE-A"), company.get("PRICE-REPORT")]
    quote = build_quote([i for i in items if i], 5, company.all())
    assert quote.ok
    assert quote.monthly_total == 250_000
    assert quote.setup_total == 300_000
    assert len(quote.conditions) == 4  # VAT, estimate, minimum 3 agents, A type only
    assert quote.lines[0].formula == "30,000원 × 5명 = 150,000원"


def test_c9_quote_below_minimum_is_refused(company: JsonCompanyData) -> None:
    item = company.get("PRICE-A")
    assert item is not None
    quote = build_quote([item], 2, company.all())
    assert not quote.ok
    assert "최소 3명" in quote.reason


def test_c10_unfilled_experience_slot_fails_review(company: JsonCompanyData) -> None:
    draft = Draft("제목", (Block("experience_slot", "직접 녹음한 과정을 적는 칸"), Block("footer")))
    body = render_body(draft, company.current(), company.all())
    report = review("제목", body, company.all(), company.current())
    assert report.result("R8").verdict is Verdict.FAIL
    assert report.result("R3").verdict is Verdict.PASS


def test_quote_notes_items_that_cannot_be_priced(company: JsonCompanyData) -> None:
    target = company.target("field-sales")
    assert target is not None
    items = [f for f in (company.get(i) for i in target.quote_items) if f]
    quote = build_quote(items, 5, company.all())
    assert quote.monthly_total == 250_000
    assert any("1 USER" in note for note in quote.notes)
