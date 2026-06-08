"""Deck import (#1, ADR-0017): POST /api/builds/import parses a pasted / uploaded list
in-process (pure compute) and seeds a NEW build — it never overwrites the live build and
never guesses a commander (an unmarked list lands as a pile in ``cards``)."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState

SOL_RING = {
    "name": "Sol Ring",
    "type_line": "Artifact",
    "cmc": 1.0,
    "mana_cost": "{1}",
    "color_identity": [],
    "oracle_text": "{T}: Add {C}{C}.",
    "prices": {"usd": "1.50"},
    "legalities": {"commander": "legal"},
}

PLAIN = "1 Sol Ring\n1 Llanowar Elves\n1 Arcane Signet\n"
WITH_COMMANDER = (
    "Commander\n1 Atraxa, Praetors' Voice\n\nDeck\n1 Sol Ring\n1 Llanowar Elves\n"
)


def _client(by_name=None):
    state = ForgeState(
        by_name=by_name or {},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        bulk_available=True,
        build_id="orig",
    )
    return TestClient(build_app(state)), state


def test_import_plain_list_seeds_a_new_build_with_no_commander():
    client, state = _client()
    r = client.post("/api/builds/import", json={"text": PLAIN, "format": "commander"})
    assert r.status_code == 200
    data = r.json()
    assert data["build_id"] != "orig"  # a NEW build, never the live one
    assert state.build_id == data["build_id"]
    assert {c["name"] for c in data["deck"]["cards"]} == {
        "Sol Ring",
        "Llanowar Elves",
        "Arcane Signet",
    }
    assert data["deck"]["commanders"] == []  # never guessed
    assert data["imported"]["cards"] == 3


def test_import_detects_a_marked_commander():
    client, _ = _client()
    data = client.post("/api/builds/import", json={"text": WITH_COMMANDER}).json()
    assert [c["name"] for c in data["deck"]["commanders"]] == [
        "Atraxa, Praetors' Voice"
    ]
    assert data["imported"]["commanders"] == 1


def test_import_reports_unhydratable_names():
    client, _ = _client(by_name={"Sol Ring": SOL_RING})
    data = client.post("/api/builds/import", json={"text": PLAIN}).json()
    assert data["imported"]["unknown"] == ["Arcane Signet", "Llanowar Elves"]


def test_import_rejects_an_empty_list():
    client, _ = _client()
    assert (
        client.post("/api/builds/import", json={"text": "   \n  "}).status_code == 400
    )


def test_import_rejects_an_unsupported_format():
    client, _ = _client()
    r = client.post("/api/builds/import", json={"text": PLAIN, "format": "modern"})
    assert r.status_code == 400
