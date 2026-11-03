"""Swap engine: template-safety, role-over trims, and emerging-theme commits."""

from dataclasses import replace

import pytest

from mtg_utils._analysis.roles import is_reliable_ramp
from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.issues import (
    PROTECTION_SEARCH,
    ROLE_SEARCH,
    Sourcing,
    top_issues,
)
from mtg_utils._tuner.swaps import (
    CutFocus,
    SwapContext,
    _blended_percentiles,
    _cut_why,
    _is_fixing,
    _upgrades,
    cut_candidates,
    propose_swaps,
    search_key,
)
from mtg_utils.testkit import test_card, test_card_ir
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


def test_is_fixing_reads_the_land_search_off_the_trees():
    # Any land card (Sylvan Scrying) can find any land: fixing. A single basic land
    # type ("a Forest card", Three Visits) is mono-color ramp. An opponent's
    # compensation search (Path to Exile) isn't yours.
    scrying = _real_cc("Sylvan Scrying", "spine", roles=("ramp",))
    three_visits = _real_cc("Three Visits", "spine", roles=("ramp",))
    path = _real_cc("Path to Exile", "spine", roles=("removal",))
    assert _is_fixing(scrying) is True
    assert _is_fixing(three_visits) is False
    assert _is_fixing(path) is False


def test_over_band_ramp_cut_keeps_basic_land_fetch_over_colorless_rock():
    # ramp over by 1; the cut must trim the redundant colorless rock, not the basic-land
    # fetch that fixes the deck's colors. Kodama is the LEAST-played (rank 900 vs 400) so
    # without the fix the play-rate tiebreak cuts it first — _is_fixing must override that.
    kodama = _real_cc("Kodama's Reach", "spine", roles=("ramp",), edhrec_rank=900)
    mind_stone = _real_cc("Mind Stone", "spine", roles=("ramp",), edhrec_rank=400)
    budgets = {"ramp": _band(2, 0, 1), "lands": _band(36, 36, 38)}
    cuts = cut_candidates([kodama, mind_stone], budgets=budgets, focus=CutFocus())
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


def test_a_premium_card_is_never_a_band_trim():
    # Ramp over by 2 under a tribal commander: the lane's two dorks trim last,
    # which would leave Sol Ring (rank 1) as the first non-lane ramp to trim.
    # A premium card is never cut to meet a band; the dorks are (lane last).
    classes = [
        _real_cc("Sol Ring", "spine", roles=["ramp"], edhrec_rank=1),
        _cc(
            "Dork A", "spine", roles=["ramp"], served=("Dinosaurs",), edhrec_rank=20000
        ),
        _cc(
            "Dork B", "spine", roles=["ramp"], served=("Dinosaurs",), edhrec_rank=30000
        ),
    ]
    budgets = {"ramp": _band(3, 0, 1)}
    cuts = cut_candidates(
        classes,
        budgets=budgets,
        focus=CutFocus(viable={"Dinosaurs"}, commander_cards={"Dork A", "Dork B"}),
    )
    assert [c.name for r, c in cuts if r == "over:ramp"] == ["Dork B", "Dork A"]
    # Where play-rate means nothing (a 60-card or limited deck) the rank is no
    # shield. (``playrate=False`` alone — a one-on-one game, where play-rate
    # may not condemn — keeps it: a shield is a quality read.)
    cuts = cut_candidates(
        classes,
        budgets=budgets,
        focus=CutFocus(viable={"Dinosaurs"}, commander_cards={"Dork A", "Dork B"}),
        playrate=False,
    )
    assert [c.name for r, c in cuts if r == "over:ramp"] == ["Dork B", "Dork A"]
    cuts = cut_candidates(
        classes,
        budgets=budgets,
        focus=CutFocus(viable={"Dinosaurs"}, commander_cards={"Dork A", "Dork B"}),
        playrate_meaningful=False,
    )
    assert next(c.name for r, c in cuts if r == "over:ramp") == "Sol Ring"


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
    # The trim's add is no ramp (a trim's add is no member of the row it trims).
    add = {
        "name": "Better Statue",
        "type_line": "Artifact",
        "oracle_text": "",
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


def test_role_over_trims_the_card_serving_no_theme_before_the_plans_own():
    """Ramp over by 1 in a lands deck: Oracle of Mul Daya serves the Landfall
    main, a plain rock none, and the rock is the more played. The trim takes the
    card serving the fewest of the deck's themes first (Desert Bloom cut Oracle
    as its least-played ramp, 2026-11-01), not the least played."""
    classes = [
        _cc(
            "Lands Oracle",
            "spine",
            roles=["ramp"],
            served=("Landfall",),
            cmc=4.0,
            edhrec_rank=1000,
        ),
        _cc("Plain Rock", "spine", roles=["ramp"], cmc=2.0, edhrec_rank=500),
    ]
    budgets = {"ramp": _band(11, 8, 10)}  # over by 1
    issue = {"kind": "role_over", "role": "ramp", "severity": 1, "message": "ramp over"}
    add = {
        "name": "Theme Card",
        "type_line": "Creature — Bear",
        "oracle_text": "",
        "cmc": 2.0,
        "prices": {"usd": "1.00"},
        "color_identity": [],
    }
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
            budgets=budgets,
            focus_result=_focus(
                viable=[{"label": "Landfall", "tier": "main", "depth": 20, "cards": []}]
            ),
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
    assert [s["cut"]["name"] for s in out["swaps"]] == ["Plain Rock"]


def test_role_over_trim_drains_the_whole_excess_and_no_more():
    """A row over its band by two trims two cards, the two least played, and
    stops there with swaps to spare: one trim per issue left Animated Army's
    ramp 13 over (26 against 10-12), six of the cards past the first trim
    guide cuts (25 precons, 2026-10-25)."""
    classes = [
        _cc("Rock A", "spine", roles=["ramp"], cmc=2.0, edhrec_rank=20000),
        _cc("Rock B", "spine", roles=["ramp"], cmc=2.0, edhrec_rank=30000),
        _cc("Rock C", "spine", roles=["ramp"], cmc=2.0, edhrec_rank=9000),
    ]
    budgets = {"ramp": _band(12, 8, 10)}  # over by 2
    issue = {"kind": "role_over", "role": "ramp", "severity": 1, "message": "ramp over"}
    adds = [
        {
            "name": f"Theme Card {i}",
            "type_line": "Creature — Bear",
            "oracle_text": "",
            "cmc": 2.0,
            "prices": {"usd": "1.00"},
            "color_identity": [],
        }
        for i in range(4)
    ]
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
            budgets=budgets,
            focus_result=_focus(viable=[{"label": "Main", "depth": 20, "cards": []}]),
            deck_signals=[],
            search_fn=lambda **_: adds,
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=5,
            top_heavy=False,
        ),
    )
    assert [s["cut"]["name"] for s in out["swaps"]] == ["Rock B", "Rock A"]


@pytest.mark.parametrize(
    ("served", "add"),
    [
        ((), "Four Drop"),  # off every main: the slot moves onto it, one band up
        (("Main",), "Two Drop"),  # on the main already: the cut's own band
    ],
)
def test_a_trims_add_keeps_its_cuts_mana_value_band(served, add):
    """Fynn v6 trimmed one-mana bites for Wurmcoil Engine and Hornet Queen: the
    trim's add came first, whatever it cost. Now the cut comes first and the add
    keeps its band (``over_band``), as an upgrade's does."""
    classes = [
        _cc("Cheap Bite", "spine", roles=["interaction"], served=served, cmc=1.0),
    ]
    budgets = {"interaction": _band(11, 8, 10)}  # over by 1
    issue = {
        "kind": "role_over",
        "role": "interaction",
        "severity": 1,
        "message": "interaction over",
    }

    def candidate(name, cmc, rank):
        return {
            "name": name,
            "type_line": "Creature — Bear",
            "oracle_text": "",
            "cmc": cmc,
            "edhrec_rank": rank,
            "prices": {"usd": "1.00"},
            "color_identity": [],
        }

    adds = [
        candidate("Seven Drop", 7.0, 10),
        candidate("Four Drop", 4.0, 20),
        candidate("Two Drop", 2.0, 30),
    ]
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        SwapContext(
            budgets=budgets,
            focus_result={
                **_focus(viable=[{"label": "Main", "depth": 20, "cards": []}]),
                "mains": ["Main"],
            },
            deck_signals=[],
            search_fn=lambda **_: adds,
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
        ),
    )
    assert [(s["cut"]["name"], s["add"]["name"]) for s in out["swaps"]] == [
        ("Cheap Bite", add)
    ]


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


