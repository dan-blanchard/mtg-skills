"""Swap engine: template-safety, role-over trims, and emerging-theme commits."""

from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.issues import (
    PROTECTION_SEARCH,
    ROLE_SEARCH,
    Sourcing,
    _reliable_ramp,
    top_issues,
)
from mtg_utils._tuner.swaps import (
    SwapContext,
    _cut_why,
    _is_fixing,
    cut_candidates,
    propose_swaps,
)
from mtg_utils.testkit import test_card
from mtg_utils.theme_presets import get_preset

# Issues are built THROUGH the interface: ``Sourcing.issue`` decides each remedy from
# the same focus / signals / budgets the test hands the swap engine — a test never
# hand-sets a remedy.
_ISSUE_FIELDS = ("role", "label", "subkind", "count", "advisory")


def _issue(sourcing, fields):
    return sourcing.issue(
        fields["kind"],
        severity=fields.get("severity", 0),
        message=fields.get("message", ""),
        **{k: fields[k] for k in _ISSUE_FIELDS if k in fields},
    )


def _swaps_for_issue_dicts(classes, issues, ctx):
    sourcing = Sourcing(ctx.focus_result, ctx.deck_signals, ctx.budgets)
    return propose_swaps(classes, [_issue(sourcing, i) for i in issues], ctx)


def _top_issues_for(*, focus_r, template_r, deck_signals=(), **metrics):
    """``issues.top_issues`` over the budgets the template rows came from."""
    budgets = {**template_r["short"], **template_r["over"]}
    return top_issues(
        focus_r=focus_r,
        template_r=template_r,
        sourcing=Sourcing(focus_r, list(deck_signals), budgets),
        **metrics,
    )


def _focus(viable=(), emerging=(), stranded=()):
    return {
        "viable_avenues": list(viable),
        "emerging": list(emerging),
        "stranded_avenues": list(stranded),
        "verdict": "FOCUSED",
    }


def _cc(
    name,
    bucket,
    roles=(),
    served=(),
    cmc=2.0,
    edhrec_rank=1000,
    oracle="",
    produced=None,
):
    return CardClass(
        name=name,
        bucket=bucket,
        roles=tuple(roles),
        served=tuple(served),
        dual_purpose=(bucket == "spine" and bool(served)),
        cmc=cmc,
        record={
            "name": name,
            "edhrec_rank": edhrec_rank,
            "oracle_text": oracle,
            "produced_mana": produced,
        },
        edhrec_rank=edhrec_rank,
    )


def _real_cc(name, bucket, roles=(), served=(), edhrec_rank=1000):
    """A real card from the testkit snapshot (ADR-0056) as a ``CardClass``, with
    only its per-printing EDHREC rank overlaid."""
    record = {**test_card(name), "edhrec_rank": edhrec_rank}
    return CardClass(
        name=name,
        bucket=bucket,
        roles=tuple(roles),
        served=tuple(served),
        dual_purpose=(bucket == "spine" and bool(served)),
        cmc=float(record.get("cmc") or 0.0),
        record=record,
        edhrec_rank=edhrec_rank,
    )


def _band(current, lo, hi, **extra):
    dev = current - hi if current > hi else (current - lo if current < lo else 0)
    return {
        "current": current,
        "min": lo,
        "max": hi,
        "target": hi,
        "remaining": max(0, lo - current),
        "deviation": dev,
        **extra,
    }


def test_is_fixing_counts_basic_land_fetch():
    # Land-fetch ramp produces no battlefield mana (produced_mana is empty on a sorcery),
    # but a basic-land search IS color fixing: a generic "basic land" fetch lets you pick
    # the color you need, and a multi-type land-name fetch grabs 2+ types. _is_fixing read
    # only produced_mana, so it protected a strictly-worse 2-color rock while cutting the
    # any-basic fetcher that fixes all of the deck's colors.
    kodama = _real_cc("Kodama's Reach", "spine", roles=("ramp",))
    farseek = _real_cc("Farseek", "spine", roles=("ramp",))
    rampant = _real_cc("Rampant Growth", "spine", roles=("ramp",))
    signet = _real_cc("Golgari Signet", "spine", roles=("ramp",))
    sol_ring = _real_cc("Sol Ring", "spine", roles=("ramp",))
    assert _is_fixing(kodama) is True
    assert _is_fixing(farseek) is True
    assert _is_fixing(rampant) is True
    assert _is_fixing(signet) is True  # 2 produced colors
    assert _is_fixing(sol_ring) is False  # colorless rock


