"""End-to-end: the tuner orchestrator over a HydratedDeck with an injected search_fn."""

import importlib

import pytest

from mtg_utils import testkit
from mtg_utils._tuner import TuneParams, tune
from mtg_utils.hydrated_deck import HydratedDeck

# Real cards from the testkit snapshot (ADR-0056). ``test_card_ir`` seeds the
# crosswalk trees memo so tune()'s signal path resolves each card in CI.
testkit.test_card_ir("Krenko, Mob Boss")
KRENKO = testkit.test_card("Krenko, Mob Boss")
testkit.test_card_ir("Goblin Rabblemaster")
RABBLE = testkit.test_card("Goblin Rabblemaster")
testkit.test_card_ir("Goblin Warchief")
WARCHIEF = testkit.test_card("Goblin Warchief")
# The fillers are real cards that emit no signal, so they serve no avenue (a
# vanilla Hill Giant opens its own "Giant tribal" avenue).
testkit.test_card_ir("Gloom Pangolin")
FILLER1 = testkit.test_card("Gloom Pangolin")
testkit.test_card_ir("Palace Guard")
FILLER2 = testkit.test_card("Palace Guard")
testkit.test_card_ir("Mountain")
MOUNTAIN = testkit.test_card("Mountain")

_DECK_CARDS = [RABBLE, WARCHIEF, FILLER1, FILLER2, MOUNTAIN]
_INDEX = {c["name"]: c for c in [KRENKO, *_DECK_CARDS]}


def _priced(name, usd):
    """A real card (testkit snapshot, ADR-0056) with its per-printing price."""
    return {**testkit.test_card(name), "prices": {"usd": usd}}


# Canned search results keyed by the role preset the tuner asks for.
_RAMP = [_priced("Burnished Hart", "1.50")]
_DRAW = [_priced("Faithless Looting", "0.50")]
_INTERACTION = [_priced("Lightning Bolt", "1.00"), _priced("Abrade", "0.40")]
_WIPE = [_priced("Blasphemous Act", "2.00")]


def _fake_search(**kw):
    presets = set(kw.get("preset_names") or ())
    if "ramp" in presets:
        return list(_RAMP)
    if "card-draw" in presets:
        return list(_DRAW)
    if presets & {"removal", "creature-removal", "counterspell", "bounce"}:
        return list(_INTERACTION)
    if "board-wipe" in presets:
        return list(_WIPE)
    return []


def _hd(deck_size=100):
    deck = {
        "format": "commander",
        "deck_size": deck_size,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [{"name": c["name"], "quantity": 1} for c in _DECK_CARDS],
    }
    return HydratedDeck.from_parsed(deck, by_name=_INDEX)


def test_diagnostic_only_returns_scorecard_no_swaps():
    out = tune(_hd(), search_fn=_fake_search, params=TuneParams(max_swaps=0))
    sc = out["scorecard"]
    assert sc["shape"]["value"] in ("aggro", "midrange", "control", "combo")
    assert "verdict" in sc["efficiency"]
    assert "verdict" in sc["focus"]
    assert "verdict" in sc["template"]
    assert isinstance(sc["top_issues"], list)
    assert out["swaps"] == []
    # The tiny deck is far under every Spine band → role_short issues dominate.
    assert any(i["kind"] == "role_short" for i in sc["top_issues"])


def test_buckets_counted():
    sc = tune(_hd(), search_fn=_fake_search, params=TuneParams())["scorecard"]
    counts = sc["counts"]
    assert counts.get("commander") == 1
    assert counts.get("land") == 1
    assert counts.get("filler", 0) >= 1  # Gloom Pangolin / Palace Guard


def test_swaps_propose_within_budget_and_pair_cut_with_add():
    out = tune(
        _hd(),
        search_fn=_fake_search,
        params=TuneParams(max_swaps=3, budget=100.0, paper_only=True),
    )
    swaps = out["swaps"]
    assert swaps, "expected at least one swap"
    for s in swaps:
        assert s["cut"]["name"]
        assert s["add"]["name"]
        assert "why" in s["cut"]
    assert out["spent"] <= 100.0
    # `spent` must equal exactly the sum of *proposed* adds' costs — a found-but-unpaired
    # add must never inflate the total.
    assert out["spent"] == round(sum(s["add"]["cost"] for s in swaps), 2)
    # Cuts come from filler first (the deck's only safe cuts).
    assert any(s["cut"]["name"] in ("Gloom Pangolin", "Palace Guard") for s in swaps)


