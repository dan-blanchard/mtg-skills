"""Swap engine: template-safety, role-over trims, and emerging-theme commits."""

from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import Signal
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.metrics import top_issues
from mtg_utils._tuner.swaps import (
    _PROTECTION_SEARCH,
    _ROLE_SEARCH,
    _spec_for_issue,
    propose_swaps,
)
from mtg_utils.theme_presets import get_preset


def _focus(viable=(), emerging=(), stranded=()):
    return {
        "viable_avenues": list(viable),
        "emerging": list(emerging),
        "stranded_avenues": list(stranded),
        "verdict": "FOCUSED",
    }


def _cc(name, bucket, roles=(), served=(), cmc=2.0, edhrec_rank=1000):
    return CardClass(
        name=name,
        bucket=bucket,
        roles=tuple(roles),
        served=tuple(served),
        dual_purpose=(bucket == "spine" and bool(served)),
        cmc=cmc,
        record={"name": name, "edhrec_rank": edhrec_rank},
        edhrec_rank=edhrec_rank,
    )


def _band(current, lo, hi):
    dev = current - hi if current > hi else (current - lo if current < lo else 0)
    return {
        "current": current,
        "min": lo,
        "max": hi,
        "target": hi,
        "remaining": max(0, lo - current),
        "deviation": dev,
    }


def test_curve_fix_does_not_overshoot_a_full_role():
    classes = [
        _cc("Filler One", "filler", cmc=4.0),
        _cc("Filler Two", "filler", cmc=3.0),
    ]
    # interaction is AT its ceiling — adding an interaction card would go off-template.
    budgets = {
        "interaction": _band(12, 8, 12),  # full
        "card_draw": _band(10, 10, 12),  # room
    }
    issue = {
        "kind": "efficiency",
        "subkind": "thin top-end",
        "severity": 3,
        "message": "curve: thin top-end",
    }
    dirty = {  # a 7-MV finisher that ALSO fills interaction (would overshoot)
        "name": "Big Removal",
        "type_line": "Sorcery",
        "oracle_text": "Destroy target creature.",
        "cmc": 7.0,
        "prices": {"usd": "1.00"},
        "color_identity": [],
    }
    clean = {  # a 7-MV finisher with no Spine role — template-safe
        "name": "Big Wincon",
        "type_line": "Sorcery",
        "oracle_text": "You win the game.",
        "cmc": 7.0,
        "prices": {"usd": "1.00"},
        "color_identity": [],
    }

    out = propose_swaps(
        classes,
        [issue],
        budgets=budgets,
        focus_result={
            "viable_avenues": [],
            "stranded_avenues": [],
            "verdict": "FOCUSED",
        },
        deck_signals=[],
        search_fn=lambda **_: [dirty, clean],
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=50.0,
        max_swaps=1,
        top_heavy=False,
    )
    assert len(out["swaps"]) == 1
    # The clean finisher is chosen over the one that would push interaction over its band.
    assert out["swaps"][0]["add"]["name"] == "Big Wincon"


def test_role_over_trims_the_over_role_not_a_floor_role():
    classes = [
        _cc("Pure Removal", "spine", roles=["interaction"]),
        _cc("Lone Wrath", "spine", roles=["interaction", "board_wipe"]),
    ]
    budgets = {
        "interaction": _band(13, 8, 12),  # over by 1 — trim from here
        "board_wipe": _band(2, 2, 3),  # AT floor — its card must not be trimmed
    }
    issue = {
        "kind": "role_over",
        "role": "interaction",
        "severity": 1,
        "message": "interaction over",
    }
    add = {
        "name": "Token Maker",
        "type_line": "Sorcery",
        "oracle_text": "Create a token.",
        "cmc": 3.0,
        "prices": {"usd": "1.00"},
        "color_identity": [],
    }
    out = propose_swaps(
        classes,
        [issue],
        budgets=budgets,
        focus_result=_focus(viable=[{"label": "Main", "depth": 20, "cards": []}]),
        deck_signals=[],
        search_fn=lambda **_: [add],
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=50.0,
        max_swaps=1,
        top_heavy=False,
    )
    assert len(out["swaps"]) == 1
    # Trims the pure removal, never the lone board wipe (which sits at its floor).
    assert out["swaps"][0]["cut"]["name"] == "Pure Removal"


