"""Promo material library. Images are tiny synthetic files."""

from pathlib import Path

from fastapi.testclient import TestClient

from factlock.adapters.asset_store import FileAssetStore
from factlock.adapters.json_repo import JsonCompanyData
from factlock.adapters.sqlite_store import SqliteDraftStore
from factlock.adapters.stored_writer import StoredDraftWriter
from factlock.adapters.xlsx_guideline import XlsxGuidelineReader
from factlock.application.service import FactLockService
from factlock.web.app import create_app

DATA = Path(__file__).resolve().parents[1] / "data" / "tlink"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def client(tmp_path: Path) -> TestClient:
    company = JsonCompanyData(DATA)
    service = FactLockService(
        company.all(), company.targets(), company.current(), None, StoredDraftWriter(DATA / "drafts"),
        SqliteDraftStore(tmp_path / "t.db"),
    )  # fmt: skip
    return TestClient(create_app(service, XlsxGuidelineReader(), "", None, FileAssetStore(tmp_path / "assets")))


def test_add_list_serve_and_delete_an_image(tmp_path: Path) -> None:
    c = client(tmp_path)
    added = c.post("/api/assets", files={"file": ("화면.png", PNG)}, data={"caption": "통화 요약 화면"}).json()
    assert added["caption"] == "통화 요약 화면"
    assert [a["id"] for a in c.get("/api/assets").json()] == [added["id"]]
    served = c.get(added["url"])
    assert served.status_code == 200 and served.headers["content-type"] == "image/png" and served.content == PNG
    assert c.delete(f"/api/assets/{added['id']}").status_code == 200
    assert c.get("/api/assets").json() == []
    assert c.get(added["url"]).status_code == 404


def test_rejects_non_images_and_missing_captions_with_fixed_codes(tmp_path: Path) -> None:
    c = client(tmp_path)
    bad = c.post("/api/assets", files={"file": ("a.png", b"<svg onload=alert(1)>")}, data={"caption": "설명"})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "asset_type_unsupported"
    assert "svg" not in bad.text
    none = c.post("/api/assets", files={"file": ("a.png", PNG)}, data={"caption": " "})
    assert none.json()["detail"]["code"] == "asset_caption_missing"
    assert c.get("/api/assets/..%2Findex.json/file").status_code == 404
