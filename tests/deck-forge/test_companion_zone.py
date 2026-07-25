"""Companion-zone tests: the outside-the-game zone (CR 702.139a-b).

Covers the zone rules at the endpoints (max one occupant per CR 103.2b, the
occupant must actually have the companion ability per CR 702.139a), import
routing, snapshot serialization, deck-size exclusion (a companion never counts
toward the exact Commander-family size, CR 903.5a), the audit's condition
warnings (CR 702.139b), and the export→import round-trip.
"""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.parse_deck import parse_deck_text

KERUGA = {
    "name": "Keruga, the Macrosage",
    "type_line": "Legendary Creature — Dinosaur Hippo",
    "cmc": 5.0,
    "mana_cost": "{3}{G}{U}",
    "color_identity": ["G", "U"],
    "oracle_text": (
        "Companion — Your starting deck contains only cards with mana value 3 "
        "or greater and land cards.\nWhen Keruga, the Macrosage enters, draw a "
        "card for each other permanent you control with mana value 3 or greater."
    ),
    "keywords": ["Companion"],
    "legalities": {"commander": "legal"},
}
YORION = {
    "name": "Yorion, Sky Nomad",
    "type_line": "Legendary Creature — Bird Serpent",
    "cmc": 4.0,
    "mana_cost": "{3}{W/U}",
    "color_identity": ["W", "U"],
    "oracle_text": (
        "Companion — Your starting deck contains at least twenty cards more "
        "than the minimum deck size.\nWhen Yorion enters, exile any number of "
        "other nonland permanents you own and control. Return them at the "
        "beginning of the next end step."
    ),
    "keywords": ["Companion"],
    "legalities": {"commander": "legal"},
}
ATRAXA = {
    "name": "Atraxa, Praetors' Voice",
    "type_line": "Legendary Creature — Phyrexian Angel Horror",
    "cmc": 4.0,
    "color_identity": ["W", "U", "B", "G"],
    "oracle_text": "Flying, vigilance, deathtouch, lifelink",
    "legalities": {"commander": "legal"},
}
SOL_RING = {
    "name": "Sol Ring",
    "type_line": "Artifact",
    "cmc": 1.0,
    "mana_cost": "{1}",
    "color_identity": [],
    "oracle_text": "{T}: Add {C}{C}.",
    "legalities": {"commander": "legal"},
}
FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "cmc": 0.0,
    "color_identity": ["G"],
    "oracle_text": "({T}: Add {G}.)",
    "legalities": {"commander": "legal"},
}
HILL_GIANT = {
    "name": "Hill Giant",
    "type_line": "Creature — Giant",
    "cmc": 4.0,
    "color_identity": ["R"],
    "oracle_text": "",
    "legalities": {"commander": "legal"},
}
INDEX = {c["name"]: c for c in (KERUGA, YORION, ATRAXA, SOL_RING, FOREST, HILL_GIANT)}


def _state(commanders=(), cards=(), companion=()):
    session = DeckSession("commander")
    for name in commanders:
        session.add(name, 1, zone="commanders")
    for name, qty in cards:
        session.add(name, qty)
    for name in companion:
        session.add(name, 1, zone="companion")
    return ForgeState(by_name=INDEX, search_fn=lambda **_: [], session=session)


def _client(state=None):
    return TestClient(build_app(state or _state()))


# ---------- zone rules at the endpoints ----------


def test_add_companion_succeeds_and_appears_in_snapshot():
    client = _client()
    r = client.post(
        "/api/deck/add", json={"name": "Keruga, the Macrosage", "zone": "companion"}
    )
    assert r.status_code == 200
    zone = r.json()["deck"]["companion"]
    assert len(zone) == 1
    # Full card_view entries, not bare names — the frontend renders the zone.
    assert zone[0]["name"] == "Keruga, the Macrosage"
    assert zone[0]["quantity"] == 1
    assert zone[0]["type_line"] == "Legendary Creature — Dinosaur Hippo"
    assert zone[0]["unknown"] is False