def test_owned_only_default_is_zero_spend():
    # budget=None → owned-only; nothing owned → no affordable adds → no swaps.
    out = tune(_hd(), search_fn=_fake_search, params=TuneParams(max_swaps=3))
    assert out["swaps"] == []
    assert out["spent"] == 0.0
    assert out["swaps_note"]  # explains it found fewer than requested

    # Owning an add makes it free → a swap appears even with no budget.
    owned = {"Lightning Bolt": 1}
    out2 = tune(
        _hd(), search_fn=_fake_search, params=TuneParams(max_swaps=3), owned=owned
    )
    names = {s["add"]["name"] for s in out2["swaps"]}
    assert "Lightning Bolt" in names
    assert out2["spent"] == 0.0


def test_suggest_commander_path_is_wired_and_safe():
    # The tiny deck has no viable avenue (depth < floor), so there is nothing to realign
    # to — the opt-in returns an empty list rather than crashing or guessing.
    out = tune(
        _hd(),
        search_fn=_fake_search,
        params=TuneParams(suggest_commander=True),
    )
    assert out["commander_suggestions"] == []
    # Off by default.
    out2 = tune(_hd(), search_fn=_fake_search, params=TuneParams())
    assert out2["commander_suggestions"] is None


def test_combos_failure_degrades_gracefully():
    # combos ride a network call; a failure must degrade to heuristic-only win-cons,
    # never break the whole diagnosis.
    def boom(_deck):
        raise RuntimeError("commander spellbook unreachable")

    out = tune(_hd(), search_fn=_fake_search, params=TuneParams(), combos_fn=boom)
    assert out["scorecard"]["wincons"]["from_combos"] == 0


def test_shape_override_respected():
    out = tune(
        _hd(),
        search_fn=_fake_search,
        params=TuneParams(shape_override="control"),
    )
    assert out["scorecard"]["shape"]["value"] == "control"
    assert out["scorecard"]["shape"]["inferred"] is False


def test_fill_gap_counts_dfc_land_via_alias_not_name_set():
    # ADR-0041: the DFC join bug. A modal DFC land's deck entry can carry only
    # its front-face name (as decklist import commonly does) while the
    # hydrated record's own canonical `name` is the full two-face string —
    # the old `_fill_gap` matched deck-entry names against a set of
    # CLASSIFIED record names with no aliasing, silently dropping every DFC
    # land it saw. The fix counts lands off the alias-resolved joined
    # records (`hd.expanded`) instead of a raw name-set membership check.
    from mtg_utils._tuner.tune import _fill_gap

    pathway = testkit.test_card("Cragcrown Pathway // Timbercrown Pathway")
    index = {
        "Krenko, Mob Boss": KRENKO,
        "Cragcrown Pathway": pathway,  # keyed by the deck entry's front face
        "Mountain": MOUNTAIN,
    }
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [
            {"name": "Cragcrown Pathway", "quantity": 4},  # front-face name
            {"name": "Mountain", "quantity": 34},
        ],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    # 4 Pathways + 34 Mountains = 38 lands, exactly at a 38-land floor.
    fill_slots, land_gap = _fill_gap(hd, deck_size=100, land_floor=38)
    assert land_gap == 0
    assert fill_slots == 61  # 100 - 38 floor - 1 commander, no shortfall to eat into it


def test_fill_gap_full_deck_never_phantom_fills():
    # Verified-review Fix 1: nonland_target is computed off the band FLOOR
    # (ADR-0041), so a COMPLETE deck whose land count sits comfortably ABOVE
    # the floor (the ADR-endorsed healthy state) previously still computed a
    # positive fill_slots — e.g. 1 commander + 59 nonlands + 40 lands = 100
    # cards, floor 38: nonland_target = 100-38-1 = 61 but current_nonland is
    # only 59, so fill_slots=2 even though the deck has ZERO open slots. The
    # fill pass then appended pure adds to an already-100-card deck. A full
    # deck must always get fill_slots=0 regardless of where the land count
    # sits inside (or above) the band.
    from mtg_utils._tuner.tune import _fill_gap

    index = {"Krenko, Mob Boss": KRENKO, "Mountain": MOUNTAIN}
    nonland_cards = [
        {"name": f"Nonland {i}", "type_line": "Creature — Goblin", "cmc": 2.0}
        for i in range(59)
    ]
    index.update({c["name"]: c for c in nonland_cards})
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [
            *({"name": c["name"], "quantity": 1} for c in nonland_cards),
            {"name": "Mountain", "quantity": 40},
        ],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    # 1 (commander) + 59 (nonland) + 40 (land) = 100 — a complete deck.
    fill_slots, _land_gap = _fill_gap(hd, deck_size=100, land_floor=38)
    assert fill_slots == 0


