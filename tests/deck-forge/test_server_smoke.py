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
    assert "download-bulk" in resp.json()["error"]
