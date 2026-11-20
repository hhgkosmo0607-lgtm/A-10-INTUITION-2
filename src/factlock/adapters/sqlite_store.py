"""Persist drafts and rule review reports as explicit JSON records in SQLite."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from factlock.domain.models import Block, Draft, Finding, ReviewReport, RuleResult, Verdict
from factlock.ports import DraftStore


def block_to_json(block: Block) -> dict[str, Any]:
    return {"type": block.type, "text": block.text, "fact_ids": list(block.fact_ids)}


def block_from_json(data: dict[str, Any]) -> Block:
    return Block(type=data["type"], text=data["text"], fact_ids=tuple(data["fact_ids"]))


def draft_to_json(draft: Draft) -> dict[str, Any]:
    return {
        "title": draft.title,
        "blocks": [block_to_json(block) for block in draft.blocks],
        "source": draft.source,
    }


def draft_from_json(data: dict[str, Any]) -> Draft:
    return Draft(
        title=data["title"],
        blocks=tuple(block_from_json(block) for block in data["blocks"]),
        source=data["source"],
    )


def finding_to_json(finding: Finding) -> dict[str, Any]:
    return {"message": finding.message, "sentence": finding.sentence, "fact_ids": list(finding.fact_ids)}


def finding_from_json(data: dict[str, Any]) -> Finding:
    return Finding(message=data["message"], sentence=data["sentence"], fact_ids=tuple(data["fact_ids"]))


def rule_result_to_json(result: RuleResult) -> dict[str, Any]:
    return {
        "rule": result.rule,
        "name": result.name,
        "verdict": result.verdict.value,
        "findings": [finding_to_json(finding) for finding in result.findings],
    }


def rule_result_from_json(data: dict[str, Any]) -> RuleResult:
    return RuleResult(
        rule=data["rule"],
        name=data["name"],
        verdict=Verdict(data["verdict"]),
        findings=tuple(finding_from_json(finding) for finding in data["findings"]),
    )


def review_report_to_json(report: ReviewReport) -> dict[str, Any]:
    return {"results": [rule_result_to_json(result) for result in report.results]}


def review_report_from_json(data: dict[str, Any]) -> ReviewReport:
    return ReviewReport(results=tuple(rule_result_from_json(result) for result in data["results"]))


class SqliteDraftStore(DraftStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS drafts ("
                "id TEXT PRIMARY KEY, draft TEXT NOT NULL, report TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def save(self, draft: Draft, report: ReviewReport) -> str:
        draft_id = uuid4().hex
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO drafts (id, draft, report, created_at) VALUES (?, ?, ?, ?)",
                (
                    draft_id,
                    json.dumps(draft_to_json(draft), ensure_ascii=False),
                    json.dumps(review_report_to_json(report), ensure_ascii=False),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return draft_id

    def load(self, draft_id: str) -> tuple[Draft, ReviewReport] | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT draft, report FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            return None
        return draft_from_json(json.loads(row[0])), review_report_from_json(json.loads(row[1]))