def test_a_combo_piece_the_proposals_own_add_completes_is_never_cut():
    # Sanguine Bond completes Exquisite Blood (backlog (s), Blood Rites): once
    # the near-miss add is taken, the dead-weight drain must not cut the piece
    # the add needs, even as the least-played filler.
    sig = _sig_of("proliferate_matters")
    label = spec_for(sig).label
    classes = [
        _real_cc("Exquisite Blood", "filler", edhrec_rank=9000),
        _cc("Junk A", "filler", cmc=4.0),
        _cc("Junk B", "filler", cmc=3.0),
        _cc("Theme Engine", "engine", served=[label]),
    ]
    focus_r = _focus(viable=[{"label": label, "depth": 20, "cards": []}])
    sourcing = Sourcing(focus_r, [sig], {})
    issues = [
        sourcing.issue(
            "near_miss_combo",
            severity=9,
            message="Sanguine Bond completes Exquisite Blood",
            label="Sanguine Bond",
            terminal=True,
            relies_on=("Exquisite Blood",),
        ),
        sourcing.issue("dead_weight", severity=7, count=3, message="dead weight"),
    ]
    payoffs = [
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
    bond = {**test_card("Sanguine Bond"), "prices": {"usd": "1.00"}}
    out = propose_swaps(
        classes,
        issues,
        SwapContext(
            budgets={},
            focus_result=focus_r,
            deck_signals=[sig],
            search_fn=lambda **kw: [bond] if kw.get("name") else payoffs,
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=10,
            top_heavy=False,
        ),
    )
    assert "Sanguine Bond" in {s["add"]["name"] for s in out["swaps"]}
    assert "Exquisite Blood" not in {s["cut"]["name"] for s in out["swaps"]}


def _sig_of(key):
    return Signal(
        key=key, scope="you", subject="", text="", source="X", confidence="high"
    )


def _near_miss_run(missing: list[str], adds: dict[str, dict], max_swaps: int = 10):
    """Near-miss issues, one per card in ``missing``, each completing Exquisite
    Blood, over a deck of filler whose top end is a four-drop; ``adds`` holds
    the record each name resolves to. The adds taken, in order."""
    sig = _sig_of("proliferate_matters")
    classes = [
        _real_cc("Exquisite Blood", "engine", edhrec_rank=900),
        *(_cc(f"Junk {i}", "filler", cmc=4.0) for i in range(5)),
    ]
    focus_r = _focus(viable=[{"label": spec_for(sig).label, "depth": 20, "cards": []}])
    sourcing = Sourcing(focus_r, [sig], {})
    issues = [
        sourcing.issue(
            "near_miss_combo",
            severity=9,
            message=f"{name} completes Exquisite Blood",
            label=name,
            terminal=True,
            relies_on=("Exquisite Blood",),
        )
        for name in missing
    ]
    out = propose_swaps(
        classes,
        issues,
        SwapContext(
            budgets={},
            focus_result=focus_r,
            deck_signals=[sig],
            search_fn=lambda **kw: [adds[kw["name"]]] if kw.get("name") in adds else [],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=max_swaps,
            top_heavy=False,
        ),
    )
    return [s["add"]["name"] for s in out["swaps"]]


def test_a_combo_piece_takes_at_most_two_partners():
    """Blood Rites took five near-miss adds, every one a partner for Exquisite
    Blood (its guides add two: Vito and Sanguine Bond). Past
    ``_COMBO_PIECE_ADDS`` on one deck card, the next line on it is the same slot
    again and is passed over."""
    adds = {
        "Sanguine Bond": {**test_card("Sanguine Bond"), "prices": {"usd": "1.00"}},
        "Vito, Thorn of the Dusk Rose": {
            **test_card("Vito, Thorn of the Dusk Rose"),
            "prices": {"usd": "1.00"},
        },
        "Marauding Blight-Priest": {
            **test_card("Marauding Blight-Priest"),
            "prices": {"usd": "1.00"},
        },
    }
    assert _near_miss_run(list(adds), adds) == [
        "Sanguine Bond",
        "Vito, Thorn of the Dusk Rose",
    ]


def test_a_combo_piece_above_the_decks_top_end_is_no_slot():
    """Mardu Surge, a token aggro deck topping out at seven, was offered
    Blightsteel Colossus (twelve) for Blade of Selves. A card asked for by name
    that costs more than anything the deck runs is passed over; the line's
    other partner at four mana is taken."""
    adds = {
        "Twelve Drop": {
            "name": "Twelve Drop",
            "type_line": "Artifact Creature — Golem",
            "oracle_text": "",
            "cmc": 12.0,
            "prices": {"usd": "1.00"},
            "color_identity": [],
        },
        "Sanguine Bond": {**test_card("Sanguine Bond"), "prices": {"usd": "1.00"}},
    }
    assert _near_miss_run(["Twelve Drop", "Sanguine Bond"], adds) == ["Sanguine Bond"]


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


def test_candidate_pool_is_paged_by_playrate_where_it_means_something():
    """The search page is the pool the ranking sees: by play-rate in the
    Commander family, by mana value where play-rate means nothing."""
    sig = _prolif_sig()
    label = spec_for(sig).label
    classes = [_cc("Filler A", "filler", cmc=3.0)]
    issue = {"kind": "dead_weight", "severity": 7, "count": 1, "message": "x"}
    seen: list[str] = []

    def search(**kw):
        seen.append(kw["sort"])
        return [
            {
                "name": "Staple",
                "type_line": "Creature",
                "oracle_text": "Proliferate.",
                "cmc": 3.0,
                "prices": {"usd": "1.00"},
                "color_identity": [],
                "edhrec_rank": 50,
            }
        ]

    def ctx(*, playrate):
        return SwapContext(
            budgets={},
            focus_result=_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
            deck_signals=[sig],
            search_fn=search,
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
            playrate=playrate,
        )

    _swaps_for_issue_dicts(classes, [issue], ctx(playrate=True))
    assert seen[-1] == "edhrec-asc"
    _swaps_for_issue_dicts(classes, [issue], ctx(playrate=False))
    assert seen[-1] == "cmc-asc"


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


@pytest.mark.parametrize(
    ("name", "reliable"),
    [
        # Genuine, unconditional ramp → sourced.
        ("Arcane Signet", True),
        # Every mana / Treasure ability gated on a condition (CR 602.5) → not
        # sourced: metalcraft, a Dragon, formidable, oil counters, max speed, an
        # opponent's turn, a creature that fought (a residue phase parks).
        ("Mox Opal", False),
        ("Mox Jasper", False),
        ("Circle of Elders", False),
        ("Tablet of Compleation", False),
        ("Endrider Catalyzer", False),
        ("Lavinia, Foil to Conspiracy", False),
        ("Boxing Ring", False),
        # No activation restriction: per its ruling Mox Amber can be activated with
        # no legendary permanent (it then adds no mana).
        ("Mox Amber", True),
        # An ungated sibling ({T}: Add {G}) makes the card reliable ramp.
        ("Fanatic of Rhonas", True),
        ("Whisperer of the Wilds", True),
        # The legendary-sorcery cast restriction gates no mana ability.
        ("Kamahl's Druidic Vow", True),
        # An Offer You Can't Refuse: the Treasures (and their mana) go to the opponent.
        ("An Offer You Can't Refuse", False),
    ],
)
def test_reliable_ramp_excludes_conditional_and_opponent_mana(name, reliable):
    """The tuner sources only ramp it can rely on: genuine producers that aren't gated
    on a condition, and never mana an opponent receives."""
    assert is_reliable_ramp(test_card(name)) is reliable


def test_cut_candidates_null_rank_low_value_is_medium_aware():
    # ADR-0040 §4 (task #99): a null edhrec_rank on a digital deck is no-data
    # (EDHREC has no Arena population), so it can't push an engine card into
    # the low_value cut queue; on paper it stays fringe-evidence and does.
    classes = [_cc("Alchemy Only", "engine", served=["Tokens"], edhrec_rank=None)]
    kw = {"budgets": {}, "focus": CutFocus()}
    paper = cut_candidates(classes, medium="paper", **kw)
    digital = cut_candidates(classes, medium="digital", **kw)
    assert ("low_value", "Alchemy Only") in [(r, c.name) for r, c in paper]
    assert [(r, c.name) for r, c in digital] == []


# ── ADR-0040 companion: FOCUSED role-fix adds prefer an on-avenue candidate ──


def _on_avenue_draw(rank):
    """A real draw spell that proliferates (ADR-0056): the proliferate serve
    reads the card's idents, which a synthetic record has none of."""
    return {
        **test_card("Tezzeret's Gambit"),
        "prices": {"usd": "2.00"},
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
    on_avenue = _on_avenue_draw(rank=2000)
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
    assert out["swaps"][0]["add"]["name"] == "Tezzeret's Gambit"
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
    kw = {"budgets": {}, "focus": CutFocus()}
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


# ── 2026-10-18: the commander's lane in the cut ranking ───────────────────────


def _polymorph_ctx(budgets, add, *, viable, lane_cards):
    return SwapContext(
        budgets=budgets,
        focus_result={
            **_focus(
                viable=[{"label": lbl, "depth": 20, "cards": []} for lbl in viable]
            ),
            "commander_lane_cards": list(lane_cards),
        },
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


_WIPE_ADD = {
    "name": "Another Wipe",
    "type_line": "Sorcery",
    "oracle_text": "Destroy all creatures.",
    "cmc": 4.0,
    "prices": {"usd": "1.00"},
    "color_identity": ["W"],
}


def test_over_band_trim_cuts_the_commanders_lane_last():
    # Board wipes over by one under a polymorph commander: a wipe that is itself
    # a polymorph piece (emits the commander's ident; best play-rate too) must
    # not be the trim; the fringe wipe off the lane is.
    held = "Cheat into play"
    classes = [
        _cc("Sweeper Polymorph", "spine", roles=["board_wipe"], served=(held,)),
        _cc(
            "Fringe Wipe",
            "spine",
            roles=["board_wipe"],
            served=("Combat",),
            edhrec_rank=2000,
        ),
    ]
    budgets = {"board_wipe": _band(4, 2, 3)}
    issue = {
        "kind": "role_over",
        "role": "board_wipe",
        "severity": 1,
        "message": "over",
    }
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        _polymorph_ctx(
            budgets, _WIPE_ADD, viable=[held], lane_cards=["Sweeper Polymorph"]
        ),
    )
    assert out["swaps"][0]["cut"]["name"] == "Fringe Wipe"


def test_over_band_trim_prefers_a_card_feeding_no_viable_avenue():
    # Equal play-rate: a wipe feeding a FED avenue only ("Combat" is not viable)
    # trims before one feeding a viable sub-theme.
    classes = [
        _cc(
            "On Theme",
            "spine",
            roles=["board_wipe"],
            served=("Go wide",),
            edhrec_rank=1000,
        ),
        _cc(
            "Off Theme",
            "spine",
            roles=["board_wipe"],
            served=("Combat",),
            edhrec_rank=1000,
        ),
    ]
    budgets = {"board_wipe": _band(4, 2, 3)}
    issue = {
        "kind": "role_over",
        "role": "board_wipe",
        "severity": 1,
        "message": "over",
    }
    out = _swaps_for_issue_dicts(
        classes,
        [issue],
        _polymorph_ctx(budgets, _WIPE_ADD, viable=["Go wide"], lane_cards=[]),
    )
    assert out["swaps"][0]["cut"]["name"] == "Off Theme"


def test_low_value_pass_skips_the_commanders_lane():
    held = "Cheat into play"
    classes = [
        _cc("Identity Echo", "engine", served=(held,), edhrec_rank=None),
        _cc("Fringe Beater", "engine", served=("Combat",), edhrec_rank=None),
    ]
    cuts = cut_candidates(
        classes,
        budgets={},
        focus=CutFocus(viable={held}, commander_cards=["Identity Echo"]),
    )
    assert [(reason, c.name) for reason, c in cuts] == [("low_value", "Fringe Beater")]


def test_fed_only_filler_says_why():
    assert (
        _cut_why("filler", _cc("Plain", "filler")) == "serves no avenue here (filler)"
    )
    assert _cut_why("filler", _cc("Legend", "filler", served=("Historic",))) == (
        "feeds only avenues nobody built toward (fed)"
    )


def test_a_deep_lane_is_the_last_cut_tier_in_the_focus_reads_order():
    """Blood Rites: forty-three Vampire carers and nothing else to cut. The lane's
    upgrade slots are the focus read's ``lane_upgrade_cards`` (its least-played
    half, plain feeders first — ``test_tuner_focus``), cut last and in that
    order; a protected card is skipped."""
    lane = [
        _cc(f"Vamp {i}", "engine", served=("Vampires",), edhrec_rank=1000 * (i + 1))
        for i in range(12)
    ]
    order = [f"Vamp {i}" for i in (9, 11, 10)]
    cuts = cut_candidates(
        lane,
        budgets={},
        focus=CutFocus(
            viable={"Vampires"},
            commander_cards={c.name for c in lane},
            lane_upgrade_cards=order,
        ),
        protected={"Vamp 11"},
    )
    assert [(r, c.name) for r, c in cuts] == [
        ("lane_upgrade", "Vamp 9"),
        ("lane_upgrade", "Vamp 10"),
    ]
    assert _cut_why("lane_upgrade").startswith("a lane feeder few decks play")


def test_popular_off_theme_cards_are_the_last_upgrade_tier():
    """A popular card serving none of the deck's themes (the focus read's
    ``popular_upgrade_cards``) is an upgrade slot taken after every other: after
    the off-lane fringe and the deep lane's half, in the focus read's order."""
    lane = [
        _cc(f"Vamp {i}", "engine", served=("Vampires",), edhrec_rank=9000 + i)
        for i in range(2)
    ]
    fringe = _cc("Fringe Kill", "spine", roles=["interaction"], edhrec_rank=4000)
    popular = [
        _cc("Popular Kill", "spine", roles=["interaction"], edhrec_rank=900),
        _cc("Popular Draw", "spine", roles=["card_draw"], edhrec_rank=400),
    ]
    cuts = cut_candidates(
        [*popular, fringe, *lane],
        budgets={},
        focus=CutFocus(
            viable={"Vampires"},
            commander_cards={c.name for c in lane},
            upgrade_cards={"Fringe Kill"},
            lane_upgrade_cards=("Vamp 1",),
            popular_upgrade_cards=("Popular Kill", "Popular Draw"),
        ),
    )
    assert [(r, c.name) for r, c in cuts] == [
        ("upgrade", "Fringe Kill"),
        ("lane_upgrade", "Vamp 1"),
        ("popular_upgrade", "Popular Kill"),
        ("popular_upgrade", "Popular Draw"),
    ]
    assert "none of the deck's themes" in _cut_why("popular_upgrade")


def test_a_band_that_is_the_commanders_lane_is_no_cut_pool():
    classes = [
        _cc(f"Rock {i}", "spine", roles=["ramp"], cmc=2.0, edhrec_rank=5000)
        for i in range(3)
    ]
    budgets = {"ramp": {**_band(3, 0, 1), "lane_row": True}}
    cuts = cut_candidates(classes, budgets=budgets, focus=CutFocus())
    assert cuts == []


def test_only_a_spine_fill_or_closer_takes_a_lane_slot():
    """Twelve lane cards and nothing else to cut: a protection shortfall (a
    Spine fill) trades a lane card; a curve fix (an engine add) does not."""
    lane = [
        _cc(
            f"Vamp {i}",
            "engine",
            served=("Vampires",),
            cmc=3.0,
            edhrec_rank=1000 * (i + 1),
        )
        for i in range(12)
    ]
    add = {
        "name": "Shield",
        "type_line": "Instant",
        "oracle_text": "Creatures you control gain hexproof and indestructible until end of turn.",
        "cmc": 2.0,
        "prices": {"usd": "1.00"},
        "color_identity": [],
    }

    def ctx():
        return SwapContext(
            budgets={},
            focus_result={
                **_focus(viable=[{"label": "Vampires", "depth": 20, "cards": []}]),
                "commander_lane_cards": [c.name for c in lane],
                "lane_upgrade_cards": [c.name for c in lane[6:]],
            },
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

    short = {"kind": "protection_short", "severity": 5, "message": "0 protection"}
    out = _swaps_for_issue_dicts(lane, [short], ctx())
    assert len(out["swaps"]) == 1
    assert out["swaps"][0]["cut"]["name"].startswith("Vamp")
    curve = {
        "kind": "efficiency",
        "subkind": "thin top-end",
        "severity": 3,
        "message": "curve",
    }
    assert _swaps_for_issue_dicts(lane, [curve], ctx())["swaps"] == []


def test_spine_fill_ranks_by_playrate_within_a_mana_value_band():
    """A Spine fill is the most-played card in the cheapest band that does the
    job, not the cheapest mana value outright: a {0} oddity (Welding Jar as the
    protection add, Engineered Explosives as the wipe — 25-precon audit) no longer
    beats a three-mana staple where play-rate means something. Where it means
    nothing (a 60-card deck) exact mana value still ranks first."""
    sig, label, classes, budgets, issue, _off, _on = _role_fix_scenario()
    zero_oddity = _off_avenue_draw("Zero Jar", cmc=0.0, rank=20000)
    played_three = _off_avenue_draw("Played Three", cmc=3.0, rank=100)
    six_drop = _off_avenue_draw("Played Six", cmc=6.0, rank=10)

    def run(*, playrate: bool):
        out = _swaps_for_issue_dicts(
            classes,
            [issue],
            SwapContext(
                budgets=budgets,
                focus_result=_focus(
                    viable=[{"label": label, "depth": 20, "cards": []}]
                ),
                deck_signals=[sig],
                search_fn=lambda **_: [zero_oddity, played_three, six_drop],
                identity="",
                fmt="commander",
                paper_only=True,
                owned={},
                budget=50.0,
                max_swaps=1,
                top_heavy=False,
                playrate=playrate,
            ),
        )
        return out["swaps"][0]["add"]["name"]

    assert run(playrate=True) == "Played Three"  # the band's most-played, not MV 6
    assert run(playrate=False) == "Zero Jar"
    # An X cost is banded at what it is cast for, not its printed mana value: a
    # {X}{W}{W} wipe (mana value 2) at rank 10 is a mid-band card, so the cheap
    # band's most-played card still wins it.
    x_wipe = {**_off_avenue_draw("X Coup", cmc=2.0, rank=10), "mana_cost": "{X}{W}{W}"}
    six_drop.update(x_wipe)  # reuse the slot: the pool is read by name
    assert run(playrate=True) == "Played Three"


# ── Upgrades: an off-lane card few decks play, traded for one doing its job ──


def _upgrade_ctx(classes, pool, *, focus_extra=None, budget=50.0):
    return SwapContext(
        budgets={},
        focus_result={
            **_focus(),
            "upgrade_cards": [c.name for c in classes],
            **(focus_extra or {}),
        },
        deck_signals=[],
        search_fn=lambda **_: pool,
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=budget,
        max_swaps=5,
        top_heavy=False,
    )


def _played(name, rank):
    return {**test_card(name), "edhrec_rank": rank, "prices": {"usd": "1.00"}}


def test_an_upgrade_does_the_cut_cards_job_and_more_decks_play_it():
    """Murder off every lane, at rank 8000, is traded for the most-played card in
    the pool doing its job (removal); Wrath of God is played more, but its job is
    a sweep, so it is never Murder's upgrade (25-precon audit, 2026-10-19)."""
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)
    pool = [_played("Wrath of God", 5), _played("Swords to Plowshares", 10)]
    out = _swaps_for_issue_dicts(
        [murder],
        [{"kind": "upgrade", "severity": 1, "count": 1}],
        _upgrade_ctx([murder], pool),
    )
    assert [(s["cut"]["name"], s["add"]["name"]) for s in out["swaps"]] == [
        ("Murder", "Swords to Plowshares")
    ]
    assert out["swaps"][0]["reason"] == (
        "upgrade interaction: Swords to Plowshares — more decks play it"
    )
    assert out["swaps"][0]["cut"]["why"].startswith("off the deck's lanes")


def test_a_job_upgrade_at_the_same_mana_never_reads_worse_at_the_job():
    """Golgari Signet at rank 8000 is not traded for Fellwar Stone at rank 10:
    the ramp read scores the Stone's borrowed colors below a Signet's own at
    the same two mana (Death Toll made that swap, 2026-11-02). Arcane Signet,
    an equal read played more, is its upgrade. A cheaper card is not held to
    the read (Duplicant for Meteor Golem, the test above)."""
    signet = _real_cc("Golgari Signet", "spine", roles=["ramp"], edhrec_rank=8000)
    # Wayfarer's Bauble is printed at one mana, but the ramp read's deploy cost
    # counts its activation (three): no cheaper card, and a worse read.
    pool = [
        _played("Fellwar Stone", 10),
        _played("Wayfarer's Bauble", 15),
        _played("Arcane Signet", 20),
    ]
    out = _swaps_for_issue_dicts(
        [signet],
        [{"kind": "upgrade", "severity": 1, "count": 1}],
        _upgrade_ctx([signet], pool),
    )
    assert [(s["cut"]["name"], s["add"]["name"]) for s in out["swaps"]] == [
        ("Golgari Signet", "Arcane Signet")
    ]
    # Another two-color Talisman is the same rock in another coat: no upgrade
    # of Talisman of Curiosity in a Temur deck however many more decks play it
    # (Living Energy, 2026-11-02); Arcane Signet's any color is more. Pongify
    # is Rapid Hybridization in another coat too. A one-shot mana source
    # never upgrades a repeatable one: Lotus Petal for Wild Growth.
    curiosity = _real_cc(
        "Talisman of Curiosity", "spine", roles=["ramp"], edhrec_rank=8000
    )
    assert not _upgrades(_played("Talisman of Creativity", 10), curiosity, "ramp")
    assert _upgrades(_played("Arcane Signet", 10), curiosity, "ramp")
    hybrid = _real_cc(
        "Rapid Hybridization", "spine", roles=["interaction"], edhrec_rank=8000
    )
    assert not _upgrades(_played("Pongify", 10), hybrid, "interaction")
    growth = _real_cc("Wild Growth", "spine", roles=["ramp"], edhrec_rank=8000)
    assert not _upgrades(_played("Lotus Petal", 10), growth, "ramp")
    # A wipe that sweeps no creatures never upgrades one that does: Vandalblast
    # for Winds of Rath (Blame Game, 2026-11-02).
    winds = _real_cc("Winds of Rath", "spine", roles=["board_wipe"], edhrec_rank=8000)
    assert not _upgrades(_played("Vandalblast", 10), winds, "board_wipe")
    assert _upgrades(_played("Blasphemous Act", 10), winds, "board_wipe")
    millikin = _real_cc("Millikin", "spine", roles=["ramp"], edhrec_rank=8000)
    assert not _upgrades(_played("Simian Spirit Guide", 10), millikin, "ramp")
    assert not _upgrades(_played("Dark Ritual", 10), millikin, "ramp")
    retriever = _real_cc("Relic Retriever", "spine", roles=["ramp"], edhrec_rank=8000)
    assert not _upgrades(_played("Simian Spirit Guide", 10), retriever, "ramp")


def test_a_theme_slot_upgraded_on_play_rate_stays_within_a_band_downward():
    """Garruk, Cursed Huntsman's six-mana slot is not Chatter of the Squirrel's
    one-mana one however many more decks play the cantrip (Squirreled Away,
    2026-11-02); Doubling Season, one band down and played more, is its
    upgrade. The card-quality read decides nothing here: it rates Garruk
    below the cantrip."""
    garruk = _real_cc("Garruk, Cursed Huntsman", "engine", edhrec_rank=8000)
    assert not _upgrades(_played("Chatter of the Squirrel", 10), garruk, None)
    assert _upgrades(_played("Doubling Season", 10), garruk, None)


def test_a_job_card_on_the_theme_page_keeps_its_job_read_across_bands():
    """Niv-Mizzet, Parun draws; on the main theme page Thrill of Possibility,
    two bands cheaper and a far weaker draw by the read, is no upgrade of it
    (Quick Draw, 2026-11-02). The cheaper exemption holds within one band:
    Duplicant for Meteor Golem (the test above)."""
    parun = _real_cc(
        "Niv-Mizzet, Parun", "spine", roles=["card_draw"], edhrec_rank=8000
    )
    thrill = _played("Thrill of Possibility", 10)
    assert not _upgrades(thrill, parun, None)
    assert not _upgrades(thrill, parun, "card_draw")


def test_an_upgrade_does_the_job_by_its_read_and_more_decks_play_it():
    """Removal has a card read (``job_quality``): Animate Dead counts as
    interaction for the role, but its "-1/-0" on the creature it returns
    removes nothing, so the read scores it None and it is no removal upgrade
    however many decks play it. A removal spell played more than the cut is
    one; one played less is not — "better" stays play-rate's (ADR-0060)."""
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)

    def upgrade(pool):
        return _swaps_for_issue_dicts(
            [murder],
            [{"kind": "upgrade", "severity": 1, "count": 1}],
            _upgrade_ctx([murder], pool),
        )["swaps"]

    assert upgrade([_played("Animate Dead", 10)]) == []
    assert upgrade([_played("Swords to Plowshares", 9000)]) == []
    assert [
        s["add"]["name"] for s in upgrade([_played("Swords to Plowshares", 100)])
    ] == ["Swords to Plowshares"]


def test_the_main_theme_upgrades_to_a_better_played_card():
    """A card with no template job is upgraded on the main theme, where no card
    read applies: more decks must play the add."""
    clunker = _real_cc("Murder", "engine", edhrec_rank=8000)
    assert not _upgrades(_played("Doom Blade", 9000), clunker, None)
    assert _upgrades(_played("Doom Blade", 100), clunker, None)


def test_an_off_theme_card_moves_onto_the_main_theme_whatever_its_play_rate():
    """A card serving none of the main avenues (``off_theme``), upgraded on the
    main theme: moving its slot there is the upgrade, so the add need not be
    more played than the cut, and it may cost one band more, as a job upgrade
    may. Living Energy's sub-theme Whirler Rogue (rank 2245) found no Energy
    card played more; the guides add Gonti's Aether Heart and Aether Refinery
    (25 precons, 2026-10-25: seven guide adds and seven guide cuts more). A job
    upgrade keeps both gates."""
    clunker = _real_cc("Murder", "engine", edhrec_rank=8000)
    assert _upgrades(_played("Doom Blade", 9000), clunker, None, off_theme=True)
    pyroclasm = _real_cc("Pyroclasm", "spine", edhrec_rank=9000)
    assert _upgrades(_played("Wrath of God", 50), pyroclasm, None, off_theme=True)
    assert not _upgrades(
        _played("Blasphemous Act", 20), pyroclasm, None, off_theme=True
    )
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)
    assert not _upgrades(
        _played("Swords to Plowshares", 9000), murder, "interaction", off_theme=True
    )