def test_over_band_ramp_cut_keeps_basic_land_fetch_over_colorless_rock():
    # ramp over by 1; the cut must trim the redundant colorless rock, not the basic-land
    # fetch that fixes the deck's colors. Kodama is the LEAST-played (rank 900 vs 40) so
    # without the fix the play-rate tiebreak cuts it first — _is_fixing must override that.
    kodama = _real_cc("Kodama's Reach", "spine", roles=("ramp",), edhrec_rank=900)
    mind_stone = _real_cc("Mind Stone", "spine", roles=("ramp",), edhrec_rank=40)
    budgets = {"ramp": _band(2, 0, 1), "lands": _band(36, 36, 38)}
    cuts = cut_candidates(
        [kodama, mind_stone], budgets=budgets, focus_verdict="FOCUSED", stranded=set()
    )
    over_ramp = [c.name for reason, c in cuts if reason == "over:ramp"]
    assert over_ramp[:1] == ["Mind Stone"]  # the colorless rock, not Kodama's Reach


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
    # ``propose_swaps`` reads its role off ``role_of``, which buckets
    # "interaction" via ``get_preset("removal").matches`` — a structural
    # (``signal_keys``) view since task #86 (the last regex-bearing built-in
    # preset flip), so it needs a real, crosswalk-resolvable ``oracle_id``.
    # Base the record on the real "Murder" card's oracle_id/oracle_text
    # (seeding the trees memo first) while keeping the scenario's own
    # "Big Removal" name/cmc/price/color_identity fields — the test cares
    # about the CURVE overshoot behavior, not this card's flavor.
    from mtg_utils import testkit

    testkit.test_card_ir("Murder")  # seeds the crosswalk trees memo
    murder = testkit.test_card("Murder")
    dirty = {  # a 7-MV finisher that ALSO fills interaction (would overshoot)
        "name": "Big Removal",
        "type_line": "Sorcery",
        "oracle_text": "Destroy target creature.",
        "oracle_id": murder["oracle_id"],
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

    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
    )
    assert len(out["swaps"]) == 1
    # The clean finisher is chosen over the one that would push interaction over its band.
    assert out["swaps"][0]["add"]["name"] == "Big Wincon"


def test_an_excluded_add_yields_its_slot_to_the_next_candidate():
    """The builder's Reject (``SwapContext.exclude``): the rejected card is never
    sourced, and the same issue is answered by the next-ranked candidate."""
    classes = [
        _cc("Filler One", "filler", cmc=4.0),
        _cc("Filler Two", "filler", cmc=3.0),
    ]
    budgets = {"card_draw": _band(10, 10, 12)}
    issue = {
        "kind": "efficiency",
        "subkind": "thin top-end",
        "severity": 3,
        "message": "curve: thin top-end",
    }

    def finisher(name):
        return {
            "name": name,
            "type_line": "Sorcery",
            "oracle_text": "You win the game.",
            "cmc": 7.0,
            "prices": {"usd": "1.00"},
            "color_identity": [],
        }

    def ctx(exclude):
        return SwapContext(
            budgets=budgets,
            focus_result={
                "viable_avenues": [],
                "stranded_avenues": [],
                "verdict": "FOCUSED",
            },
            deck_signals=[],
            search_fn=lambda **_: [finisher("First Pick"), finisher("Second Pick")],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
            exclude=exclude,
        )

    plain = _swaps_for_issue_dicts(classes, [issue], ctx(()))
    assert [s["add"]["name"] for s in plain["swaps"]] == ["First Pick"]
    rejected = _swaps_for_issue_dicts(classes, [issue], ctx({"First Pick"}))
    assert [s["add"]["name"] for s in rejected["swaps"]] == ["Second Pick"]
    assert rejected["swaps"][0]["cut"] == plain["swaps"][0]["cut"]
    # Both rejected: the issue yields nothing, and the note says the rejection is why.
    none = _swaps_for_issue_dicts(classes, [issue], ctx({"First Pick", "Second Pick"}))
    assert none["swaps"] == []
    assert "No alternative to First Pick, Second Pick" in none["note"]
    assert "curve: thin top-end" in none["note"]


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
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
    )
    assert len(out["swaps"]) == 1
    # Trims the pure removal, never the lone board wipe (which sits at its floor).
    assert out["swaps"][0]["cut"]["name"] == "Pure Removal"


