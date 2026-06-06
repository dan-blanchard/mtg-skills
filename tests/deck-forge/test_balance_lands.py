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


def test_balance_targets_the_floor_not_recommended():
    client = _client()
    assert client.get("/api/snapshot").json()["mana"]["land_count"] == 0
    mana = client.post("/api/deck/balance-lands").json()["mana"]
    # fills to the FAIL floor (= Burgess), not all the way to the recommended count.
    assert mana["land_count"] == mana["land_count_floor"]
    assert mana["land_count_floor"] == mana["burgess_formula"]["result"]
    assert mana["land_count"] <= mana["recommended_land_count"]
    assert mana["land_count_status"] != "FAIL"


def test_balance_distributes_by_color_demand():
    snap = _client().post("/api/deck/balance-lands").json()
    add = snap["balanced"]["add"]
    # pips favor white (commander W + double-white spell) → more Plains than Islands.
    assert add.get("Plains", 0) > add.get("Island", 0) > 0
    assert "Swamp" not in add  # off-identity basics never added


def test_rebalance_swaps_basics_at_count_net_zero():
    # already at the floor but all white basics → swap some Plains for Islands, no net
    # change in land count.
    idx = {**BASICS, CMD["name"]: CMD, SPELL["name"]: SPELL}
    session = DeckSession("commander")
    session.add("WU Captain", zone="commanders")
    session.add("Double White")
    state = ForgeState(
        by_name=idx, search_fn=lambda **_: [], session=session, bulk_available=True
    )
    client = TestClient(build_app(state))
    floor = client.get("/api/snapshot").json()["mana"]["land_count_floor"]
    session.add("Plains", floor)  # at the floor, but mono-white basics
    assert client.get("/api/snapshot").json()["mana"]["land_count"] == floor

    snap = client.post("/api/deck/balance-lands").json()
    bal = snap["balanced"]
    assert bal["remove"].get("Plains", 0) > 0  # over-produced white trimmed
    assert bal["add"].get("Island", 0) > 0  # under-produced blue added
    assert snap["mana"]["land_count"] == floor  # net-zero count


def test_noop_when_at_floor_and_balanced():
    client = _client()
    client.post("/api/deck/balance-lands")  # floor + balanced colors
    snap = client.post("/api/deck/balance-lands").json()  # nothing left to do
    assert snap["balanced"] == {"add": {}, "remove": {}}
