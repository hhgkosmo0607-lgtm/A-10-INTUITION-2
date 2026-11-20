"""Write data/tlink/*.json from one readable table. Edit here, then run: uv run python scripts/build_tlink_data.py"""

import json
import urllib.parse
from pathlib import Path

D = "2026-11-20"
SITE = "홈페이지 www.tlinkcrm.com"
OUT = Path(__file__).resolve().parents[1] / "data" / "tlink"


def won(*amounts: int) -> list[dict[str, object]]:
    return [{"amount": a, "unit": "원"} for a in amounts]


BASE = "https://www.tlinkcrm.com/"
BLOG = "https://blog.naver.com/mobilecrm/"
# More specific hints first, so "티링크 비즈" does not win over a more specific page name.
PAGES = {
    "공식 블로그 2026-10-06 모바일 CRM 글": BLOG + "224433241171",
    "공식 블로그 2026-09-30 AI 녹취 글": BLOG + "224427082392",
    "공식 블로그 2026-10-06 PC폰 글": BLOG + "224433250722",
    "공식 블로그 2026-10-06 콜백 글": BLOG + "224433086858",
    "공식 블로그 2026-10-06 고객관리 글": BLOG + "224433059285",
    "상담신청 페이지": BASE + "center.php",
    "AI 경영분석 보고서": BASE + "report.php",
    "보고서 예시": BASE + "management.php",
    "학교용 녹취": BASE + "school.php",
    "티링크 모바일": BASE + "mobile.php",
    "티링크 PC폰": BASE + "softphone.php",
    "티링크 콜백": BASE + "callback.php",
    "티링크 비즈": BASE + "bizsolution.php",
    "티링크 온": BASE + "tlinkon.php",
    "인터넷전화": BASE + "ipphone.php",
    "AI 녹취": BASE + "recording.php",
    "회사소개": BASE + "info.php",
    "연혁": BASE + "history.php",
    "첫 화면": BASE,
}
# Exact words on the page, so the browser can jump to and highlight them.
QUOTES = {
    "COND-ANDROID": "아이폰 사용 불가",
    "COND-MIN3": "최소 3명",
    "COND-PCADDON": "별도 부가서비스 신청이 필요합니다",
    "NUM-RATE": "녹취 성공률",
    "PRICE-MOBILE": "1 USER 20,000원",
}


def fact(id: str, kind: str, statement: str, where: str, **extra: object) -> dict[str, object]:
    """Online sources get a page link; received files (guideline, manuals, proposal) get none."""
    url = next((link for hint, link in PAGES.items() if hint in where), "")
    quote = QUOTES.get(id, "")
    if url and quote:
        url += "#:~:text=" + urllib.parse.quote(quote)
    source = {"where": where, "checked": D, "url": url, "quote": quote}
    return {"id": id, "kind": kind, "statement": statement, "source": source, **extra}


PRICE_REQ = ["COND-VAT", "COND-ESTIMATE"]
TYPE_REQ = [*PRICE_REQ, "COND-MIN3"]
CENTER = f"{SITE} 상담신청 페이지(견적 계산기)"