def test_role_over_trim_cuts_least_played_excess_not_a_staple():
    # Ramp over by 1. A premium staple (Sol Ring, rank 1, serving no thematic
    # avenue) and a fringe on-theme ramp (rank 30000). The over-band trim must cut
    # the least-played card, never the staple — the pre-fix sort keyed on
    # served-count first, so it cut Sol Ring (0 avenues) over the fringe ramp.
    classes = [
        _real_cc("Sol Ring", "spine", roles=["ramp"], edhrec_rank=1),
        _cc(
            "Fringe Rock",
            "spine",
            roles=["ramp"],
            served=("Lands matter",),
            cmc=3.0,
            edhrec_rank=30000,
        ),
    ]
    budgets = {"ramp": _band(11, 8, 10)}  # over by 1
    issue = {"kind": "role_over", "role": "ramp", "severity": 1, "message": "ramp over"}
    add = {
        "name": "Better Rock",
        "type_line": "Artifact",
        "oracle_text": "{T}: Add {C}.",
        "cmc": 2.0,
        "prices": {"usd": "1.00"},
        "color_identity": [],
    }
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
    )
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["cut"]["name"] == "Fringe Rock"


def test_role_search_specs_reference_only_real_presets():
    # Regression: ROLE_SEARCH["ramp"] once named a 'ramp' preset that did not exist,
    # which made card_search raise BadParameter and 500'd /api/tune for any ramp-short
    # deck.
    for spec in [*ROLE_SEARCH.values(), PROTECTION_SEARCH]:
        for preset in spec.get("preset_names", ()):
            get_preset(preset)  # raises KeyError on an unknown preset → test fails
    # ADR-0051: ramp is sourced by the SAME preset roles.is_ramp counts it by — never a
    # hand-copied oracle regex that can drift from the role.
    assert ROLE_SEARCH["ramp"]["preset_names"] == ("ramp",)
    assert "oracle" not in ROLE_SEARCH["ramp"]


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
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
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
    kinds = {i.kind for i in _top_issues_for(focus_r=heavy, **base)}
    assert "dead_weight" in kinds
    # A couple of off-theme cards is normal, not "dead weight".
    light = {**heavy, "filler": 1}
    assert "dead_weight" not in {i.kind for i in _top_issues_for(focus_r=light, **base)}
    # No theme to deepen and no short role → advisory only, no swap issue.
    no_target = {**heavy, "viable_avenues": []}
    assert "dead_weight" not in {
        i.kind for i in _top_issues_for(focus_r=no_target, **base)
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
    issues = _top_issues_for(
        efficiency_r={"verdict": "ok"},
        focus_r=focus_r,
        template_r={"short": {}, "over": {}},
        wincons_r={"status": "ok"},
        protection_r={"status": "ok"},
        commander_r={"misfit": False},
    )
    kinds = [i.kind for i in issues]
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
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
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
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
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
    assert "dead_weight" in {i.kind for i in _top_issues_for(focus_r=fr, **base)}


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
    out = _swaps_for_issue_dicts(
        classes,
        [],
        SwapContext(
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
        ),
    )
    fills = [s for s in out["swaps"] if s["cut"] is None]
    assert len(fills) == 8  # filled exactly the open slots, with pure adds (no cut)
    assert "Sneaky Land" not in {s["add"]["name"] for s in fills}  # lands reserved


def test_fill_slots_zero_leaves_a_full_deck_untouched():
    # A complete deck (fill_slots=0) gets no fill adds — only the normal swap behavior.
    out = _swaps_for_issue_dicts(
        [_cc("Filler", "filler", cmc=3.0)],
        [],
        SwapContext(
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
        ),
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
    sourcing = Sourcing(
        _focus(emerging=[{"label": label, "depth": 7, "cards": []}]), [sig], {}
    )
    remedy = sourcing.remedy_for("under_supported_theme", label=label)
    spec = remedy.spec if remedy else None
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
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
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
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
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


def test_reliable_ramp_excludes_conditional_and_opponent_mana():
    """The tuner sources only ramp it can rely on: genuine producers that aren't gated
    on board state, and never mana an opponent receives."""

    def rock(oracle, type_line="Artifact"):
        return {"type_line": type_line, "oracle_text": oracle}

    # Genuine, unconditional ramp → sourced.
    assert _reliable_ramp(rock("{T}: Add one mana of any color."))
    # Mox Opal (metalcraft) / Mox Jasper (a Dragon): conditional rocks → not sourced.
    assert not _reliable_ramp(
        rock(
            "Metalcraft — {T}: Add one mana of any color. Activate only if you "
            "control three or more artifacts."
        )
    )
    assert not _reliable_ramp(
        rock("{T}: Add one mana of any color. Activate only if you control a Dragon.")
    )
    # An Offer You Can't Refuse: the Treasures (and their mana) go to the opponent.
    assert not _reliable_ramp(
        rock(
            "Counter target noncreature spell. Its controller creates two Treasure "
            "tokens. (They're artifacts with \"{T}, Sacrifice this token: Add one "
            'mana of any color.")',
            type_line="Instant",
        )
    )


def test_cut_candidates_null_rank_low_value_is_medium_aware():
    # ADR-0040 §4 (task #99): a null edhrec_rank on a digital deck is no-data
    # (EDHREC has no Arena population), so it can't push an engine card into
    # the low_value cut queue; on paper it stays fringe-evidence and does.
    classes = [_cc("Alchemy Only", "engine", served=["Tokens"], edhrec_rank=None)]
    kw = {"budgets": {}, "focus_verdict": "FOCUSED", "stranded": set()}
    paper = cut_candidates(classes, medium="paper", **kw)
    digital = cut_candidates(classes, medium="digital", **kw)
    assert ("low_value", "Alchemy Only") in [(r, c.name) for r, c in paper]
    assert [(r, c.name) for r, c in digital] == []


# ── ADR-0040 companion: FOCUSED role-fix adds prefer an on-avenue candidate ──


def _on_avenue_draw(name, cmc, rank):
    return {
        "name": name,
        "type_line": "Sorcery",
        "oracle_text": "Draw a card. Proliferate.",
        "cmc": cmc,
        "prices": {"usd": "2.00"},
        "color_identity": [],
        "edhrec_rank": rank,
    }


def _off_avenue_draw(name, cmc, rank):
    return {
        "name": name,
        "type_line": "Sorcery",
        "oracle_text": "Draw a card.",
        "cmc": cmc,
        "prices": {"usd": "1.00"},
        "color_identity": [],
        "edhrec_rank": rank,
    }


def _role_fix_scenario():
    """A card_draw shortfall (role_short, a Spine kind — efficiency-first with
    no synergy input) plus a cheaper off-avenue candidate and a pricier
    on-avenue one, matching the Sliver Weftwinder benchmark failure mode."""
    sig = _prolif_sig()
    label = spec_for(sig).label
    classes = [_cc("Filler Card", "filler", cmc=3.0)]
    budgets = {"card_draw": _band(5, 10, 12)}
    issue = {
        "kind": "role_short",
        "role": "card_draw",
        "severity": 5,
        "message": "card draw short by 5",
    }
    off_avenue = _off_avenue_draw("Generic Draw", cmc=1.0, rank=50)
    on_avenue = _on_avenue_draw("Prolif Draw", cmc=2.0, rank=2000)
    return sig, label, classes, budgets, issue, off_avenue, on_avenue


def test_focused_role_fix_prefers_on_avenue_over_cheaper_off_avenue():
    # Old behavior: the cheaper off-avenue card ranks first (efficiency-first
    # sort has no synergy term at all) and would win. At FOCUSED, the pricier
    # on-avenue candidate must win instead, since it's still in-budget.
    sig, label, classes, budgets, issue, off_avenue, on_avenue = _role_fix_scenario()
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
            budgets=budgets,
            focus_result=_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
            deck_signals=[sig],
            search_fn=lambda **_: [off_avenue, on_avenue],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
        ),
    )
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["add"]["name"] == "Prolif Draw"
    assert "off-avenue fallback" not in out["swaps"][0]["reason"]