def test_fill_gap_undersized_deck_keeps_its_fill_behavior():
    # Companion to the full-deck cap above: a genuinely under-sized deck (real
    # open slots) must still compute its true fill_slots, uncapped by the new
    # open-slots guard.
    from mtg_utils._tuner.tune import _fill_gap

    index = {"Krenko, Mob Boss": KRENKO, "Mountain": MOUNTAIN}
    nonland_cards = [
        {"name": f"Nonland {i}", "type_line": "Creature — Goblin", "cmc": 2.0}
        for i in range(10)
    ]
    index.update({c["name"]: c for c in nonland_cards})
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [
            *({"name": c["name"], "quantity": 1} for c in nonland_cards),
            {"name": "Mountain", "quantity": 30},
        ],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    # 1 (commander) + 10 (nonland) + 30 (land) = 41 of 100 — genuinely open.
    fill_slots, _land_gap = _fill_gap(hd, deck_size=100, land_floor=38)
    assert fill_slots == 51  # 100 - 38 floor - 1 commander - 10 existing nonland


def test_fill_gap_no_shortfall_when_at_the_floor_not_the_comfortable_max():
    # ADR-0041: the shortfall threshold is the band FLOOR (Karsten-adjusted),
    # not the band's comfortable-max top (raw Burgess) — a deck already at
    # its floor must show 0 gap even though it may sit below the top.
    from mtg_utils._tuner.tune import _fill_gap

    index = {"Krenko, Mob Boss": KRENKO, "Mountain": MOUNTAIN}
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [{"name": "Mountain", "quantity": 40}],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    _fill_slots, land_gap = _fill_gap(hd, deck_size=100, land_floor=38)
    assert land_gap == 0


def test_scorecard_surfaces_full_mana_audit():
    # ADR-0029 enrichment: the scorecard carries the full mana audit (color balance,
    # land status), not just the recommended_land_count the swap pass needs.
    sc = tune(_hd(), search_fn=_fake_search, params=TuneParams())["scorecard"]
    assert "mana" in sc
    assert "overall_status" in sc["mana"]


@pytest.fixture
def captured_protected(monkeypatch):
    """Spy on the ``protected`` set tune() hands the swap proposer — the wiring
    under test; the proposer's own protected-respect contract is tested separately."""
    # The package re-exports the ``tune`` FUNCTION under the module's name, so an
    # attribute import would bind the function; resolve the module itself.
    tune_mod = importlib.import_module("mtg_utils._tuner.tune")

    captured: dict = {}
    real_propose = tune_mod.swaps_mod.propose_swaps

    def spy(classes, issues, ctx):
        captured["protected"] = set(ctx.protected or ())
        return real_propose(classes, issues, ctx)

    monkeypatch.setattr(tune_mod.swaps_mod, "propose_swaps", spy)
    return captured


def test_wincon_at_floor_is_protected_from_cuts(captured_protected):
    # The proposer guarded template-role floors and combo pieces but was wincon-blind:
    # it could cut a card the SAME scorecard counts as a win condition, dropping the deck
    # below the wincon floor it just reported. tune() must add the heuristic finishers to
    # the proposer's `protected` set while the deck is at/below the wincon floor (the
    # propose_swaps protected-respect contract is separately tested). Verify the wiring by
    # capturing the `protected` argument.
    captured = captured_protected

    lab = testkit.test_card("Laboratory Maniac")
    index = {KRENKO["name"]: KRENKO, lab["name"]: lab, MOUNTAIN["name"]: MOUNTAIN}
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [
            {"name": "Laboratory Maniac", "quantity": 1},
            {"name": "Mountain", "quantity": 1},
        ],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    out = tune(hd, search_fn=_fake_search, params=TuneParams(max_swaps=5, budget=100.0))
    # Precondition: Lab Man is a counted wincon and the deck is at/below the floor.
    assert "Laboratory Maniac" in out["scorecard"]["wincons"]["cards"]
    assert (
        out["scorecard"]["wincons"]["count"] <= out["scorecard"]["wincons"]["target"][0]
    )
    # The wincon name must be threaded into the proposer's protected set.
    assert "Laboratory Maniac" in captured["protected"]


def test_scorecard_surfaces_curve_histogram():
    sc = tune(_hd(), search_fn=_fake_search, params=TuneParams())["scorecard"]
    assert "curve" in sc
    assert isinstance(sc["curve"], dict)


def test_scorecard_surfaces_combo_list_not_just_count():
    def combos_fn(_deck):
        return {
            "combos": [
                {"cards": ["Krenko, Mob Boss", "Mountain"], "result": "Infinite"}
            ]
        }

    sc = tune(_hd(), search_fn=_fake_search, params=TuneParams(), combos_fn=combos_fn)[
        "scorecard"
    ]
    assert "combos" in sc
    assert sc["combos"]["combos"]  # the actual list, not just a tally


