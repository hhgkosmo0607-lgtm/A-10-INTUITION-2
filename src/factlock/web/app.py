"""HTTP layer. Error bodies carry a fixed code and a Korean message, never the submitted content."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from factlock.adapters.doc_text import MAX_BYTES, read_document
from factlock.application.service import FactLockService, Unavailable, UnknownFact, UnknownTarget
from factlock.domain.models import Fact, ReviewReport
from factlock.ports import DocumentError, GuidelineError, GuidelineReader

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 2 * 1024 * 1024

GUIDELINE_MESSAGES = {
    "guideline_unreadable": "엑셀 파일을 읽을 수 없습니다. .xlsx 파일인지 확인해 주세요.",
    "guideline_too_large": "파일이 2MB를 넘습니다.",
    "guideline_missing_required": "'필수' 키워드 줄을 찾지 못했습니다.",
    "guideline_missing_emphasis": "'강조내용' 줄이나 번호가 붙은 항목을 찾지 못했습니다.",
}
AI_MESSAGES = {
    "live_writer_not_configured": "연결된 AI가 없습니다.",
    "ai_not_configured": "연결된 AI가 없습니다.",
    "stored_requested": "AI를 부르지 않도록 선택했습니다.",
    "stored_draft_missing": "이 타깃은 저장된 초안이 없습니다. AI가 연결되어야 초안을 만들 수 있습니다.",
    "no_matching_products": "회사 자료에서 이 고객에게 맞는 제품을 찾지 못했습니다.",
    "claude_cli_signed_out": "Claude Code 로그인이 만료되었습니다. 터미널에서 claude를 실행해 다시 로그인해 주세요.",
    "claude_cli_timeout": "AI 응답이 너무 오래 걸렸습니다.",
    "codex_cli_timeout": "AI 응답이 너무 오래 걸렸습니다.",
    "claude_auth_failed": "API 키 인증에 실패했습니다.",
    "claude_rate_limited": "AI 요청 한도에 걸렸습니다.",
    "claude_unreachable": "AI 서버에 연결하지 못했습니다.",
    "claude_refused": "AI가 요청을 거절했습니다.",
}
DOCUMENT_MESSAGES = {
    "document_too_large": "파일이 30MB를 넘습니다.",
    "document_type_unsupported": "읽을 수 있는 형식은 PDF, PPTX, DOCX, XLSX, TXT, MD입니다.",
    "document_unreadable": "파일을 읽지 못했습니다. 암호가 걸렸거나 손상된 파일일 수 있습니다.",
    "document_has_no_text": "글자를 찾지 못했습니다. 그림으로만 된 문서일 수 있습니다.",
}
AI_DEFAULT = "AI가 답하지 못했습니다. 잠시 뒤 다시 시도해 주세요."


def ai_message(code: str) -> str:
    return AI_MESSAGES.get(code, AI_DEFAULT) if code else ""


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
    ai: bool = False


class PlanIn(BaseModel):
    description: str = Field(min_length=2, max_length=200)


def _fact(fact: Fact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "kind": fact.kind,
        "statement": fact.statement,
        "status": fact.status.value,
        "source": fact.source.where,
        "url": fact.source.url,
        "quote": fact.source.quote,
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


def create_app(service: FactLockService, reader: GuidelineReader, engine_name: str = "") -> FastAPI:
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
            "engine": engine_name,
            "targets": [{"id": t.id, "name": t.name, "status": t.status} for t in service.targets],
            "guideline": guideline_view(),
            "fact_counts": {
                status: sum(1 for f in facts if f.status.value == status)
                for status in ("confirmed", "conflict", "claim", "pending")
            },
        }

    @app.get("/api/facts")
    def facts() -> list[dict[str, Any]]:
        return [_fact(fact) for fact in service.facts]

    @app.post("/api/documents")
    async def documents(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        data = await file.read(MAX_BYTES + 1)
        try:
            pages = read_document(file.filename or "", data)
        except DocumentError as error:
            message = DOCUMENT_MESSAGES.get(error.code, "문서를 읽지 못했습니다.")
            raise HTTPException(400, {"code": error.code, "message": message}) from None
        try:
            result = service.ingest_document(file.filename or "문서", [(p.locator, p.text) for p in pages])
        except Unavailable as error:
            raise HTTPException(503, {"code": error.code, "message": ai_message(error.code)}) from None
        return {
            "added": [_fact(f) for f in result.added],
            "rejected": [asdict(item) for item in result.rejected],
            "pages_read": result.pages_read,
            "pages_skipped": result.pages_skipped,
        }

    @app.post("/api/facts/{fact_id}/confirm")
    def confirm(fact_id: str) -> dict[str, Any]:
        try:
            return _fact(service.confirm_fact(fact_id))
        except UnknownFact:
            raise HTTPException(
                404, {"code": "unknown_fact", "message": "문서에서 읽은 사실만 확정할 수 있습니다."}
            ) from None

    @app.delete("/api/facts/{fact_id}")
    def discard(fact_id: str) -> dict[str, Any]:
        try:
            service.discard_fact(fact_id)
        except UnknownFact:
            raise HTTPException(
                404, {"code": "unknown_fact", "message": "문서에서 읽은 사실만 지울 수 있습니다."}
            ) from None
        return {"deleted": fact_id}

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
            "reason": result.reason,
        }

    @app.post("/api/targets/plan")
    def plan(body: PlanIn) -> dict[str, Any]:
        try:
            target = service.plan_target(body.description)
        except Unavailable as error:
            raise HTTPException(503, {"code": error.code, "message": ai_message(error.code)}) from None
        return {"id": target.id, "name": target.name, "status": target.status}

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
        except Unavailable as error:
            raise HTTPException(503, {"code": error.code, "message": ai_message(error.code)}) from None
        used = {fact_id for block in result.draft.blocks for fact_id in block.fact_ids}
        by_id = {fact.id: fact for fact in service.facts}
        return {
            "draft_id": result.draft_id,
            "source": result.draft.source,
            "fallback_code": result.fallback_code,
            "fallback_message": ai_message(result.fallback_code),
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
            return _report(service.review_text(body.title, body.body, body.target_id, body.ai))
        except UnknownTarget:
            raise _bad_target() from None

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