def test_focused_role_fix_labels_reason_when_nothing_is_on_avenue():
    # No candidate serves the deck's viable avenue at all — the best-ranked
    # (cheapest) one still ships, but the reason says it's a fallback.
    sig, label, classes, budgets, issue, off_avenue, _on_avenue = _role_fix_scenario()
    off_avenue_b = _off_avenue_draw("Generic Draw B", cmc=2.0, rank=2000)
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
            budgets=budgets,
            focus_result=_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
            deck_signals=[sig],
            search_fn=lambda **_: [off_avenue, off_avenue_b],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
        ),
    )
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["add"]["name"] == "Generic Draw"  # still best-ranked
    assert "(off-avenue fallback)" in out["swaps"][0]["reason"]


def test_spread_thin_role_fix_keeps_efficiency_first_untouched():
    # Same candidates as the FOCUSED preference test, but SPREAD-THIN: the
    # avenue guard must not apply — the cheaper card wins, unlabeled, exactly
    # as before this companion fix.
    sig, label, classes, budgets, issue, off_avenue, on_avenue = _role_fix_scenario()
    focus_result = {
        "viable_avenues": [{"label": label, "depth": 20, "cards": []}],
        "emerging": [],
        "stranded_avenues": [],
        "verdict": "SPREAD-THIN",
    }
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
            budgets=budgets,
            focus_result=focus_result,
            deck_signals=[sig],
            search_fn=lambda **_: [off_avenue, on_avenue],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
        ),
    )
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["add"]["name"] == "Generic Draw"
    assert "off-avenue fallback" not in out["swaps"][0]["reason"]