FACTS = [
    # contact
    fact("CONTACT-HOME", "contact", "홈페이지: www.tlinkcrm.com", "가이드라인"),
    fact("CONTACT-BLOG", "contact", "블로그: https://blog.naver.com/mobilecrm", "가이드라인"),
    fact("CONTACT-TEL", "contact", "상담 문의: 1877-3836", "가이드라인"),
    fact("CONTACT-FORM", "contact", "상담 신청: https://www.tlinkcrm.com/center.php", "가이드라인"),
    # company and numbers
    fact(
        "CO-FOUNDED",
        "company",
        "㈜티링크앤주인닷컴은 2006년에 설립된 정보통신 전문 기업입니다.",
        f"{SITE} 회사소개",
    ),
    fact("CO-PATENT", "company", "등록 특허는 3건입니다.", f"{SITE} 회사소개", anchors=["특허"]),
    fact(
        "NUM-CLIENTS",
        "number",
        "도입 기업은 1,000여 개입니다.",
        f"{SITE} 첫 화면, 제안서",
        values=[{"amount": 1000, "unit": "개"}],
        anchors=["도입 기업", "개 기업", "기업이 이미"],
    ),
    fact(
        "NUM-RATE",
        "number",
        "인터넷전화 녹취 성공률은 99%입니다.",
        f"{SITE} AI 녹취",
        values=[{"amount": 99, "unit": "%"}],
        anchors=["녹취 성공률", "성공률"],
    ),
    fact(
        "NUM-KEPCO",
        "number",
        "최대 구축 규모는 한국전력 3,000석입니다.",
        f"{SITE} AI 녹취",
        values=[{"amount": 3000, "unit": "석"}],
        anchors=["한국전력", "최대 구축"],
    ),
    fact(
        "NUM-SEJONG",
        "number",
        "세종텔레콤에 1,000석 규모로 구축했습니다.",
        f"{SITE} 학교용 녹취",
        values=[{"amount": 1000, "unit": "석"}, {"amount": 1000, "unit": "USER"}],
        anchors=["세종텔레콤"],
    ),
    fact(
        "NUM-TRAVEL",
        "number",
        "여행박사에 300석 규모로 구축했습니다.",
        f"{SITE} 학교용 녹취",
        values=[{"amount": 300, "unit": "석"}],
        anchors=["여행박사"],
    ),
    fact(
        "NUM-SCHOOL",
        "number",
        "학교 실적은 페이지에 따라 '150여 개'와 '200여 개'로 다릅니다.",
        f"{SITE} 연혁, 학교용 녹취",
        status="conflict",
        values=[{"amount": 150, "unit": "개"}, {"amount": 200, "unit": "개"}],
        anchors=["학교"],
    ),
    fact(
        "EX-CALLS",
        "number",
        "공개된 종합리포트 예시(2026-08-03~08-09)의 한 주 상담은 115건입니다.",
        f"{SITE} 보고서 예시",
        values=[{"amount": 115, "unit": "건"}],
        anchors=["예시", "한 주"],
        scope="종합리포트 예시",
    ),
    # products
    fact(
        "PROD-NAME",
        "product",
        "가이드라인이 정한 제품 이름은 '티링크 비즈레코딩'입니다.",
        "가이드라인",
        anchors=["티링크 비즈레코딩", "비즈레코딩"],
    ),
    fact(
        "PROD-RECORDING",
        "product",
        "티링크 AI 녹취는 인터넷전화·스마트폰·소프트폰 통화를 하나의 녹취 서버에 모으고 STT로 글로 바꿔 요약합니다.",
        f"{SITE} AI 녹취",
        anchors=["티링크 AI 녹취", "AI 녹취"],
    ),
    fact(
        "PROD-MOBILE",
        "product",
        "티링크 모바일은 휴대폰 녹취 파일을 중앙 서버로 전송해 보관합니다.",
        f"{SITE} 티링크 모바일",
        anchors=["티링크 모바일", "모바일 CRM", "휴대폰 통화녹음", "휴대폰 통화 녹음", "휴대폰 녹취"],
        requires=["COND-ANDROID"],
    ),
    fact(
        "PROD-CRM",
        "product",
        "티링크 고객관리(CRM)는 고객 정보와 상담·통화·문자·주문 이력을 한 화면에서 관리합니다.",
        "CRM 매뉴얼",
        anchors=["티링크 고객관리", "티링크노트"],
    ),
    fact(
        "PROD-PCPHONE",
        "product",
        "티링크 PC폰(TlinkPhone)은 전화기 없이 PC에 설치해 쓰는 전화기입니다.",
        f"{SITE} 티링크 PC폰",
        anchors=["PC폰", "TlinkPhone", "티링크폰"],
    ),
    fact(
        "PROD-REPORT",
        "product",
        "종합리포트는 경영 분석 대시보드, 상담원 역량 분석, 인사고과 평가표, 신입사원 교육자료로 이루어집니다.",
        f"{SITE} AI 경영분석 보고서, 제안서",
        anchors=["종합리포트", "종합 리포트"],
    ),
    fact(
        "PROD-BIZ",
        "product",
        "티링크 비즈는 상담 현황판, 자동 배분, 콜백 예약, IVR, 녹취 연동을 묶은 콜센터 솔루션입니다.",
        f"{SITE} 티링크 비즈",
        anchors=["티링크 비즈 콜센터", "콜센터 솔루션"],
    ),
    # features
    fact(
        "FEAT-UNIFIED",
        "feature",
        "사무실 인터넷 전화기, 외근 중 스마트폰, 재택 소프트폰의 통화가 하나의 녹취 서버에 모입니다.",
        f"{SITE} AI 녹취",
    ),
    fact(
        "FEAT-MIRROR",
        "feature",
        "라우터와 패킷 미러링 스위치로 통화를 복제해 녹음하므로 기존 회선과 전화기를 바꾸지 않습니다.",
        f"{SITE} AI 녹취",
        anchors=["미러링"],
    ),
    fact("FEAT-CARRIER", "feature", "LG, SK, KT, 삼성SDS 회선을 모두 녹취할 수 있습니다.", f"{SITE} AI 녹취"),
    fact(
        "FEAT-STT",
        "feature",
        "통화가 끝나면 STT 문자변환, 한 줄 요약, 키워드, 화자별 대화가 기록됩니다.",
        "제안서, 휴대폰 매뉴얼",
    ),
    fact(
        "FEAT-FOLLOWUP",
        "feature",
        "가이드라인은 통화 후 고객 요청사항과 후속 조치 내용이 자동으로 기록된다고 설명합니다.",
        "가이드라인",
    ),
    fact(
        "FEAT-STATS",
        "feature",
        "통화 통계는 총 통화, 수신·발신, 평균 통화시간, 담당자별 통화량을 보여 줍니다.",
        "CRM 매뉴얼",
    ),
    fact("FEAT-HISTORY", "feature", "고객 화면에 그 고객의 상담·통화·문자·주문 이력이 쌓입니다.", "CRM 매뉴얼"),
    fact(
        "FEAT-REASSIGN",
        "feature",
        "가이드라인은 담당자가 변경되어도 이전 상담 이력을 빠르게 확인할 수 있다고 설명합니다.",
        "가이드라인",
    ),
    fact(
        "FEAT-DASH",
        "feature",
        "경영 분석 대시보드는 핵심 지표, 영업기회 현황, 미결 건 추적, 해지 위험 고객 조기경보, RED 알림을 보여 줍니다.",
        f"{SITE} 보고서 예시",
    ),
    fact(
        "FEAT-EVAL",
        "feature",
        "상담원 역량 분석과 인사고과 평가표는 통화 원문을 근거로 하며, 표본이 부족하면 '평가 표본 부족'으로 표시합니다.",
        f"{SITE} 보고서 예시, 제안서",
    ),
    fact(
        "FEAT-TRAIN",
        "feature",
        "신입사원 교육자료는 Best·Worst 사례집, 상황별 응대 플레이북, 롤플레잉 시나리오로 이루어집니다.",
        "제안서",
    ),
    fact(
        "FEAT-SECURITY",
        "feature",
        "녹취파일은 AES256으로, 비밀번호는 SHA256으로 암호화합니다.",
        f"{SITE} AI 녹취",
    ),
    fact(
        "FEAT-ROLE",
        "feature",
        "권한은 상담원과 매니저로 나뉘고, 통계와 리포트는 매니저 이상만 볼 수 있습니다.",
        "CRM 매뉴얼",
    ),
    fact(
        "FEAT-DAILY",
        "feature",
        "일일 리포트는 통화·상담·매출 현황과 담당자별 실적을 요약합니다.",
        "CRM 매뉴얼",
    ),
    fact(
        "FEAT-PDF",
        "feature",
        "종합리포트는 시작일과 종료일을 고르면 생성되고 PDF로 내려받을 수 있습니다.",
        "CRM 매뉴얼",
    ),
    fact(
        "FEAT-PCSTT",
        "feature",
        "PC폰은 통화 중 음성을 글로 바꿔 보여 주고 외국어 통화를 통역합니다.",
        f"{SITE} 티링크 PC폰",
        anchors=["실시간 STT", "실시간 통역", "실시간 텍스트"],
        requires=["COND-PCADDON"],
    ),
    fact(
        "FEAT-PCANY",
        "feature",
        "PC폰은 사무실, 재택, 외근 어디서나 같은 내선번호로 걸고 받습니다.",
        f"{SITE} 티링크 PC폰",
    ),
    fact(
        "FEAT-CALLBACK",
        "feature",
        "티링크 콜백은 모든 상담원이 통화 중일 때 고객을 대기시키고 통화 대기 목록을 보여 줍니다.",
        f"{SITE} 티링크 콜백",
    ),
    # school recording
    fact(
        "PROD-SCHOOL",
        "product",
        "학교용 녹취는 녹취서버 1대로 교내 인터넷전화 전체를 녹음하는 구매형 상품입니다.",
        f"{SITE} 학교용 녹취",
        anchors=["학교용 녹취", "티링크레코딩"],
        scope="학교",
    ),
    fact(
        "FEAT-SCHOOL-ID",
        "feature",
        "선생님마다 개인 계정이 주어져 본인 통화만 확인하고, 전체 확인은 관리자만 할 수 있습니다.",
        f"{SITE} 학교용 녹취",
        scope="학교",
    ),
    fact(
        "FEAT-SCHOOL-NET",
        "feature",
        "학교용 녹취서버는 학내망에서만 접속할 수 있습니다.",
        f"{SITE} 학교용 녹취",
        scope="학교",
    ),
    fact(
        "FEAT-SCHOOL-KEEP",
        "feature",
        "학교용 녹취는 통신사가 바뀌어도 기존 녹취파일을 보관합니다.",
        f"{SITE} 학교용 녹취",
        scope="학교",
    ),
    fact(
        "FEAT-SCHOOL-LOG",
        "feature",
        "누가 언제 어떤 녹음을 들었는지 재생 기록이 남습니다.",
        f"{SITE} 학교용 녹취",
        scope="학교",
    ),
    fact(
        "PAIN-SCHOOL",
        "pain",
        "녹음되는 전화기가 민원실에만 있어 민원 전화를 받으면 자리를 옮겨야 합니다.",
        f"{SITE} 학교용 녹취",
    ),
    fact(
        "PAIN-SCHOOL-COMPLAINT",
        "pain",
        "일부 학부모의 악성 민원이 교육 활동 침해를 넘어 선생님 개인에게까지 이어지고 있습니다.",
        f"{SITE} 학교용 녹취",
    ),
    fact(
        "PRICE-SCHOOL",
        "price",
        "학교용 녹취서버는 교내 전화기 전체 기준 1,500,000원이며 구축 시 1회만 청구하고 월 사용요금이 없습니다.",
        f"{SITE} 학교용 녹취",
        values=won(1_500_000),
        anchors=["학교용 녹취서버", "구축 비용"],
        requires=["COND-SCHOOL-ENV"],
        pricing={"monthly": 0, "per_agent": False, "setup": 1_500_000, "min_agents": 1},
        scope="학교",
    ),
    fact(
        "COND-SCHOOL-ENV",
        "condition",
        "학교용 녹취의 실제 견적은 학교 환경에 따라 달라질 수 있습니다.",
        f"{SITE} 학교용 녹취",
        markers=["환경에 따라"],
    ),
    # callback, small office
    fact(
        "PROD-CALLBACK",
        "product",
        "티링크 콜백은 부재중 통화를 모아서 확인할 수 있는 콜백 알리미 시스템입니다.",
        f"{SITE} 티링크 콜백",
        anchors=["티링크 콜백", "콜백 알리미"],
    ),
    fact(
        "PAIN-MISSED",
        "pain",
        "상담원이 모두 통화 중이거나 자리를 비운 사이 걸려 온 전화는 그대로 끊깁니다.",
        "공식 블로그 2026-10-06 콜백 글",
    ),
    fact(
        "PAIN-WHO",
        "pain",
        "전화가 걸려 왔을 때 이 고객이 누구였는지, 지난번에 무슨 상담을 했는지 찾느라 응대가 늦어집니다.",
        "공식 블로그 2026-10-06 고객관리 글",
    ),
    fact(
        "FEAT-POPUP",
        "feature",
        "전화가 오는 순간 상담원 PC 화면에 고객 정보가 팝업으로 뜹니다.",
        "공식 블로그 2026-10-06 고객관리 글",
    ),
    fact(
        "FEAT-CLICKCALL",
        "feature",
        "고객 화면에서 버튼을 누르면 연결된 단말기에서 바로 전화가 발신됩니다.",
        "공식 블로그 2026-10-06 고객관리 글",
    ),
    fact(
        "FEAT-SMS",
        "feature",
        "고객관리 화면에서 SMS·LMS·MMS 문자를 보내고, 엑셀로 수신자를 올려 대량 발송할 수 있습니다.",
        "CRM 매뉴얼",
    ),
    # telemarketing
    fact(
        "PAIN-TM",
        "pain",
        "일반전화(02, 031, 070 등)로 걸면 고객이 잘 받지 않습니다.",
        f"{SITE} 티링크 모바일",
    ),
    fact(
        "FEAT-010",
        "feature",
        "발신번호 변작 없이 010 번호를 그대로 사용해 발신합니다.",
        f"{SITE} 티링크 모바일",
    ),
    fact("FEAT-CARD", "feature", "명함을 사진으로 찍어 등록하고 관리할 수 있습니다.", f"{SITE} 티링크 모바일"),
    fact(
        "FEAT-FACE",
        "feature",
        "모바일 앱에서 고객을 직접 만나 나눈 대화도 녹음(대면 녹취)할 수 있습니다.",
        "공식 블로그 2026-10-06 모바일 CRM 글",
    ),
    # multilingual sites
    fact(
        "PROD-ON",
        "product",
        "티링크온은 LTE·Wi-Fi 네트워크 기반의 업무용 PTT 무전 솔루션입니다.",
        f"{SITE} 티링크 온",
        anchors=["티링크온", "티링크 온"],
    ),
    fact(
        "FEAT-ON-RANGE",
        "feature",
        "티링크온은 인터넷망을 사용해 무전 주파수 반경의 제약 없이 통신합니다.",
        f"{SITE} 티링크 온",
    ),
    fact(
        "FEAT-ON-TRANSLATE",
        "feature",
        "티링크온의 AI 실시간 통역은 부가서비스이며 30개국 이상의 언어를 지원합니다.",
        f"{SITE} 티링크 온",
        values=[{"amount": 30, "unit": "개"}],
        anchors=["개국"],
    ),
    fact(
        "FEAT-ON-LOG",
        "feature",
        "무전 통화와 통역 세션이 서버에 자동으로 기록되고 요약됩니다.",
        f"{SITE} 티링크 온",
    ),
    fact(
        "FEAT-ON-SOS",
        "feature",
        "버튼을 3초간 누르면 회사 전체 사용자에게 긴급알림이 전파됩니다.",
        f"{SITE} 티링크 온",
    ),
    fact(
        "PAIN-ON",
        "pain",
        "외국인 근로자가 함께 일하는 현장에서는 작업 지시를 여러 언어로 전달해야 합니다.",
        f"{SITE} 티링크 온",
    ),
    # pains (from the company's own pages)
    fact(
        "PAIN-MOBILE",
        "pain",
        "휴대폰으로 통화하면 녹음이 직원 개인 폰에만 남고, 누가 어떤 고객과 무슨 이야기를 했는지 회사에서 알 수 없습니다.",
        "공식 블로그 2026-10-06 모바일 CRM 글",
    ),
    fact(
        "PAIN-NO-RECORD",
        "pain",
        "영업직원은 통화 후 CRM에 기록을 남기지 않고, 회의록은 불완전하거나 미작성 상태로 남습니다.",
        f"{SITE} 첫 화면",
    ),
    fact(
        "PAIN-FIND",
        "pain",
        "고객이 한 말을 확인하려면 녹음 파일을 하나하나 찾아 들어야 합니다.",
        "공식 블로그 2026-09-30 AI 녹취 글",
    ),
    fact(
        "PAIN-REMOTE",
        "pain",
        "재택근무에서는 개인 휴대폰으로 전화를 받게 되고 고객에게 개인 번호가 남습니다.",
        f"{SITE} 티링크 PC폰",
    ),
    fact(
        "PAIN-PHONE-SET",
        "pain",
        "재택근무자가 늘면 직원마다 전화기를 새로 놓아야 하는지가 고민입니다.",
        "공식 블로그 2026-10-06 PC폰 글",
    ),
    # phrases the company itself uses
    fact("PHRASE-REPORT", "phrase", "통화가 끝나면, 보고서가 시작됩니다.", "제안서"),
    fact("PHRASE-AI", "phrase", "기록은 AI에게, 성장은 당신에게.", f"{SITE} 첫 화면"),
    fact(
        "PHRASE-TOOL",
        "phrase",
        "상담원을 감시하는 도구가 아니라, 경영자가 팀 전체를 한눈에 읽고 다음 결정을 내리게 돕는 도구입니다.",
        f"{SITE} 첫 화면",
    ),
    # prices
    fact(
        "PRICE-A",
        "price",
        "A타입(고객관리 + 녹취 + 문자변환·요약 + 일일보고서)은 상담원당 월 30,000원입니다.",
        CENTER,
        values=won(30_000, 300_000),
        anchors=["A타입"],
        requires=TYPE_REQ,
        pricing={"monthly": 30_000, "per_agent": True, "setup": 300_000, "min_agents": 3},
    ),
    fact(
        "PRICE-B",
        "price",
        "B타입(고객관리 + 녹취)은 상담원당 월 20,000원입니다.",
        CENTER,
        values=won(20_000, 300_000),
        anchors=["B타입"],
        requires=TYPE_REQ,
        pricing={"monthly": 20_000, "per_agent": True, "setup": 300_000, "min_agents": 3},
    ),
    fact(
        "PRICE-C",
        "price",
        "C타입(녹취)은 상담원당 월 10,000원입니다.",
        CENTER,
        values=won(10_000, 300_000),
        anchors=["C타입"],
        requires=TYPE_REQ,
        pricing={"monthly": 10_000, "per_agent": True, "setup": 300_000, "min_agents": 3},
    ),
    fact(
        "PRICE-SETUP",
        "price",
        "A·B·C 타입의 최초 설정비는 300,000원입니다.",
        CENTER,
        values=won(300_000),
        anchors=["설정비", "설치비"],
        requires=PRICE_REQ,
    ),
    fact(
        "PRICE-REPORT",
        "price",
        "종합리포트는 월 100,000원이며 매월 3회까지 생성할 수 있습니다.",
        CENTER,
        values=won(100_000),
        anchors=["종합리포트", "종합 리포트"],
        requires=[*PRICE_REQ, "COND-ATYPE"],
        pricing={"monthly": 100_000, "per_agent": False, "setup": 0, "min_agents": 1},
    ),
    fact(
        "PRICE-IVR",
        "price",
        "IVR(대표번호 안내멘트)은 월 20,000원, 설정비 50,000원입니다.",
        CENTER,
        values=won(20_000, 50_000),
        anchors=["IVR"],
        requires=PRICE_REQ,
        pricing={"monthly": 20_000, "per_agent": False, "setup": 50_000, "min_agents": 1},
    ),
    fact(
        "PRICE-CALLBACK",
        "price",
        "콜백은 월 20,000원, 설정비 50,000원입니다.",
        CENTER,
        values=won(20_000, 50_000),
        anchors=["콜백"],
        requires=PRICE_REQ,
        pricing={"monthly": 20_000, "per_agent": False, "setup": 50_000, "min_agents": 1},
    ),
    fact(
        "PRICE-MOBILE",
        "price",
        "티링크 모바일 이용료는 1 USER 20,000원입니다.",
        f"{SITE} 티링크 모바일",
        values=won(20_000),
        anchors=["1 USER", "USER"],
        scope="(A·B·C 타입 요금과의 관계는 자료에 없습니다.)",
    ),
    # conditions
    fact("COND-VAT", "condition", "가격은 부가세 별도입니다.", CENTER, markers=["부가세 별도", "VAT 별도"]),
    fact(
        "COND-ESTIMATE",
        "condition",
        "표시된 금액은 예시 견적이며 정확한 비용은 상담 후 확정됩니다.",
        CENTER,
        markers=["예시 견적", "예상 견적", "상담 후 확정"],
    ),
    fact("COND-MIN3", "condition", "A·B·C 타입은 상담원 최소 3명부터입니다.", CENTER, markers=["최소 3명"]),
    fact(
        "COND-ATYPE",
        "condition",
        "종합리포트는 A타입을 선택한 경우에만 이용할 수 있습니다.",
        CENTER,
        markers=["A타입"],
    ),
    fact(
        "COND-ANDROID",
        "condition",
        "티링크 모바일은 안드로이드 10 이상에서 사용할 수 있고 아이폰은 사용할 수 없습니다.",
        f"{SITE} 티링크 모바일",
        markers=["아이폰"],
    ),
    fact(
        "COND-PCADDON",
        "condition",
        "PC폰의 실시간 텍스트 변환과 통화번역은 별도 부가서비스입니다.",
        f"{SITE} 티링크 PC폰",
        markers=["부가서비스"],
    ),
    # company claims (not verified)
    fact(
        "CLAIM-RATE",
        "claim-note",
        "회사는 인터넷전화를 '업계 최저 기본요금'이라고 설명합니다.",
        f"{SITE} 인터넷전화",
        status="claim",
        anchors=["기본요금"],
    ),
]

