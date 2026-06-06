"""The Mana Gate's 'Balance lands' action: POST /api/deck/balance-lands adds basic
lands of each color to reach the recommended land count, distributed by color demand,
so the gate passes."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _basic(name, color, subtype):
    return {
        "name": name,
        "type_line": f"Basic Land — {subtype}",
        "cmc": 0.0,
        "mana_cost": "",
        "color_identity": [],
        "produced_mana": [color],
        "oracle_text": f"({{T}}: Add {{{color}}}.)",
        "keywords": [],
    }


BASICS = {
    "Plains": _basic("Plains", "W", "Plains"),
    "Island": _basic("Island", "U", "Island"),
    "Swamp": _basic("Swamp", "B", "Swamp"),
    "Mountain": _basic("Mountain", "R", "Mountain"),
    "Forest": _basic("Forest", "G", "Forest"),
    "Wastes": _basic("Wastes", "C", "Wastes"),
}
CMD = {
    "name": "WU Captain",
    "type_line": "Legendary Creature — Bird Soldier",
    "cmc": 3.0,
    "mana_cost": "{1}{W}{U}",
    "color_identity": ["W", "U"],
    "oracle_text": "",
    "keywords": ["Flying"],
}
SPELL = {
    "name": "Double White",
    "type_line": "Sorcery",
    "cmc": 2.0,
    "mana_cost": "{W}{W}",
    "color_identity": ["W"],
    "oracle_text": "Draw a card.",
    "keywords": [],
}


def _client():
    idx = {**BASICS, CMD["name"]: CMD, SPELL["name"]: SPELL}
    session = DeckSession("commander")
    session.add("WU Captain", zone="commanders")
    session.add("Double White")
    state = ForgeState(
        by_name=idx, search_fn=lambda **_: [], session=session, bulk_available=True
    )
    return TestClient(build_app(state))


def test_balance_lands_reaches_recommended_and_passes():
    client = _client()
    assert client.get("/api/snapshot").json()["mana"]["land_count"] == 0
    snap = client.post("/api/deck/balance-lands").json()
    mana = snap["mana"]
    assert mana["land_count"] == mana["recommended_land_count"]
    assert mana["land_count_status"] == "PASS"


def test_balance_lands_distributes_by_color_demand():
    snap = _client().post("/api/deck/balance-lands").json()
    added = snap["balanced"]
    # pips favor white (commander W + double-white spell) → more Plains than Islands,
    # but both colors get basics.
    assert added.get("Plains", 0) > added.get("Island", 0) > 0
    assert "Swamp" not in added  # off-identity basics never added
    names = [e["name"] for e in snap["deck"]["cards"]]
    assert "Plains" in names
    assert "Island" in names


def test_balance_lands_is_noop_when_already_full():
    client = _client()
    client.post("/api/deck/balance-lands")  # fills the base
    snap = client.post("/api/deck/balance-lands").json()  # nothing left to add
    assert snap["balanced"] == {}