def test_the_swap_engine_reads_off_theme_against_the_main_avenues():
    """``propose_swaps`` passes ``off_theme`` for a cut serving none of the
    focus read's mains: a slot-holder on a sub moves onto the main theme for a
    less-played payoff, one already on the main theme does not."""
    sig = _sig_of("proliferate_matters")
    label = spec_for(sig).label
    adds = [
        {
            "name": "Payoff 0",
            "type_line": "Creature",
            "oracle_text": "Proliferate.",
            "cmc": 2.0,
            "edhrec_rank": 9000,
            "prices": {"usd": "1.00"},
            "color_identity": [],
        }
    ]

    def upgrade(served):
        cut = _cc("Sub Card", "engine", served=served, edhrec_rank=8000)
        ctx = SwapContext(
            budgets={},
            focus_result={
                **_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
                "mains": [label],
                "upgrade_cards": [cut.name],
            },
            deck_signals=[sig],
            search_fn=lambda **_: adds,
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=5,
            top_heavy=False,
        )
        swaps = _swaps_for_issue_dicts(
            [cut], [{"kind": "upgrade", "severity": 1, "count": 1}], ctx
        )["swaps"]
        return [s["add"]["name"] for s in swaps]

    assert upgrade(("Some sub",)) == ["Payoff 0"]
    assert upgrade((label,)) == []


def test_a_job_read_gates_out_a_card_that_does_not_do_the_job():
    """Card draw has a read: a looter nets no card (Faithless Looting reads
    None), so it is no draw upgrade however many decks play it; Night's
    Whisper, which nets two, is."""
    divination = _real_cc("Divination", "spine", roles=["card_draw"], edhrec_rank=8000)
    assert not _upgrades(_played("Faithless Looting", 10), divination, "card_draw")
    assert _upgrades(_played("Night's Whisper", 100), divination, "card_draw")


def test_an_ordering_read_blends_with_play_rate_and_quality():
    """An ordering job's candidates take the read's percentile plus play-rate's
    plus the card's quality read's (``card_quality``, ADR-0063), each weighing
    the same. On the job read and play-rate alone these three tie (each leads
    one order and trails the other by as much); the quality read breaks the tie
    — Swiftfoot Boots (0.03, the permanent read) over Flawless Maneuver (0.0)
    over Heroic Intervention (-0.4, the spell read). A job with no read blends
    nothing."""
    cards = [
        _played("Swiftfoot Boots", 30),  # protection read 0.89
        _played("Heroic Intervention", 300),  # protection read 1.11
        _played("Flawless Maneuver", 3000),  # protection read 1.29
    ]
    mix = _blended_percentiles(cards, "protection")
    assert (
        mix["Swiftfoot Boots"] > mix["Flawless Maneuver"] > mix["Heroic Intervention"]
    )
    assert _blended_percentiles(cards, None) == {}


def test_an_upgrade_reads_its_jobs_whole_match_set():
    """A job with a card read searches the role's whole match set, not a
    play-rate page: an upgrade that sits past the 600 more-played matches doing
    no job of the cut's is still found."""
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)
    fillers = [
        {
            "name": f"Filler Beast {i}",
            "type_line": "Creature",
            "cmc": 2.0,
            "edhrec_rank": i + 1,
            "prices": {"usd": "1.00"},
        }
        for i in range(700)
    ]
    out = _swaps_for_issue_dicts(
        [murder],
        [{"kind": "upgrade", "severity": 1, "count": 1}],
        _upgrade_ctx([murder], [*fillers, _played("Swords to Plowshares", 701)]),
    )
    assert [s["add"]["name"] for s in out["swaps"]] == ["Swords to Plowshares"]


def test_cards_that_tie_share_a_blend_whatever_order_they_come_in():
    """A percentile is the share of the cards strictly below, so two cards the
    read scores alike and as many decks play (Swords to Plowshares and Path to
    Exile) share the job-read and play-rate terms; only the quality read parts
    them (Path's land search is one more effect per cast), and the input order —
    the search's, or the synergy ranking's — moves no card's blend."""
    cards = [
        _played("Murder", 900),
        _played("Swords to Plowshares", 40),
        _played("Path to Exile", 40),
    ]
    mix = _blended_percentiles(cards, "interaction")
    assert mix["Path to Exile"] > mix["Swords to Plowshares"] > mix["Murder"]
    assert _blended_percentiles(cards[::-1], "interaction") == mix


def test_a_job_upgrade_costs_at_most_one_mana_value_band_more():
    """A two-mana sweep may be upgraded to a four-mana one (the next band), never
    to a top-band one however played (Blasphemous Act, mana value 9); a cheap
    card on the main theme (no job) keeps its band (2026-10-24: one band of room
    matched more guide adds for job upgrades, fewer for theme upgrades)."""
    pyroclasm = _real_cc("Pyroclasm", "spine", roles=["board_wipe"], edhrec_rank=9000)
    assert _upgrades(_played("Toxic Deluge", 30), pyroclasm, "board_wipe")
    assert _upgrades(_played("Wrath of God", 50), pyroclasm, "board_wipe")
    assert not _upgrades(_played("Blasphemous Act", 20), pyroclasm, "board_wipe")
    assert not _upgrades(_played("Wrath of God", 50), pyroclasm, None)
    assert _upgrades(_played("Toxic Deluge", 30), pyroclasm, None)


def _serving(monkeypatch, on_theme):
    """``rank_candidates`` faked so the cards named in ``on_theme`` serve the
    deck's one viable avenue ("Artifacts") and no card has synergy."""
    from mtg_utils._tuner import swaps as swaps_mod

    def fake_rank(cards, **_kw):
        return [
            {
                "card": c,
                "score": {
                    "synergy_score": 0.0,
                    "served": ["Artifacts"] if c["name"] in on_theme else [],
                },
            }
            for c in cards
        ]

    monkeypatch.setattr(swaps_mod, "rank_candidates", fake_rank)


_ARTIFACTS = {"viable_avenues": [{"label": "Artifacts", "depth": 20, "cards": []}]}


def test_theme_fit_breaks_a_near_tie_on_the_job_read(monkeypatch):
    """Ramp's read breaks a near tie by theme fit (``JobRead.theme_ties``, Dan's
    call): Talisman of Dominance, which serves the deck's avenue, reads as well
    as Arcane Signet (0.7 each) and goes before it, though twenty times fewer
    decks play it. Commander's Sphere also serves the avenue but reads far
    worse (0.27), so the staple keeps the slot."""
    manalith = _real_cc("Manalith", "spine", roles=["ramp"], edhrec_rank=9000)

    def upgrade(pool, on_theme):
        _serving(monkeypatch, on_theme)
        return [
            s["add"]["name"]
            for s in _swaps_for_issue_dicts(
                [manalith],
                [{"kind": "upgrade", "severity": 1, "count": 1}],
                _upgrade_ctx([manalith], pool, focus_extra=_ARTIFACTS),
            )["swaps"]
        ]

    signet = _played("Arcane Signet", 20)
    talisman = _played("Talisman of Dominance", 400)
    sphere = _played("Commander's Sphere", 400)
    assert upgrade([signet, talisman], {"Talisman of Dominance"}) == [
        "Talisman of Dominance"
    ]
    assert upgrade([signet, sphere], {"Commander's Sphere"}) == ["Arcane Signet"]
    assert upgrade([signet, talisman], set()) == ["Arcane Signet"]


def _spine_fill(issue, budgets, pool, *, focus_extra=None):
    filler = _cc("Filler Card", "filler", cmc=3.0)
    return [
        s["add"]["name"]
        for s in _swaps_for_issue_dicts(
            [filler],
            [issue],
            SwapContext(
                budgets=budgets,
                focus_result={**_focus(), **(focus_extra or {})},
                deck_signals=[],
                search_fn=lambda **_: pool,
                identity="",
                fmt="commander",
                paper_only=True,
                owned={},
                budget=50.0,
                max_swaps=1,
                top_heavy=False,
            ),
        )["swaps"]
    ]


def test_the_wipe_read_orders_a_board_wipe_fill():
    """A board-wipe shortfall fills with the card the wipe read rates best
    (``JobRead.fill_orders``), not the cheapest band's most played: the band
    made Wail of War (read 0.07) Death Toll's wipe over Find // Finality (0.28).
    Blasphemous Act (0.69) beats Wrath of God (0.32) and Pyroclasm (-0.11)."""
    pool = [
        _played("Pyroclasm", 5),
        _played("Wrath of God", 10),
        _played("Blasphemous Act", 500),
    ]
    issue = {"kind": "role_short", "role": "board_wipe", "severity": 5}
    assert _spine_fill(issue, {"board_wipe": _band(1, 3, 4)}, pool) == [
        "Blasphemous Act"
    ]


def test_a_protection_fill_skips_the_avenue_guard(monkeypatch):
    """Protection guards the deck's threats whatever avenue they are on, so its
    fill takes the most-played card of the cheapest band even at FOCUSED, where
    the ADR-0040 guard picks an on-avenue card first: Animated Army's protection
    fill was the $36 Sword of Feast and Famine (it serves Combat) over Swiftfoot
    Boots. A card-draw fill still keeps the guard."""
    _serving(monkeypatch, {"Lightning Greaves"})
    pool = [_played("Swiftfoot Boots", 12), _played("Lightning Greaves", 50)]
    issue = {
        "kind": "protection_short",
        "severity": 3,
        "message": "0 protection — this Shape usually wants ~5",
    }
    assert _spine_fill(issue, {}, pool, focus_extra=_ARTIFACTS) == ["Swiftfoot Boots"]


def test_only_the_upgrade_issue_draws_an_upgrade_slot_doing_a_job():
    """A protection shortfall (a Spine fill that may take a lane slot) never
    takes an upgrade slot that does a job: Murder's slot is the upgrade
    issue's, for a better removal spell."""
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)
    out = _swaps_for_issue_dicts(
        [murder],
        [{"kind": "protection_short", "severity": 5, "message": "0 protection"}],
        _upgrade_ctx([murder], [_played("Heroic Intervention", 50)]),
    )
    assert out["swaps"] == []


def test_a_theme_add_is_the_most_played_card_on_its_page(monkeypatch):
    """Where play-rate means something, the theme page's most played card wins,
    however low its synergy score: the page's search already holds only the
    theme's cards, and a synergy floor on top cost guide adds (backlog (t),
    2026-10-30). Without play-rate the best fit leads."""
    from mtg_utils._tuner import swaps as swaps_mod

    scores = {"Box Ticker": 5.0, "Played Fit": 1.5, "Unfit Staple": 0.5}
    pool = [
        {**_off_avenue_draw("Box Ticker", cmc=3.0, rank=20000)},
        {**_off_avenue_draw("Played Fit", cmc=3.0, rank=100)},
        {**_off_avenue_draw("Unfit Staple", cmc=3.0, rank=1)},
    ]

    def fake_rank(cards, **_kw):
        return [
            {"card": c, "score": {"synergy_score": scores[c["name"]], "served": []}}
            for c in cards
        ]

    monkeypatch.setattr(swaps_mod, "rank_candidates", fake_rank)
    sig = _prolif_sig()
    label = spec_for(sig).label

    def run(*, playrate):
        out = _swaps_for_issue_dicts(
            [_cc("Filler Card", "filler", cmc=3.0)],
            [{"kind": "dead_weight", "severity": 8, "count": 1}],
            SwapContext(
                budgets={},
                focus_result=_focus(viable=[{"label": label, "depth": 20}]),
                deck_signals=[sig],
                search_fn=lambda **_: pool,
                identity="",
                fmt="commander",
                paper_only=True,
                owned={},
                budget=50.0,
                max_swaps=1,
                top_heavy=False,
                playrate=playrate,
            ),
        )
        return out["swaps"][0]["add"]["name"]

    assert run(playrate=True) == "Unfit Staple"
    assert run(playrate=False) == "Box Ticker"