def test_scorecard_bracket_gate_present_when_target_set():
    sc = tune(_hd(), search_fn=_fake_search, params=TuneParams(target_bracket=2))[
        "scorecard"
    ]
    assert sc["bracket"]["target_bracket"] == 2
    assert "pass" in sc["bracket"]


def test_no_bracket_section_without_target():
    sc = tune(_hd(), search_fn=_fake_search, params=TuneParams())["scorecard"]
    assert sc.get("bracket") is None


def test_grant_covered_commander_downgrades_card_draw_shortfall_to_advisory():
    # ADR-0040 §1 / the benchmark this fixes: a Sliver Weftwinder deck's commander
    # grants every Sliver a repeatable per-body draw trigger. The card_draw band
    # stays a literal count (the deck runs zero dedicated draw), but the shortfall
    # must read advisory — no swap should burn budget sourcing generic draw spells.
    testkit.test_card_ir("Sliver Weftwinder")  # seeds the crosswalk trees memo
    weftwinder = testkit.test_card("Sliver Weftwinder")
    sliver_filler = testkit.test_card("Sentinel Sliver")
    index = {
        weftwinder["name"]: weftwinder,
        sliver_filler["name"]: sliver_filler,
        MOUNTAIN["name"]: MOUNTAIN,
    }
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Sliver Weftwinder", "quantity": 1}],
        "cards": [
            {"name": "Sentinel Sliver", "quantity": 1},
            {"name": "Mountain", "quantity": 1},
        ],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    out = tune(
        hd, search_fn=_fake_search, params=TuneParams(max_swaps=10, budget=1000.0)
    )
    sc = out["scorecard"]

    short = sc["template"]["short"]
    # Literal numbers untouched — the deck runs zero dedicated draw either way.
    assert short["card_draw"]["current"] == 0
    assert short["card_draw"]["grant_covered"] is True
    assert short["card_draw"]["grant_covered_by"] == "Sliver Weftwinder"
    # ramp is short too, but has NO commander grant covering it — stays actionable.
    assert "grant_covered" not in short.get("ramp", {})

    issues_by_role = {
        i["role"]: i for i in sc["top_issues"] if i["kind"] == "role_short"
    }
    assert issues_by_role["card_draw"]["advisory"] is True
    assert issues_by_role["ramp"].get("advisory", False) is False

    # The swap proposer must never burn a swap sourcing generic draw spells.
    assert all(s["add"]["name"] != "Faithless Looting" for s in out["swaps"])
    # Other short roles still get normal swap treatment (ramp/interaction/wipe).
    assert any(
        s["add"]["name"] in {"Burnished Hart", "Lightning Bolt", "Abrade"}
        for s in out["swaps"]
    )


def test_lands_band_is_single_source_between_mana_and_template():
    # Verified-review Fix 2: slot_budgets re-derived the "lands" band from ITS
    # OWN ramp tally over hd.expanded() (cards + sideboard, commanders
    # EXCLUDED) while mana_audit counts commanders + cards (sideboard
    # excluded) — a deck with ramp ONLY in a zone one tally reads and the
    # other doesn't (here: sideboard) produced two DIFFERENT land bands for
    # the same deck. tune() must thread mana_audit's own already-derived band
    # through so both surfaces agree exactly (the contradiction ADR-0041
    # exists to eliminate).
    boss = {
        "name": "Simple Boss",
        "type_line": "Legendary Creature — Human",
        "oracle_text": "",
        "cmc": 2.0,
        "color_identity": ["G"],
    }
    rock = testkit.test_card("Mind Stone")
    index = {boss["name"]: boss, rock["name"]: rock, MOUNTAIN["name"]: MOUNTAIN}
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Simple Boss", "quantity": 1}],
        "cards": [{"name": "Mountain", "quantity": 1}],
        "sideboard": [{"name": "Mind Stone", "quantity": 8}],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    out = tune(hd, search_fn=_fake_search, params=TuneParams())
    sc = out["scorecard"]
    mana_band = sc["mana"]["land_band"]
    lands = sc["template"]["budgets"]["lands"]
    assert (lands["min"], lands["max"]) == (mana_band["floor"], mana_band["top"])


def test_commander_closer_grant_counts_toward_win_conditions():
    # Verified-review Fix 5: a commander granting a closer-grade ability
    # (team double strike) was invisible to win_conditions before this fix —
    # classify_deck never computed grant_closer for the commander bucket.
    testkit.test_card_ir("Bonescythe Sliver")
    bone = testkit.test_card("Bonescythe Sliver")
    index = {bone["name"]: bone, MOUNTAIN["name"]: MOUNTAIN}
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Bonescythe Sliver", "quantity": 1}],
        "cards": [{"name": "Mountain", "quantity": 1}],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    out = tune(hd, search_fn=_fake_search, params=TuneParams())
    assert "Bonescythe Sliver" in out["scorecard"]["wincons"]["cards"]


