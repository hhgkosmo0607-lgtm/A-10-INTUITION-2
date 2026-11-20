"""SQLite persistence tests using synthetic drafts and isolated databases."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from factlock.adapters.sqlite_store import SqliteDraftStore
from factlock.domain.models import Block, Draft, Finding, ReviewReport, RuleResult, Verdict


@pytest.mark.parametrize("populated", [False, True])
def test_round_trip_restores_dataclasses_tuples_and_verdicts(tmp_path: Path, populated: bool) -> None:
    path = tmp_path / "nested" / "drafts.db"
    store = SqliteDraftStore(path)
    draft = Draft("Synthetic title", ())
    report = ReviewReport(())
    if populated:
        draft = Draft(
            title="합성 초안",
            blocks=(
                Block(
                    "sentence",
                    "Synthetic text with 'quotes' and a newline.\nNext line.",
                    ("FACT-A", "FACT-B"),
                ),
                Block("heading", "Synthetic heading"),
                Block("experience_slot"),
                Block("footer", "example.test"),
            ),
            source="claude",
        )
        report = ReviewReport(
            results=(
                RuleResult("R1", "Required keywords", Verdict.PASS),
                RuleResult(
                    "R2",
                    "Emphasis",
                    Verdict.FAIL,
                    (
                        Finding("Synthetic issue", "Synthetic sentence", ("FACT-A", "FACT-B")),
                        Finding("Another issue"),
                    ),
                ),
                RuleResult("R10", "Disclosure", Verdict.CHECK),
            )
        )

    draft_id = store.save(draft, report)
    loaded = SqliteDraftStore(path).load(draft_id)

    assert loaded == (draft, report)
    assert loaded is not None
    restored_draft, restored_report = loaded
    assert isinstance(restored_draft.blocks, tuple)
    assert isinstance(restored_report.results, tuple)
    for block in restored_draft.blocks:
        assert isinstance(block.fact_ids, tuple)
    for result in restored_report.results:
        assert isinstance(result.verdict, Verdict)
        assert isinstance(result.findings, tuple)
        for finding in result.findings:
            assert isinstance(finding.fact_ids, tuple)
    assert restored_report.passed is (not populated)


def test_unknown_id_returns_none(tmp_path: Path) -> None:
    store = SqliteDraftStore(tmp_path / "drafts.db")
    assert store.load("unknown") is None
    assert store.load("' OR 1=1 --") is None


def test_two_saves_use_distinct_uuid4_ids_and_keep_both_records(tmp_path: Path) -> None:
    store = SqliteDraftStore(tmp_path / "drafts.db")
    draft = Draft("Synthetic title", (Block("sentence", "Synthetic text"),))
    report = ReviewReport(())

    first_id = store.save(draft, report)
    second_id = store.save(draft, report)

    assert first_id != second_id
    for draft_id in (first_id, second_id):
        assert UUID(draft_id).hex == draft_id
        assert UUID(draft_id).version == 4
        assert store.load(draft_id) == (draft, report)


def test_stores_json_text_and_utc_creation_time(tmp_path: Path) -> None:
    path = tmp_path / "drafts.db"
    store = SqliteDraftStore(path)
    before = datetime.now(UTC)
    draft_id = store.save(Draft("Synthetic title", ()), ReviewReport(()))
    after = datetime.now(UTC)

    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute("SELECT draft, report, created_at FROM drafts WHERE id = ?", (draft_id,)).fetchone()

    assert row is not None
    assert json.loads(row[0]) == {"title": "Synthetic title", "blocks": [], "source": "stored"}
    assert json.loads(row[1]) == {"results": []}
    created_at = datetime.fromisoformat(row[2])
    assert created_at.tzinfo == UTC
    assert before <= created_at <= after