def test_the_draw_gate_rejects_an_engine_its_deck_cannot_fuel():
    """Skullclamp draws when the equipped creature dies: in a deck of instants
    and sorceries it has no bodies to lose, so it is no card-draw upgrade
    there, however many decks play it; in a deck of X/1s and token makers it
    is."""
    divination = _real_cc("Divination", "spine", roles=["card_draw"], edhrec_rank=8000)
    clamp = _played("Skullclamp", 10)
    spells = [
        test_card(n)
        for n in ("Lightning Bolt", "Brainstorm", "Opt", "Counterspell", "Ponder")
    ]
    bodies = [
        test_card(n)
        for n in (
            "Llanowar Elves",
            "Raise the Alarm",
            "Young Pyromancer",
            "Krenko, Mob Boss",
        )
    ]
    assert not _upgrades(clamp, divination, "card_draw", deck=spells)
    assert _upgrades(clamp, divination, "card_draw", deck=bodies)
    assert _upgrades(clamp, divination, "card_draw")  # no deck: no fit to read


def test_a_spine_fill_is_gated_by_its_jobs_read():
    """A card-draw shortfall fills with a card the draw read says draws: a
    looter nets no card, so Faithless Looting fills no card-draw slot however
    many decks play it, and Night's Whisper does."""
    filler = _cc("Filler Card", "filler", cmc=3.0)
    issue = {"kind": "role_short", "role": "card_draw", "severity": 5}

    def fill(pool):
        return _swaps_for_issue_dicts(
            [filler],
            [issue],
            SwapContext(
                budgets={"card_draw": _band(5, 10, 12)},
                focus_result=_focus(),
                deck_signals=[],
                search_fn=lambda **_: pool,
                identity="",
                fmt="commander",
                paper_only=True,
                owned={},
                budget=50.0,
                max_swaps=1,
                top_heavy=False,
            ),
        )["swaps"]

    assert fill([_played("Faithless Looting", 10)]) == []
    assert [s["add"]["name"] for s in fill([_played("Night's Whisper", 500)])] == [
        "Night's Whisper"
    ]


def test_an_interaction_fill_may_be_a_counterspell():
    """Removal's read covers only part of the interaction job: an interaction
    shortfall may fill with Counterspell, which the read can't score."""
    filler = _cc("Filler Card", "filler", cmc=3.0)
    out = _swaps_for_issue_dicts(
        [filler],
        [{"kind": "role_short", "role": "interaction", "severity": 5}],
        SwapContext(
            budgets={"interaction": _band(5, 10, 12)},
            focus_result=_focus(),
            deck_signals=[],
            search_fn=lambda **_: [_played("Counterspell", 50)],
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
        ),
    )
    assert [s["add"]["name"] for s in out["swaps"]] == ["Counterspell"]


def test_a_job_upgrade_is_not_held_to_theme_fit(monkeypatch):
    """A removal upgrade trades a card for better removal, not for a card that
    fits the theme: Swords to Plowshares, played most, wins over Doom Blade even
    when Doom Blade fits the deck's themes far better (the fit floor kept
    Swords and Path behind Dragon Tempest in a goad deck)."""
    from mtg_utils._tuner import swaps as swaps_mod

    scores = {"Swords to Plowshares": 0.1, "Doom Blade": 5.0}

    def fake_rank(cards, **_kw):
        return [
            {"card": c, "score": {"synergy_score": scores[c["name"]], "served": []}}
            for c in cards
        ]

    monkeypatch.setattr(swaps_mod, "rank_candidates", fake_rank)
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)
    out = _swaps_for_issue_dicts(
        [murder],
        [{"kind": "upgrade", "severity": 1, "count": 1}],
        _upgrade_ctx(
            [murder], [_played("Doom Blade", 500), _played("Swords to Plowshares", 10)]
        ),
    )
    assert [s["add"]["name"] for s in out["swaps"]] == ["Swords to Plowshares"]


def test_a_top_heavy_decks_upgrade_is_not_capped_at_four_mana():
    """A top-heavy deck caps its adds at four mana so a fix can't make the curve
    heavier, but an upgrade takes no higher mana-value band than its cut: Meteor
    Golem may still become Duplicant (the cap hid Gishath, Ghalta and The First
    Sliver from the 25 precons' upgrades, 2026-10-19)."""
    import dataclasses

    golem = _real_cc("Meteor Golem", "spine", roles=["interaction"], edhrec_rank=8000)
    pool = [_played("Duplicant", 500)]

    def search(*, cmc_max=None, **_kw):
        return [c for c in pool if cmc_max is None or c["cmc"] <= cmc_max]

    ctx = dataclasses.replace(
        _upgrade_ctx([golem], pool), top_heavy=True, search_fn=search
    )
    out = _swaps_for_issue_dicts(
        [golem], [{"kind": "upgrade", "severity": 1, "count": 1}], ctx
    )
    assert [(s["cut"]["name"], s["add"]["name"]) for s in out["swaps"]] == [
        ("Meteor Golem", "Duplicant")
    ]


def test_a_theme_pages_by_its_serve():
    """A theme with no search of its own pages the cards its serving predicate
    admits, a mana-value band narrowing it; a search by card type overrides it
    (a tribe's serve also admits generic tribal support that would crowd out
    its members) — ``pages_by_serve``."""
    from mtg_utils._analysis.signal_specs import Serve
    from mtg_utils._tuner.swaps import _run_search

    serve = Serve(keywords=frozenset({"defender"}))
    calls: list[dict] = []

    def search(**kw):
        calls.append(kw)
        return []

    common = {
        "identity": "WG",
        "fmt": "commander",
        "paper_only": True,
        "cmc_cap": None,
        "limit": 150,
    }
    _run_search(search, {"_serve": serve}, **common)
    _run_search(search, {"card_type": "Sliver", "_serve": serve}, **common)
    _run_search(search, {"cmc_max": 0, "_serve": serve}, **common)
    assert (calls[0]["oracle"], calls[0]["serve"]) == (None, serve)
    assert (calls[1]["card_type"], calls[1]["serve"]) == ("Sliver", None)
    assert (calls[2]["cmc_max"], calls[2]["serve"]) == (0, serve)


def _plain(name, rank):
    """A theme candidate with no text: every one scores level, so play-rate
    alone orders the page."""
    return {
        "name": name,
        "type_line": "Creature — Construct",
        "oracle_text": "",
        "cmc": 3.0,
        "prices": {"usd": "1.00"},
        "color_identity": [],
        "edhrec_rank": rank,
    }


def _dead_weight_ctx(viable, signals, search, fillers, **ctx_extra):
    classes = [_cc(f"Junk {i}", "filler", cmc=3.0) for i in range(fillers)]
    issue = {"kind": "dead_weight", "severity": 7, "count": fillers, "message": "x"}
    ctx = SwapContext(
        **ctx_extra,
        budgets={},
        focus_result=_focus(viable=viable),
        deck_signals=signals,
        search_fn=search,
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=100.0,
        max_swaps=fillers,
        top_heavy=False,
    )
    return [
        s["add"]["name"] for s in _swaps_for_issue_dicts(classes, [issue], ctx)["swaps"]
    ]


def _type_sig(key):
    return Signal(
        key=key, scope="you", subject="", text="", source="X", confidence="high"
    )


def test_a_type_searched_theme_takes_one_support_card_in_five_never_the_first():
    # The Artifacts theme searches by card type: its own members page first,
    # and its serve's broader page adds support that is not of the type, more
    # played than every member, held to one add in five.
    sig = _type_sig("artifacts_matter")
    label = spec_for(sig).label
    members = [_plain(f"Member {i}", 100 + i) for i in range(4)]
    support = [_plain(f"Support {i}", 10 + i) for i in range(3)]

    def search(**kw):
        # The type search pages the members; the serve's page is wider.
        return members if kw.get("card_type") else [*support, *members]

    adds = _dead_weight_ctx(
        [{"label": label, "tier": "main", "depth": 20}], [sig], search, fillers=5
    )
    assert adds == [*(m["name"] for m in members), "Support 0"]


def test_the_theme_is_shared_by_depth_over_two_mains():
    # Two mains, 30 and 15 deep: the deeper takes the first two adds, then the
    # shallower its first (depth per add taken, the earlier avenue on a tie).
    deep, shallow = _type_sig("artifacts_matter"), _type_sig("enchantments_matter")
    pages = {
        "Artifact": [_plain(f"Deep {i}", 100 + i) for i in range(3)],
        "Enchantment": [_plain(f"Shallow {i}", 200 + i) for i in range(3)],
    }

    def search(**kw):
        return pages.get(kw.get("card_type") or "", [])

    adds = _dead_weight_ctx(
        [
            {"label": spec_for(deep).label, "tier": "main", "depth": 30},
            {"label": spec_for(shallow).label, "tier": "main", "depth": 15},
        ],
        [deep, shallow],
        search,
        fillers=3,
    )
    assert adds == ["Deep 0", "Deep 1", "Shallow 0"]


def test_the_commanders_token_doublers_take_one_theme_add():
    # A main 30 deep and a commander that copies tokens, ten deck cards doing
    # so: the token doublers page (``Sourcing.multiplier_avenue``, depth 10) is
    # asked once the main has taken three adds, and takes one add only.
    from mtg_utils._analysis.signal_specs import _TOKEN_DOUBLER_EXTRA

    deep, copies = _type_sig("artifacts_matter"), _type_sig("token_copy_makers")
    members = [_plain(f"Deep {i}", 100 + i) for i in range(6)]
    doublers = [_plain(f"Doubler {i}", 50 + i) for i in range(3)]

    def search(**kw):
        if kw.get("serve") == _TOKEN_DOUBLER_EXTRA.serve:
            return doublers
        return members if kw.get("card_type") == "Artifact" else []

    adds = _dead_weight_ctx(
        [{"label": spec_for(deep).label, "tier": "main", "depth": 30}],
        [deep, copies],
        search,
        fillers=5,
        commander_idents={("token_copy_makers", "you", "")},
        emitters={
            ("token_copy_makers", "you", ""): frozenset(
                f"Copier {i}" for i in range(10)
            )
        },
    )
    assert adds == ["Deep 0", "Deep 1", "Deep 2", "Doubler 0", "Deep 3"]


def test_a_fodder_makers_job_upgrade_makes_fodder_under_a_polymorph_commander():
    # Occult Epiphany's Spirits are bodies for Jace's -3 to exile: its draw slot
    # goes to a card that makes fodder too, however much more played the other is.
    from dataclasses import replace

    from mtg_utils._analysis.signals import Signal

    wants = Signal(key="wants_fodder", scope="you", subject="", text="", source="x")
    epiphany = _real_cc(
        "Occult Epiphany", "spine", roles=["card_draw"], edhrec_rank=8000
    )
    arena, shop = _played("Phyrexian Arena", 10), _played("Thopter Shop", 7000)
    issues = [{"kind": "upgrade", "severity": 1, "count": 1}]
    held = {("wants_fodder", "you", "")}

    def add(pool, idents=()):
        ctx = replace(
            _upgrade_ctx([epiphany], pool),
            deck_signals=[wants],
            commander_idents=idents,
        )
        return [
            s["add"]["name"]
            for s in _swaps_for_issue_dicts([epiphany], issues, ctx)["swaps"]
        ]

    assert add([arena]) == ["Phyrexian Arena"]
    assert add([arena], held) == []
    assert add([arena, shop], held) == ["Thopter Shop"]


def _murder_upgrade(path_rank, path_usd, budget):
    """The add trading Murder (rank 8000) up to five swaps on ``budget``: Swords
    to Plowshares at rank 10 and $5, or Path to Exile."""
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)
    pool = [
        {**_played("Swords to Plowshares", 10), "prices": {"usd": "5.00"}},
        {**_played("Path to Exile", path_rank), "prices": {"usd": path_usd}},
    ]
    out = _swaps_for_issue_dicts(
        [murder],
        [{"kind": "upgrade", "severity": 1, "count": 1}],
        _upgrade_ctx([murder], pool, budget=budget),
    )
    return [s["add"]["name"] for s in out["swaps"]]


def test_within_an_even_share_of_the_budget_the_most_played_card_is_the_add():
    """An add costing no more than an even share of what is left over the swaps
    still open (``_Purse.share``) takes the slot: $50 over five swaps is $10 a
    swap, so Swords to Plowshares at $5 keeps it over a cheaper near tie."""
    assert _murder_upgrade(14, "1.00", 50.0) == ["Swords to Plowshares"]


def test_past_the_share_the_first_card_that_fits_it_is_the_add():
    """$20 over five swaps is $4 a swap: Swords to Plowshares at $5 spends past
    it, so the most played card after it that fits the share is the add — Path
    to Exile at $1, a near tie of Swords at rank 14 or not at rank 40."""
    assert _murder_upgrade(14, "1.00", 20.0) == ["Path to Exile"]
    assert _murder_upgrade(40, "1.00", 20.0) == ["Path to Exile"]


def test_past_the_share_no_upgrade_takes_most_of_what_is_left():
    """$8 over five swaps: Swords to Plowshares at $5 is past the share and more
    than ``_PURSE_CAP`` of the purse, so Path to Exile at $3, no near tie at rank
    40, is the add; at $10 of budget Swords is within the cap and keeps the slot
    (no cheaper card in the window fits the share)."""
    assert _murder_upgrade(40, "3.00", 8.0) == ["Path to Exile"]
    assert _murder_upgrade(40, "3.00", 10.0) == ["Swords to Plowshares"]


def test_past_the_share_with_nothing_inside_it_a_near_tie_goes_to_the_cheaper_card():
    """$10 over five swaps is $2 a swap, and neither card fits it: a card within
    a factor of two of the first pick's play-rate (``_CHEAPER_TIE``) that costs
    less is the add, the budget it leaves reaching the issues after it — Path
    to Exile at rank 14 and $3; at rank 40 it is no near tie and Swords keeps
    the slot."""
    assert _murder_upgrade(14, "3.00", 10.0) == ["Path to Exile"]
    assert _murder_upgrade(40, "3.00", 10.0) == ["Swords to Plowshares"]


def test_specs_that_differ_after_the_search_are_one_search():
    """A remedy's page and the same page with a tuner-side filter, or credited to
    an avenue, run one search (``search_key``: what ``_run_search`` reads); a
    different serve, card type or band is another search."""
    serve = spec_for(_type_sig("artifacts_matter")).serve
    page = {"card_type": "Vampire", "_serve": serve}
    same = [
        {**page, "_filter": is_reliable_ramp},
        {**page, "_avenue": "Vampire tribal", "_share": 0.2},
    ]
    assert all(search_key(s) == search_key(page) for s in same)
    other = [
        {**page, "_serve": None},
        {**page, "card_type": "Goblin"},
        {**page, "cmc_max": 3},
    ]
    assert all(search_key(s) != search_key(page) for s in other)


