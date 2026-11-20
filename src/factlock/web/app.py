"""HTTP layer. Error bodies carry a fixed code and a Korean message, never the submitted content."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from factlock.application.service import FactLockService, UnknownTarget
from factlock.domain.models import Fact, ReviewReport
from factlock.ports import GuidelineError, GuidelineReader

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 2 * 1024 * 1024

GUIDELINE_MESSAGES = {
    "guideline_unreadable": "엑셀 파일을 읽을 수 없습니다. .xlsx 파일인지 확인해 주세요.",
    "guideline_too_large": "파일이 2MB를 넘습니다.",
    "guideline_missing_required": "'필수' 키워드 줄을 찾지 못했습니다.",
    "guideline_missing_emphasis": "'강조내용' 줄이나 번호가 붙은 항목을 찾지 못했습니다.",
}
FALLBACK_MESSAGES = {
    "live_writer_not_configured": "API 키가 없어 AI를 부르지 못했습니다.",
    "stored_requested": "AI를 부르지 않도록 선택했습니다.",
    "claude_auth_failed": "API 키 인증에 실패했습니다.",
    "claude_rate_limited": "요청 한도에 걸렸습니다.",
    "claude_api_error": "AI 서버 오류가 났습니다.",
    "claude_unreachable": "AI 서버에 연결하지 못했습니다.",
    "claude_refused": "AI가 요청을 거절했습니다.",
    "claude_truncated": "AI 답이 중간에 끊겼습니다.",
    "claude_bad_output": "AI 답의 형식이 맞지 않았습니다.",
}


class BundleIn(BaseModel):
    target_id: str
    agents: int = Field(ge=1, le=10_000)


class DraftIn(BaseModel):
    target_id: str
    live: bool = True


class ReviewIn(BaseModel):
    title: str = Field(max_length=300)
    body: str = Field(max_length=60_000)
    target_id: str | None = None


def _fact(fact: Fact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "kind": fact.kind,
        "statement": fact.statement,
        "status": fact.status.value,
        "source": fact.source.where,
        "checked": fact.source.checked,
        "scope": fact.scope,
    }


def _report(report: ReviewReport) -> dict[str, Any]:
    counts = {"pass": 0, "fail": 0, "check": 0}
    for result in report.results:
        counts[result.verdict.value] += 1
    return {"passed": report.passed, "counts": counts, "results": [asdict(r) for r in report.results]}


def _bad_target() -> HTTPException:
    return HTTPException(404, {"code": "unknown_target", "message": "없는 타깃입니다."})


def create_app(service: FactLockService, reader: GuidelineReader) -> FastAPI:
    app = FastAPI(title="FactLock", docs_url=None, redoc_url=None)

    def guideline_view() -> dict[str, Any]:
        g = service.guideline
        return {
            "required_keywords": list(g.required_keywords),
            "title_keywords": list(g.title_keywords),
            "footer": list(g.footer),
            "emphasis": [
                {
                    "no": i.no,
                    "text": i.text,
                    "terms": [list(group) for group in i.any_of],
                    "confirmed": i.terms_confirmed,
                }
                for i in g.emphasis
            ],
        }

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        facts = service.facts
        return {
            "live": service.live_available,
            "targets": [{"id": t.id, "name": t.name, "status": t.status} for t in service.targets],
            "guideline": guideline_view(),
            "fact_counts": {
                status: sum(1 for f in facts if f.status.value == status)
                for status in ("confirmed", "conflict", "claim")
            },
        }

    @app.get("/api/facts")
    def facts() -> list[dict[str, Any]]:
        return [_fact(fact) for fact in service.facts]

    @app.post("/api/bundle")
    def bundle(body: BundleIn) -> dict[str, Any]:
        try:
            result = service.bundle(body.target_id, body.agents)
        except UnknownTarget:
            raise _bad_target() from None
        return {
            "target": {"id": result.target.id, "name": result.target.name, "status": result.target.status},
            "products": [_fact(f) for f in result.products],
            "pains": [_fact(f) for f in result.pains],
            "conditions": [_fact(f) for f in result.conditions],
            "quote": asdict(result.quote),
        }

    @app.post("/api/guideline")
    async def guideline(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        data = await file.read(MAX_UPLOAD + 1)
        try:
            if len(data) > MAX_UPLOAD:
                raise GuidelineError("guideline_too_large")
            service.use_guideline(reader.read(data))
        except GuidelineError as error:
            message = GUIDELINE_MESSAGES.get(error.code, "가이드라인을 읽지 못했습니다.")
            raise HTTPException(400, {"code": error.code, "message": message}) from None
        return guideline_view()

    @app.post("/api/drafts")
    def drafts(body: DraftIn) -> dict[str, Any]:
        try:
            result = service.make_draft(body.target_id, body.live)
        except UnknownTarget:
            raise _bad_target() from None
        used = {fact_id for block in result.draft.blocks for fact_id in block.fact_ids}
        by_id = {fact.id: fact for fact in service.facts}
        return {
            "draft_id": result.draft_id,
            "source": result.draft.source,
            "fallback_code": result.fallback_code,
            "fallback_message": FALLBACK_MESSAGES.get(result.fallback_code, ""),
            "title": result.draft.title,
            "blocks": [asdict(block) for block in result.draft.blocks],
            "body": result.body,
            "dropped": [asdict(item) for item in result.dropped],
            "facts": {fact_id: _fact(by_id[fact_id]) for fact_id in sorted(used) if fact_id in by_id},
            "report": _report(result.report),
        }

    @app.post("/api/review")
    def review(body: ReviewIn) -> dict[str, Any]:
        try:
            return _report(service.review_text(body.title, body.body, body.target_id))
        except UnknownTarget:
            raise _bad_target() from None

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