def test_role_search_specs_reference_only_real_presets():
    # Regression: _ROLE_SEARCH["ramp"] used a nonexistent 'ramp' preset, which made
    # card_search raise BadParameter and 500'd /api/tune for any ramp-short deck.
    for spec in [*_ROLE_SEARCH.values(), _PROTECTION_SEARCH]:
        for preset in spec.get("preset_names", ()):
            get_preset(preset)  # raises KeyError on an unknown preset → test fails
    # ramp has no theme_preset, so it must be sourced by oracle text, not a preset.
    assert "ramp" not in _ROLE_SEARCH["ramp"].get("preset_names", ())
    assert _ROLE_SEARCH["ramp"].get("oracle")


def test_dead_weight_replaces_filler_with_synergy_not_engine_cards():
    # Real signal so the main-theme search spec resolves (as it does on a live deck).
    sig = Signal(
        key="proliferate_matters",
        scope="you",
        subject="",
        text="",
        source="X",
        confidence="high",
    )
    label = spec_for(sig).label
    classes = [
        _cc("Junk A", "filler", cmc=4.0),
        _cc("Junk B", "filler", cmc=3.0),
        _cc("Junk C", "filler", cmc=2.0),
        _cc("Theme Engine", "engine", served=[label]),
    ]
    issue = {"kind": "dead_weight", "severity": 7, "count": 3, "message": "dead weight"}
    adds = [
        {
            "name": f"Payoff {i}",
            "type_line": "Creature",
            "oracle_text": "Proliferate.",
            "cmc": 3.0,
            "prices": {"usd": "1.00"},
            "color_identity": [],
        }
        for i in range(3)
    ]
    out = propose_swaps(
        classes,
        [issue],
        budgets={},
        focus_result=_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
        deck_signals=[sig],
        search_fn=lambda **_: adds,
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=50.0,
        max_swaps=10,
        top_heavy=False,
    )
    cut_names = {s["cut"]["name"] for s in out["swaps"]}
    # Only filler is cut — never the engine card that serves the plan.
    assert cut_names <= {"Junk A", "Junk B", "Junk C"}
    assert "Theme Engine" not in cut_names
    assert len(out["swaps"]) == 3  # all three junk cards replaced with synergy adds


def test_top_issues_flags_dead_weight_only_with_a_redeploy_target():
    base = {
        "efficiency_r": {"verdict": "ok"},
        "template_r": {"short": {}, "over": {}},
        "wincons_r": {"status": "ok"},
        "protection_r": {"status": "ok"},
        "commander_r": {"misfit": False},
    }
    heavy = {
        "filler": 6,
        "viable_avenues": [{"label": "X"}],
        "emerging": [],
        "verdict": "FOCUSED",
        "stranded_avenues": [],
    }
    kinds = {i["kind"] for i in top_issues(focus_r=heavy, **base)}
    assert "dead_weight" in kinds
    # A couple of off-theme cards is normal, not "dead weight".
    light = {**heavy, "filler": 1}
    assert "dead_weight" not in {i["kind"] for i in top_issues(focus_r=light, **base)}
    # No theme to deepen and no short role → advisory only, no swap issue.
    no_target = {**heavy, "viable_avenues": []}
    assert "dead_weight" not in {
        i["kind"] for i in top_issues(focus_r=no_target, **base)
    }


def test_dead_weight_outranks_theme_refocus():
    # A do-nothing card should be replaced before the deck abandons a thin theme: with
    # both signals present, dead_weight must sort ahead of spread_thin.
    focus_r = {
        "filler": 6,
        "viable_avenues": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
        "emerging": [],
        "verdict": "SPREAD-THIN",
        "stranded_avenues": ["A", "B"],
    }
    issues = top_issues(
        efficiency_r={"verdict": "ok"},
        focus_r=focus_r,
        template_r={"short": {}, "over": {}},
        wincons_r={"status": "ok"},
        protection_r={"status": "ok"},
        commander_r={"misfit": False},
    )
    kinds = [i["kind"] for i in issues]
    assert kinds.index("dead_weight") < kinds.index("spread_thin")


def _prolif_sig():
    return Signal(
        key="proliferate_matters",
        scope="you",
        subject="",
        text="",
        source="X",
        confidence="high",
    )