def test_spine_led_role_fix_keeps_efficiency_first_untouched():
    # Same candidates, SPINE-LED verdict: also untouched.
    sig, label, classes, budgets, issue, off_avenue, on_avenue = _role_fix_scenario()
    focus_result = {
        "viable_avenues": [{"label": label, "depth": 20, "cards": []}],
        "emerging": [],
        "stranded_avenues": [],
        "verdict": "SPINE-LED",
    }
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
            budgets=budgets,
            focus_result=focus_result,
            deck_signals=[sig],
            search_fn=lambda **_: [off_avenue, on_avenue],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
        ),
    )
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["add"]["name"] == "Generic Draw"
    assert "off-avenue fallback" not in out["swaps"][0]["reason"]


def test_focused_role_over_not_gated_by_role_fix_guard():
    # role_over's remedy is not a Spine fill (it ranks synergy-first) — the ADR-0040
    # guard (scoped to ``Remedy.spine``) must not change its existing behavior:
    # best-synergy wins, no label.
    classes = [
        _cc("Pure Removal", "spine", roles=["interaction"]),
        _cc("Lone Wrath", "spine", roles=["interaction", "board_wipe"]),
    ]
    budgets = {
        "interaction": _band(13, 8, 12),
        "board_wipe": _band(2, 2, 3),
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
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
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
        ),
    )
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["add"]["name"] == "Token Maker"
    assert "off-avenue fallback" not in out["swaps"][0]["reason"]


def test_cut_why_weak_granter_message_differs_from_fringe_playrate():
    # Verified-review Fix 6: a weak-grade Granter is condemned by ability
    # QUALITY (playrate-independent, ADR-0040 §2) — the cut reason must say
    # so, not the fringe-playrate message (factually wrong for a well-ranked
    # weak Granter, e.g. rank 500).
    weak_granter = CardClass(
        name="Weak Granter",
        bucket="engine",
        roles=(),
        served=("Slivers",),
        dual_purpose=False,
        cmc=2.0,
        record={"name": "Weak Granter"},
        edhrec_rank=500,
        grant_grade="weak",
    )
    fringe = _cc("Fringe Card", "engine", served=["Slivers"], edhrec_rank=30000)
    weak_why = _cut_why("low_value", weak_granter)
    fringe_why = _cut_why("low_value", fringe)
    assert "weak ability" in weak_why.lower()
    assert "barely played" not in weak_why.lower()
    assert "barely played" in fringe_why.lower()
    assert weak_why != fringe_why