def test_a_spine_fill_takes_a_jobless_upgrade_slot_before_a_lane_slot():
    """A Spine fill whose own pool is dry takes an off-lane upgrade slot doing
    no job before a lane slot: the upgrade issue would trade that card for a
    theme card anyway (25 precons, 2026-10-26: Multiverse Reforged's Swiftfoot
    Boots, a guide add)."""
    clunker = _real_cc("Grizzly Bears", "engine", edhrec_rank=8000)
    lane = [
        _cc(f"Vamp {i}", "engine", served=("Vampires",), edhrec_rank=9000 + i)
        for i in range(2)
    ]
    ctx = _upgrade_ctx(
        [clunker],
        [_played("Heroic Intervention", 50)],
        focus_extra={
            "commander_lane_cards": [c.name for c in lane],
            "lane_upgrade_cards": [c.name for c in lane],
        },
    )
    out = _swaps_for_issue_dicts(
        [clunker, *lane],
        [{"kind": "protection_short", "severity": 5, "message": "0 protection"}],
        replace(ctx, max_swaps=1),
    )
    assert [(s["cut"]["name"], s["add"]["name"]) for s in out["swaps"]] == [
        ("Grizzly Bears", "Heroic Intervention")
    ]


def _job_and_theme_search(job_card: dict, theme_card: dict):
    """A fake search whose job pages hold both cards and whose pages of the
    Proliferate theme (its preset, or its serve's page) hold only the theme's:
    a real theme page is the theme's own cards, and its most played card wins
    it."""

    def search(**kw):
        theme = kw.get("serve") is not None or "proliferate" in kw["preset_names"]
        return [theme_card] if theme else [job_card, theme_card]

    return search


def _full_job_swap(current):
    """One removal spell off the main theme, its row at ``current`` of 8-10,
    upgraded: a better-played removal spell and a theme payoff on the page."""
    sig = _sig_of("proliferate_matters")
    label = spec_for(sig).label
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)
    ctx = SwapContext(
        budgets={"interaction": _band(current, 8, 10)},
        focus_result={
            **_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
            "mains": [label],
            "upgrade_cards": [murder.name],
        },
        deck_signals=[sig],
        search_fn=_job_and_theme_search(
            _played("Swords to Plowshares", 10), _played("Evolution Sage", 9000)
        ),
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=50.0,
        max_swaps=1,
        top_heavy=False,
    )
    swaps = _swaps_for_issue_dicts(
        [murder], [{"kind": "upgrade", "severity": 1, "count": 1}], ctx
    )["swaps"]
    return [s["add"]["name"] for s in swaps]


def test_a_full_jobs_upgrade_moves_onto_the_theme():
    """A removal spell in a deck at its interaction row's max: the template
    says another removal spell adds nothing, so its slot goes to the theme's
    add (no dearer than the removal upgrade); below the max it keeps its job
    (25 precons, 2026-10-26: five guide adds more, a guide cut more)."""
    assert _full_job_swap(10) == ["Evolution Sage"]
    assert _full_job_swap(9) == ["Swords to Plowshares"]


def test_a_granters_slot_may_go_to_a_better_grant():
    """A Granter is judged by its grant (ADR-0040 §4): a solid Granter's theme
    upgrade may be a Granter whose grant grades higher, however few decks play
    it — Galerider Sliver's flying, premium — but not a weak one, and never on
    a job upgrade (25 precons, 2026-10-26: two guide cuts more)."""
    # The grade reads each card's trees: build them from the snapshot first.
    for name in ("Sentinel Sliver", "Galerider Sliver", "Enduring Sliver"):
        test_card_ir(name)
    cut = replace(_real_cc("Sentinel Sliver", "engine"), grant_grade="solid")
    better = _played("Galerider Sliver", 9000)
    assert _upgrades(better, cut, None)
    assert not _upgrades(_played("Enduring Sliver", 9000), cut, None)
    assert not _upgrades(better, cut, "card_draw")


def test_protection_at_the_shapes_target_moves_onto_the_theme():
    """Protection is full at the Shape's target (ADR-0024), as a row at its
    max: a protection card's slot goes to the theme's add then, and keeps its
    job below the target (25 precons, 2026-10-26: Blame Game, two guide adds
    more)."""
    sig = _sig_of("proliferate_matters")
    label = spec_for(sig).label
    boots = _real_cc("Swiftfoot Boots", "spine", edhrec_rank=8000)

    def upgrade(target):
        ctx = SwapContext(
            budgets={},
            focus_result={
                **_focus(viable=[{"label": label, "depth": 20, "cards": []}]),
                "mains": [label],
                "upgrade_cards": [boots.name],
            },
            deck_signals=[sig],
            search_fn=_job_and_theme_search(
                _played("Lightning Greaves", 10), _played("Evolution Sage", 9000)
            ),
            identity="",
            fmt="commander",
            paper_only=True,
            owned={},
            budget=50.0,
            max_swaps=1,
            top_heavy=False,
            protection_target=target,
            protection_count=1,
        )
        swaps = _swaps_for_issue_dicts(
            [boots], [{"kind": "upgrade", "severity": 1, "count": 1}], ctx
        )["swaps"]
        return [s["add"]["name"] for s in swaps]

    assert upgrade(1) == ["Evolution Sage"]
    assert upgrade(2) == ["Lightning Greaves"]


def test_a_counterspell_upgrades_a_removal_cut_on_the_interaction_page():
    """The interaction read covers counterspells (2026-10-31), so a counterspell
    more decks play replaces a removal cut as any interaction upgrade does; a
    counter of an ability alone (Stifle) is still no answer."""
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)

    def upgrade(pool):
        return _swaps_for_issue_dicts(
            [murder],
            [{"kind": "upgrade", "severity": 1, "count": 1}],
            _upgrade_ctx([murder], pool),
        )["swaps"]

    assert [s["add"]["name"] for s in upgrade([_played("Counterspell", 100)])] == [
        "Counterspell"
    ]
    assert upgrade([_played("Stifle", 100)]) == []


# ── A polymorph commander's flips ─────────────────────────────────────────────

#: Jace, Multiverse Architect's own idents: wants fodder, flips into a creature
#: or planeswalker card (``read_deck_signals``' ``commander_idents``).
_POLYMORPH_IDENTS = frozenset(
    {
        ("wants_fodder", "you", ""),
        ("cheat_into_play", "you", "Creature"),
        ("cheat_into_play", "you", "Planeswalker"),
    }
)
_WANTS_FODDER = Signal(key="wants_fodder", scope="you", subject="", text="", source="x")


def _polymorph_bombs():
    """Four flips of a polymorph deck: creature and planeswalker cards at six and
    seven mana (the top band), what the deck wants its polymorph to reveal."""
    return [
        _real_cc(name, "engine", served=("Cheat into play",), edhrec_rank=3000)
        for name in (
            "Sun Titan",
            "Overlord of the Mistmoors",
            "Myr Battlesphere",
            "Elspeth, Sun's Champion",
        )
    ]


def _swaps_under_polymorph(classes, issues, ctx):
    """``_swaps_for_issue_dicts`` with the commander's idents on the sourcing
    too, so the issues' remedies read the polymorph commander as the engine does."""
    sourcing = Sourcing(
        ctx.focus_result,
        ctx.deck_signals,
        ctx.budgets,
        commander_idents=ctx.commander_idents,
    )
    return propose_swaps(classes, [_issue(sourcing, i) for i in issues], ctx)


def test_a_polymorph_trim_takes_repeatable_makers_first_and_keeps_the_flips_bombs():
    """Ramp over by three under Jace: the trims go to the fodder page in its own
    order (``issues._fodder_lead``) — a maker whose token comes every turn
    first, a noncreature one (Bitterblossom) before a creature (Loyal
    Apprentice), the one-shot (Raise the Alarm) last, whatever their play-rate.
    A creature maker is a flip too, so it is admitted only while the deck's
    flips stay mostly its bombs (``swaps._WHIFF_SHARE``: one in four): the
    second one (Young Pyromancer) is left out and the one-shot takes the slot.
    Dan's Jace tune (2026-11-01) took ten such creatures beside eleven bombs cut."""
    rocks = [
        _real_cc(name, "spine", roles=["ramp"], edhrec_rank=8000 + i)
        for i, name in enumerate(("Mind Stone", "Commander's Sphere", "Arcane Signet"))
    ]
    pool = [
        _played("Young Pyromancer", 500),
        _played("Loyal Apprentice", 300),
        _played("Bitterblossom", 3000),
        _played("Raise the Alarm", 2000),
    ]
    ctx = SwapContext(
        budgets={"ramp": _band(13, 8, 10)},  # over by 3
        focus_result=_focus(viable=[{"label": "Main", "depth": 20, "cards": []}]),
        deck_signals=[_WANTS_FODDER],
        commander_idents=_POLYMORPH_IDENTS,
        search_fn=lambda **_: pool,
        identity="",
        fmt="commander",
        paper_only=True,
        owned={},
        budget=50.0,
        max_swaps=5,
        top_heavy=False,
    )
    out = _swaps_under_polymorph(
        [*_polymorph_bombs(), *rocks],
        [{"kind": "role_over", "role": "ramp", "severity": 3, "message": "ramp over"}],
        ctx,
    )
    assert [s["add"]["name"] for s in out["swaps"]] == [
        "Bitterblossom",
        "Loyal Apprentice",
        "Raise the Alarm",
    ]


def test_a_cheap_creature_that_is_no_fodder_is_a_whiff_under_a_polymorph_commander():
    """Murder's interaction upgrade: Banisher Priest, more played, is a creature
    card, and under Jace every creature card in the library is a flip — a
    three-mana one beside six- and seven-mana bombs is a whiff
    (``swaps.flip_floor_band``), so the upgrade is Swords to Plowshares. Under
    any other commander Banisher Priest is the add."""
    murder = _real_cc("Murder", "spine", roles=["interaction"], edhrec_rank=8000)
    pool = [_played("Banisher Priest", 10), _played("Swords to Plowshares", 100)]
    issue = [{"kind": "upgrade", "severity": 1, "count": 1}]
    classes = [murder, *_polymorph_bombs()]

    def upgrade(ctx):
        return [
            s["add"]["name"]
            for s in _swaps_under_polymorph(classes, issue, ctx)["swaps"]
        ]

    plain = _upgrade_ctx([murder], pool)
    assert upgrade(plain) == ["Banisher Priest"]
    polymorph = replace(
        plain, deck_signals=[_WANTS_FODDER], commander_idents=_POLYMORPH_IDENTS
    )
    assert upgrade(polymorph) == ["Swords to Plowshares"]


def test_a_flips_upgrade_is_a_better_flip_under_a_polymorph_commander():
    """An off-plan bomb with no job (Myr Battlesphere, little played) is a
    polymorph deck's flip: its slot goes to a better flip off the commander's
    cheat page (Terror of the Peaks — a five-power body the cheat lane's payoff
    arm serves), never to a token maker, however many more decks play it
    (Bitterblossom). The guides trade the Jace precon's off-plan bombs for
    better ones; under any other commander the slot has no page here."""
    cheat = Signal(
        key="cheat_into_play", scope="you", subject="Creature", text="", source="x"
    )
    sphere = _real_cc("Myr Battlesphere", "engine", edhrec_rank=8000)
    pool = [_played("Bitterblossom", 100), _played("Terror of the Peaks", 300)]
    issue = [{"kind": "upgrade", "severity": 1, "count": 1}]
    classes = [sphere, *_polymorph_bombs()]

    def upgrade(ctx):
        return [
            (s["add"]["name"], s["reason"])
            for s in _swaps_under_polymorph(classes, issue, ctx)["swaps"]
        ]

    plain = _upgrade_ctx([sphere], pool)
    assert upgrade(plain) == []
    polymorph = replace(
        plain, deck_signals=[_WANTS_FODDER, cheat], commander_idents=_POLYMORPH_IDENTS
    )
    assert upgrade(polymorph) == [
        (
            "Terror of the Peaks",
            "upgrade a flip: Terror of the Peaks — more decks play it",
        )
    ]


@pytest.mark.parametrize(
    ("draw_row", "add"),
    [
        (_band(12, 10, 12), "Terror of the Peaks"),  # at the max: it needs its flip
        (_band(11, 10, 12), "Terror of the Peaks"),  # in band: the same
        (_band(5, 10, 12), "Phyrexian Arena"),  # short: the deck needs the draw
    ],
)
def test_a_flip_with_a_job_keeps_a_flips_slot_unless_its_row_is_short(draw_row, add):
    """Niv-Mizzet, Ghost Counsel draws under Jace with card draw over its band:
    the deck needs no more draw, it needs its flip, so the slot goes to the
    flips' page; only a short row keeps the job page."""
    cheat = Signal(
        key="cheat_into_play", scope="you", subject="Creature", text="", source="x"
    )
    sphere = _real_cc(
        "Myr Battlesphere", "spine", roles=["card_draw"], edhrec_rank=8000
    )
    pool = [_played("Phyrexian Arena", 50), _played("Terror of the Peaks", 300)]
    ctx = replace(
        _upgrade_ctx([sphere], pool),
        budgets={"card_draw": draw_row},
        deck_signals=[_WANTS_FODDER, cheat],
        commander_idents=_POLYMORPH_IDENTS,
    )
    out = _swaps_under_polymorph(
        [sphere, *_polymorph_bombs()],
        [{"kind": "upgrade", "severity": 1, "count": 1}],
        ctx,
    )
    assert [s["add"]["name"] for s in out["swaps"]] == [add]


def test_a_tribe_members_slot_stays_the_tribes():
    """Disa holds the Lhurgoyf tribe beside a "Your graveyard" main: a cut
    Lhurgoyf's upgrade comes off the tribe's own page (Tarmogoyf), never the
    main's (Life from the Loam, more played), as the guides add Lhurgoyfs and
    changelings (2026-11-01). Under a commander holding no tribe the main's
    page takes the slot."""
    tribe = Signal(
        key="type_matters", scope="you", subject="Lhurgoyf", text="", source="x"
    )
    graveyard = Signal(
        key="graveyard_matters", scope="you", subject="", text="", source="x"
    )
    tribe_label, main_label = spec_for(tribe).label, spec_for(graveyard).label
    goyf = _real_cc("Mortivore", "engine", served=(tribe_label,), edhrec_rank=9000)
    loam, tarmo = _played("Life from the Loam", 10), _played("Tarmogoyf", 500)

    def search(**kw):
        return [tarmo] if kw.get("card_type") == "Lhurgoyf" else [loam, tarmo]

    focus = {
        "viable_avenues": [
            {"label": main_label, "tier": "main", "depth": 28, "cards": []},
            {"label": tribe_label, "tier": "sub", "depth": 11, "cards": []},
        ],
        "mains": [main_label],
    }
    ctx = replace(
        _upgrade_ctx([goyf], [loam, tarmo], focus_extra=focus),
        deck_signals=[tribe, graveyard],
        search_fn=search,
    )
    issue = [{"kind": "upgrade", "severity": 1, "count": 1}]

    def adds(c):
        return [
            (s["add"]["name"], s["reason"])
            for s in _swaps_for_issue_dicts([goyf], issue, c)["swaps"]
        ]

    assert adds(ctx) == [
        (
            "Life from the Loam",
            "upgrade the main theme: Life from the Loam — more decks play it",
        )
    ]
    held = replace(
        ctx, focus_result={**ctx.focus_result, "commander_tribes": [tribe_label]}
    )
    assert adds(held) == [
        ("Tarmogoyf", "upgrade a Lhurgoyf: Tarmogoyf — more decks play it")
    ]


# ── The commander's needs on a theme page ─────────────────────────────────────


def _need_page(label: str, need, page) -> tuple[str, int, dict]:
    """A need page as ``tune`` builds one (``swaps.need_pages``): its suppliers
    in ``page``, taking no shared add of its own (``_cap`` 0)."""
    return (label, 1, {"_need": need, "_page": page, "_cap": 0, "_avenue": label})