def test_combo_piece_protected_from_cuts():
    # ADR-0029: cut_candidates is combo-aware — a card that's part of a combo must not
    # be proposed as a cut, even when it would otherwise be the top filler cut.
    def combos_fn(_deck):
        return {
            "combos": [
                {"cards": ["Gloom Pangolin", "Krenko, Mob Boss"], "result": "Infinite"}
            ]
        }

    out = tune(
        _hd(),
        search_fn=_fake_search,
        params=TuneParams(max_swaps=3, budget=100.0, paper_only=True),
        combos_fn=combos_fn,
    )
    cut_names = {s["cut"]["name"] for s in out["swaps"] if s["cut"]}
    assert "Gloom Pangolin" not in cut_names


def _oversized_hd(over=3, deck_size=100, lands=38):
    """A commander deck `over` cards past its exact legal size: 1 commander +
    `lands` Mountains (exactly at a 38-land floor) + enough distinct nonland
    filler (empty oracle text → bucket "filler", all safe cuts) to overflow."""
    filler = [
        {
            "name": f"Filler {i}",
            "type_line": "Creature — Giant",
            "oracle_text": "",
            "cmc": 3.0,
            "color_identity": ["R"],
        }
        for i in range(deck_size - 1 - lands + over)
    ]
    index = {KRENKO["name"]: KRENKO, MOUNTAIN["name"]: MOUNTAIN}
    index.update({c["name"]: c for c in filler})
    deck = {
        "format": "commander",
        "deck_size": deck_size,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [
            *({"name": c["name"], "quantity": 1} for c in filler),
            {"name": "Mountain", "quantity": lands},
        ],
    }
    return HydratedDeck.from_parsed(deck, by_name=index)


def test_oversized_deck_yields_exactly_overflow_size_cuts():
    # CR 903.5a: a Commander deck's minimum AND maximum size are both 100 —
    # a 103-card deck is illegal, so Tune must propose exactly 3 cuts.
    out = tune(_oversized_hd(over=3), search_fn=_fake_search, params=TuneParams())
    cuts = out["size_cuts"]
    assert len(cuts) == 3
    for c in cuts:
        assert c["reason"] == "over:deck_size"
        assert "CR 903.5a" in c["message"]
        assert "3 over" in c["message"]
        assert c["name"] != "Krenko, Mob Boss"  # never the commander
        assert c["name"] != "Mountain"  # never a land (the floor holds)
        assert c["why"]  # rides the existing cut ranking's explanation
    # Distinct proposals — no card is cut twice.
    assert len({c["name"] for c in cuts}) == 3
    # The scorecard surfaces the overflow for "N over legal size" rendering.
    assert out["scorecard"]["size"] == {
        "total": 103,
        "deck_size": 100,
        "exact": True,
        "overflow": 3,
        "shortfall": 0,
    }


def test_size_rules_cover_every_commander_family_format():
    # Every format the tuner accepts must have an exact-size CR citation, or the
    # over-size message silently loses its rule reference.
    from mtg_utils.formats import COMMANDER_FORMATS, FORMATS

    for fmt in COMMANDER_FORMATS:
        assert FORMATS[fmt].size_rule, fmt
    assert (
        FORMATS["competitive_brawl"].size_rule == "CR 903.5a"
    )  # 100-card, like Commander


def test_legal_sized_deck_yields_no_size_cuts():
    out = tune(_oversized_hd(over=0), search_fn=_fake_search, params=TuneParams())
    assert out["size_cuts"] == []
    assert out["scorecard"]["size"]["overflow"] == 0
    # The tiny fixture deck (far under 100) is under-sized, never over.
    out2 = tune(_hd(), search_fn=_fake_search, params=TuneParams())
    assert out2["size_cuts"] == []
    assert out2["scorecard"]["size"]["overflow"] == 0


def test_size_cuts_produced_even_at_max_swaps_zero():
    # Legality-driven, not tuning-driven: a scorecard-only run (max_swaps=0,
    # no budget) must still report the cuts needed to reach the legal 100.
    out = tune(
        _oversized_hd(over=3),
        search_fn=_fake_search,
        params=TuneParams(max_swaps=0),
    )
    assert len(out["size_cuts"]) == 3
    assert out["swaps"] == []


def test_size_cut_cards_excluded_from_regular_swap_cut_pool():
    # A card proposed as a size cut must not ALSO be proposed as the cut side
    # of a regular paired swap in the same run (owned add makes swaps free).
    out = tune(
        _oversized_hd(over=3),
        search_fn=_fake_search,
        params=TuneParams(max_swaps=5, budget=100.0),
    )
    size_cut_names = {c["name"] for c in out["size_cuts"]}
    assert len(size_cut_names) == 3
    swap_cut_names = {s["cut"]["name"] for s in out["swaps"] if s["cut"]}
    assert not (size_cut_names & swap_cut_names)


