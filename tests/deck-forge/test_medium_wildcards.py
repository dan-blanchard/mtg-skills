"""Paper/digital medium + Arena wildcard costing + the 60/100 paper-Historic-Brawl size.

medium drives the active Collection slot (paper deck → paper slot) and the cost mode
(digital → wildcards, paper → USD); paper Historic Brawl may be 60 or 100 cards, which
flows into the footer target and the land math."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.testkit import printing_row, test_card, test_printing


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
    "shock": {"rarity": "uncommon"},
    "thoughtseize": {"rarity": "rare"},
    "sol ring": {"rarity": "uncommon"},
}


def _digital_state():
    by_name = {
        "Shock": test_card("Shock"),
        "Thoughtseize": test_card("Thoughtseize"),
        "Mountain": test_card("Mountain"),
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
    state.by_name["Keruga, the Macrosage"] = test_card("Keruga, the Macrosage")
    state.rarity_index["historic_brawl"]["keruga, the macrosage"] = {"rarity": "rare"}
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


# ── Ownership: every readout sums the served per-card shortfall ──────────────
def _hare_state(owned, medium="digital"):
    """A Hare Apparent build (17 copies — an "any number" card) against a collection
    holding ``owned`` of them."""
    from pathlib import Path

    state = ForgeState(
        by_name={"Hare Apparent": test_card("Hare Apparent")},
        search_fn=lambda **_: [],
        session=DeckSession("historic_brawl"),
        bulk_available=True,
    )
    state.session.set_medium(medium)
    state.bulk_path = Path("/dev/null")
    state.rarity_index["historic_brawl"] = {"hare apparent": {"rarity": "common"}}
    state.session.add("Hare Apparent", 17)
    slot = "arena" if medium == "digital" else "paper"
    engine.set_collection(
        state, slot, {"cards": [{"name": "Hare Apparent", "quantity": owned}]}
    )
    return state


def _served_short(state):
    client = TestClient(build_app(state))
    (row,) = client.get("/api/deck").json()["deck"]["cards"]
    return row["copies_short"]


def test_an_arena_playset_covers_every_copy_of_an_any_number_card():
    state = _hare_state(4)
    assert _served_short(state) == 0
    assert engine.wildcard_cost(state) == {
        "mythic": 0,
        "rare": 0,
        "uncommon": 0,
        "common": 0,
    }


def test_three_owned_on_arena_is_three_copies_not_a_playset():
    state = _hare_state(3)
    assert _served_short(state) == 14
    assert engine.wildcard_cost(state)["common"] == 14


def test_paper_has_no_playset_rule():
    assert _served_short(_hare_state(4, medium="paper")) == 13


def test_served_shortfall_matches_the_footer_total():
    # The footer total and the per-row shortfall come from the same rule, so the
    # browser's per-group sums can't disagree with it.
    state = _digital_state()
    engine.set_collection(
        state, "arena", {"cards": [{"name": "Thoughtseize", "quantity": 1}]}
    )
    rows = engine.snapshot(state)["deck"]["cards"]
    short = {r["name"]: r["copies_short"] for r in rows}
    assert short == {"Shock": 1, "Thoughtseize": 0, "Mountain": 0}


# ── Basic lands: owned in every medium; a SPECIAL pinned printing is owned in paper
# only if the collection holds that exact printing ──
_PRINTINGS = {
    p["id"]: p
    for p in (
        test_printing("Forest", "m21", "274"),
        test_printing("Forest", "znr", "278", full_art=True, frame_effects=["fullart"]),
    )
}
_OTHER = printing_row("dmu", "277", quantity=30)


def _forest_state(medium, *, pin=None, finish=None, pile=None):
    state = ForgeState(
        by_name={
            "Forest": test_card("Forest"),
            "Snow-Covered Forest": test_card("Snow-Covered Forest"),
        },
        search_fn=lambda **_: [],
        session=DeckSession("historic_brawl"),
        bulk_available=True,
    )
    state.session.set_medium(medium)
    state.printing_by_id = dict(_PRINTINGS)
    state.session.add("Forest", 2)
    state.session.add("Snow-Covered Forest", 2)
    if pin:
        state.session.set_printing("Forest", pin, finish=finish)
    slot = "arena" if medium == "digital" else "paper"
    if pile is None:
        pile = {"cards": [{"name": "Forest", "quantity": 30, "printings": [_OTHER]}]}
    engine.set_collection(state, slot, pile)
    return state


def _shorts(state):
    rows = engine.snapshot(state)["deck"]["cards"]
    return {r["name"]: r["copies_short"] for r in rows}


def test_unlisted_basics_are_free_and_snow_basics_are_not():
    for medium in ("paper", "digital"):
        state = _forest_state(medium)
        assert _shorts(state) == {"Forest": 0, "Snow-Covered Forest": 2}
        rows = {r["name"]: r for r in engine.snapshot(state)["deck"]["cards"]}
        assert rows["Forest"]["covered_by"] == "free"
        assert "owned" not in rows["Forest"]  # free, not owned


def test_a_plain_printing_pin_stays_owned_in_paper():
    assert _shorts(_forest_state("paper", pin="m21-274"))["Forest"] == 0


def test_a_special_pin_is_short_unless_that_printing_is_held():
    empty = {"cards": []}
    assert _shorts(_forest_state("paper", pin="znr-278", pile=empty))["Forest"] == 2
    name_only = {"cards": [{"name": "Forest", "quantity": 20}]}
    state = _forest_state("paper", pin="znr-278", pile=name_only)
    assert _shorts(state)["Forest"] == 2
    foil = _forest_state("paper", pin="m21-274", finish="foil", pile=empty)
    assert _shorts(foil)["Forest"] == 2
    held = printing_row("znr", "278", quantity=2)
    pile = {"cards": [{"name": "Forest", "quantity": 32, "printings": [_OTHER, held]}]}
    assert _shorts(_forest_state("paper", pin="znr-278", pile=pile))["Forest"] == 0


def test_any_forest_style_is_free_on_arena():
    for pin, finish in (("znr-278", None), ("m21-274", "foil")):
        state = _forest_state("digital", pin=pin, finish=finish, pile={"cards": []})
        assert _shorts(state)["Forest"] == 0


def test_seventeen_hare_apparent_with_one_owned_is_not_owned():
    # The owned tick and "N of M owned" mean "covered", not "owned at all".
    state = _hare_state(1, medium="paper")
    (row,) = engine.snapshot(state)["deck"]["cards"]
    assert row["copies_short"] == 16
    assert "owned" not in row
    assert engine.snapshot(state)["collection"]["owned"] == 0
    covered = _hare_state(17, medium="paper")
    assert engine.snapshot(covered)["collection"]["owned"] == 1


def test_owned_snow_covered_basics_cover_the_deck_and_reach_the_tuner():
    # Snow-Covered Forest is an ordinary collected card: four owned cover the
    # deck's two in both media, and the tuner's purse sees them too.
    pile = {"cards": [{"name": "Snow-Covered Forest", "quantity": 4}]}
    for medium in ("paper", "digital"):
        state = _forest_state(medium, pile=pile)
        assert _shorts(state)["Snow-Covered Forest"] == 0
        assert engine.owned_collection(state)["Snow-Covered Forest"] == 4
