"""Endpoint tests for the deck-forge backend hub (DI, no bulk data needed)."""

from fastapi.testclient import TestClient

from mtg_utils._card_ir import compat_lookup as _ir_lookup
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.events import EventHub
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.testkit import test_card, test_card_ir

LLANOWAR = {
    **test_card("Llanowar Elves"),
    "rarity": "common",
    "prices": {"usd": "0.15"},
    "image_uris": {
        "small": "https://img/elf-small.jpg",
        "normal": "https://img/elf-normal.jpg",
        "art_crop": "https://img/elf-art.jpg",
    },
}
FOREST = {**test_card("Forest"), "rarity": "common", "prices": {"usd": "0.05"}}
ATRAXA = {
    **test_card("Atraxa, Praetors' Voice"),
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

# ADR-0027 t2b4a-B: partner_background is IR-served from the Scryfall `Partner`
# keyword array — the real record carries the keyword and its oracle_id.
ISHAI = test_card("Ishai, Ojutai Dragonspeaker")

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
    "layout": "normal",
    "unknown": False,
    "copy_limit": None,  # a basic land: unlimited (CR 100.2a)
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
    # Every Commander-family format is accepted, Competitive Brawl included.
    snap = client.post("/api/deck/format", json={"format": "competitive_brawl"}).json()
    assert snap["deck"]["format"] == "competitive_brawl"
    assert snap["deck"]["medium"] == "digital"
    # ...and it is Arena-only, so a paper medium is refused like digital commander.
    paper = client.post("/api/deck/medium", json={"medium": "paper"})
    assert paper.status_code == 400
    bad = client.post("/api/deck/format", json={"format": "bogus"})
    assert bad.status_code == 400


def test_partner_avenue_filters_to_valid_partners(monkeypatch):
    # One commander with plain Partner → the avenue searches for legal partners
    # (color-agnostic), not the generic "any partner/background card".
    # ADR-0027 t2b4a-B: partner_background is IR-served, so wire Ishai's REAL IR
    # into the crosswalk index (the hybrid path reads the record's keywords + needs
    # an IR). test_card_ir also seeds the concept-tree memo from the snapshot's
    # stored phase records, so the engine's own trees_for finds Ishai's real tree.
    ishai_ir = test_card_ir("Ishai, Ojutai Dragonspeaker")
    monkeypatch.setattr(
        _ir_lookup, "_crosswalk_index", lambda: {ishai_ir.oracle_id: ishai_ir}
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


def test_snapshot_carries_the_busy_meter_and_the_reporter_drives_it():
    """The first-launch signals-index build reports into the state: the snapshot
    shows the job (done / total / time left) while it runs and null when idle,
    and the estimate starts unknown (the pass has just begun), not at zero."""
    from mtg_utils._deck_forge import engine
    from mtg_utils._deck_forge.app import busy_reporter

    client = make_client(session=DeckSession("commander"))
    assert client.get("/api/snapshot").json()["busy"] is None
    st = ForgeState(
        by_name={}, search_fn=lambda **_: [], session=DeckSession("commander")
    )
    report = busy_reporter(st)
    report("signals-index", engine.SIGNALS_INDEX_LABEL, 0, 4000)
    assert st.busy["done"] == 0
    assert st.busy["eta_s"] is None  # nothing to pace yet
    report("signals-index", engine.SIGNALS_INDEX_LABEL, 1000, 4000)
    assert st.busy["total"] == 4000
    assert st.busy["label"] == engine.SIGNALS_INDEX_LABEL
    assert st.busy["eta_s"] is not None
    report("signals-index", engine.SIGNALS_INDEX_LABEL, 4000, 4000)
    assert st.busy is None


def test_the_busy_meter_is_first_come_between_concurrent_jobs():
    """Two passes in flight (a launch warm and a foreground discover) report as
    different jobs: the second is ignored — never a jittery total, never one
    clearing the other's bar — until the first finishes."""
    from mtg_utils._deck_forge import engine

    st = ForgeState(
        by_name={}, search_fn=lambda **_: [], session=DeckSession("commander")
    )
    first = engine.record_busy(st, "discovery-a", "Indexing", 1, 10)
    assert engine.record_busy(st, "discovery-b", "Indexing", 5, 6) is first
    assert st.busy["job"] == "discovery-a"
    assert engine.record_busy(st, "discovery-b", "Indexing", 6, 6) is first  # no clear
    assert engine.record_busy(st, "discovery-a", "Indexing", 10, 10) is None
    assert st.busy is None
    assert (
        engine.record_busy(st, "discovery-b", "Indexing", 3, 6)["job"] == "discovery-b"
    )