def test_medium_threads_to_the_low_value_reads():
    # ADR-0040 §4 (task #99): real Krenko + Rabblemaster (edhrec_rank=None in
    # the snapshot's minimal records) give one engine card: fringe-evidence on
    # paper, no-data on digital. Proves TuneParams.medium reaches metrics.focus.
    # Historic Brawl, because it is played in BOTH media — ``Format.game`` resolves an override the format cannot honour
    # (digital on Commander) back to the format's own medium.
    testkit.test_card_ir("Krenko, Mob Boss")  # seeds the crosswalk trees memo
    testkit.test_card_ir("Goblin Rabblemaster")
    index = {
        c["name"]: c
        for c in (
            testkit.test_card("Krenko, Mob Boss"),
            testkit.test_card("Goblin Rabblemaster"),
            MOUNTAIN,
        )
    }
    deck = {
        "format": "historic_brawl",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [
            {"name": "Goblin Rabblemaster", "quantity": 1},
            {"name": "Mountain", "quantity": 1},
        ],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    paper = tune(
        hd, search_fn=_fake_search, params=TuneParams(max_swaps=0, medium="paper")
    )
    digital = tune(
        hd,
        search_fn=_fake_search,
        params=TuneParams(max_swaps=0, medium="digital"),
    )
    assert paper["scorecard"]["focus"]["low_value_cards"] == ["Goblin Rabblemaster"]
    assert digital["scorecard"]["focus"]["low_value_cards"] == []


def test_voltron_pieces_at_the_closer_floor_are_protected_from_cuts(
    captured_protected,
):
    # ADR-0024 amendment: under a commander-damage plan (CR 903.10a) the equipment
    # suite IS the synthetic closer, so at/below the closer floor the proposer must
    # not cut its pieces — the same guard test_wincon_at_floor_is_protected_from_cuts
    # verifies for a named finisher.
    captured = captured_protected

    swords = [
        {
            "name": f"Sword {i}",
            "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature gets +2/+2.\nEquip {2}",
            "keywords": ["Equip"],
            "cmc": 3.0,
            "color_identity": [],
        }
        for i in range(4)
    ]
    index = {KRENKO["name"]: KRENKO, MOUNTAIN["name"]: MOUNTAIN}
    index.update({s["name"]: s for s in swords})
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [{"name": s["name"], "quantity": 1} for s in swords]
        + [{"name": "Mountain", "quantity": 1}],
    }
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    out = tune(hd, search_fn=_fake_search, params=TuneParams(max_swaps=5, budget=100.0))
    wins = out["scorecard"]["wincons"]
    assert wins["voltron_commander_damage"] is True
    assert wins["count"] <= wins["target"][0]
    assert {s["name"] for s in swords} <= captured["protected"]


def _historic_brawl_hd():
    deck = {
        "format": "historic_brawl",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [{"name": c["name"], "quantity": 1} for c in _DECK_CARDS],
    }
    return HydratedDeck.from_parsed(deck, by_name=_INDEX)


def _searched_pools(hd, params):
    """The ``paper_only`` values tune() handed the candidate search."""
    seen: set[bool] = set()

    def spy(**kw):
        seen.add(kw["paper_only"])
        return _fake_search(**kw)

    tune(hd, search_fn=spy, params=params)
    return seen


def test_the_candidate_pool_follows_the_medium_not_the_format():
    # A paper Historic Brawl table buys paper printings; the same format built for
    # Arena searches Arena's. The hub once derived this from `is_arena` (False for a
    # paper build) while the CLI derived it from the medium (True) — same deck, two
    # pools. tune() now asks the Format, so no caller can disagree.
    hd = _historic_brawl_hd()
    paper = TuneParams(max_swaps=3, budget=100.0, medium="paper")
    assert _searched_pools(hd, paper) == {True}
    digital = TuneParams(max_swaps=3, wildcard_budget={"rare": 4}, medium="digital")
    assert _searched_pools(hd, digital) == {False}
    # No medium given → the format's default (digital for the Arena Brawl formats).
    assert _searched_pools(hd, TuneParams(max_swaps=3)) == {False}
    # An explicit override still wins.
    forced = TuneParams(max_swaps=3, medium="digital", paper_only=True)
    assert _searched_pools(hd, forced) == {True}


