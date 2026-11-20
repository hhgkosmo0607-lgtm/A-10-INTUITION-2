"""Write the stored drafts used when the live writer is unavailable. Run: uv run python scripts/build_tlink_drafts.py"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "tlink" / "drafts"


def h(text: str, *ids: str) -> dict[str, object]:
    return {"type": "heading", "text": text, "fact_ids": list(ids)}


def s(text: str, *ids: str) -> dict[str, object]:
    return {"type": "sentence", "text": text, "fact_ids": list(ids)}


def slot(text: str) -> dict[str, object]:
    return {"type": "experience_slot", "text": text, "fact_ids": []}


FOOTER = {"type": "footer", "text": "", "fact_ids": []}
PRICE_NOTE = s(
    "가격은 부가세 별도의 예시 견적이며 정확한 비용은 상담 후 확정됩니다. A·B·C 타입은 상담원 최소 3명부터입니다.",
    "COND-VAT",
    "COND-ESTIMATE",
    "COND-MIN3",
)

FIELD_SALES = {
    "title": "티링크 비즈레코딩 소개: 영업사원 통화관리를 통화요약과 업무자동화로 바꾸는 콜센터 프로그램",
    "blocks": [
        s("이 글은 티링크가 제공한 자료를 바탕으로 작성한 협찬 소개 글입니다."),
        s("안녕하세요. 오늘은 외근이 많은 영업 조직을 위한 티링크 비즈레코딩을 소개합니다.", "PROD-NAME"),
        s(
            "티링크 비즈레코딩은 영업사원 통화관리를 위해 휴대폰 통화녹음과 인터넷전화 자동녹취를 한곳에 모으는 콜센터 프로그램입니다.",
            "PROD-NAME",
            "PROD-MOBILE",
            "FEAT-UNIFIED",
        ),
        s("통화 기록을 사람이 따로 적지 않아도 되는 업무자동화가 이 글의 주제입니다."),
        h("기존 영업관리의 문제"),
        s(
            "휴대폰으로 통화하면 녹음이 직원 개인 폰에만 남고, 누가 어떤 고객과 무슨 이야기를 했는지 회사에서 알 수 없습니다.",
            "PAIN-MOBILE",
        ),
        s(
            "영업직원은 통화 후 CRM에 기록을 남기지 않고, 회의록은 불완전하거나 미작성 상태로 남습니다.",
            "PAIN-NO-RECORD",
        ),
        h("휴대폰과 인터넷전화를 함께 녹음합니다"),
        s(
            "사무실 인터넷 전화기, 외근 중 스마트폰, 재택 소프트폰의 통화가 하나의 녹취 서버에 모입니다.",
            "FEAT-UNIFIED",
        ),
        s(
            "사무실에서는 인터넷전화, 외근 중에는 휴대폰, 집에서는 PC폰을 쓰면 됩니다.",
            "FEAT-UNIFIED",
            "PROD-PCPHONE",
        ),
        s("통신사는 LG, SK, KT, 삼성SDS 회선을 모두 녹취할 수 있습니다.", "FEAT-CARRIER"),
        s("티링크 모바일은 휴대폰 녹취 파일을 중앙 서버로 전송해 보관합니다.", "PROD-MOBILE"),
        s(
            "다만 티링크 모바일은 안드로이드 10 이상에서 사용할 수 있고 아이폰은 사용할 수 없습니다.",
            "PROD-MOBILE",
            "COND-ANDROID",
        ),
        s(
            "라우터와 패킷 미러링 스위치로 통화를 복제해 녹음하므로 기존 회선과 전화기를 바꾸지 않습니다.",
            "FEAT-MIRROR",
        ),
        h("통화가 끝나면 자동으로 기록됩니다"),
        s("통화가 끝나면 STT 문자변환, 한 줄 요약, 키워드, 화자별 대화가 기록됩니다.", "FEAT-STT"),
        s(
            "AI 통화요약과 함께 고객 요청사항과 후속 조치 내용도 자동으로 기록된다고 가이드라인은 설명합니다.",
            "FEAT-FOLLOWUP",
        ),
        slot(
            "직접 통화 한 건을 녹음하고, 녹취 결과와 AI 요약이 생성되는 과정을 화면 이미지와 함께 적어 주세요"
        ),
        h("영업사원 관리"),
        s("통화 통계는 총 통화, 수신·발신, 평균 통화시간, 담당자별 통화량을 보여 줍니다.", "FEAT-STATS"),
        s("고객 화면에 그 고객의 상담 이력과 통화·문자·주문 이력이 쌓입니다.", "FEAT-HISTORY"),
        s(
            "통화 기록이 CRM에 연결되어, 담당자가 변경되어도 이전 상담 이력을 빠르게 확인할 수 있다고 합니다.",
            "FEAT-REASSIGN",
        ),
        h("경영진을 위한 종합리포트", "PROD-REPORT"),
        s(
            "종합리포트는 경영 분석 대시보드, 상담원 역량 분석, 인사고과 평가표, 신입사원 교육자료로 이루어집니다.",
            "PROD-REPORT",
        ),
        s(
            "경영 분석 대시보드는 핵심 지표, 영업기회 현황, 미결 건 추적, 해지 위험 고객 조기경보, RED 알림을 보여 줍니다.",
            "FEAT-DASH",
        ),
        s(
            "일일 리포트가 통화·상담·매출 현황을 요약하므로, 보고서를 따로 쓰는 일을 줄일 수 있습니다.",
            "FEAT-DAILY",
        ),
        s(
            "상담원 역량 분석과 인사고과 평가표는 통화 원문을 근거로 하므로 코칭과 성과 관리의 근거가 됩니다.",
            "FEAT-EVAL",
        ),
        h("보안"),
        s("녹취파일은 AES256으로, 비밀번호는 SHA256으로 암호화합니다.", "FEAT-SECURITY"),
        s("권한은 상담원과 매니저로 나뉘고, 통계와 리포트는 매니저 이상만 볼 수 있습니다.", "FEAT-ROLE"),
        h("비용"),
        s("A타입(고객관리 + 녹취 + 문자변환·요약 + 일일보고서)은 상담원당 월 30,000원입니다.", "PRICE-A"),
        s(
            "종합리포트는 A타입을 선택한 경우에만 이용할 수 있고, 월 100,000원이며 매월 3회까지 생성할 수 있습니다.",
            "PRICE-REPORT",
            "PROD-REPORT",
            "COND-ATYPE",
        ),
        PRICE_NOTE,
        h("마무리"),
        s("통화가 끝나면, 보고서가 시작됩니다.", "PHRASE-REPORT"),
        s(
            "단순한 통화녹음 서비스가 아니라, 영업 활동을 자동으로 기록하고 경영에 필요한 정보로 정리해 주는 기업용 영업관리 솔루션입니다."
        ),
        FOOTER,
    ],
}

REMOTE = {
    "title": "재택 콜센터를 위한 콜센터 프로그램: 티링크 PC폰과 통화요약으로 업무자동화",
    "blocks": [
        s("이 글은 티링크가 제공한 자료를 바탕으로 작성한 협찬 소개 글입니다."),
        s(
            "안녕하세요. 오늘은 재택근무 상담 조직을 위한 콜센터 프로그램 구성과 업무자동화 방법을 소개합니다."
        ),
        h("재택 상담의 고민"),
        s("재택근무에서는 개인 휴대폰으로 전화를 받게 되고 고객에게 개인 번호가 남습니다.", "PAIN-REMOTE"),
        s("재택근무자가 늘면 직원마다 전화기를 새로 놓아야 하는지가 고민입니다.", "PAIN-PHONE-SET"),
        h("전화기 없이 PC로 걸고 받습니다"),
        s("티링크 PC폰(TlinkPhone)은 전화기 없이 PC에 설치해 쓰는 전화기입니다.", "PROD-PCPHONE"),
        s("PC폰은 사무실, 재택, 외근 어디서나 같은 내선번호로 걸고 받습니다.", "PROD-PCPHONE", "FEAT-PCANY"),
        s(
            "PC폰은 통화 중 음성을 글로 바꿔 보여 주는 실시간 STT를 지원하며, 이 기능은 별도 부가서비스입니다.",
            "PROD-PCPHONE",
            "FEAT-PCSTT",
            "COND-PCADDON",
        ),
        h("콜센터 운영과 녹취"),
        s(
            "티링크 비즈는 상담 현황판, 자동 배분, 콜백 예약, IVR, 녹취 연동을 묶은 콜센터 솔루션입니다.",
            "PROD-BIZ",
        ),
        s(
            "티링크 AI 녹취는 인터넷전화·스마트폰·소프트폰 통화를 하나의 녹취 서버에 모으고 STT로 글로 바꿔 요약합니다.",
            "PROD-RECORDING",
        ),
        s(
            "통화가 끝나면 STT 문자변환, 한 줄 요약, 키워드, 화자별 대화가 기록되어 통화요약을 따로 쓰지 않아도 됩니다.",
            "FEAT-STT",
        ),
        s(
            "티링크 콜백은 모든 상담원이 통화 중일 때 고객을 대기시키고 통화 대기 목록을 보여 줍니다.",
            "FEAT-CALLBACK",
        ),
        slot("재택 환경에서 PC폰으로 전화를 받고 녹취와 요약을 확인한 과정을 화면 이미지와 함께 적어 주세요"),
        h("보안"),
        s("녹취파일은 AES256으로, 비밀번호는 SHA256으로 암호화합니다.", "FEAT-SECURITY"),
        h("비용"),
        s("A타입(고객관리 + 녹취 + 문자변환·요약 + 일일보고서)은 상담원당 월 30,000원입니다.", "PRICE-A"),
        s("IVR(대표번호 안내멘트)은 월 20,000원, 설정비 50,000원입니다.", "PRICE-IVR"),
        s("콜백은 월 20,000원, 설정비 50,000원입니다.", "PRICE-CALLBACK"),
        PRICE_NOTE,
        h("마무리"),
        s("기록은 AI에게, 성장은 당신에게.", "PHRASE-AI"),
        FOOTER,
    ],
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, draft in (("field-sales", FIELD_SALES), ("remote-callcenter", REMOTE)):
        (OUT / f"{name}.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print("drafts written")