TARGETS = [
    {
        "id": "field-sales",
        "name": "외근 영업 조직",
        "pains": ["PAIN-MOBILE", "PAIN-NO-RECORD"],
        "bundle": ["PROD-MOBILE", "PROD-RECORDING", "PROD-CRM", "PROD-REPORT"],
        "quote_items": ["PRICE-A", "PRICE-REPORT", "PRICE-MOBILE"],
        "must_conditions": ["COND-ANDROID"],
        "status": "proposed",
    },
    {
        "id": "remote-callcenter",
        "name": "재택 콜센터",
        "pains": ["PAIN-REMOTE", "PAIN-PHONE-SET"],
        "bundle": ["PROD-PCPHONE", "PROD-BIZ", "PROD-RECORDING"],
        "quote_items": ["PRICE-A", "PRICE-IVR", "PRICE-CALLBACK"],
        "must_conditions": [],
        "status": "proposed",
    },
    {
        "id": "school",
        "name": "학교",
        "pains": ["PAIN-SCHOOL", "PAIN-SCHOOL-COMPLAINT"],
        "bundle": ["PROD-SCHOOL"],
        "quote_items": ["PRICE-SCHOOL"],
        "must_conditions": [],
        "status": "proposed",
    },
    {
        "id": "small-office",
        "name": "소호 사무실",
        "pains": ["PAIN-MISSED", "PAIN-WHO"],
        "bundle": ["PROD-CALLBACK", "PROD-CRM"],
        "quote_items": ["PRICE-B", "PRICE-CALLBACK"],
        "must_conditions": [],
        "status": "proposed",
    },
    {
        "id": "telemarketing",
        "name": "전화 영업·보험대리점",
        "pains": ["PAIN-TM", "PAIN-MOBILE"],
        "bundle": ["PROD-MOBILE", "PROD-CRM"],
        "quote_items": ["PRICE-B", "PRICE-MOBILE"],
        "must_conditions": ["COND-ANDROID"],
        "status": "proposed",
    },
    {
        "id": "multilingual-site",
        "name": "다국어 현장(건설·제조·물류)",
        "pains": ["PAIN-ON"],
        "bundle": ["PROD-ON"],
        "quote_items": [],
        "must_conditions": [],
        "status": "proposed",
    },
]