def test_the_medium_picks_the_currency_the_purse_spends():
    # Both purses ride along; the medium picks one (Format.cost_mode). A digital
    # build never spends USD, a paper build never spends wildcards.
    hd = _historic_brawl_hd()
    both = {"budget": 100.0, "wildcard_budget": {"common": 9, "uncommon": 9}}
    paper = tune(
        hd,
        search_fn=_fake_search,
        params=TuneParams(max_swaps=3, medium="paper", **both),
    )
    assert paper["wildcards_spent"] is None
    assert paper["swaps"]
    digital = tune(
        hd,
        search_fn=_fake_search,
        params=TuneParams(max_swaps=3, medium="digital", **both),
    )
    assert digital["spent"] == 0.0
    assert digital["wildcards_spent"] is not None
    # No wildcard purse on a digital build is the all-zero owned-only pass, even
    # with a USD budget on the table.
    broke = tune(
        hd,
        search_fn=_fake_search,
        params=TuneParams(max_swaps=3, medium="digital", budget=100.0),
    )
    assert broke["swaps"] == []
    assert broke["wildcards_spent"] == dict.fromkeys(
        ("mythic", "rare", "uncommon", "common"), 0
    )


def test_game_changer_room_is_the_gates_ceiling_less_the_gates_count():
    from mtg_utils._tuner.tune import _game_changer_room

    def gate(count):
        return {
            "ceilings": {"game_changers": 3, "mass_land_denial": 0},
            "counts": {"game_changers": count},
        }

    assert _game_changer_room(gate(1)) == 2
    # Already over: NEGATIVE, never clamped to 0 — one cut must not buy an add.
    assert _game_changer_room(gate(5)) == -2
    # No target bracket / a one-on-one game / brackets 4-5: nothing constrains adds.
    assert _game_changer_room(None) is None
    assert _game_changer_room({"ceilings": {}}) is None


def test_the_bracket_gate_reports_the_count_it_measured():
    from mtg_utils._tuner.bracket import bracket_gate

    records = [
        # The snapshot doesn't carry ``game_changer``; it is overlaid.
        {**testkit.test_card("Rhystic Study"), "game_changer": True},
        testkit.test_card("Forest"),
    ]
    gate = bracket_gate(records, 2)
    assert gate["ceilings"]["game_changers"] == 0
    assert gate["counts"] == {"game_changers": 1}


# ── the constructed family: 60-card norms, no Commander-only axes ─────────────

BOLT = _priced("Lightning Bolt", "1.00")
SIDEBOARD_FILLER = {
    "name": "Sideboard Filler",
    "type_line": "Creature — Ogre",
    "oracle_text": "",
    "cmc": 5.0,
    "color_identity": ["R"],
}
_MODERN_INDEX = {**_INDEX, "Lightning Bolt": BOLT, "Sideboard Filler": SIDEBOARD_FILLER}


def _hd_modern(*, bolts=3, total=58, sideboard=()):
    nonland = [
        ("Lightning Bolt", bolts),
        ("Goblin Rabblemaster", 4),
        ("Goblin Warchief", 4),
        ("Gloom Pangolin", 4),
        ("Palace Guard", 4),
    ]
    lands = total - sum(q for _, q in nonland)
    deck = {
        "format": "modern",
        "commanders": [],
        "cards": [{"name": n, "quantity": q} for n, q in nonland]
        + [{"name": "Mountain", "quantity": lands}],
        "sideboard": [{"name": n, "quantity": q} for n, q in sideboard],
    }
    return HydratedDeck.from_parsed(deck, by_name=_MODERN_INDEX)


def test_constructed_scorecard_omits_the_commander_only_axes():
    out = tune(
        _hd_modern(),
        search_fn=_fake_search,
        params=TuneParams(target_bracket=2, suggest_commander=True),
    )
    sc = out["scorecard"]
    assert sc["commander_fit"] is None
    assert sc["bracket"] is None  # WotC brackets are a Commander construct
    assert out["commander_suggestions"] is None
    kinds = {i["kind"] for i in sc["top_issues"]}
    assert not kinds & {"commander_misfit", "voltron_no_commander_damage"}
    # The constructed template: interaction + card draw + an advisory creature
    # count, no ramp / wipe rows, every row labelled.
    budgets = sc["template"]["budgets"]
    assert list(budgets) == ["lands", "interaction", "card_draw", "creatures"]
    assert budgets["creatures"]["advisory"] is True
    assert budgets["interaction"]["label"] == "Interaction (incl. sweepers)"
    assert sc["efficiency"]["ramp"]["status"] == "n/a"


def test_constructed_size_is_a_shortfall_never_an_overflow():
    short = tune(_hd_modern(total=58), search_fn=_fake_search, params=TuneParams())
    assert short["scorecard"]["size"] == {
        "total": 58,
        "deck_size": 60,
        "exact": False,
        "overflow": 0,
        "shortfall": 2,
    }
    assert short["size_cuts"] == []
    over = tune(_hd_modern(total=62), search_fn=_fake_search, params=TuneParams())
    assert over["scorecard"]["size"]["overflow"] == 0  # CR 100.2a: a floor
    assert over["size_cuts"] == []