def test_low_value_swap_cut_why_reflects_weak_grant_grade_end_to_end():
    sig = _prolif_sig()
    label = spec_for(sig).label
    weak_granter = CardClass(
        name="Weak Granter",
        bucket="engine",
        roles=(),
        served=(label,),
        dual_purpose=False,
        cmc=2.0,
        record={
            "name": "Weak Granter",
            "type_line": "Creature",
            "oracle_text": "Proliferate.",
        },
        edhrec_rank=500,
        grant_grade="weak",
    )
    issue = {"kind": "dead_weight", "severity": 8, "count": 1, "message": "x"}
    add = {
        "name": "Better Card",
        "type_line": "Creature",
        "oracle_text": "Proliferate.",
        "cmc": 3.0,
        "prices": {"usd": "1.00"},
        "color_identity": [],
        "edhrec_rank": 200,
    }
    out = _swaps_for_issue_dicts(
        [weak_granter],
        [issue],
        SwapContext(
            budgets={},
            focus_result=_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
            deck_signals=[sig],
            search_fn=lambda **_: [add],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=10,
            top_heavy=False,
        ),
    )
    assert len(out["swaps"]) == 1
    why = out["swaps"][0]["cut"]["why"].lower()
    assert "weak ability" in why
    assert "barely played" not in why


def test_cut_candidates_granter_quality_gates_low_value():
    # ADR-0040 §2/§4 (task #97): the low_value cut queue condemns a Granter by
    # quality, never playrate — premium/solid stay out even unranked; weak
    # goes in even when well-ranked.
    def gc(name, grade, rank=None):
        base = _cc(name, "engine", served=["Slivers"], edhrec_rank=rank)
        return CardClass(
            name=base.name,
            bucket=base.bucket,
            roles=base.roles,
            served=base.served,
            dual_purpose=base.dual_purpose,
            cmc=base.cmc,
            record=base.record,
            grant_grade=grade,
        )

    classes = [
        gc("Premium Granter", "premium"),
        gc("Weak Granter", "weak", rank=500),
    ]
    kw = {"budgets": {}, "focus_verdict": "FOCUSED", "stranded": set()}
    got = [(r, c.name) for r, c in cut_candidates(classes, **kw)]
    assert ("low_value", "Weak Granter") in got
    assert all(name != "Premium Granter" for _, name in got)


def test_a_grant_covered_role_sources_nothing_on_any_path():
    # ADR-0040 §1: the three sourcing paths (the issue loop, the dead-weight
    # redeploy, the fill pass) all read ONE answer — Sourcing — so a Grant-covered
    # short role sources nothing anywhere, while its shortfall stays visible.
    covered = Sourcing(
        _focus(), [], {"card_draw": _band(0, 10, 12, grant_covered=True)}
    )
    assert covered.role_spec("card_draw") is None  # the fill pass
    assert covered.remedy_for("role_short", role="card_draw") is None  # issue loop
    assert covered.redeploy() is None  # the dead-weight redeploy
    assert not covered.has_redeploy_target()
    issue = covered.issue("role_short", role="card_draw", severity=10, message="m")
    assert issue.advisory is True
    assert issue.grant_covered is True
    assert issue.remedy is None
    # A normal (non-covered) short role is unaffected — still actionable everywhere.
    plain = Sourcing(_focus(), [], {"card_draw": _band(0, 10, 12)})
    assert plain.role_spec("card_draw") == ROLE_SEARCH["card_draw"]
    assert (
        plain.remedy_for("role_short", role="card_draw").spec
        == (ROLE_SEARCH["card_draw"])
    )
    assert plain.redeploy() == ROLE_SEARCH["card_draw"]


def test_propose_swaps_never_sources_a_grant_covered_role_short_issue():
    # End-to-end: even though the search_fn WOULD happily return draw spells, an
    # issue flagged grant_covered must never turn into a swap — the shortfall stays
    # advisory, not suppressed (a literal cut still isn't taken for it either).
    classes = [
        _cc("Filler One", "filler", cmc=4.0),
        _cc("Filler Two", "filler", cmc=3.0),
    ]
    covered_issue = {
        "kind": "role_short",
        "role": "card_draw",
        "severity": 10,
        # Coverage is read off the budgets row below, never hand-set on the issue.
        "message": "card draw short by 10 — covered by Sliver Weftwinder",
    }
    draw_spell = {**test_card("Faithless Looting"), "prices": {"usd": "0.50"}}
    out = _swaps_for_issue_dicts(
        classes,
        [covered_issue],
        SwapContext(
            budgets={"card_draw": _band(0, 10, 12, grant_covered=True)},
            focus_result=_focus(),
            deck_signals=[],
            search_fn=lambda **_: [draw_spell],
            identity="R",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=100.0,
            max_swaps=10,
            top_heavy=False,
        ),
    )
    assert out["swaps"] == []