def test_add_second_companion_is_rejected_zone_occupied():
    state = _state(companion=["Keruga, the Macrosage"])
    r = _client(state).post(
        "/api/deck/add", json={"name": "Yorion, Sky Nomad", "zone": "companion"}
    )
    assert r.status_code == 400
    msg = r.json()["error"]
    assert "Keruga, the Macrosage" in msg
    assert "103.2b" in msg
    # Never silently replaced: the original occupant is still there.
    assert state.session.to_deck_dict()["companion"] == [
        {"name": "Keruga, the Macrosage", "quantity": 1}
    ]


def test_add_same_companion_twice_is_rejected():
    state = _state(companion=["Keruga, the Macrosage"])
    r = _client(state).post(
        "/api/deck/add", json={"name": "Keruga, the Macrosage", "zone": "companion"}
    )
    assert r.status_code == 400


def test_add_companion_with_qty_above_one_is_rejected():
    r = _client().post(
        "/api/deck/add",
        json={"name": "Keruga, the Macrosage", "zone": "companion", "qty": 2},
    )
    assert r.status_code == 400
    assert "103.2b" in r.json()["error"]


def test_add_non_companion_card_is_rejected():
    r = _client().post("/api/deck/add", json={"name": "Sol Ring", "zone": "companion"})
    assert r.status_code == 400
    assert r.json()["error"] == "Sol Ring has no companion ability (CR 702.139a)"


def test_remove_from_companion_zone_works_like_any_zone():
    state = _state(companion=["Keruga, the Macrosage"])
    r = _client(state).post(
        "/api/deck/remove",
        json={"name": "Keruga, the Macrosage", "zone": "companion"},
    )
    assert r.status_code == 200
    assert r.json()["deck"]["companion"] == []


# ---------- deck-size math excludes the zone ----------


def test_exactly_full_deck_plus_companion_has_no_deck_maximum_warning():
    # 1 commander + 99 cards = exactly 100 (CR 903.5a); the companion is outside
    # the game (CR 702.139a-b) and must not tip the count to 101.
    state = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Forest", 99)],
        companion=["Keruga, the Macrosage"],
    )
    warns = engine.legality_warnings(
        engine.hydrate_session(state), max_cards=state.session.deck_size
    )
    assert "deck_maximum" not in {w["category"] for w in warns}


def test_overfull_deck_still_warns_with_companion_present():
    state = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Forest", 100)],
        companion=["Keruga, the Macrosage"],
    )
    warns = engine.legality_warnings(
        engine.hydrate_session(state), max_cards=state.session.deck_size
    )
    assert "deck_maximum" in {w["category"] for w in warns}
    assert any("101" in w["message"] for w in warns)


def test_tune_scorecard_size_total_excludes_companion():
    state = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Hill Giant", 1), ("Forest", 2)],
        companion=["Keruga, the Macrosage"],
    )
    r = _client(state).post("/api/tune", json={"max_swaps": 0})
    assert r.status_code == 200
    assert r.json()["scorecard"]["size"]["total"] == 4  # 1 commander + 3 cards


# ---------- audit: condition violations with CR cites ----------


def test_audit_flags_keruga_condition_with_cr_cite():
    # Keruga requires every nonland to be mana value 3+; Sol Ring is a 1-drop.
    state = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Sol Ring", 1), ("Hill Giant", 1), ("Forest", 2)],
        companion=["Keruga, the Macrosage"],
    )
    warns = _client(state).get("/api/audit").json()["warnings"]
    companion_warns = [w for w in warns if w["category"] == "companion"]
    assert len(companion_warns) == 1
    msg = companion_warns[0]["message"]
    assert "Keruga, the Macrosage" in msg
    assert "Sol Ring" in msg
    assert "702.139b" in msg


def test_audit_yorion_is_unsatisfiable_in_exact_size_formats():
    # All deck-forge formats are exact-size (CR 903.5a / 903.12d): "minimum + 20"
    # can never be met, and the audit says so instead of passing silently.
    state = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Forest", 2)],
        companion=["Yorion, Sky Nomad"],
    )
    warns = _client(state).get("/api/audit").json()["warnings"]
    companion_warns = [w for w in warns if w["category"] == "companion"]
    assert len(companion_warns) == 1
    assert "Yorion, Sky Nomad" in companion_warns[0]["message"]
    assert "702.139b" in companion_warns[0]["message"]