def _swaps_with_needs(classes, issues, ctx):
    sourcing = Sourcing(
        ctx.focus_result,
        ctx.deck_signals,
        ctx.budgets,
        need_avenues=ctx.need_avenues,
    )
    return propose_swaps(classes, [_issue(sourcing, i) for i in issues], ctx)


def test_a_theme_page_puts_the_cards_the_commander_asks_for_first():
    """Ellivere makes Aura tokens and draws per enchantment: her Voltron page
    held Equipment by play-rate (Basilisk Collar, Blackblade Reforged) over the
    Auras the guides add. With the commander's specific needs (enchantments,
    voltron gear) a card supplying more of them leads the page and is an
    upgrade of a cut supplying fewer, however few decks play it: Rancor, an
    Aura, over Basilisk Collar, an Equipment, for Blackblade Reforged's slot
    (the cut supplies the voltron need, so its slot is upgraded off that need's
    page — ``Sourcing.upgrade_spec`` — in the needs' order). Without the needs,
    play-rate picks the Collar."""
    from mtg_utils._analysis.commander_need import Need

    voltron = Signal(
        key="voltron_matters", scope="you", subject="", text="", source="x"
    )
    label = spec_for(voltron).label
    blade = _real_cc("Blackblade Reforged", "engine", served=(label,), edhrec_rank=300)
    # The deck builds toward both needs (``swaps._NEED_BUILT_FLOOR`` cards each):
    # five Auras and five Equipment beside the cut.
    suit = []
    for i in range(5):
        aura = _cc(f"Aura {i}", "engine", served=(label,))
        aura.record["type_line"] = "Enchantment — Aura"
        gear = _cc(f"Gear {i}", "engine", served=(label,))
        gear.record["type_line"] = "Artifact — Equipment"
        suit += [aura, gear]
    pool = [_played("Basilisk Collar", 100), _played("Rancor", 2000)]
    ctx = _upgrade_ctx(
        [blade],
        pool,
        focus_extra={
            "viable_avenues": [
                {"label": label, "tier": "main", "depth": 20, "cards": []}
            ],
            "mains": [label],
        },
    )
    ctx = replace(ctx, deck_signals=[voltron])
    issue = [{"kind": "upgrade", "severity": 1, "count": 1}]
    assert [
        s["add"]["name"] for s in _swaps_with_needs([blade, *suit], issue, ctx)["swaps"]
    ] == ["Basilisk Collar"]
    needs = (
        _need_page(
            "enchantments matter",
            Need(
                "payoff",
                "enchantments matter",
                "x",
                types=frozenset({frozenset({"enchantment"})}),
            ),
            pool,
        ),
        _need_page(
            "voltron matters",
            Need(
                "payoff",
                "voltron matters",
                "x",
                types=frozenset({frozenset({"aura"}), frozenset({"equipment"})}),
            ),
            pool,
        ),
    )
    with_needs = replace(ctx, need_avenues=needs)
    assert [
        s["add"]["name"]
        for s in _swaps_with_needs([blade, *suit], issue, with_needs)["swaps"]
    ] == ["Rancor"]


def test_an_upgrade_keeps_what_the_cut_gives_the_commander():
    """Whatever the job, a candidate supplying fewer of the commander's needs
    than the cut is no upgrade: Living Death (cards leave Teval's graveyard) is
    no interaction slot for Assassin's Trophy, however many more decks play it.
    Without the needs read it is."""
    living_death = _real_cc(
        "Living Death", "spine", roles=["interaction"], edhrec_rank=3000
    )
    trophy = _played("Assassin's Trophy", 100)

    def needs(record):
        return 1 if record["name"] == "Living Death" else 0

    assert _upgrades(trophy, living_death, "interaction")
    assert not _upgrades(trophy, living_death, "interaction", needs=needs)


def test_over_band_trim_takes_a_card_the_commander_asks_for_last():
    """Equal otherwise, an over-band row trims the member supplying none of the
    commander's built needs before one supplying one: Oracle of Mul Daya's
    extra land drops under a land-sacrificing Yuma are what the deck asks for,
    not surplus ramp (Desert Bloom)."""
    classes = [
        _cc("Oracle", "spine", roles=["ramp"], edhrec_rank=1000),
        _cc("Rock", "spine", roles=["ramp"], edhrec_rank=1000),
    ]
    cuts = cut_candidates(
        classes,
        budgets={"ramp": _band(2, 0, 1)},
        focus=CutFocus(),
        needs=lambda record: int(record["name"] == "Oracle"),
    )
    assert [c.name for _reason, c in cuts] == ["Rock"]


def test_a_need_count_admission_never_trades_down_a_card_that_already_served():
    """Shield-Wall Sentinel ticks two of Felothar's boxes (a defender, toughness
    4) to Zetalpa, Primal Dawn's one (toughness 8), and four times fewer decks
    play it: no upgrade, since Zetalpa already served the commander and the
    card-quality read rates the Sentinel far below it. Jaddi Offshoot's slot
    goes to Stalwart Shield-Bearers (two boxes, no weaker a card). A jobless
    cut is never traded down, whatever it serves: Gray Merchant's slot (no
    need of Felothar's) is no Wall of Souls either."""
    zetalpa = _real_cc("Zetalpa, Primal Dawn", "engine", edhrec_rank=1630)
    jaddi = _real_cc("Jaddi Offshoot", "engine", edhrec_rank=4000)
    gary = _real_cc("Gray Merchant of Asphodel", "engine", edhrec_rank=300)
    boxes = {
        "Zetalpa, Primal Dawn": 1,
        "Jaddi Offshoot": 1,
        "Shield-Wall Sentinel": 2,
        "Stalwart Shield-Bearers": 2,
        "Wall of Souls": 1,
    }

    def needs(record):
        return boxes.get(record["name"], 0)

    assert not _upgrades(
        _played("Shield-Wall Sentinel", 6071), zetalpa, None, needs=needs
    )
    # Off the deck's main lanes too: moving the slot onto the theme is no
    # reason to trade Zetalpa down.
    assert not _upgrades(
        _played("Shield-Wall Sentinel", 6071),
        zetalpa,
        None,
        off_theme=True,
        needs=needs,
    )
    assert _upgrades(_played("Stalwart Shield-Bearers", 6000), jaddi, None, needs=needs)
    assert not _upgrades(_played("Wall of Souls", 9000), gary, None, needs=needs)


def test_a_led_page_is_sorted_whole_before_it_is_cut():
    """A need lead must see the suppliers below the play-rate head: with the
    page cut to its limit first, Hazel's Squirrel makers (two of her needs) sat
    past the token makers' first 150 and never led. Here the cut supplies the
    need, so its slot is upgraded off the need's page, where the one other
    supplier sits last of two hundred by play-rate: it is the add (the two
    hundred supply nothing and keep nothing of the cut's)."""
    from mtg_utils._analysis.commander_need import Need

    label = "Tokens"
    cut = _cc("Weak Maker", "engine", served=(label,), edhrec_rank=9000)
    cut.record.update(type_line="Creature — Beast", cmc=3.0, acorn=True)
    suit = []
    for i in range(5):  # the deck builds toward the need
        card = _cc(f"Acorn {i}", "engine", served=(label,))
        card.record["acorn"] = True
        suit.append(card)
    pool = []
    for i in range(200):
        card = {**_played("Raise the Alarm", 100 + i), "name": f"Popular Maker {i}"}
        card["oracle_id"] = f"popular-{i}"
        pool.append(card)
    acorn = {
        **_played("Raise the Alarm", 8000),
        "name": "Acorn Maker",
        "oracle_id": "acorn",
    }
    acorn["acorn"] = True
    pool.append(acorn)
    need = Need("payoff", "acorn makers", "x", predicate=lambda c: bool(c.get("acorn")))
    ctx = _upgrade_ctx(
        [cut],
        pool,
        focus_extra={
            "viable_avenues": [
                {"label": label, "tier": "main", "depth": 20, "cards": []}
            ],
            "mains": [label],
        },
    )
    ctx = replace(ctx, need_avenues=(_need_page(need.label, need, pool),))
    issue = [{"kind": "upgrade", "severity": 1, "count": 1}]
    adds = [
        s["add"]["name"] for s in _swaps_with_needs([cut, *suit], issue, ctx)["swaps"]
    ]
    assert adds == ["Acorn Maker"]


@pytest.mark.parametrize(
    ("interaction_row", "add"),
    [(_band(9, 10, 12), "An Offer You Can't Refuse"), (_band(11, 10, 12), "Tarmogoyf")],
)
def test_a_tribe_member_with_a_job_keeps_the_tribes_slot_unless_its_row_is_short(
    interaction_row, add
):
    """Aryel, Knight of Windgrace's removal under a Knights commander: with
    interaction in band, the slot stays a Knight's (as a flip's does); a short
    row keeps the job page. Here a Lhurgoyf that removes, under Disa."""
    tribe = Signal(
        key="type_matters", scope="you", subject="Lhurgoyf", text="", source="x"
    )
    tribe_label = spec_for(tribe).label
    goyf = _real_cc(
        "Mortivore",
        "spine",
        roles=["interaction"],
        served=(tribe_label,),
        edhrec_rank=9000,
    )
    offer, tarmo = _played("An Offer You Can't Refuse", 34), _played("Tarmogoyf", 500)

    def search(**kw):
        return [tarmo] if kw.get("card_type") == "Lhurgoyf" else [offer, tarmo]

    ctx = replace(
        _upgrade_ctx([goyf], [offer, tarmo]),
        budgets={"interaction": interaction_row},
        deck_signals=[tribe],
        search_fn=search,
    )
    ctx = replace(
        ctx,
        focus_result={
            **ctx.focus_result,
            "viable_avenues": [
                {"label": tribe_label, "tier": "main", "depth": 11, "cards": []}
            ],
            "mains": [tribe_label],
            "commander_tribes": [tribe_label],
        },
    )
    out = _swaps_for_issue_dicts(
        [goyf], [{"kind": "upgrade", "severity": 1, "count": 1}], ctx
    )
    assert [s["add"]["name"] for s in out["swaps"]] == [add]


def test_an_upgrade_keeps_the_broad_need_its_cut_supplies():
    """Anikthea's enchantment need is too broad to page (over ``BROAD_SHARE``
    of an Abzan pool), but Cast Out, an enchantment she returns, is still no
    upgrade to Assassin's Trophy: an upgrade keeps every need its cut supplies
    (``needs_kept``; Enduring Enchantments, 2026-11-02). Without the kept
    needs the same trade passes."""
    from mtg_utils._analysis.commander_need import commander_needs, satisfies

    needs = [
        n
        for n in commander_needs([test_card("Anikthea, Hand of Erebos")])
        if n.label == "enchantments matter"
    ]
    assert needs

    def kept(record):
        return sum(1 for n in needs if satisfies(record, n))

    cast_out = _real_cc("Cast Out", "spine", roles=["interaction"], edhrec_rank=8000)
    trophy = _played("Assassin's Trophy", 10)
    assert _upgrades(trophy, cast_out, "interaction")
    assert not _upgrades(trophy, cast_out, "interaction", needs_kept=kept)


def test_a_need_supplier_is_never_low_value_fodder():
    """A fringe-played Engine card is a low-value cut unless it supplies one of
    the commander's needs: Juniper Order Ranger's counters under Bright-Palm
    went for a closer (Call for Backup, 2026-11-02)."""
    classes = [
        _cc("Need Engine", "engine", served=["Counters"], edhrec_rank=60000),
        _cc("Idle Engine", "engine", served=["Counters"], edhrec_rank=60000),
    ]
    cuts = cut_candidates(
        classes,
        budgets={},
        focus=CutFocus(),
        needs=lambda record: int(record["name"] == "Need Engine"),
    )
    assert [c.name for _reason, c in cuts] == ["Idle Engine"]


def test_over_band_trim_takes_a_multi_role_card_last():
    """Equal otherwise, an over-band row trims a card filling only that role
    before one filling two (Wrenn and Seven's ramp beside its draw, Death
    Toll 2026-11-02)."""
    classes = [
        _cc("Ramp and Draw", "spine", roles=["ramp", "card_draw"], edhrec_rank=1000),
        _cc("Plain Rock", "spine", roles=["ramp"], edhrec_rank=1000),
    ]
    cuts = cut_candidates(classes, budgets={"ramp": _band(2, 0, 1)}, focus=CutFocus())
    assert [c.name for _reason, c in cuts] == ["Plain Rock"]


def test_over_band_trim_takes_a_mana_doubler_last():
    """Forsaken Monument doubles colorless mana — the ramp's point, not its
    surplus — so an over-band ramp row trims Mind Stone first (Eldrazi
    Incursion, 2026-11-02)."""
    classes = [
        _real_cc("Forsaken Monument", "spine", roles=["ramp"], edhrec_rank=1000),
        _real_cc("Mind Stone", "spine", roles=["ramp"], edhrec_rank=1000),
    ]
    cuts = cut_candidates(classes, budgets={"ramp": _band(2, 0, 1)}, focus=CutFocus())
    assert [c.name for _reason, c in cuts] == ["Mind Stone"]


def test_over_band_trim_takes_a_tribe_member_last():
    """Equal otherwise, an over-band row trims the member of the commander's
    tribe after the rest (Cavalier of Thorns under an Elemental commander)."""
    classes = [
        _cc("Elemental Ramp", "spine", roles=["ramp"], edhrec_rank=1000),
        _cc("Plain Rock", "spine", roles=["ramp"], edhrec_rank=1000),
    ]
    cuts = cut_candidates(
        classes,
        budgets={"ramp": _band(2, 0, 1)},
        focus=CutFocus(),
        tribe_member=lambda record: record["name"] == "Elemental Ramp",
    )
    assert [c.name for _reason, c in cuts] == ["Plain Rock"]