def test_dead_weight_never_sources_a_grant_covered_role():
    # Verified-review Fix 4: the dead-weight redeploy (filler into the
    # worst-short Spine role when there's no viable avenue to deepen) is a
    # THIRD sourcing path the #98 advisory downgrade once missed — now all
    # three read `Sourcing`, and this pins the end-to-end behaviour. A
    # grant-covered card_draw shortfall must never source a "fill card_draw"
    # dead-weight add.
    classes = [
        _cc("Junk A", "filler", cmc=4.0),
        _cc("Junk B", "filler", cmc=3.0),
    ]
    issue = {"kind": "dead_weight", "severity": 7, "count": 2, "message": "dead weight"}
    draw_spell = {**test_card("Faithless Looting"), "prices": {"usd": "0.50"}}
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
            budgets={"card_draw": _band(0, 10, 12, grant_covered=True)},
            focus_result=_focus(),
            deck_signals=[],
            search_fn=lambda **_: [draw_spell],
            identity="R",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=100.0,
            max_swaps=10,
            top_heavy=False,
        ),
    )
    assert out["swaps"] == []


def test_top_issues_dead_weight_ignored_when_only_short_role_is_grant_covered():
    # Companion to the above at the top_issues level: when the ONLY short
    # Spine role is grant-covered (and there's no viable avenue either), there
    # is genuinely nowhere to redeploy filler — the dead_weight issue must not
    # even fire (has_target must not count a grant-covered short role as a
    # real target).
    base = {
        "efficiency_r": {"verdict": "ok"},
        "wincons_r": {"status": "ok"},
        "protection_r": {"status": "ok"},
        "commander_r": {"misfit": False},
    }
    heavy = {
        "filler": 6,
        "viable_avenues": [],
        "emerging": [],
        "verdict": "SPINE-LED",
        "stranded_avenues": [],
    }
    covered_short = {"card_draw": _band(0, 10, 12, grant_covered=True)}
    kinds = {
        i.kind
        for i in _top_issues_for(
            focus_r=heavy, template_r={"short": covered_short, "over": {}}, **base
        )
    }
    assert "dead_weight" not in kinds
    # A short role that ISN'T grant-covered still counts as a real target.
    uncovered_short = {"card_draw": _band(0, 10, 12)}
    kinds2 = {
        i.kind
        for i in _top_issues_for(
            focus_r=heavy, template_r={"short": uncovered_short, "over": {}}, **base
        )
    }
    assert "dead_weight" in kinds2


def test_fill_pass_skips_a_grant_covered_role():
    # A grant-covered role must not get pure fill-adds either (ADR-0040 §1 stops
    # the swap engine end to end) — only the OTHER short role gets filled.
    interaction_spell = {
        **test_card("Swords to Plowshares"),
        "prices": {"usd": "1.00"},
        "edhrec_rank": 50,
    }
    budgets = {
        "card_draw": _band(0, 10, 12, grant_covered=True),
        "interaction": _band(0, 10, 12),
    }
    out = _swaps_for_issue_dicts(
        [_cc("Filler", "filler", cmc=3.0)],
        [],
        SwapContext(
            budgets=budgets,
            focus_result=_focus(),
            deck_signals=[],
            search_fn=lambda **_: [interaction_spell],
            identity="W",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=100.0,
            max_swaps=50,
            top_heavy=False,
            fill_slots=10,
        ),
    )
    fills = [s for s in out["swaps"] if s["cut"] is None]
    assert fills  # interaction still gets filled
    assert all(s["add"]["name"] != "Faithless Looting" for s in fills)
    assert all("card draw" not in s["reason"].lower() for s in fills)


# ── ADR-0030: the proposer respects the target bracket's Game Changer ceiling ───


