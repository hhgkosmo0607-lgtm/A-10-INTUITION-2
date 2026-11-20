"""Composition root: wire adapters into the service. Run with `uvicorn factlock.web.main:app`.

FACTLOCK_AI chooses the AI engine: auto (default), claude-cli, codex-cli, api, off.
"auto" tries the Claude API key if set, then the Claude Code CLI, then the Codex CLI.
"""

import os
from pathlib import Path

import anthropic
from fastapi import FastAPI

from factlock.adapters.ai_json import ClaudeApiJson, ClaudeCliJson, CodexCliJson, FirstAvailableJson
from factlock.adapters.ai_steps import AiDraftWriter, AiFactExtractor, AiMeaningReviewer, AiTargetPlanner
from factlock.adapters.extra_facts import JsonExtraFacts
from factlock.adapters.json_repo import JsonCompanyData
from factlock.adapters.sqlite_store import SqliteDraftStore
from factlock.adapters.stored_writer import StoredDraftWriter
from factlock.adapters.xlsx_guideline import XlsxGuidelineReader
from factlock.application.service import FactLockService
from factlock.ports import JsonModel
from factlock.web.app import create_app

ROOT = Path(__file__).resolve().parents[3]


def ai_engine(choice: str, codex_effort: str = "low") -> FirstAvailableJson | None:
    engines: list[JsonModel] = []
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if choice in ("auto", "api") and has_key:
        engines.append(ClaudeApiJson(anthropic.Anthropic(timeout=180.0, max_retries=1)))
    if choice in ("auto", "claude-cli") and ClaudeCliJson.available():
        engines.append(ClaudeCliJson())
    if choice in ("auto", "codex-cli") and CodexCliJson.available():
        engines.append(CodexCliJson(codex_effort))
    return FirstAvailableJson(engines) if engines else None


def build() -> FastAPI:
    folder = Path(os.environ.get("FACTLOCK_DATA", ROOT / "data" / "tlink"))
    company = JsonCompanyData(folder)
    choice = os.environ.get("FACTLOCK_AI", "auto")
    engine = ai_engine(choice)  # quick steps: target plan and meaning review
    writer = ai_engine(choice, "medium")  # the draft gets more thinking time
    service = FactLockService(
        company.all(),
        company.targets(),
        company.current(),
        AiDraftWriter(writer) if writer else None,
        StoredDraftWriter(folder / "drafts"),
        SqliteDraftStore(Path(os.environ.get("FACTLOCK_DB", ROOT / "var" / "factlock.db"))),
        AiTargetPlanner(engine) if engine else None,
        AiMeaningReviewer(engine) if engine else None,
        AiFactExtractor(engine) if engine else None,
        JsonExtraFacts(Path(os.environ.get("FACTLOCK_EXTRA_FACTS", ROOT / "var" / "extra_facts.json"))),
    )
    return create_app(service, XlsxGuidelineReader(), engine.name if engine else "")


app = build()