def test_constructed_counts_copies_not_names():
    sc = tune(_hd_modern(bolts=4), search_fn=_fake_search, params=TuneParams())[
        "scorecard"
    ]
    # Four 4-of creatures are sixteen creature SLOTS (the type-line row and the
    # shape evidence both count copies); ``counts`` stays per distinct name.
    assert sc["template"]["budgets"]["creatures"]["current"] == 16
    creatures = next(e for e in sc["shape"]["evidence"] if "creatures" in e["label"])
    assert creatures["label"].startswith("16 creatures")
    # ``counts`` stays per distinct name: five nonland names, however many copies.
    assert sum(v for k, v in sc["counts"].items() if k != "land") == 5


def _interaction_search(**_kw):
    """Every search answers the two interaction spells. The real Bolts in the
    60-card deck meet its interaction floor, so the adds come from the dead-weight
    redeploy and the open-slot fill, whose theme searches ``_fake_search``
    leaves empty."""
    return list(_INTERACTION)


def test_constructed_adds_another_copy_up_to_the_limit():
    # 3 Bolts, 2 open slots → an add proposes the 4th Bolt (copy 4), and with 4
    # already in the deck the 5th is never proposed.
    three = tune(
        _hd_modern(bolts=3),
        search_fn=_interaction_search,
        params=TuneParams(max_swaps=6, budget=100.0, paper_only=True),
    )
    adds = [s["add"] for s in three["swaps"]]
    bolt = next(a for a in adds if a["name"] == "Lightning Bolt")
    assert bolt["copy"] == 4
    four = tune(
        _hd_modern(bolts=4),
        search_fn=_interaction_search,
        params=TuneParams(max_swaps=6, budget=100.0, paper_only=True),
    )
    assert all(s["add"]["name"] != "Lightning Bolt" for s in four["swaps"])
    assert any(s["add"]["name"] == "Abrade" for s in four["swaps"])


def test_constructed_cuts_one_copy_at_a_time():
    out = tune(
        _hd_modern(bolts=4),
        search_fn=_interaction_search,
        params=TuneParams(max_swaps=3, budget=100.0, paper_only=True),
    )
    cuts = [s["cut"] for s in out["swaps"] if s["cut"]]
    assert cuts, "the four-of fillers are dead weight to swap out"
    assert all(c["quantity"] == 1 for c in cuts)
    assert all(c["name"] in ("Gloom Pangolin", "Palace Guard") for c in cuts)


def test_sideboard_never_counts_and_is_never_cut():
    out = tune(
        _hd_modern(sideboard=[("Sideboard Filler", 4)]),
        search_fn=_fake_search,
        params=TuneParams(max_swaps=4, budget=100.0, paper_only=True),
    )
    sc = out["scorecard"]
    assert "Sideboard Filler" not in sc["focus"]["filler_cards"]
    assert all((s["cut"] or {}).get("name") != "Sideboard Filler" for s in out["swaps"])
    assert sc["size"]["total"] == 58


def test_commander_scorecard_is_unchanged_by_the_family_switch():
    # The Commander numbers are the calibration every readout was tuned on: the
    # scorecard's axes and floors read exactly as before.
    sc = tune(_hd(), search_fn=_fake_search, params=TuneParams())["scorecard"]
    assert sc["commander_fit"] is not None
    assert list(sc["template"]["budgets"]) == [
        "lands",
        "ramp",
        "card_draw",
        "interaction",
        "board_wipe",
    ]
    assert sc["focus"]["main_floor"] == 20
    assert sc["focus"]["sub_floor"] == 10
    assert sc["efficiency"]["ramp"]["want"] in (9, 10, 12)
    assert sc["size"]["exact"] is True


def test_advisory_rows_never_drive_the_verdict_or_an_issue():
    # A control-ish 60 with few creatures: the creature row is a fact beside the
    # verdict, never an off-template deviation and never a role_short / role_over.
    out = tune(_hd_modern(), search_fn=_fake_search, params=TuneParams())
    sc = out["scorecard"]
    tmpl = sc["template"]
    assert "creatures" not in tmpl["short"]
    assert "creatures" not in tmpl["over"]
    assert all(
        i.get("role") != "creatures"
        for i in sc["top_issues"]
        if i["kind"] in ("role_short", "role_over")
    )
    assert set(tmpl["advisory"]) <= {"creatures"}


def test_calibration_base_size_is_the_templates():
    from mtg_utils._analysis.budgets import template_for
    from mtg_utils._tuner.calibration import CALIBRATIONS

    for family, cal in CALIBRATIONS.items():
        assert cal.base_size == template_for(family).base_size
