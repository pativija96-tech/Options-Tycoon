"""
Static pages must be revalidated on every load so deploys show up immediately.

Run: python -m pytest tests/test_static_cache_headers.py -v
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from main import RevalidatingStaticFiles

    (tmp_path / "page.html").write_text("<p>hi</p>")
    (tmp_path / "app.js").write_text("var x = 1;")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")

    app = FastAPI()
    app.mount("/static", RevalidatingStaticFiles(directory=str(tmp_path)), name="static")
    return TestClient(app)


@pytest.mark.parametrize("path", ["/static/page.html", "/static/app.js"])
def test_pages_and_scripts_revalidate(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers.get("etag")  # needed for cheap 304 revalidation


def test_unchanged_page_returns_304_with_header(client):
    etag = client.get("/static/page.html").headers["etag"]
    resp = client.get("/static/page.html", headers={"If-None-Match": etag})
    assert resp.status_code == 304
    assert resp.headers["cache-control"] == "no-cache"


def test_images_keep_default_caching(client):
    resp = client.get("/static/logo.png")
    assert resp.status_code == 200
    assert "cache-control" not in resp.headers
