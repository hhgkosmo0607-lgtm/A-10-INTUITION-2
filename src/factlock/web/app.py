"""HTTP layer. Error bodies carry a fixed code and a Korean message, never the submitted content."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from factlock.application.service import (
    DocumentView,
    FactLockService,
    Ingested,
    Unavailable,
    UnknownDocument,
    UnknownFact,
    UnknownTarget,
)
from factlock.domain.models import Asset, Block, Carousel, Fact, ReviewReport, Slide
from factlock.ports import (
    AssetError,
    AssetLibrary,
    DocumentError,
    GuidelineError,
    GuidelineReader,
)
from factlock.web.messages import (
    ASSET_MESSAGES,
    DOCUMENT_MESSAGES,
    GUIDELINE_MESSAGES,
    ai_message,
)
from factlock.web.schemas import (
    BundleIn,
    CarouselReviewIn,
    DraftIn,
    PlanIn,
    ReviewIn,
    UserFactIn,
    choices_from,
)

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 2 * 1024 * 1024


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


def create_app(
    service: FactLockService,
    reader: GuidelineReader,
    engine_name: str = "",
    brand: dict[str, str] | None = None,
    assets: AssetLibrary | None = None,
    max_document_bytes: int = 30 * 1024 * 1024,
) -> FastAPI:
    app = FastAPI(title="AdCheck", docs_url=None, redoc_url=None)

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
            "brand": brand or {"name": "", "background": "#1c1b19", "text": "#ffffff", "accent": "#9fc1ff"},
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

    def asset_view(asset: Asset) -> dict[str, str]:
        return {
            "id": asset.id,
            "caption": asset.caption,
            "filename": asset.filename,
            "url": f"/api/assets/{asset.id}/file",
        }

    @app.get("/api/assets")
    def list_assets() -> list[dict[str, str]]:
        return [asset_view(a) for a in assets.all()] if assets else []

    @app.post("/api/assets")
    async def add_asset(file: UploadFile = File(...), caption: str = Form("")) -> dict[str, str]:  # noqa: B008
        if assets is None:
            raise HTTPException(503, {"code": "assets_off", "message": "자료함을 쓸 수 없습니다."})
        data = await file.read(assets.max_bytes + 1)
        try:
            return asset_view(assets.add(file.filename or "image", data, caption))
        except AssetError as error:
            message = ASSET_MESSAGES.get(error.code, "이미지를 넣지 못했습니다.")
            raise HTTPException(400, {"code": error.code, "message": message}) from None

    @app.get("/api/assets/{asset_id}/file")
    def asset_file(asset_id: str) -> FileResponse:
        found = assets.get(asset_id) if assets else None
        if found is None:
            raise HTTPException(404, {"code": "unknown_asset", "message": "없는 자료입니다."})
        return FileResponse(found[1], media_type=found[0].content_type)

    @app.delete("/api/assets/{asset_id}")
    def delete_asset(asset_id: str) -> dict[str, str]:
        if assets is None or not assets.delete(asset_id):
            raise HTTPException(404, {"code": "unknown_asset", "message": "없는 자료입니다."})
        return {"deleted": asset_id}

    def document_view(view: DocumentView, result: Ingested | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": view.document.id,
            "filename": view.document.filename,
            "pages": view.document.pages,
            "added": view.document.added,
            "url": view.link,
            "facts": view.facts,
            "pending": view.pending,
        }
        if result is not None:
            out["added_facts"] = [_fact(f) for f in result.added]
            out["rejected"] = [asdict(item) for item in result.rejected]
            out["pages_read"] = result.pages_read
            out["pages_skipped"] = result.pages_skipped
        return out

    def no_document() -> HTTPException:
        return HTTPException(404, {"code": "unknown_document", "message": "없는 문서입니다."})

    @app.get("/api/documents")
    def list_documents() -> list[dict[str, Any]]:
        return [document_view(view) for view in service.documents()]

    @app.post("/api/documents")
    async def add_document(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        data = await file.read(max_document_bytes + 1)
        try:
            return document_view(*service.add_document(file.filename or "문서", data))
        except DocumentError as error:
            message = DOCUMENT_MESSAGES.get(error.code, "문서를 읽지 못했습니다.")
            raise HTTPException(400, {"code": error.code, "message": message}) from None
        except Unavailable as error:
            raise HTTPException(503, {"code": error.code, "message": ai_message(error.code)}) from None

    @app.post("/api/documents/{document_id}/analyze")
    def reanalyse_document(document_id: str) -> dict[str, Any]:
        try:
            return document_view(*service.reanalyse_document(document_id))
        except UnknownDocument:
            raise no_document() from None
        except DocumentError as error:
            message = DOCUMENT_MESSAGES.get(error.code, "문서를 읽지 못했습니다.")
            raise HTTPException(400, {"code": error.code, "message": message}) from None
        except Unavailable as error:
            raise HTTPException(503, {"code": error.code, "message": ai_message(error.code)}) from None

    @app.get("/api/documents/{document_id}/file")
    def document_file(document_id: str) -> FileResponse:
        try:
            document, path = service.document_file(document_id)
        except UnknownDocument:
            raise no_document() from None
        return FileResponse(path, filename=document.filename)

    @app.delete("/api/documents/{document_id}")
    def remove_document(document_id: str) -> dict[str, Any]:
        try:
            return {"deleted": document_id, "facts_removed": service.remove_document(document_id)}
        except UnknownDocument:
            raise no_document() from None

    @app.post("/api/facts")
    def add_fact(body: UserFactIn) -> dict[str, Any]:
        return _fact(service.add_user_fact(body.statement, body.kind))

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
            "saved": {
                "pains": [_fact(f) for f in result.saved_pains],
                "conditions": [_fact(f) for f in result.saved_conditions],
                "content": [_fact(f) for f in result.saved_content],
            },
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
            result = service.make_draft(body.target_id, choices_from(body))
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

    @app.post("/api/carousel")
    def carousel(body: DraftIn) -> dict[str, Any]:
        try:
            result = service.make_carousel(body.target_id, choices_from(body))
        except UnknownTarget:
            raise _bad_target() from None
        except Unavailable as error:
            raise HTTPException(503, {"code": error.code, "message": ai_message(error.code)}) from None
        used = {i for s in result.carousel.slides for i in s.fact_ids}
        used |= {i for b in result.carousel.caption for i in b.fact_ids}
        by_id = {fact.id: fact for fact in service.facts}
        return {
            "source": result.carousel.source,
            "fallback_message": ai_message(result.fallback_code),
            "slides": [asdict(s) for s in result.carousel.slides],
            "caption": [asdict(b) for b in result.carousel.caption],
            "hashtags": list(result.carousel.hashtags),
            "dropped": [asdict(item) for item in result.dropped],
            "facts": {i: _fact(by_id[i]) for i in sorted(used) if i in by_id},
            "report": _report(result.report),
        }

    @app.post("/api/carousel/review")
    def carousel_review(body: CarouselReviewIn) -> dict[str, Any]:
        edited = Carousel(
            tuple(Slide(s.kicker, s.headline, s.body) for s in body.slides),
            tuple(Block("sentence", line) for line in body.caption.splitlines() if line.strip()),
            tuple(body.hashtags),
        )
        try:
            return _report(service.review_carousel(edited, body.target_id, choices_from(body)))
        except UnknownTarget:
            raise _bad_target() from None

    @app.post("/api/review")
    def review(body: ReviewIn) -> dict[str, Any]:
        try:
            return _report(service.review_text(body.title, body.body, body.target_id, body.ai, choices_from(body)))
        except UnknownTarget:
            raise _bad_target() from None

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
