"""Smoke tests for the deck-forge backend hub (M1 walking skeleton).

Bulk loading is patched out so these stay fast and hermetic (no ~500MB load, no
network), exercising the no-bulk graceful-degradation branch of the production wiring.
"""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import production
from mtg_utils.deck_forge_server import VERSION, create_app


def test_health_ok(monkeypatch):
    monkeypatch.setattr(production, "default_bulk_path", lambda: None)
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == VERSION


def test_index_serves_placeholder(monkeypatch):
    monkeypatch.setattr(production, "default_bulk_path", lambda: None)
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "deck-forge" in resp.text


def test_find_without_bulk_fails_loudly(monkeypatch):
    # The production wiring (create_app + no bulk on disk) must surface the 503 guard
    # on the live card-finding endpoint. /api/find replaced /api/search (ADR-0021).
    monkeypatch.setattr(production, "default_bulk_path", lambda: None)
    client = TestClient(create_app())
    resp = client.post("/api/find", json={"type": "Creature"})
    assert resp.status_code == 503
    assert "download-mtgjson" in resp.json()["error"]


def test_cross_origin_post_rejected(monkeypatch):
    # Local-server CSRF guard: a state-changing request whose Origin host differs
    # from the target Host is refused (a malicious site can't drive the local API).
    monkeypatch.setattr(production, "default_bulk_path", lambda: None)
    client = TestClient(create_app())
    resp = client.post(
        "/api/deck/format",
        json={"format": "commander"},
        headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8765"},
    )
    assert resp.status_code == 403
    assert "cross-origin" in resp.json()["error"]


def test_same_origin_post_allowed(monkeypatch):
    # Same Origin host as the target Host passes the guard (real SPA traffic).
    monkeypatch.setattr(production, "default_bulk_path", lambda: None)
    client = TestClient(create_app())
    resp = client.post(
        "/api/deck/format",
        json={"format": "commander"},
        headers={"Origin": "http://127.0.0.1:8765", "Host": "127.0.0.1:8765"},
    )
    assert resp.status_code != 403


def test_no_origin_post_allowed(monkeypatch):
    # Non-browser clients (curl, tests) send no Origin/Referer and are not blocked.
    monkeypatch.setattr(production, "default_bulk_path", lambda: None)
    client = TestClient(create_app())
    resp = client.post("/api/deck/format", json={"format": "commander"})
    assert resp.status_code != 403