def _gc_scenario(room, *, cut_is_game_changer=False):
    """A protection-short deck whose best add is a Game Changer, with a plain
    alternative behind it; ``room`` is the bracket's remaining Game Changer headroom."""
    filler = _cc("Dead Card", "filler", cmc=5.0)
    filler.record["game_changer"] = cut_is_game_changer
    staple = {
        "name": "Staple Game Changer",
        "type_line": "Instant",
        "oracle_text": "",
        "cmc": 1.0,
        "edhrec_rank": 5,
        "game_changer": True,
        "prices": {"usd": "1.00"},
        "color_identity": [],
    }
    plain = {**staple, "name": "Plain Protection", "cmc": 2.0, "game_changer": False}
    issue = {"kind": "protection_short", "severity": 3, "message": "protection"}
    out = _swaps_for_issue_dicts(
        [filler],
        [issue],
        SwapContext(
            budgets={},
            focus_result=_focus(),
            deck_signals=[],
            search_fn=lambda **_: [staple, plain],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
            game_changer_room=room,
        ),
    )
    return [s["add"]["name"] for s in out["swaps"]]


def test_no_target_bracket_means_no_game_changer_ceiling():
    assert _gc_scenario(None) == ["Staple Game Changer"]


def test_a_game_changer_is_never_proposed_past_the_bracket_ceiling():
    # ADR-0030: "The swap proposer respects the ceiling (won't propose a Game-Changer
    # add that breaches the target)" — the next-best legal add ships instead.
    assert _gc_scenario(0) == ["Plain Protection"]
    assert _gc_scenario(1) == ["Staple Game Changer"]


def test_a_deck_over_the_ceiling_cannot_cut_its_way_into_a_new_game_changer():
    # Two over the ceiling (room -2): cutting ONE Game Changer leaves the deck still one
    # over, so the freed slot must not buy a Game Changer add. A clamped room (0) once
    # read that cut as +1 headroom and proposed one.
    assert _gc_scenario(-2, cut_is_game_changer=True) == ["Plain Protection"]
    # One under after the cut (room 0 → 1)… but the add is picked BEFORE the cut is
    # secured, so a swap never spends room its own cut would free.
    assert _gc_scenario(0, cut_is_game_changer=True) == ["Plain Protection"]


# ── Ownership: each added copy is free only when Format.copies_short covers it ───


def _fill(owned, *, wildcard_budget=None, budget=None, slots=4):
    """Pure fill adds of one candidate — Swords to Plowshares, a four-of here — into
    ``slots`` open slots of a constructed build short on interaction."""
    candidate = {
        **test_card("Swords to Plowshares"),
        "rarity": "uncommon",
        "prices": {"usd": "1.00"},
        "edhrec_rank": 50,
    }
    out = _swaps_for_issue_dicts(
        [_cc("Filler", "filler", cmc=3.0)],
        [],
        SwapContext(
            budgets={"interaction": _band(0, 10, 12)},
            focus_result=_focus(),
            deck_signals=[],
            search_fn=lambda **_: [candidate],
            identity="W",
            fmt="historic",
            paper_only=wildcard_budget is None,
            owned=owned,
            budget=budget,
            max_swaps=50,
            top_heavy=False,
            fill_slots=slots,
            wildcard_budget=wildcard_budget,
            medium="paper" if wildcard_budget is None else "digital",
            max_copies=4,
        ),
    )
    return [s for s in out["swaps"] if s["cut"] is None]


_NO_WILDCARDS = {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0}


def test_owned_covers_only_the_copies_you_own():
    # One owned copy pays for the first add only; the second copy is a wildcard (none
    # left) or a purchase (owned-only pass), so the fill stops at one.
    assert len(_fill({"Swords to Plowshares": 1}, wildcard_budget=_NO_WILDCARDS)) == 1
    assert len(_fill({"Swords to Plowshares": 2})) == 2


def test_an_arena_playset_covers_every_copy():
    fills = _fill({"Swords to Plowshares": 4}, wildcard_budget=_NO_WILDCARDS)
    assert len(fills) == 4


def test_a_crafted_copy_never_reads_as_owned():
    # Two owned, two crafted: the swap's ``owned`` follows the same coverage the purse
    # charged, so the third and fourth copies say "not owned" (they cost a wildcard).
    fills = _fill(
        {"Swords to Plowshares": 2},
        wildcard_budget={**_NO_WILDCARDS, "uncommon": 2},
    )
    assert [
        (f["add"]["copy"], f["add"]["owned"], f["add"]["covered_by"]) for f in fills
    ] == [
        (1, True, "owned"),
        (2, True, "owned"),
        (3, False, None),
        (4, False, None),
    ]
    # Each add serves its shortfall (the copy it costs), which the UI sums.
    assert [f["add"]["copies_short"] for f in fills] == [0, 0, 1, 1]
