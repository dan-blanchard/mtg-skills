"""End-to-end: the tuner orchestrator over a HydratedDeck with an injected search_fn."""

from mtg_utils._tuner import TuneParams, tune
from mtg_utils.hydrated_deck import HydratedDeck

KRENKO = {
    "name": "Krenko, Mob Boss",
    "type_line": "Legendary Creature — Goblin Warrior",
    "oracle_text": "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
    "cmc": 4.0,
    "color_identity": ["R"],
}
RABBLE = {
    "name": "Goblin Rabblemaster",
    "type_line": "Creature — Goblin Warrior",
    "oracle_text": "Other Goblin creatures you control attack each combat if able.\nAt the beginning of combat on your turn, create a 1/1 red Goblin creature token with haste.\nWhenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Goblin.",
    "cmc": 3.0,
    "color_identity": ["R"],
}
WARCHIEF = {
    "name": "Goblin Warchief",
    "type_line": "Creature — Goblin Warrior",
    "oracle_text": "Goblin spells you cast cost {1} less to cast. Goblins you control "
    "have haste.",
    "cmc": 3.0,
    "color_identity": ["R"],
}
FILLER1 = {
    "name": "Hill Giant",
    "type_line": "Creature — Giant",
    "oracle_text": "",
    "cmc": 4.0,
    "color_identity": ["R"],
}
FILLER2 = {
    "name": "Lumbering Battlement",
    "type_line": "Creature — Beast",
    "oracle_text": "Vigilance\nWhen this creature enters, exile any number of other nontoken creatures you control until it leaves the battlefield.\nThis creature gets +2/+2 for each card exiled with it.",
    "cmc": 6.0,
    "color_identity": [],
}
MOUNTAIN = {
    "name": "Mountain",
    "type_line": "Basic Land — Mountain",
    "oracle_text": "({T}: Add {R}.)",
    "cmc": 0.0,
    "color_identity": [],
}

_DECK_CARDS = [RABBLE, WARCHIEF, FILLER1, FILLER2, MOUNTAIN]
_INDEX = {c["name"]: c for c in [KRENKO, *_DECK_CARDS]}


def _priced(name, oracle, cmc, usd):
    return {
        "name": name,
        "type_line": "Instant",
        "oracle_text": oracle,
        "cmc": cmc,
        "color_identity": ["R"],
        "prices": {"usd": usd},
    }


# Canned search results keyed by the role preset the tuner asks for.
_RAMP = [_priced("Burnished Hart", "{T}: Add {C}.", 3.0, "1.50")]
_DRAW = [_priced("Faithless Looting", "Draw two cards.", 1.0, "0.50")]
_INTERACTION = [
    _priced(
        "Lightning Bolt", "Lightning Bolt deals 3 damage to any target.", 1.0, "1.00"
    ),
    _priced("Abrade", "Destroy target artifact.", 2.0, "0.40"),
]
_WIPE = [_priced("Blasphemous Act", "Destroy all creatures.", 9.0, "2.00")]


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
    assert counts.get("filler", 0) >= 1  # Hill Giant / Lumbering Battlement


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
    assert any(
        s["cut"]["name"] in ("Hill Giant", "Lumbering Battlement") for s in swaps
    )


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


def test_signals_resolved_through_card_ir(monkeypatch):
    # ADR-0029: the tuner must thread the Card IR resolver into signal extraction, not
    # run the regex-only path. End-to-end IR needs a built sidecar (absent in tests), so
    # we verify the wiring — rank_deck_signals is called with a non-None ir_for resolver.
    import sys

    from mtg_utils._deck_forge.signals import rank_deck_signals as real

    # _tuner/__init__ re-exports the tune() function, shadowing the tune submodule —
    # so reach the real module object via sys.modules, not attribute access.
    tune_mod = sys.modules["mtg_utils._tuner.tune"]
    captured = {}

    def spy(records, commander_names, **kw):
        captured["ir_for"] = kw.get("ir_for")
        return real(records, commander_names, **kw)

    monkeypatch.setattr(tune_mod, "rank_deck_signals", spy)
    tune(_hd(), search_fn=_fake_search, params=TuneParams())
    assert captured["ir_for"] is not None
    assert callable(captured["ir_for"])


def test_scorecard_surfaces_full_mana_audit():
    # ADR-0029 enrichment: the scorecard carries the full mana audit (color balance,
    # land status), not just the recommended_land_count the swap pass needs.
    sc = tune(_hd(), search_fn=_fake_search, params=TuneParams())["scorecard"]
    assert "mana" in sc
    assert "overall_status" in sc["mana"]


def test_wincon_at_floor_is_protected_from_cuts(monkeypatch):
    # The proposer guarded template-role floors and combo pieces but was wincon-blind:
    # it could cut a card the SAME scorecard counts as a win condition, dropping the deck
    # below the wincon floor it just reported. tune() must add the heuristic finishers to
    # the proposer's `protected` set while the deck is at/below the wincon floor (the
    # propose_swaps protected-respect contract is separately tested). Verify the wiring by
    # capturing the `protected` argument.
    import sys

    tune_mod = sys.modules["mtg_utils._tuner.tune"]
    captured = {}
    real_propose = tune_mod.swaps_mod.propose_swaps

    def spy(*args, **kw):
        captured["protected"] = set(kw.get("protected") or ())
        return real_propose(*args, **kw)

    monkeypatch.setattr(tune_mod.swaps_mod, "propose_swaps", spy)

    lab = {
        "name": "Laboratory Maniac",
        "type_line": "Creature — Human Wizard",
        "oracle_text": "If you would draw a card while your library has no cards in it, "
        "you win the game instead.",
        "cmc": 3.0,
        "color_identity": ["R"],
    }
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


def test_combo_piece_protected_from_cuts():
    # ADR-0029: cut_candidates is combo-aware — a card that's part of a combo must not
    # be proposed as a cut, even when it would otherwise be the top filler cut.
    def combos_fn(_deck):
        return {
            "combos": [
                {"cards": ["Hill Giant", "Krenko, Mob Boss"], "result": "Infinite"}
            ]
        }

    out = tune(
        _hd(),
        search_fn=_fake_search,
        params=TuneParams(max_swaps=3, budget=100.0, paper_only=True),
        combos_fn=combos_fn,
    )
    cut_names = {s["cut"]["name"] for s in out["swaps"]}
    assert "Hill Giant" not in cut_names