def test_dead_weight_cuts_fringe_theme_cards_keeps_played_ones():
    sig = _prolif_sig()
    label = spec_for(sig).label
    classes = [
        _cc("Good Engine", "engine", served=[label], edhrec_rank=500),  # played
        _cc("Vanilla Beater", "engine", served=[label], edhrec_rank=27000),  # fringe
        _cc("Unranked Beater", "engine", served=[label], edhrec_rank=None),  # fringe
    ]
    issue = {"kind": "dead_weight", "severity": 8, "count": 2, "message": "x"}
    adds = [
        {
            "name": f"Better {i}",
            "type_line": "Creature",
            "oracle_text": "Proliferate.",
            "cmc": 3.0,
            "prices": {"usd": "1.00"},
            "color_identity": [],
            "edhrec_rank": 200,
        }
        for i in range(3)
    ]
    out = propose_swaps(
        classes,
        [issue],
        budgets={},
        focus_result=_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
        deck_signals=[sig],
        search_fn=lambda **_: adds,
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=50.0,
        max_swaps=10,
        top_heavy=False,
    )
    cut = {s["cut"]["name"] for s in out["swaps"]}
    assert {"Vanilla Beater", "Unranked Beater"} <= cut  # fringe theme cards upgraded
    assert "Good Engine" not in cut  # a well-played theme card is spared


def test_add_prefers_higher_playrate_over_cheaper_chaff():
    sig = _prolif_sig()
    label = spec_for(sig).label
    classes = [_cc("Filler A", "filler", cmc=3.0)]
    issue = {"kind": "dead_weight", "severity": 7, "count": 1, "message": "x"}
    staple = {
        "name": "Staple",
        "type_line": "Creature",
        "oracle_text": "Proliferate.",
        "cmc": 3.0,
        "prices": {"usd": "5.00"},
        "color_identity": [],
        "edhrec_rank": 50,
    }
    chaff = {
        "name": "Chaff",
        "type_line": "Creature",
        "oracle_text": "Proliferate.",
        "cmc": 3.0,
        "prices": {"usd": "0.10"},
        "color_identity": [],
        "edhrec_rank": 40000,
    }
    out = propose_swaps(
        classes,
        [issue],
        budgets={},
        focus_result=_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
        deck_signals=[sig],
        search_fn=lambda **_: [chaff, staple],
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=50.0,
        max_swaps=1,
        top_heavy=False,
    )
    # Equal synergy → the played staple wins over the cheaper but unplayed chaff.
    assert out["swaps"][0]["add"]["name"] == "Staple"


def test_dead_weight_fires_on_fringe_theme_cards_without_filler():
    base = {
        "efficiency_r": {"verdict": "ok"},
        "template_r": {"short": {}, "over": {}},
        "wincons_r": {"status": "ok"},
        "protection_r": {"status": "ok"},
        "commander_r": {"misfit": False},
    }
    fr = {
        "filler": 0,
        "low_value": 4,
        "viable_avenues": [{"label": "X"}],
        "emerging": [],
        "verdict": "FOCUSED",
        "stranded_avenues": [],
    }
    assert "dead_weight" in {i["kind"] for i in top_issues(focus_r=fr, **base)}


def test_fill_pass_adds_without_cuts_to_grow_an_undersized_deck():
    sig = _prolif_sig()
    label = spec_for(sig).label
    classes = [_cc("Existing Theme Card", "engine", served=[label], edhrec_rank=500)]
    budgets = {"ramp": _band(0, 10, 12)}  # ramp short → fill toward floor
    adds = [
        {
            "name": f"Mana Dork {i}",
            "type_line": "Creature — Elf",
            "oracle_text": "Add {G}.",
            "cmc": 1.0,
            "prices": {"usd": "1.00"},
            "color_identity": ["G"],
            "edhrec_rank": 300,
        }
        for i in range(20)
    ]
    # A land matching the ramp oracle ("Add") must NOT be filled — land slots are reserved.
    a_land = {
        "name": "Sneaky Land",
        "type_line": "Land",
        "oracle_text": "{T}: Add {G}.",
        "cmc": 0.0,
        "prices": {"usd": "1.00"},
        "color_identity": ["G"],
        "edhrec_rank": 100,
    }
    out = propose_swaps(
        classes,
        [],
        budgets=budgets,
        focus_result=_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
        deck_signals=[sig],
        search_fn=lambda **_: [a_land, *adds],
        identity="G",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=100.0,
        max_swaps=50,
        top_heavy=False,
        fill_slots=8,
    )
    fills = [s for s in out["swaps"] if s["cut"] is None]
    assert len(fills) == 8  # filled exactly the open slots, with pure adds (no cut)
    assert "Sneaky Land" not in {s["add"]["name"] for s in fills}  # lands reserved