def test_a_payoff_for_what_the_deck_does_not_do_is_dead_there():
    """Banner of Kinship, Door of Destinies and Coat of Arms choose a creature
    type: dead in a deck with no tribe, alive with twelve Dinosaurs. Hardened
    Scales doubles counters: dead where nothing places them. Etali's poison
    payoff is fed by its own poison, Myr Battlesphere's Myr reference by its
    own tokens, and a card caring about nothing the read names (Panharmonicon)
    is never dead."""
    from collections import Counter

    from mtg_utils._tuner.swaps import dead_payoff

    no_tribe, dinos = Counter(), Counter({"dinosaur": 12})
    none, counters = Counter(), Counter({"plus_one_makers": 6})
    no_types = Counter()

    def dead(name, keys=none, tribes=no_tribe, types=no_types):
        return dead_payoff(test_card(name), keys, tribes, types)

    for name in ("Banner of Kinship", "Door of Destinies", "Coat of Arms"):
        assert dead(name), name
        assert not dead(name, tribes=dinos), name
    assert dead("Hardened Scales")
    # A doubler wants twice the floor: six counter cards are incidental
    # (Anikthea's), twelve are the plan.
    assert dead("Hardened Scales", keys=counters)
    assert not dead("Hardened Scales", keys=Counter({"plus_one_makers": 12}))
    for name in (
        "Etali, Primal Conqueror // Etali, Primal Sickness",
        "Myr Battlesphere",
        "Panharmonicon",
        "Asceticism",
        "Farseek",  # a Plains is no tribe
        "Black Market Connections",  # a life payment wants no life gain
    ):
        assert not dead(name), name
    # A choose-a-type card is tribal through and through: Vanquisher's Banner
    # draws nothing without a tribe, whatever page asks for it.
    from mtg_utils._tuner.swaps import chooses_a_type_without_tribe

    assert chooses_a_type_without_tribe(test_card("Vanquisher's Banner"), no_tribe)
    assert not chooses_a_type_without_tribe(test_card("Vanquisher's Banner"), dinos)
    assert not chooses_a_type_without_tribe(test_card("Farseek"), no_tribe)
    # A trigger gated on a tribe the deck lacks, and nothing else to do: Dragon
    # Tempest's damage waits on Dragons that never come; with ten Dragons it
    # is alive.
    assert dead("Dragon Tempest")
    assert not dead("Dragon Tempest", tribes=Counter({"dragon": 10}))
    # Ygra, Eater of All's Food gate is fed by the Food she makes of everything.
    assert not dead("Ygra, Eater of All")
    # A unit gated on a card type or a gear type the deck lacks is as dead as
    # one gated on a tribe: Talrand's and Docent of Perfection's tokens wait on
    # instants and sorceries (thirteen are too few; twenty are a spellslinger
    # deck), Puresteel Paladin's draw on Equipment (two, or six), Death
    # Baron's anthem on Zombies (its own Zombie type feeds no static), Kor
    # Spiritdancer's draw on Auras, Rising of the Day's bonus on legends
    # (seven, or fifteen). Sai, Master Thopterist's cast trigger is unfed in a
    # Humans deck, but its draw can be activated; Knight of the White Orchid's
    # Plains is a land type, no gate (2026-11-02).
    few_spells = Counter({"instant": 7, "sorcery": 6})
    many_spells = Counter({"instant": 10, "sorcery": 10})
    for name in ("Talrand, Sky Summoner", "Docent of Perfection // Final Iteration"):
        assert dead(name, types=few_spells), name
        assert not dead(name, types=many_spells), name
    assert dead("Puresteel Paladin", types=Counter({"equipment": 2, "artifact": 12}))
    assert not dead(
        "Puresteel Paladin", types=Counter({"equipment": 6, "artifact": 12})
    )
    assert dead("Death Baron")
    assert not dead("Death Baron", tribes=Counter({"zombie": 6}))
    assert dead("Kor Spiritdancer")
    assert not dead("Kor Spiritdancer", types=Counter({"aura": 8}))
    assert dead("Rising of the Day", types=Counter({"legendary": 7}))
    assert not dead("Rising of the Day", types=Counter({"legendary": 15}))
    assert not dead("Knight of the White Orchid")
    # An activated ability or a spell is gated by its cost or its effects over
    # your permanents: Sai's draw costs two artifacts, Skirk Prospector's mana a
    # Goblin, Grinding Station's mill an artifact; Brass Squire moves your
    # Equipment; Inspiring Call draws for your creatures with +1/+1 counters;
    # Intangible Virtue pumps your creature tokens (Clues are none). An
    # ability no gate holds keeps a card (Asceticism); Krenko's Goblins are his
    # own. A card's own type feeds no gate: Scourge of Valkas's one Dragon is
    # itself (the reviewers' pass, 2026-11-02).
    assert dead("Sai, Master Thopterist", types=Counter({"artifact": 12}))
    assert not dead("Sai, Master Thopterist", types=Counter({"artifact": 20}))
    assert dead("Skirk Prospector")
    assert not dead("Skirk Prospector", tribes=Counter({"goblin": 6}))
    assert dead("Grinding Station", types=Counter({"artifact": 8}))
    assert not dead("Grinding Station", types=Counter({"artifact": 20}))
    assert dead("Brass Squire")
    assert not dead("Brass Squire", types=Counter({"equipment": 6}))
    assert dead("Inspiring Call")
    assert not dead("Inspiring Call", keys=Counter({"plus_one_makers": 6}))
    assert dead("Intangible Virtue", types=Counter({"creature tokens": 2}))
    assert not dead("Intangible Virtue", types=Counter({"creature tokens": 6}))
    assert dead("Scourge of Valkas")
    assert not dead("Scourge of Valkas", tribes=Counter({"dragon": 6}))
    assert not dead("Krenko, Mob Boss")
    assert not dead("Asceticism")
    # A cost reduction's color is its gate: Oketra's Monument's white creature
    # spells, a colorless card dead in Golgari (Squirreled Away, 2026-11-02).
    assert dead("Oketra's Monument", types=Counter({"color:g": 20}))
    assert not dead("Oketra's Monument", types=Counter({"color:w": 20}))
    # A library effect's filter is yours with no controller on it: Heroes'
    # Podium finds and pumps legendary creatures (Animated Army's ten), Open
    # the Armory finds gear. An opponent's discard is the gate on Waste Not's
    # triggers, fed by the deck's discard makers (Multiverse Reforged forces
    # none).
    assert dead("Heroes' Podium", types=Counter({"legendary": 10}))
    assert not dead("Heroes' Podium", types=Counter({"legendary": 20}))
    assert dead("Open the Armory")
    assert not dead("Open the Armory", types=Counter({"equipment": 8}))
    assert dead("Waste Not")
    assert not dead("Waste Not", keys=Counter({"opponent_discard": 6}))
    # Your own discard is a gate too: Monument to Endurance under no outlets.
    assert dead("Monument to Endurance")
    assert not dead("Monument to Endurance", keys=Counter({"discard_outlet": 6}))
    # A proliferate spell adds to counters the deck must already place:
    # Ripples of Potential under four counter makers (Family Matters).
    assert dead("Ripples of Potential", keys=Counter({"plus_one_makers": 4}))
    assert not dead("Ripples of Potential", keys=Counter({"plus_one_makers": 8}))
    # A draw spell with a proliferate rider draws whatever it finds.
    assert not dead("Tezzeret's Gambit")
    # The gate rule alone is what a job page applies.
    from mtg_utils._tuner.swaps import gated_without_feed

    assert gated_without_feed(test_card("Dragon Tempest"), no_tribe, no_types)
    assert not gated_without_feed(
        test_card("Dragon Tempest"), Counter({"dragon": 10}), no_types
    )
    assert not gated_without_feed(test_card("Farseek"), no_tribe, no_types)
    # Sram, Senior Edificer draws for gear a deck without gear never casts.
    assert gated_without_feed(test_card("Sram, Senior Edificer"), no_tribe, no_types)
    assert not gated_without_feed(
        test_card("Sram, Senior Edificer"), no_tribe, Counter({"aura": 6})
    )
    # A commander that makes permanents every creature type fields every
    # tribe on the battlefield: Coat of Arms is alive under Omo, Queen of
    # Vesuva, dead under Bello. Dragon Tempest's triggers wait on a Dragon
    # or flyer entering, and Omo's everything counters are on creatures
    # already out: dead under both (2026-11-02).
    from mtg_utils._tuner.swaps import deck_profile

    for commander, alive in (
        ("Omo, Queen of Vesuva", {"Coat of Arms"}),
        ("Bello, Bard of the Brambles", set()),
    ):
        keys, tribes, types = deck_profile(
            [
                _real_cc(commander, "commander"),
                _real_cc("Cultivate", "spine", roles=("ramp",)),
            ]
        )
        for name in ("Coat of Arms", "Dragon Tempest"):
            dead = dead_payoff(test_card(name), keys, tribes, types)
            assert dead is (name not in alive), (commander, name)


def test_a_kinship_trigger_is_gated_on_the_cards_own_types():
    """Wolf-Skull Shaman's kinship reveals a Wolf only off an Elf or Shaman:
    in a Squirrel deck with five of them its Wolves never come, whatever
    tokens it would make (Squirreled Away, 2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    shaman = test_card("Wolf-Skull Shaman")
    squirrels = Counter({"squirrel": 25, "elf": 4, "shaman": 1})
    assert gated_without_feed(shaman, squirrels, Counter())
    elves = Counter({"elf": 12})
    assert not gated_without_feed(shaman, elves, Counter())


def test_a_listed_type_choice_is_fed_only_by_a_listed_tribe():
    """Dawn-Blessed Pennant chooses among Elemental, Elf, Faerie, Giant,
    Goblin, Kithkin, Merfolk and Treefolk: Most Wanted's twelve Humans feed
    nothing it can name (2026-11-02); a free choice (Vanquisher's Banner)
    takes any tribe."""
    from collections import Counter

    from mtg_utils._tuner.swaps import chooses_a_type_without_tribe

    humans, elves = Counter({"human": 12}), Counter({"elf": 12})
    pennant = test_card("Dawn-Blessed Pennant")
    assert chooses_a_type_without_tribe(pennant, humans)
    assert not chooses_a_type_without_tribe(pennant, elves)
    assert not chooses_a_type_without_tribe(test_card("Vanquisher's Banner"), humans)


def test_tokens_of_a_type_are_fed_by_their_makers_not_the_types_cards():
    """Gleaming Overseer's "Zombie tokens you control have hexproof and
    menace" waits on Zombie tokens: Cavalry Charge's seven Zombie cards make
    none (2026-11-02). Six makers of Zombie tokens feed it."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    overseer = test_card("Gleaming Overseer")
    zombies = Counter({"zombie": 7})
    assert gated_without_feed(overseer, zombies, Counter())
    assert not gated_without_feed(overseer, zombies, Counter({"zombie tokens": 6}))


def test_a_triggers_granted_static_and_an_attraction_are_its_gates():
    """Chocobo Knights' attack trigger grants double strike to "creatures you
    control with counters on them": three counter makers don't feed it
    (Cavalry Charge, 2026-11-02). Squirrel Squatters opens an Attraction,
    which a player does only with an Attraction deck (CR 701.51a)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    knights = test_card("Chocobo Knights")
    assert gated_without_feed(
        knights, Counter(), Counter(), Counter({"plus_one_makers": 3})
    )
    assert not gated_without_feed(
        knights, Counter(), Counter(), Counter({"plus_one_makers": 8})
    )
    assert gated_without_feed(test_card("Squirrel Squatters"), Counter(), Counter())


def test_a_narrow_sweep_is_no_upgrade_of_a_whole_board_one():
    """Aetherize returns only the attacking creatures: cheaper than Fumigate,
    it is still no upgrade of a sweep of the whole board (Counter
    Intelligence, 2026-11-02); Wrath of God is."""
    fumigate = _real_cc("Fumigate", "spine", roles=["board_wipe"], edhrec_rank=8000)
    assert not _upgrades(_played("Aetherize", 10), fumigate, "board_wipe")
    assert _upgrades(_played("Wrath of God", 10), fumigate, "board_wipe")


def test_a_one_shot_spell_is_no_upgrade_of_a_job_engine():
    """Vanquisher's Banner draws on every creature spell of the chosen type;
    And They Shall Know No Fear is one turn of +1/+0 and indestructible, and
    draws nothing: no upgrade of the Banner's slot (Cavalry Charge,
    2026-11-02). A creature the read can't see is not held to it."""
    banner = _real_cc(
        "Vanquisher's Banner", "spine", roles=["card_draw"], edhrec_rank=8000
    )
    assert not _upgrades(_played("And They Shall Know No Fear", 10), banner, None)


def test_a_cards_own_tokens_feed_only_their_own_type():
    """Invisible Woman, Sue Storm waits on counters on "other Heroes you
    control"; her Wall tokens are no Heroes, so a deck with none leaves her
    trigger dead (Abzan Armor, 2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    sue = test_card("Invisible Woman, Sue Storm")
    assert gated_without_feed(sue, Counter(), Counter())
    assert not gated_without_feed(sue, Counter({"hero": 8}), Counter())


def test_a_redirect_that_copies_is_no_copy_of_a_creature_commanders_spell():
    """Wyll's Reversal copies a "spell or ability with one or more targets":
    Nelly Borca's creature spell has none, so it copies her targeted attack
    trigger at most, never her spell (Blame Game, 2026-11-02)."""
    from mtg_utils._analysis.multipliers import Commander, multiplier_reasons

    reasons = multiplier_reasons(
        test_card("Wyll's Reversal"),
        Commander(test_card("Nelly Borca, Impulsive Accuser")),
    )
    assert reasons
    assert all(r.kind != "copy_commander_spell" for r in reasons)


def test_a_wipe_sparing_the_decks_board_is_never_traded_for_a_symmetric_one():
    """Winds of Rath spares enchanted creatures: under ten Auras it is
    one-sided, and Wrath of God is no upgrade of it there, however the read
    weighs the two (Virtue and Valor, 2026-11-02). A sweep that only kills
    small creatures (Contagion Engine) is no upgrade of one that kills the
    board (Starstorm)."""
    from mtg_utils._analysis.job_quality import read_for
    from mtg_utils._tuner.swaps import _spares_less_of_the_deck, _sweeps_fewer_kinds

    auras = [test_card("Ethereal Armor")] * 10
    assert _spares_less_of_the_deck(
        test_card("Wrath of God"), test_card("Winds of Rath"), auras
    )
    assert not _spares_less_of_the_deck(
        test_card("Wrath of God"), test_card("Winds of Rath"), auras[:3]
    )
    assert _sweeps_fewer_kinds(
        read_for("board_wipe"), test_card("Contagion Engine"), test_card("Starstorm")
    )


def test_a_static_working_only_beside_a_type_is_gated_on_it():
    """Gravecrawler casts from your graveyard "as long as you control a
    Zombie": a deck without Zombies never recasts it (Necron Dynasties,
    2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    crawler = test_card("Gravecrawler")
    assert gated_without_feed(crawler, Counter(), Counter())
    assert not gated_without_feed(crawler, Counter({"zombie": 12}), Counter())


def test_a_power_line_that_kills_the_commander_is_no_one_sided_sweep():
    """Dusk spares a deck of small creatures but kills Ellivere of the Wild
    Court: under her, Winds of Rath (one-sided under ten Auras) is not
    upgraded to it (Virtue and Valor, 2026-11-02). Under Kaust, Eyes of the
    Glade (power 2) Dusk stays one-sided."""
    from mtg_utils._tuner.swaps import _spares_less_of_the_deck

    auras = [test_card("Ethereal Armor")] * 10 + [test_card("Wall of Omens")] * 10
    dusk, winds = test_card("Dusk // Dawn"), test_card("Winds of Rath")
    ellivere = test_card("Ellivere of the Wild Court")
    assert _spares_less_of_the_deck(dusk, winds, auras, [ellivere])
    walls = [test_card("Wall of Omens")] * 20
    wrath = test_card("Wrath of God")
    assert _spares_less_of_the_deck(
        wrath, dusk, walls, [test_card("Kaust, Eyes of the Glade")]
    )
    assert not _spares_less_of_the_deck(wrath, dusk, walls, [ellivere])


def test_a_power_line_spares_nothing_in_a_deck_built_on_attachments():
    """Ten Auras grow the creatures they enchant past their printed power:
    Dusk kills Killian's enchanted attackers, so it is no one-sided sweep
    there (Silverquill Influence, 2026-11-02)."""
    from mtg_utils._analysis.job_quality import board_wipe

    small = [test_card("Wall of Omens")] * 10
    dusk = test_card("Dusk // Dawn")
    assert board_wipe.features(dusk, small)["one_sided"] == 1.0
    auras = small + [test_card("Ethereal Armor")] * 10
    assert board_wipe.features(dusk, auras)["one_sided"] == 0.0


