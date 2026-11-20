"""Composition root: wire adapters into the service. Run with `uvicorn factlock.web.main:app`."""

import os
from pathlib import Path

import anthropic
from fastapi import FastAPI

from factlock.adapters.claude_writer import ClaudeDraftWriter
from factlock.adapters.json_repo import JsonCompanyData
from factlock.adapters.sqlite_store import SqliteDraftStore
from factlock.adapters.stored_writer import StoredDraftWriter
from factlock.adapters.xlsx_guideline import XlsxGuidelineReader
from factlock.application.service import FactLockService
from factlock.web.app import create_app

ROOT = Path(__file__).resolve().parents[3]


def build() -> FastAPI:
    folder = Path(os.environ.get("FACTLOCK_DATA", ROOT / "data" / "tlink"))
    company = JsonCompanyData(folder)
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    # A short timeout and one retry keep a live demo from hanging; the stored draft takes over on failure.
    live = ClaudeDraftWriter(anthropic.Anthropic(timeout=120.0, max_retries=1)) if has_key else None
    service = FactLockService(
        company.all(),
        company.targets(),
        company.current(),
        live,
        StoredDraftWriter(folder / "drafts"),
        SqliteDraftStore(Path(os.environ.get("FACTLOCK_DB", ROOT / "var" / "factlock.db"))),
    )
    return create_app(service, XlsxGuidelineReader())


app = build()
