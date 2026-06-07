"""Endpoint tests for the deck-forge backend hub (DI, no bulk data needed)."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.events import EventHub
from mtg_utils._deck_forge.state import DeckSession, ForgeState

LLANOWAR = {
    "name": "Llanowar Elves",
    "type_line": "Creature — Elf Druid",
    "mana_cost": "{G}",
    "cmc": 1.0,
    "color_identity": ["G"],
    "produced_mana": ["G"],
    "oracle_text": "{T}: Add {G}.",
    "rarity": "common",
    "prices": {"usd": "0.15"},
    "image_uris": {
        "small": "https://img/elf-small.jpg",
        "normal": "https://img/elf-normal.jpg",
        "art_crop": "https://img/elf-art.jpg",
    },
}
FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "mana_cost": "",
    "cmc": 0.0,
    "color_identity": ["G"],
    "produced_mana": ["G"],
    "oracle_text": "({T}: Add {G}.)",
    "rarity": "common",
    "prices": {"usd": "0.05"},
}
ATRAXA = {
    "name": "Atraxa, Praetors' Voice",
    "type_line": "Legendary Creature — Phyrexian Angel Horror",
    "mana_cost": "{G}{W}{U}{B}",
    "cmc": 4.0,
    "color_identity": ["W", "U", "B", "G"],
    "oracle_text": "Flying, vigilance, deathtouch, lifelink",
    "rarity": "mythic",
    "prices": {"usd": "12.00"},
}

PLANESWALKER = {
    "name": "Test Walker",
    "type_line": "Legendary Planeswalker — Test",
    "mana_cost": "{2}{U}",
    "cmc": 3.0,
    "color_identity": ["U"],
    "oracle_text": "+1: Draw a card.",
    "rarity": "mythic",
    "prices": {"usd": "5.00"},
    "legalities": {"commander": "legal", "brawl": "legal", "standardbrawl": "legal"},
}

INDEX = {c["name"]: c for c in (LLANOWAR, FOREST, ATRAXA, PLANESWALKER)}


def make_client(*, search_results=None, session=None):
    state = ForgeState(
        by_name=INDEX,
        search_fn=lambda **_: list(search_results or []),
        session=session or DeckSession("commander"),
        hub=EventHub(),
    )
    return TestClient(build_app(state))


def test_add_known_card_appears_in_deck_with_images():
    client = make_client()
    resp = client.post("/api/deck/add", json={"name": "Llanowar Elves"})
    assert resp.status_code == 200
    cards = resp.json()["deck"]["cards"]
    assert cards[0]["name"] == "Llanowar Elves"
    assert cards[0]["quantity"] == 1
    assert cards[0]["images"]["small"] == "https://img/elf-small.jpg"


def test_add_unknown_card_is_rejected():
    client = make_client()
    resp = client.post("/api/deck/add", json={"name": "Definitely Not A Card"})
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_remove_card():
    session = DeckSession("commander")
    session.add("Forest", 2)
    client = make_client(session=session)
    resp = client.post("/api/deck/remove", json={"name": "Forest", "qty": 1})
    assert resp.status_code == 200
    assert resp.json()["deck"]["cards"] == [
        {"name": "Forest", "quantity": 1, **_FOREST_VIEW}
    ]


_FOREST_VIEW = {
    "type_line": "Basic Land — Forest",
    "mana_cost": "",
    "cmc": 0.0,
    "color_identity": ["G"],
    "oracle_text": "({T}: Add {G}.)",
    "rarity": "common",
    "prices": {"usd": "0.05"},
    "images": None,
    "game_changer": None,
    "can_be_commander": False,
    "layout": "",
    "unknown": False,
}


def test_card_view_flags_commander_eligibility():
    session = DeckSession("commander")
    session.add("Atraxa, Praetors' Voice", zone="commanders")
    session.add("Forest", 1)
    client = make_client(session=session)
    snap = client.get("/api/snapshot").json()
    assert snap["deck"]["commanders"][0]["can_be_commander"] is True
    assert snap["deck"]["cards"][0]["can_be_commander"] is False


def test_commander_eligibility_is_format_aware():
    # A legendary planeswalker is a commander in historic_brawl but NOT in commander.
    client = make_client(search_results=[PLANESWALKER])
    body = {"name": "Test Walker"}
    res_cmd = client.post("/api/search", json=body).json()["results"][0]
    assert res_cmd["can_be_commander"] is False  # default commander format
    client.post("/api/deck/format", json={"format": "historic_brawl"})
    res_hb = client.post("/api/search", json=body).json()["results"][0]
    assert res_hb["can_be_commander"] is True


def test_set_format_changes_format_and_rejects_unknown():
    client = make_client()
    snap = client.post("/api/deck/format", json={"format": "brawl"}).json()
    assert snap["deck"]["format"] == "brawl"
    bad = client.post("/api/deck/format", json={"format": "bogus"})
    assert bad.status_code == 400


def test_search_projects_results_with_images():
    client = make_client(search_results=[LLANOWAR])
    resp = client.post("/api/search", json={"color_identity": "G", "type": "Creature"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["name"] == "Llanowar Elves"
    assert results[0]["images"]["normal"] == "https://img/elf-normal.jpg"
    assert results[0]["cmc"] == 1.0


def test_stats_endpoint_counts_lands_and_creatures():
    session = DeckSession("commander")
    session.add("Forest")
    session.add("Llanowar Elves")
    client = make_client(session=session)
    stats = client.get("/api/stats").json()
    assert stats["land_count"] == 1
    assert stats["creature_count"] == 1


def test_mana_audit_endpoint_reports_status_and_land_count():
    session = DeckSession("commander")
    session.add("Atraxa, Praetors' Voice", zone="commanders")
    session.add("Forest", 30)
    client = make_client(session=session)
    audit = client.get("/api/mana-audit").json()
    assert audit["land_count"] == 30
    assert audit["overall_status"] in {"PASS", "WARN", "FAIL"}


def test_snapshot_bundles_deck_stats_mana():
    client = make_client()
    snap = client.get("/api/snapshot").json()
    assert set(snap) >= {"deck", "stats", "mana"}