def test_a_tap_creatures_cost_gates_the_ability_on_their_type():
    """High Perfect Morcant's proliferate costs "tap three untapped Elves you
    control", and its trigger waits on another Elf entering: a deck of three
    Elves feeds neither (Blight Curse, 2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    morcant = test_card("High Perfect Morcant")
    assert gated_without_feed(morcant, Counter({"elf": 3}), Counter())
    assert not gated_without_feed(morcant, Counter({"elf": 12}), Counter())


def test_a_non_type_trigger_is_fed_by_the_decks_other_creatures():
    """Winota, Joiner of Forces waits on "a non-Human creature you control"
    attacking: a deck of Humans never feeds it (Riders of Rohan,
    2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    winota = test_card("Winota, Joiner of Forces")
    humans = Counter({"human": 28})
    assert gated_without_feed(winota, humans, Counter({"creature": 31}))
    assert not gated_without_feed(winota, humans, Counter({"creature": 40}))


def test_a_chosen_type_read_off_spells_takes_the_printed_tribes():
    """Omo makes a creature with an everything counter every type, on the
    battlefield only: Herald's Horn's discount and reveal look at spells and
    library cards, so a deck of four Hydras doesn't feed it; Coat of Arms and
    Distant Melody read your permanents (Tricky Terrain, 2026-11-02)."""
    from mtg_utils._tuner.swaps import _chosen_type_on_battlefield

    assert not _chosen_type_on_battlefield(test_card("Herald's Horn"))
    assert _chosen_type_on_battlefield(test_card("Coat of Arms"))
    assert _chosen_type_on_battlefield(test_card("Distant Melody"))
    assert _chosen_type_on_battlefield(test_card("Vanquisher's Banner"))


def test_a_wipe_role_with_no_creature_sweep_is_upgraded_as_interaction():
    """Maelstrom Pulse's "all other permanents with the same name" and
    Dismantling Wave's artifact-and-enchantment cycling sweep no creatures:
    their job is interaction, never the wipe page (Squirreled Away, Avengers
    Assemble, 2026-11-02)."""
    from mtg_utils._tuner.issues import upgrade_job

    roles = {"board_wipe", "interaction"}
    assert upgrade_job(roles, test_card("Maelstrom Pulse")) == "interaction"
    assert upgrade_job(roles, test_card("Dismantling Wave")) == "interaction"
    assert upgrade_job({"board_wipe"}, test_card("Wrath of God")) == "board_wipe"


def test_a_tribe_slot_takes_only_creatures():
    """A party counts creatures (CR 700.8): Diviner's Wand, a Kindred Wizard
    Equipment, is no Wizard for Nalia's slot (Party Time, 2026-11-02)."""
    from mtg_utils._tuner.issues import _tribe_member_filter

    member = _tribe_member_filter("Wizard")
    assert not member(test_card("Diviner's Wand"))
    assert member(test_card("Archmage Emeritus"))


def test_a_wipe_the_commander_survives_is_never_traded_for_one_that_kills_it():
    """The Day of the Doctor's chapter IV: "Choose up to three Doctors. You
    may exile all other creatures" keeps the Tenth Doctor; The Battle of
    Bywater's "power 3 or greater" kills him (Timey Wimey, 2026-11-02). Under
    a commander that is no Doctor the Day keeps nothing of note."""
    from mtg_utils._tuner.swaps import _spares_less_of_the_deck

    deck = [test_card("Colossal Dreadmaw")] * 20
    day, battle = test_card("The Day of the Doctor"), test_card("The Battle of Bywater")
    tenth = test_card("The Tenth Doctor")
    assert _spares_less_of_the_deck(battle, day, deck, [tenth])
    # "Destroy all other creatures" spares its own Soldiers, not the Doctor.
    assert _spares_less_of_the_deck(test_card("Martial Coup"), day, deck, [tenth])
    assert not _spares_less_of_the_deck(
        battle, day, deck, [test_card("Ellivere of the Wild Court")]
    )


def test_a_count_sized_trigger_is_gated_on_the_counted_types():
    """Valley Rotcaller drains for "the number of other Squirrels, Bats,
    Lizards, and Rats you control": dead without them (Most Wanted),
    live in a Squirrel deck (Squirreled Away, 2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    rotcaller = test_card("Valley Rotcaller")
    assert gated_without_feed(rotcaller, Counter({"rat": 1}), Counter())
    assert not gated_without_feed(rotcaller, Counter({"squirrel": 12}), Counter())


def test_an_equipment_back_face_is_equipment():
    """Harvest Hand returns as Scrounged Scythe, an Equipment: a voltron page
    under an Aura commander drops it (Virtue and Valor, 2026-11-02)."""
    from mtg_utils._tuner.issues import _is_equipment

    assert _is_equipment(test_card("Harvest Hand // Scrounged Scythe"))
    assert not _is_equipment(test_card("Snake Umbra"))


def test_a_trigger_on_any_token_waits_on_token_makers():
    """Mirkwood Bats drains "whenever you create or sacrifice a token":
    dead without token makers (Endless Punishment, 2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    bats = test_card("Mirkwood Bats")
    assert gated_without_feed(bats, Counter(), Counter(), Counter({"token_maker": 2}))
    assert not gated_without_feed(
        bats, Counter(), Counter(), Counter({"treasure_makers": 6})
    )


def test_creature_removal_and_ramp_are_held_to_what_the_cut_does():
    """Return to Nature answers no creature, so it is no upgrade of Lethal
    Scheme (Sultai Arisen); Exploration Broodship's station-gated land drop
    is a quarter of Careful Cultivation's mana a turn (Virtue and Valor,
    2026-11-02). A counterspell is outside the creature test."""
    from mtg_utils._tuner.swaps import _reads_worse_at_the_job

    assert _reads_worse_at_the_job(
        test_card("Return to Nature"), test_card("Lethal Scheme"), "interaction", []
    )
    assert not _reads_worse_at_the_job(
        test_card("Counterspell"), test_card("Lethal Scheme"), "interaction", []
    )
    assert _reads_worse_at_the_job(
        test_card("Exploration Broodship"), test_card("Careful Cultivation"), "ramp", []
    )


def test_life_above_the_starting_total_waits_on_lifegain():
    """Doctor Strange, Surgeon pumps only "if you have at least 10 life more
    than your starting life total": dead under three lifegain cards
    (Avengers Assemble, 2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import gated_without_feed

    strange = test_card("Doctor Strange, Surgeon")
    assert gated_without_feed(
        strange, Counter(), Counter(), Counter({"lifegain_makers": 3})
    )
    assert not gated_without_feed(
        strange, Counter(), Counter(), Counter({"lifegain_makers": 9})
    )


def test_a_cheaper_card_is_a_tempo_upgrade_only_while_it_keeps_the_job():
    """Key to the City's discard-to-untap draw keeps under 0.4 of Smuggler's
    Share at card draw, so cheaper is no excuse (Blame Game, 2026-11-02);
    Duplicant keeps about half of Meteor Golem and stays a tempo upgrade."""
    from mtg_utils._tuner.swaps import _reads_worse_at_the_job

    assert _reads_worse_at_the_job(
        test_card("Key to the City"), test_card("Smuggler's Share"), "card_draw", []
    )
    assert not _reads_worse_at_the_job(
        test_card("Duplicant"), test_card("Meteor Golem"), "interaction", []
    )


def test_a_card_that_stops_land_plays_is_read():
    """Aggressive Mining: "You can't play lands" (World Shaper, 2026-11-02)."""
    from mtg_utils._tuner.swaps import _stops_land_plays

    assert _stops_land_plays(test_card("Aggressive Mining"))
    assert not _stops_land_plays(test_card("Sol Ring"))


def test_a_card_paying_a_creature_is_no_cheaper():
    """Fling is a mana cheaper than Fiend Hunter but asks a creature too, so
    it is no tempo upgrade (Riders of Rohan, 2026-11-02)."""
    from mtg_utils._tuner.swaps import _reads_worse_at_the_job

    assert _reads_worse_at_the_job(
        test_card("Fling"), test_card("Fiend Hunter"), "interaction", []
    )


def test_the_answered_targets_controller_acts_by_the_abilitys_scope():
    """ "Destroy target creature or planeswalker. Its controller investigates"
    (Fateful Absence) is the answered player's, by the ability's
    ``player_scope``; so is Unwanted Remake's manifest dread once corrected;
    Tasha's Hideous Laughter steals nothing you may cast."""
    from mtg_utils._card_ir.crosswalk.reads import acts_for_answered_target, tag_of
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_signals

    def answered(card, tag):
        (tree,) = trees_for(card)
        return any(
            acts_for_answered_target(u, c.node)
            for u in tree.units
            for c in u.effects
            if tag_of(c.node) == tag
        )

    assert answered(test_card("Fateful Absence"), "Investigate")
    assert answered(test_card("Unwanted Remake"), "ManifestDread")
    signals = test_signals("Tasha's Hideous Laughter")
    assert not any(sig.key == "theft_makers" for sig in signals)


def test_an_add_the_commander_already_grants_is_dead():
    """Felothar the Steadfast lets "Creatures you control ... attack as
    though they didn't have defender": Rolling Stones's Walls-only grant does
    nothing more (Abzan Armor, 2026-11-02); Behind the Scenes's skulk does."""
    from mtg_utils._tuner.swaps import _commander_already_grants

    felothar = [test_card("Felothar the Steadfast")]
    assert _commander_already_grants(test_card("Rolling Stones"), felothar)
    assert _commander_already_grants(test_card("Animate Wall"), felothar)
    assert not _commander_already_grants(test_card("Behind the Scenes"), felothar)


def test_an_add_whose_fuel_the_proposal_cuts_is_dropped():
    """Losheel, Clockwork Scholar draws when artifact creatures enter: added
    to a deck of Ornithopters, it runs; when the same proposal cuts the
    Ornithopters for bears, it doesn't (2026-11-02)."""
    from types import SimpleNamespace

    from mtg_utils._tuner.swaps import _unfueled_adds

    thopter, bear = test_card("Ornithopter"), test_card("Grizzly Bears")
    losheel = test_card("Losheel, Clockwork Scholar")
    deck = [thopter] * 8 + [bear] * 8
    cut = SimpleNamespace(name="Ornithopter")
    keep = [(cut, losheel, 0.0, False)]
    assert _unfueled_adds(keep, deck) == []
    gut = keep + [(cut, bear, 0.0, False)] * 7
    assert _unfueled_adds(gut, deck) == [0]


def test_a_battlefield_chosen_type_draw_is_fed_under_omo():
    """Kindred Discovery draws when "a creature you control of the chosen
    type enters or attacks": no tribe in a deck of spells feeds it, unless
    Omo, Queen of Vesuva makes its creatures every type (Tricky Terrain,
    2026-11-02)."""
    from types import SimpleNamespace

    from mtg_utils._tuner.swaps import _unfueled_adds

    deck = [test_card("Lightning Bolt")] * 30 + [test_card("Grizzly Bears")]
    add = [
        (
            SimpleNamespace(name="Lightning Bolt"),
            test_card("Kindred Discovery"),
            0.0,
            False,
        )
    ]
    assert _unfueled_adds(add, deck) == [0]
    assert _unfueled_adds(add, deck, [test_card("Omo, Queen of Vesuva")]) == []


def test_a_card_milling_only_opponents_fills_no_graveyard_of_yours():
    """Mindcrank's "that player mills that many cards" reaches only an
    opponent's library: dead in Szarekh's self-mill deck (Necron Dynasties,
    2026-11-02); Perpetual Timepiece's "Mill two cards" is yours."""
    from mtg_utils._tuner.swaps import _mills_only_opponents

    assert _mills_only_opponents(test_card("Mindcrank"))
    assert _mills_only_opponents(test_card("Altar of the Brood"))
    assert not _mills_only_opponents(test_card("Perpetual Timepiece"))


def test_an_entering_tribe_trigger_counts_printed_types_under_omo():
    """Dragon Tempest deals damage "whenever a Dragon you control enters":
    Omo's everything counters are on creatures already out, so under Omo the
    trigger waits on the deck's printed Dragons — Elvish Warmaster's Elves
    went to Tricky Terrain so (2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import _Tribes, _unit_gates

    gated = _unit_gates(test_card("Dragon Tempest"))
    gate = next(g for g in gated.gates if g.entering and "dragon" in g.words)
    tribes = _Tribes({"dragon": 20})
    tribes.printed = Counter({"dragon": 2})
    assert not gated.fed(gate, tribes, Counter(), Counter())
    assert gated.fed(gate, Counter({"dragon": 20}), Counter(), Counter())


def test_a_mono_colour_dork_is_no_upgrade_to_a_fixer_in_three_colours():
    """Ignoble Hierarch taps for {B}, {R} or {G}; Llanowar Elves only {G}:
    no upgrade under a three-colour commander (Graveyard Overdrive's Disa,
    2026-11-02), whatever the read's small weight on fixing says."""
    from mtg_utils._tuner.swaps import _reads_worse_at_the_job

    hierarch, elves = test_card("Ignoble Hierarch"), test_card("Llanowar Elves")
    jund = [test_card("Disa the Restless")]
    assert _reads_worse_at_the_job(elves, hierarch, "ramp", None, jund)


def test_a_symmetric_bounce_is_no_upgrade_to_a_kill():
    """Slinn Voda's kicked "return all creatures to their owners' hands" for
    Oversimplify's "Exile all creatures" (Quandrix Unlimited, 2026-11-02):
    the creatures come back. Cyclonic Rift's overload bounces only theirs."""
    from mtg_utils._tuner.swaps import _bounces_for_a_kill

    kill = test_card("Oversimplify")
    bears = [test_card("Grizzly Bears")] * 10
    assert _bounces_for_a_kill(test_card("Slinn Voda, the Rising Deep"), kill, bears)
    assert not _bounces_for_a_kill(test_card("Cyclonic Rift"), kill, bears)
    # Wave Goodbye spares creatures with +1/+1 counters: none in a deck of
    # bears (Revenant Recon's three counter cards, 2026-11-02).
    assert _bounces_for_a_kill(test_card("Wave Goodbye"), kill, bears)


def test_a_self_mill_deck_holds_mostly_its_own_mill():
    """A deck milling itself (Stitcher's Supplier) stays one with an
    opponent-mill card among them; half and half it is no longer
    (2026-11-02)."""
    from mtg_utils._tuner.swaps import _self_mill_deck

    own = _real_cc("Stitcher's Supplier", "theme")
    theirs = _real_cc("Mindcrank", "theme")
    assert _self_mill_deck([own] * 7 + [theirs])
    assert not _self_mill_deck([own] * 4 + [theirs] * 4)


def test_a_dropped_adds_cut_takes_the_next_fueled_add():
    """When the whole-proposal recheck drops an add the final deck can't fuel
    (Losheel, Clockwork Scholar's artifact-creature draw in a deck of bears),
    its cut takes the search's next add the deck does fuel (2026-11-02)."""
    from types import SimpleNamespace

    from mtg_utils._tuner.swaps import _next_fueled_add

    deck = [test_card("Grizzly Bears")] * 12
    order = [test_card("Losheel, Clockwork Scholar"), test_card("Divination")]
    unfueled: set[str] = set()

    def find_add(_spec, **_options):
        for card in order:
            if card["name"] not in unfueled:
                return card, 0.0, False
        return None

    cut = SimpleNamespace(name="Grizzly Bears")
    picked = _next_fueled_add(({}, {}), cut, find_add, [], deck, (), unfueled)
    assert picked is not None
    assert picked[0]["name"] == "Divination"
    assert "Losheel, Clockwork Scholar" in unfueled
    assert _next_fueled_add(None, cut, find_add, [], deck, (), set()) is None


def test_a_return_of_your_gear_waits_on_the_decks_gear():
    """Forge Anew's "return target Equipment card from your graveyard" (its
    instant-speed equip unparsed) is dead in a deck with no Equipment —
    Snake Umbra's slot in Virtue and Valor went to it (2026-11-02)."""
    from collections import Counter

    from mtg_utils._tuner.swaps import dead_payoff

    forge = test_card("Forge Anew")
    auras = Counter({"creature": 30, "aura": 20})
    gear = Counter({"creature": 30, "equipment": 10})
    assert dead_payoff(forge, Counter(), Counter(), auras)
    assert not dead_payoff(forge, Counter(), Counter(), gear)
