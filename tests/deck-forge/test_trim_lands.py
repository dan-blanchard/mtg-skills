"""The Mana Gate's 'Trim lands' action (FLOOD remedy, #13): POST /api/deck/trim-lands
removes basics back down to the recommended land count (max of Burgess/Karsten),
removing over-produced colors first. Soft — the frontend only surfaces it above the
flood line (recommended + 2), but the endpoint trims whenever the deck is over
recommended and is a no-op otherwise."""

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


def _client(plains=0):
    idx = {**BASICS, CMD["name"]: CMD, SPELL["name"]: SPELL}
    session = DeckSession("commander")
    session.add("WU Captain", zone="commanders")
    session.add("Double White")
    if plains:
        session.add("Plains", plains)
    state = ForgeState(
        by_name=idx, search_fn=lambda **_: [], session=session, bulk_available=True
    )
    return TestClient(build_app(state))


def test_trim_brings_a_flooded_deck_back_to_recommended():
    client = _client(plains=50)  # way over the flood line
    before = client.get("/api/snapshot").json()["mana"]
    assert before["land_count"] == 50
    assert before["land_count"] > before["recommended_land_count"] + 2  # FLOOD

    snap = client.post("/api/deck/trim-lands").json()
    mana = snap["mana"]
    assert mana["land_count"] == mana["recommended_land_count"]  # trimmed to target


def test_trim_removes_over_produced_basics_first():
    client = _client(plains=50)  # all white basics; demand is W-heavy but wants some U
    snap = client.post("/api/deck/trim-lands").json()
    trimmed = snap["trimmed"]
    assert trimmed["remove"].get("Plains", 0) > 0  # over-produced white trimmed down
    assert "Swamp" not in trimmed["add"]  # never adds off-identity basics


def test_trim_is_noop_when_not_over_recommended():
    client = _client(plains=0)  # 0 lands — under recommended, nothing to trim
    snap = client.post("/api/deck/trim-lands").json()
    assert snap["trimmed"] == {"add": {}, "remove": {}}
    assert client.get("/api/snapshot").json()["mana"]["land_count"] == 0