def test_fill_slots_zero_leaves_a_full_deck_untouched():
    # A complete deck (fill_slots=0) gets no fill adds — only the normal swap behavior.
    out = propose_swaps(
        [_cc("Filler", "filler", cmc=3.0)],
        [],
        budgets={},
        focus_result=_focus(),
        deck_signals=[],
        search_fn=lambda **_: [],
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=100.0,
        max_swaps=50,
        top_heavy=False,
        fill_slots=0,
    )
    assert out["swaps"] == []


def test_emerging_theme_proposes_a_commit_add():
    sig = Signal(
        key="proliferate_matters",
        scope="you",
        subject="",
        text="",
        source="X",
        confidence="high",
    )
    label = spec_for(sig).label
    issue = {"kind": "under_supported_theme", "label": label}
    spec = _spec_for_issue(
        issue, _focus(emerging=[{"label": label, "depth": 7, "cards": []}]), [sig]
    )
    assert spec is not None  # resolves to the emerging theme's search → "commit" adds


def _finisher(name, rarity):
    return {
        "name": name,
        "type_line": "Sorcery",
        "oracle_text": "You win the game.",
        "cmc": 7.0,
        "rarity": rarity,
        "prices": {"usd": "1.00"},
        "color_identity": [],
    }


def test_wildcard_budget_gates_adds_by_rarity():
    """Digital: an add is only sourced while its rarity's wildcard budget holds, and the
    spend is tracked per tier (wildcards aren't interchangeable)."""
    classes = [_cc("Filler One", "filler", cmc=4.0)]
    budgets = {"card_draw": _band(10, 10, 12)}  # room, no role pressure
    issue = {
        "kind": "efficiency",
        "subkind": "thin top-end",
        "severity": 3,
        "message": "curve: thin top-end",
    }
    # Budget allows one rare but no mythic — the mythic must be skipped, the rare taken.
    out = propose_swaps(
        classes,
        [issue],
        budgets=budgets,
        focus_result=_focus(),
        deck_signals=[],
        search_fn=lambda **_: [
            _finisher("Pricey Mythic", "mythic"),
            _finisher("Fine Rare", "rare"),
        ],
        identity="",
        fmt="historic_brawl",
        paper_only=False,
        owned={},
        budget=None,
        max_swaps=1,
        top_heavy=False,
        wildcard_budget={"mythic": 0, "rare": 1, "uncommon": 0, "common": 0},
    )
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["add"]["name"] == "Fine Rare"
    assert out["spent"] == 0.0  # USD total is always a float (0 in digital)
    assert out["wildcards_spent"] == {
        "mythic": 0,
        "rare": 1,
        "uncommon": 0,
        "common": 0,
    }


def test_wildcard_owned_is_free_even_at_zero_budget():
    """Digital: an owned card costs no wildcard, so it's added under an all-zero budget
    while an unowned one of the same rarity is not."""
    classes = [_cc("Filler One", "filler", cmc=4.0)]
    budgets = {"card_draw": _band(10, 10, 12)}
    issue = {
        "kind": "efficiency",
        "subkind": "thin top-end",
        "severity": 3,
        "message": "curve: thin top-end",
    }
    out = propose_swaps(
        classes,
        [issue],
        budgets=budgets,
        focus_result=_focus(),
        deck_signals=[],
        search_fn=lambda **_: [
            _finisher("Unowned Rare", "rare"),
            _finisher("Owned Rare", "rare"),
        ],
        identity="",
        fmt="historic_brawl",
        paper_only=False,
        owned={"Owned Rare": 1},
        budget=None,
        max_swaps=1,
        top_heavy=False,
        wildcard_budget={"mythic": 0, "rare": 0, "uncommon": 0, "common": 0},
    )
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["add"]["name"] == "Owned Rare"
    assert out["spent"] == 0.0
    assert out["wildcards_spent"] == {
        "mythic": 0,
        "rare": 0,
        "uncommon": 0,
        "common": 0,
    }
