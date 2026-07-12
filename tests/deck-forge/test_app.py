"""Endpoint tests for the deck-forge backend hub (DI, no bulk data needed)."""

from fastapi.testclient import TestClient

from mtg_utils._card_ir.crosswalk import ConceptTree
from mtg_utils._deck_forge import _ir_lookup
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.events import EventHub
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.card_ir import Card, Face
from mtg_utils.deck import split_type_line

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
    "oracle_text": "Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)",
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

ISHAI = {
    "name": "Ishai, Ojutai Dragonspeaker",
    # ADR-0027 t2b4a-B: partner_background is IR-served from the Scryfall `Partner`
    # keyword array, so the partner fixture carries the keyword + an oracle_id.
    "oracle_id": "oid-ishai",
    "type_line": "Legendary Creature — Bird Monk",
    "mana_cost": "{W}{U}",
    "cmc": 2.0,
    "color_identity": ["W", "U"],
    "oracle_text": "Flying\nWhenever an opponent casts a spell, put a +1/+1 counter on Ishai.\nPartner (You can have two commanders if both have partner.)",
    "legalities": {"commander": "legal"},
    "keywords": ["Flying", "Partner"],
}

INDEX = {c["name"]: c for c in (LLANOWAR, FOREST, ATRAXA, PLANESWALKER, ISHAI)}


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


def test_set_format_changes_format_and_rejects_unknown():
    client = make_client()
    snap = client.post("/api/deck/format", json={"format": "brawl"}).json()
    assert snap["deck"]["format"] == "brawl"
    bad = client.post("/api/deck/format", json={"format": "bogus"})
    assert bad.status_code == 400


def test_partner_avenue_filters_to_valid_partners(monkeypatch):
    # One commander with plain Partner → the avenue searches for legal partners
    # (color-agnostic), not the generic "any partner/background card".
    # ADR-0027 t2b4a-B: partner_background is IR-served, so wire a non-None IR for
    # Ishai's oracle_id (the hybrid path reads the record's keywords + needs an IR).
    ishai_index = {
        "oid-ishai": Card(
            oracle_id="oid-ishai",
            name="Ishai",
            faces=(Face(name="Ishai", abilities=()),),
        )
    }
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: ishai_index)
    # ADR-0039 task #80 step 6: extract_signals_hybrid is now crosswalk-only —
    # partner_background is a keyword-field lookup (no typed substrate needed),
    # so a zero-unit text-only tree (the same shape _ir_lookup's own W2c
    # phase-missing-face synthesis produces) is enough.
    type_words, sub_words = split_type_line(ISHAI["type_line"])
    ishai_tree = ConceptTree(
        name=ISHAI["name"],
        oracle_id=ISHAI["oracle_id"],
        units=(),
        card_types=tuple(w.capitalize() for w in type_words if w != "legendary"),
        card_subtypes=tuple(w.capitalize() for w in sub_words),
        card_supertypes=("Legendary",) if "legendary" in type_words else (),
        cmc=int(ISHAI["cmc"]),
        oracle=ISHAI["oracle_text"],
    )
    monkeypatch.setattr(
        _ir_lookup,
        "trees_for",
        lambda card, bulk=None: (  # noqa: ARG005
            (ishai_tree,) if card.get("oracle_id") == "oid-ishai" else ()
        ),
    )
    session = DeckSession("commander")
    session.add("Ishai, Ojutai Dragonspeaker", zone="commanders")
    client = make_client(session=session)
    avenues = {a["label"]: a for a in client.get("/api/snapshot").json()["avenues"]}
    assert "Partner / Background" in avenues
    search = avenues["Partner / Background"]["search"]
    assert search.get("color_identity") == "WUBRG"  # partners aren't color-restricted
    assert "partner" in (search.get("oracle") or "").lower()


def test_partner_avenue_hidden_when_slot_filled():
    # Two commanders → no open partner slot → no partner avenue offered.
    session = DeckSession("commander")
    session.add("Ishai, Ojutai Dragonspeaker", zone="commanders")
    session.add("Atraxa, Praetors' Voice", zone="commanders")
    client = make_client(session=session)
    labels = {a["label"] for a in client.get("/api/snapshot").json()["avenues"]}
    assert "Partner / Background" not in labels


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
