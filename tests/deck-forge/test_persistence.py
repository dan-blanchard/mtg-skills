"""M5 tests: build store (autosave/library), session load, exports."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.exporters import export_arena, export_as
from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._deck_forge.state import DeckSession, ForgeState

DECK = {
    "format": "commander",
    "commanders": [{"name": "Atraxa", "quantity": 1}],
    "cards": [{"name": "Forest", "quantity": 8}, {"name": "Sol Ring", "quantity": 1}],
    "sideboard": [],
}


def test_build_store_save_list_load_delete(tmp_path):
    store = BuildStore(tmp_path)
    store.save("b1", "My Deck", DECK)
    summaries = store.list()
    assert len(summaries) == 1
    assert summaries[0]["name"] == "My Deck"
    assert summaries[0]["card_count"] == 10  # 1 + 8 + 1
    assert store.load("b1")["deck"] == DECK
    assert store.delete("b1") is True
    assert store.list() == []


def test_session_round_trips_through_deck_dict():
    session = DeckSession.from_deck_dict(DECK)
    assert session.to_deck_dict() == DECK


def test_export_arena_has_section_headers():
    text = export_arena(DECK)
    assert "Commander" in text
    assert "1 Atraxa" in text
    assert "Deck" in text
    assert "8 Forest" in text


def test_export_as_unknown_format_returns_none():
    assert export_as(DECK, "bogus") is None


def _client(tmp_path):
    state = ForgeState(
        by_name={},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        store=BuildStore(tmp_path),
        build_id="current",
    )
    return TestClient(build_app(state)), state


def test_autosave_persists_on_add(tmp_path):
    state = ForgeState(
        by_name={"Forest": {"name": "Forest", "type_line": "Basic Land — Forest"}},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        store=BuildStore(tmp_path),
        build_id="current",
    )
    client = TestClient(build_app(state))
    client.post("/api/deck/add", json={"name": "Forest", "qty": 3})
    saved = state.store.load("current")
    assert saved["deck"]["cards"] == [{"name": "Forest", "quantity": 3}]


def test_builds_load_swaps_session(tmp_path):
    client, state = _client(tmp_path)
    state.store.save("saved1", "Saved", DECK)
    snap = client.post("/api/builds/load", json={"id": "saved1"}).json()
    assert snap["build_id"] == "saved1"
    assert state.session.to_deck_dict() == DECK


def test_builds_load_404_for_unknown(tmp_path):
    client, _ = _client(tmp_path)
    assert client.post("/api/builds/load", json={"id": "nope"}).status_code == 404


def test_export_endpoint_moxfield_and_json(tmp_path):
    client, state = _client(tmp_path)
    state.session.add("Forest", 2)
    mox = client.get("/api/export", params={"fmt": "moxfield"}).json()
    assert mox["format"] == "moxfield"
    assert "2 Forest" in mox["text"]
    js = client.get("/api/export", params={"fmt": "json"}).json()
    assert js["deck"]["cards"] == [{"name": "Forest", "quantity": 2}]
