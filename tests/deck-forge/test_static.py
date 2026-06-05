"""Tests for serving the built SPA (static mount) vs the placeholder fallback."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _state() -> ForgeState:
    return ForgeState(
        by_name={},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
    )


def test_serves_built_spa_when_present(tmp_path):
    (tmp_path / "index.html").write_text('<!doctype html><div id="app"></div>')
    client = TestClient(build_app(_state(), frontend_dist=tmp_path))
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="app"' in resp.text


def test_placeholder_when_no_built_spa():
    client = TestClient(build_app(_state(), frontend_dist=None))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "deck-forge" in resp.text
