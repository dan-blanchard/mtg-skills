"""End-to-end: the tuner orchestrator over a HydratedDeck with an injected search_fn."""

from mtg_utils._tuner import TuneParams, tune
from mtg_utils.hydrated_deck import HydratedDeck

KRENKO = {
    "name": "Krenko, Mob Boss",
    "type_line": "Legendary Creature — Goblin Warrior",
    "oracle_text": "{T}: Create a number of 1/1 red Goblin creature tokens equal to "
    "the number of Goblins you control.",
    "cmc": 4.0,
    "color_identity": ["R"],
}
RABBLE = {
    "name": "Goblin Rabblemaster",
    "type_line": "Creature — Goblin Warrior",
    "oracle_text": "At the beginning of combat on your turn, create a 1/1 red Goblin "
    "creature token with haste.",
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
    "type_line": "Artifact Creature — Wall",
    "oracle_text": "",
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


def test_shape_override_respected():
    out = tune(
        _hd(),
        search_fn=_fake_search,
        params=TuneParams(shape_override="control"),
    )
    assert out["scorecard"]["shape"]["value"] == "control"
    assert out["scorecard"]["shape"]["inferred"] is False
