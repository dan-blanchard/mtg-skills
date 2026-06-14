"""Route tests for POST /api/tune — the thin adapter over the tuner core (ADR-0023)."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState

CMD = {
    "name": "Goblin Boss",
    "type_line": "Legendary Creature — Goblin Warrior",
    "cmc": 4.0,
    "color_identity": ["R"],
    "oracle_text": "{T}: Create a 1/1 red Goblin creature token.",
    "prices": {"usd": "5.00"},
}
RABBLE = {
    "name": "Goblin Rabblemaster",
    "type_line": "Creature — Goblin Warrior",
    "cmc": 3.0,
    "color_identity": ["R"],
    "oracle_text": "Other Goblin creatures you control attack each combat if able.\nAt the beginning of combat on your turn, create a 1/1 red Goblin creature token with haste.\nWhenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Goblin.",
    "prices": {"usd": "2.00"},
}
FILLER = {
    "name": "Hill Giant",
    "type_line": "Creature — Giant",
    "cmc": 4.0,
    "color_identity": ["R"],
    "oracle_text": "",
    "prices": {"usd": "0.10"},
}
MOUNTAIN = {
    "name": "Mountain",
    "type_line": "Basic Land — Mountain",
    "cmc": 0.0,
    "color_identity": [],
    "oracle_text": "({T}: Add {R}.)",
}
BOLT = {
    "name": "Lightning Bolt",
    "type_line": "Instant",
    "cmc": 1.0,
    "color_identity": ["R"],
    "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    "prices": {"usd": "1.00"},
}
INDEX = {c["name"]: c for c in (CMD, RABBLE, FILLER, MOUNTAIN, BOLT)}


def _client(*, search_results=None, bulk=True):
    session = DeckSession("commander")
    session.add("Goblin Boss", zone="commanders")
    session.add("Goblin Rabblemaster")
    session.add("Hill Giant")
    session.add("Mountain")
    state = ForgeState(
        by_name=INDEX,
        search_fn=lambda **_: list(search_results or []),
        session=session,
        bulk_available=bulk,
    )
    return TestClient(build_app(state))


def test_tune_diagnose_only_returns_scorecard():
    r = _client().post("/api/tune", json={"max_swaps": 0})
    assert r.status_code == 200
    data = r.json()
    sc = data["scorecard"]
    assert sc["shape"]["value"] in ("aggro", "midrange", "control", "combo")
    assert sc["template"]["verdict"] in ("on-template", "off-template")
    assert "counts" in sc
    assert data["swaps"] == []


def test_tune_proposes_swaps_with_budget():
    # search_fn returns Bolt for any role query → an affordable interaction add.
    r = _client(search_results=[BOLT]).post(
        "/api/tune", json={"max_swaps": 2, "budget": 50.0}
    )
    data = r.json()
    assert data["swaps"], "expected swaps when a budget and adds are available"
    for s in data["swaps"]:
        assert s["cut"]["name"]
        assert s["add"]["name"] == "Lightning Bolt"
    assert data["spent"] <= 50.0


def test_tune_owned_only_default_no_spend():
    r = _client(search_results=[BOLT]).post("/api/tune", json={"max_swaps": 2})
    data = r.json()
    assert data["swaps"] == []  # owned-only + nothing owned → no buys
    assert data["spent"] == 0.0


def test_tune_no_bulk_returns_error_envelope():
    r = _client(bulk=False).post("/api/tune", json={"max_swaps": 0})
    # Mirrors /api/find: a no-bulk JSONResponse rather than a crash.
    assert r.json() != {"scorecard": None}
    assert "scorecard" not in r.json()


def test_tune_shape_override():
    r = _client().post("/api/tune", json={"shape_override": "control"})
    sc = r.json()["scorecard"]
    assert sc["shape"]["value"] == "control"
    assert sc["shape"]["inferred"] is False