E = [
    (
        1,
        "제목과 첫 문단에 네 가지 키워드를 포함",
        [["티링크 비즈레코딩"], ["영업사원 통화관리"], ["휴대폰 통화녹음"], ["인터넷전화 자동녹취"]],
    ),
    (
        2,
        "휴대폰·인터넷전화·PC폰 통화를 함께 녹음하고 한 화면에서 확인, 통신사 KT·SK·LG 모두 가능",
        [["휴대폰"], ["인터넷전화"], ["PC폰"], ["KT"], ["SK"], ["LG"]],
    ),
    (
        3,
        "통화가 끝나면 STT 문자변환, AI 통화요약, 핵심 키워드, 고객 요청사항과 후속 조치가 자동 기록",
        [["STT", "문자변환"], ["통화요약", "AI 요약"], ["키워드"], ["후속 조치", "후속조치"]],
    ),
    (
        4,
        "영업사원별 통화량, 평균 통화시간, 상담 이력, 미결 상담과 후속 연락 여부 관리",
        [["통화량"], ["통화시간"], ["상담 이력", "상담이력"], ["미결"]],
    ),
    (
        5,
        "고객별 통화기록과 상담 내용을 CRM에 연결, 담당자가 변경되어도 이전 이력 확인",
        [["CRM"], ["담당자가 변경", "담당자가 바뀌"], ["이력"]],
    ),
    (
        6,
        "조직별·직원별 영업 활동, 미결 업무, 고객 이탈 위험을 종합 리포트와 경영 대시보드에서 확인",
        [["종합 리포트", "종합리포트"], ["대시보드"], ["이탈", "해지 위험"]],
    ),
    (
        7,
        "통화 메모와 일일 보고서 작성 시간을 줄이고 객관적 데이터로 코칭과 성과관리",
        [["보고서"], ["코칭"], ["성과"]],
    ),
    (
        8,
        "통화 한 건을 직접 녹음하고 녹취 결과와 AI 요약이 생성되는 과정을 실제 사용 후기로 작성",
        [["녹음"], ["AI 요약", "통화요약"]],
    ),
    (
        9,
        "휴대폰 통화 화면, 녹취 목록, AI 통화요약, 직원별 통계, 종합 리포트 화면을 이미지와 함께 소개",
        [["화면"]],
    ),
    (10, "기업용 영업관리 솔루션이라는 점을 결론에서 강조", [["영업관리 솔루션", "영업 관리 솔루션"]]),
    (
        11,
        "AES256·SHA256 암호화와 사용자별 접근권한 등 보안 기능 소개",
        [["AES256"], ["SHA256"], ["접근권한", "접근 권한", "권한"]],
    ),
]
GUIDELINE = {
    "required_keywords": ["통화요약", "콜센터 프로그램", "업무자동화"],
    "title_keywords": ["티링크 비즈레코딩", "영업사원 통화관리", "휴대폰 통화녹음", "인터넷전화 자동녹취"],
    "emphasis": [{"no": n, "text": t, "any_of": a, "terms_confirmed": False} for n, t, a in E],
    "footer": ["tlinkcrm.com", "blog.naver.com/mobilecrm", "1877-3836"],
    "targets": ["field-sales"],
}

if __name__ == "__main__":
    ids = [f["id"] for f in FACTS]
    assert len(ids) == len(set(ids)), "duplicate fact id"
    for name, payload in (("facts", FACTS), ("targets", TARGETS), ("guideline", GUIDELINE)):
        (OUT / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(len(FACTS), "facts,", len(TARGETS), "targets,", len(GUIDELINE["emphasis"]), "emphasis items")
