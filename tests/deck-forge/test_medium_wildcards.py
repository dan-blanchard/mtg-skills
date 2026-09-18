"""Paper/digital medium + Arena wildcard costing + the 60/100 paper-Historic-Brawl size.

medium drives the active Collection slot (paper deck → paper slot) and the cost mode
(digital → wildcards, paper → USD); paper Historic Brawl may be 60 or 100 cards, which
flows into the footer target and the land math."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _state(fmt="historic_brawl"):
    return ForgeState(
        by_name={},
        search_fn=lambda **_: [],
        session=DeckSession(fmt),
        bulk_available=True,
    )


# ── medium defaults + the paper/digital toggle ───────────────────────────────
def test_medium_defaults_by_format():
    assert DeckSession("commander").medium == "paper"  # paper-only
    assert DeckSession("brawl").medium == "digital"  # Arena is the common case
    assert DeckSession("historic_brawl").medium == "digital"
    assert DeckSession("competitive_brawl").medium == "digital"  # Arena-only


def test_competitive_brawl_is_always_digital_even_if_override_set():
    s = DeckSession("competitive_brawl")
    s.set_medium("paper")  # ignored — the format has no paper counterpart
    assert s.medium == "digital"
    assert s.deck_size == 100


def test_commander_is_always_paper_even_if_override_set():
    s = DeckSession("commander")
    s.set_medium("digital")  # ignored — commander has no digital medium
    assert s.medium == "paper"


def test_medium_drives_the_active_collection_slot():
    state = _state("historic_brawl")
    assert engine.active_slot(state) == "arena"  # digital default
    state.session.set_medium("paper")
    assert engine.active_slot(state) == "paper"  # paper HB reads the paper slot


def test_set_medium_endpoint_rejects_digital_commander():
    client = TestClient(build_app(_state("commander")))
    assert (
        client.post("/api/deck/medium", json={"medium": "digital"}).status_code == 400
    )


def test_set_medium_endpoint_switches_slot():
    client = TestClient(build_app(_state("historic_brawl")))
    snap = client.post("/api/deck/medium", json={"medium": "paper"}).json()
    assert snap["deck"]["medium"] == "paper"
    assert snap["collection"]["active_slot"] == "paper"


# ── 60 / 100 for paper Historic Brawl ────────────────────────────────────────
def test_deck_size_choosable_only_for_paper_historic_brawl():
    s = DeckSession("historic_brawl")  # digital
    s.set_deck_size(60)
    assert s.deck_size == 100  # digital HB is locked to 100
    s.set_medium("paper")
    assert s.deck_size == 60  # now the override applies
    assert DeckSession("brawl").deck_size == 60  # brawl always 60
    assert DeckSession("commander").deck_size == 100


def test_deck_size_endpoint_and_footer_target():
    client = TestClient(build_app(_state("historic_brawl")))
    client.post("/api/deck/medium", json={"medium": "paper"})
    snap = client.post("/api/deck/deck-size", json={"deck_size": 60}).json()
    assert snap["deck"]["deck_size"] == 60


def test_deck_size_endpoint_rejects_bad_value():
    client = TestClient(build_app(_state("historic_brawl")))
    assert client.post("/api/deck/deck-size", json={"deck_size": 42}).status_code == 400
    # A size some Commander-family medium may choose is accepted and lies dormant
    # (set 60 under Commander, toggle to paper Historic Brawl later and it applies).
    cmd = TestClient(build_app(_state("commander")))
    snap = cmd.post("/api/deck/deck-size", json={"deck_size": 60}).json()
    assert snap["deck"]["deck_size"] == 100


def test_snapshot_serves_the_format_table_the_spa_reads():
    from mtg_utils.formats import FORMATS, format_options

    client = TestClient(build_app(_state("historic_brawl")))
    snap = client.get("/api/snapshot").json()
    rows = snap["format_options"]
    assert rows == format_options()
    # Every Format the table declares, in table order — the SPA groups by family.
    assert [r["id"] for r in rows] == list(FORMATS)
    by_id = {r["id"]: r for r in rows}
    assert by_id["modern"]["family"] == "constructed"
    # Exactly what the Header derives its pickers from: media and per-medium sizes.
    assert by_id["commander"]["media"] == ["paper"]
    assert by_id["historic_brawl"]["medium_labels"] == {
        "digital": "Arena",
        "paper": "Paper",
    }
    assert by_id["competitive_brawl"]["media"] == ["digital"]
    assert by_id["historic_brawl"]["size_choices"] == {
        "digital": [100],
        "paper": [60, 100],
    }


# ── wildcard cost for digital builds ─────────────────────────────────────────
_RARITY_INDEX = {
    "shock": {"rarity": "uncommon", "exempt_from_4cap": False},
    "thoughtseize": {"rarity": "rare", "exempt_from_4cap": False},
    "sol ring": {"rarity": "uncommon", "exempt_from_4cap": False},
}


def _digital_state():
    by_name = {
        "Shock": {"name": "Shock", "type_line": "Instant", "color_identity": ["R"]},
        "Thoughtseize": {
            "name": "Thoughtseize",
            "type_line": "Sorcery",
            "color_identity": ["B"],
        },
        "Mountain": {"name": "Mountain", "type_line": "Basic Land — Mountain"},
    }
    state = ForgeState(
        by_name=by_name,
        search_fn=lambda **_: [],
        session=DeckSession("historic_brawl"),  # digital
        bulk_available=True,
    )
    # Stub the cached rarity index + a non-None bulk_path so wildcard_cost runs without
    # touching disk (``CardPool.rarity_index`` is exercised separately in scryfall_lookup's tests).
    # The cache is keyed by FORMAT, not legality key: competitive_brawl shares
    # historic_brawl's ``brawl`` key but admits the cards that key marks banned.
    from pathlib import Path

    state.bulk_path = Path("/dev/null")
    state.rarity_index["historic_brawl"] = _RARITY_INDEX
    for n in ("Shock", "Thoughtseize", "Mountain"):
        state.session.add(n)
    return state


def test_wildcard_cost_for_digital_excludes_basics():
    state = _digital_state()
    wc = engine.wildcard_cost(state)
    # 1 uncommon (Shock) + 1 rare (Thoughtseize); the basic Mountain is never charged.
    assert wc == {"mythic": 0, "rare": 1, "uncommon": 1, "common": 0}


def test_wildcard_cost_subtracts_owned_copies():
    state = _digital_state()
    engine.set_collection(
        state, "arena", {"cards": [{"name": "Thoughtseize", "quantity": 1}]}
    )
    wc = engine.wildcard_cost(state)
    assert wc == {"mythic": 0, "rare": 0, "uncommon": 1, "common": 0}  # rare now owned


def test_wildcard_cost_charges_the_companion():
    # On Arena the companion is a sideboard card you must own (a Historic build's
    # Yorion is crafted like any other), so it costs wildcards.
    state = _digital_state()
    state.by_name["Keruga, the Macrosage"] = {
        "name": "Keruga, the Macrosage",
        "type_line": "Legendary Creature — Dinosaur Hippo",
        "color_identity": ["G", "U"],
        "keywords": ["Companion"],
        "oracle_text": "Companion — Each nonland card in your starting deck has mana value 3 or greater.",
    }
    state.rarity_index["historic_brawl"]["keruga, the macrosage"] = {
        "rarity": "rare",
        "exempt_from_4cap": False,
    }
    state.session.add("Keruga, the Macrosage", zone="companion")
    wc = engine.wildcard_cost(state)
    assert wc == {"mythic": 0, "rare": 2, "uncommon": 1, "common": 0}


def test_paper_build_has_no_wildcard_cost():
    state = _digital_state()
    state.session.set_medium("paper")
    assert engine.wildcard_cost(state) is None  # paper → USD, not wildcards


def test_snapshot_exposes_wildcards_only_when_digital():
    state = _digital_state()
    assert engine.snapshot(state)["wildcards"] == {
        "mythic": 0,
        "rare": 1,
        "uncommon": 1,
        "common": 0,
    }
    state.session.set_medium("paper")
    assert engine.snapshot(state)["wildcards"] is None