def test_audit_satisfied_condition_emits_no_companion_warning():
    state = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Hill Giant", 1), ("Forest", 2)],
        companion=["Keruga, the Macrosage"],
    )
    warns = _client(state).get("/api/audit").json()["warnings"]
    assert not [w for w in warns if w["category"] == "companion"]


def test_finalize_gates_on_companion_violation():
    state = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Sol Ring", 1), ("Forest", 2)],
        companion=["Keruga, the Macrosage"],
    )
    report = _client(state).post("/api/finalize", json={}).json()
    assert report["legality_status"] == "FAIL"
    assert any(w["category"] == "companion" for w in report["warnings"])


# ---------- import routing ----------


def test_import_routes_companion_section_to_the_zone():
    text = (
        "Commander\n1 Atraxa, Praetors' Voice\n\n"
        "Companion\n1 Keruga, the Macrosage\n\n"
        "Deck\n1 Hill Giant\n2 Forest\n"
    )
    data = _client().post("/api/builds/import", json={"text": text}).json()
    assert data["deck"]["companion"][0]["name"] == "Keruga, the Macrosage"
    assert data["imported"]["companion"] == 1
    assert data["imported"]["warnings"] == []
    # The companion never counts as a maindeck card.
    assert data["imported"]["cards"] == 3


def test_import_demotes_second_companion_to_cards_with_warning():
    text = "Companion\n1 Keruga, the Macrosage\n1 Yorion, Sky Nomad\n\nDeck\n2 Forest\n"
    data = _client().post("/api/builds/import", json={"text": text}).json()
    assert [e["name"] for e in data["deck"]["companion"]] == ["Keruga, the Macrosage"]
    assert "Yorion, Sky Nomad" in {c["name"] for c in data["deck"]["cards"]}
    assert any("103.2b" in w for w in data["imported"]["warnings"])


def test_import_demotes_non_companion_to_cards_with_warning():
    text = "Companion\n1 Sol Ring\n\nDeck\n2 Forest\n"
    data = _client().post("/api/builds/import", json={"text": text}).json()
    assert data["deck"]["companion"] == []
    assert "Sol Ring" in {c["name"] for c in data["deck"]["cards"]}
    assert any("702.139a" in w for w in data["imported"]["warnings"])


def test_import_keeps_unknown_companion_name_in_the_zone():
    # An un-hydratable name can't be proven a non-companion; it stays in the
    # zone and surfaces through the `unknown` channel like any other zone.
    text = "Companion\n1 Mystery Cat\n\nDeck\n2 Forest\n"
    data = _client().post("/api/builds/import", json={"text": text}).json()
    assert data["deck"]["companion"][0]["name"] == "Mystery Cat"
    assert data["deck"]["companion"][0]["unknown"] is True
    assert "Mystery Cat" in data["imported"]["unknown"]


# ---------- export round-trip ----------


def test_export_arena_and_moxfield_round_trip_the_companion_zone():
    state = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Forest", 2)],
        companion=["Keruga, the Macrosage"],
    )
    client = _client(state)
    for fmt in ("arena", "moxfield"):
        text = client.get("/api/export", params={"fmt": fmt}).json()["text"]
        assert "Companion" in text
        parsed = parse_deck_text(text, format="commander")
        assert parsed["companion"] == [
            {"name": "Keruga, the Macrosage", "quantity": 1}
        ], fmt
        assert "Keruga, the Macrosage" not in {e["name"] for e in parsed["cards"]}, fmt


def test_session_round_trips_companion_through_deck_dict():
    state = _state(companion=["Keruga, the Macrosage"])
    deck = state.session.to_deck_dict()
    assert deck["companion"] == [{"name": "Keruga, the Macrosage", "quantity": 1}]
    assert DeckSession.from_deck_dict(deck).to_deck_dict() == deck
