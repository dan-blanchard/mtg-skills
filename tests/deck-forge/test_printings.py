"""Printing picker (C): list a card's printings, pin one, and have it drive the deck
view (image / price / set) + export, round-tripping through the session."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _printing(set_code, collector, usd, released):
    return {
        "name": "Sol Ring",
        "oracle_id": "oid-sol-ring",
        "id": f"id-{set_code}",
        "set": set_code,
        "set_name": f"{set_code} set",
        "collector_number": collector,
        "released_at": released,
        "rarity": "uncommon",
        "finishes": ["nonfoil"],
        "prices": {"usd": usd},
        "image_uris": {
            "small": f"https://img/{set_code}/small.jpg",
            "normal": f"https://img/{set_code}/normal.jpg",
        },
        "type_line": "Artifact",
        "cmc": 1.0,
        "color_identity": [],
        "oracle_text": "{T}: Add {C}{C}.",
        "mana_cost": "{1}",
        "legalities": {"commander": "legal"},
        "keywords": [],
    }


CHEAP = _printing("LEA", "1", "2.00", "1993-08-05")
PREMIUM = _printing("C21", "263", "5.00", "2021-04-23")


def _state():
    return ForgeState(
        by_name={"Sol Ring": CHEAP},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        bulk_available=True,
        printings_by_oracle={"oid-sol-ring": [PREMIUM, CHEAP]},
        printing_by_id={"id-LEA": CHEAP, "id-C21": PREMIUM},
    )


def _client(state=None):
    return TestClient(build_app(state or _state()))


def test_printings_lists_all_printings_of_a_card():
    res = _client().get("/api/printings?name=Sol Ring").json()
    sets = [p["set"] for p in res["printings"]]
    assert sets == ["C21", "LEA"]  # newest first
    assert res["printings"][0]["prices"]["usd"] == "5.00"


def test_chosen_printing_drives_deck_view_image_price_and_set():
    c = _client()
    c.post("/api/deck/add", json={"name": "Sol Ring", "zone": "cards"})
    snap = c.post(
        "/api/deck/printing", json={"name": "Sol Ring", "printing_id": "id-C21"}
    ).json()
    card = snap["deck"]["cards"][0]
    assert card["printing_id"] == "id-C21"
    assert card["set"] == "C21"
    assert card["collector_number"] == "263"
    assert card["prices"]["usd"] == "5.00"
    assert card["images"]["small"] == "https://img/C21/small.jpg"


def test_export_honors_chosen_printing_suffix():
    c = _client()
    c.post("/api/deck/add", json={"name": "Sol Ring", "zone": "cards"})
    c.post("/api/deck/printing", json={"name": "Sol Ring", "printing_id": "id-C21"})
    text = c.get("/api/export?fmt=moxfield").json()["text"]
    assert "1 Sol Ring (C21) 263" in text


def test_clearing_printing_reverts_to_default():
    c = _client()
    c.post("/api/deck/add", json={"name": "Sol Ring", "zone": "cards"})
    c.post("/api/deck/printing", json={"name": "Sol Ring", "printing_id": "id-C21"})
    snap = c.post(
        "/api/deck/printing", json={"name": "Sol Ring", "printing_id": None}
    ).json()
    card = snap["deck"]["cards"][0]
    assert "printing_id" not in card
    assert card["prices"]["usd"] == "2.00"  # back to the cheap default


def test_invalid_printing_id_is_a_400():
    c = _client()
    c.post("/api/deck/add", json={"name": "Sol Ring", "zone": "cards"})
    r = c.post(
        "/api/deck/printing", json={"name": "Sol Ring", "printing_id": "id-NOPE"}
    )
    assert r.status_code == 400


def test_printing_round_trips_through_session():
    session = DeckSession("commander")
    session.add("Sol Ring", 1, zone="cards")
    session.set_printing("Sol Ring", "id-C21", zone="cards")
    rebuilt = DeckSession.from_deck_dict(session.to_deck_dict())
    assert rebuilt.printing_of("Sol Ring", zone="cards") == "id-C21"
    # removing the last copy drops the pinned printing
    rebuilt.remove("Sol Ring", 1, zone="cards")
    assert rebuilt.printing_of("Sol Ring", zone="cards") is None
