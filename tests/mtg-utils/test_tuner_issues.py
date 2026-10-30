"""Tuning issues carry their own remedy (``_tuner.issues``): ``Sourcing`` is the one
owner of "is this actionable, and how" for all three swap-sourcing paths."""

import pytest

from mtg_utils._tuner.issues import (
    CUT_FILLER,
    CUT_GENERIC,
    CUT_UPGRADE,
    PROTECTION_SEARCH,
    ROLE_SEARCH,
    WINCON_SEARCH,
    Sourcing,
    cut_over,
    keep_search,
    top_issues,
)
from mtg_utils.testkit import test_card


def _band(current, lo, hi, **extra):
    dev = current - hi if current > hi else (current - lo if current < lo else 0)
    return {"current": current, "min": lo, "max": hi, "deviation": dev, **extra}


def _focus(viable=(), emerging=(), stranded=(), verdict="FOCUSED", **extra):
    return {
        "viable_avenues": list(viable),
        "emerging": list(emerging),
        "stranded_avenues": list(stranded),
        "verdict": verdict,
        "filler": 0,
        "low_value": 0,
        **extra,
    }


# combo-search's near-miss shape: one named card short of a Spellbook combo.
_NEAR_MISS = {
    "cards": ["Painter's Servant", "Grindstone"],
    "result": ["Infinite mill"],
    "missing_card": "Grindstone",
}


def _every_issue():
    """One scorecard that trips every kind ``top_issues`` can emit."""
    budgets = {
        "ramp": _band(2, 10, 12),
        "interaction": _band(15, 10, 12),
    }
    focus_r = _focus(
        viable=[{"label": "Goblins"}],
        emerging=[{"label": "Tokens", "depth": 6}],
        stranded=["Noise"],
        verdict="SPREAD-THIN",
        filler=6,
        upgrade_cards=["Clunky Removal"],
        lane_upgrade_cards=["Vamp 9", "Vamp 10"],
    )
    return top_issues(
        efficiency_r={"verdict": "thin top-end"},
        focus_r=focus_r,
        template_r={
            "short": {"ramp": budgets["ramp"]},
            "over": {"interaction": budgets["interaction"]},
        },
        wincons_r={
            "status": "low",
            "count": 0,
            "target": [2, 4],
            "life": 25,
            "voltron_needs_real_damage": True,
        },
        protection_r={"status": "low", "count": 0, "target": 3},
        commander_r={"misfit": True, "serves_viable": [], "viable_count": 1},
        sourcing=Sourcing(focus_r, [], budgets, keep={"_serve": None}),
        near_misses=[_NEAR_MISS],
    )


def test_a_near_miss_outranks_dead_weight_only_when_it_ends_the_game():
    from mtg_utils.combo_search import ends_the_game

    def near(*result):
        return {"cards": ["A", "B"], "result": list(result), "missing_card": "B"}

    assert ends_the_game(near("Infinite mill"))
    assert ends_the_game(near("Each opponent loses the game"))
    assert ends_the_game(near("Infinite damage", "Infinite storm count"))
    # Value lines, and a line bounded by a life total: a nudge, not the best swap.
    assert not ends_the_game(near("Infinite colorless mana", "Infinite storm count"))
    assert not ends_the_game(near("Near-infinite lifegain"))
    assert not ends_the_game(near("Near-infinite damage to all players"))
    assert not ends_the_game(near("Infinite creature ETB", "Infinite lifegain"))


def test_every_emitted_kind_has_a_decided_remedy():
    issues = {i.kind: i for i in _every_issue()}
    assert set(issues) == {
        "role_short",
        "role_over",
        "dead_weight",
        "under_supported_theme",
        "spread_thin",
        "wincon_short",
        "voltron_no_commander_damage",
        "protection_short",
        "efficiency",
        "commander_misfit",
        "near_miss_combo",
        "commander_keeps",
        "upgrade",
    }
    # No swap fixes a commander or a plan — and nothing else is silently unsourced
    # just because a kind was added without a branch.
    assert issues["commander_misfit"].remedy is None
    assert issues["voltron_no_commander_damage"].remedy is None
    assert issues["commander_misfit"].advisory is True
    assert issues["voltron_no_commander_damage"].advisory is True
    # Spine fills: efficiency-first, from the generic cut pool.
    short = issues["role_short"].remedy
    assert (short.spec, short.spine, short.cut_from) == (
        ROLE_SEARCH["ramp"],
        True,
        CUT_GENERIC,
    )
    prot = issues["protection_short"].remedy
    assert (prot.spec, prot.spine) == (PROTECTION_SEARCH, True)
    # A closer on the main lane (here no main avenue has a spec, so the closer
    # regex pages the search), narrowed to what the wincons metric counts.
    wincon = issues["wincon_short"].remedy
    assert {k: v for k, v in wincon.spec.items() if k != "_filter"} == WINCON_SEARCH
    assert callable(wincon.spec["_filter"])
    assert wincon.spine is False
    # A trim drains THAT role's excess (the pool holds exactly the excess:
    # one trim left Animated Army 13 ramp over its band, 2026-10-25); dead
    # weight drains the filler pool.
    over = issues["role_over"].remedy
    assert (over.cut_from, over.drain) == (cut_over("interaction"), True)
    dead = issues["dead_weight"].remedy
    assert (dead.cut_from, dead.drain) == (CUT_FILLER, True)
    assert not any(
        i.remedy.drain
        for k, i in issues.items()
        if i.remedy and k not in ("dead_weight", "upgrade", "role_over")
    )
    # A curve fix asks for the missing CMC band.
    assert issues["efficiency"].remedy.spec.get("cmc_min") == 6
    # A near-miss asks for exactly its missing card.
    near = issues["near_miss_combo"]
    assert near.remedy.spec == {"name": "Grindstone"}
    assert near.label == "Grindstone"
    assert near.severity == 9  # game-winning: above dead weight
    # The upgrade slots, off-lane and deep-lane together, rank last and drain
    # their own pool, then the lane's.
    upgrade = issues["upgrade"]
    assert (upgrade.severity, upgrade.count) == (1, 3)
    assert upgrade.remedy.cut_from == CUT_UPGRADE
    assert upgrade.remedy.spec_for_cut is not None
    assert upgrade.remedy.drain
    assert upgrade.remedy.lane_ok


def test_role_over_deepens_the_commanders_lane_before_an_emerging_theme():
    # A trimmed slot goes to the commander's own lane when the deck has one (the
    # Jace precon's trimmed rock becomes a polymorph piece), else to the first
    # emerging direction as before.
    from mtg_utils._analysis.signal_specs import spec_for
    from mtg_utils._analysis.signals import Signal

    cheat = Signal(key="cheat_into_play", scope="you", subject="", text="", source="x")
    prolif = Signal(
        key="proliferate_makers", scope="you", subject="", text="", source="x"
    )
    main, emerging = spec_for(cheat).label, spec_for(prolif).label
    budgets = {"ramp": _band(15, 10, 12)}
    held = Sourcing(
        _focus(
            viable=[{"label": main}],
            emerging=[{"label": emerging, "depth": 6}],
            commander_avenues=[main],
        ),
        [cheat, prolif],
        budgets,
    )
    assert held.remedy_for("role_over", role="ramp").spec == {
        **spec_for(cheat).search,
        "_serve": spec_for(cheat).serve,
        "_avenue": main,
    }
    unheld = Sourcing(
        _focus(viable=[{"label": main}], emerging=[{"label": emerging, "depth": 6}]),
        [cheat, prolif],
        budgets,
    )
    assert unheld.remedy_for("role_over", role="ramp").spec == {
        **spec_for(prolif).search,
        "_serve": spec_for(prolif).serve,
        "_avenue": emerging,
    }


def test_the_theme_is_shared_over_the_main_avenues_only():
    # Squirreled Away reads two mains (Squirrels, Sacrifice) and a sub (Go
    # wide): the theme's adds are shared by depth over the two mains, and a
    # sub keeps none.
    from mtg_utils._analysis.signal_specs import spec_for
    from mtg_utils._analysis.signals import Signal

    def sig(key):
        return Signal(key=key, scope="you", subject="", text="", source="x")

    sigs = [sig("cheat_into_play"), sig("proliferate_makers"), sig("token_maker")]
    first, second, sub = (spec_for(s).label for s in sigs)
    src = Sourcing(
        _focus(
            viable=[
                {"label": first, "tier": "main", "depth": 19},
                {"label": sub, "tier": "sub", "depth": 27},
                {"label": second, "tier": "main", "depth": 33},
            ]
        ),
        sigs,
        {},
    )
    assert [(label, depth) for label, depth, _spec in src.theme_avenues()] == [
        (first, 19),
        (second, 33),
    ]
    assert src.theme() == {**src.main_avenue(), "_share": True}
    assert src.main_avenue()["_avenue"] == first
    # Every remedy that deepens "the theme" asks for the shared theme.
    assert src.remedy_for("dead_weight").spec["_share"]
    assert src.remedy_for("spread_thin").spec["_share"]
    # A role-over trim still deepens one named avenue.
    assert "_share" not in src.remedy_for("role_over", role="ramp").spec


def test_with_no_viable_avenue_there_is_no_theme_to_share():
    src = Sourcing(_focus(), [], {})
    assert src.theme_avenues() == []
    assert src.theme() == {}
    assert src.remedy_for("spread_thin") is None


def test_issues_are_ranked_by_severity():
    severities = [i.severity for i in _every_issue()]
    assert severities == sorted(severities, reverse=True)


def test_an_unknown_kind_sources_nothing():
    assert Sourcing(_focus(), [], {}).remedy_for("not_a_kind") is None


def test_to_json_is_the_wire_shape_never_the_remedy():
    issues = {i.kind: i for i in _every_issue()}
    short = issues["role_short"].to_json()
    assert set(short) == {
        "kind",
        "role",
        "severity",
        "advisory",
        "grant_covered",
        "message",
    }
    assert short["advisory"] is False
    assert short["grant_covered"] is False
    assert set(issues["role_over"].to_json()) == {"kind", "role", "severity", "message"}
    assert set(issues["dead_weight"].to_json()) == {
        "kind",
        "severity",
        "count",
        "message",
    }
    assert set(issues["efficiency"].to_json()) == {
        "kind",
        "subkind",
        "severity",
        "message",
    }
    for issue in issues.values():
        assert "remedy" not in issue.to_json()


def test_a_grant_covered_role_sources_nothing_on_any_path():
    # ADR-0040 §1. The issue loop, the dead-weight redeploy and the fill pass all read
    # Sourcing — so the rule is stated (and tested) once, not once per path.
    budgets = {
        "card_draw": _band(
            0, 10, 12, grant_covered=True, grant_covered_by="Sliver Weftwinder"
        )
    }
    covered = Sourcing(_focus(), [], budgets)
    assert covered.grant_cover("card_draw") == "Sliver Weftwinder"
    assert covered.role_spec("card_draw") is None  # the fill pass
    assert covered.remedy_for("role_short", role="card_draw") is None  # issue loop
    assert covered.short_roles() == []
    assert covered.redeploy() is None  # the dead-weight redeploy
    assert not covered.has_redeploy_target()
    # The shortfall itself is never suppressed — it downgrades to advisory.
    issue = covered.issue("role_short", role="card_draw", severity=10, message="m")
    assert (issue.advisory, issue.grant_covered, issue.remedy) == (True, True, None)
    assert issue.severity == 10

    plain = Sourcing(_focus(), [], {"card_draw": _band(0, 10, 12)})
    assert plain.grant_cover("card_draw") is None
    assert plain.role_spec("card_draw") == ROLE_SEARCH["card_draw"]
    assert plain.short_roles() == ["card_draw"]
    assert plain.redeploy() == ROLE_SEARCH["card_draw"]
    assert plain.has_redeploy_target()


@pytest.mark.parametrize("role", ["lands", "not_a_role"])
def test_a_role_nothing_sources_has_no_spec(role):
    # `lands` short is the land tooling's job, never a Tune add.
    sourcing = Sourcing(_focus(), [], {role: _band(30, 36, 38)})
    assert sourcing.role_spec(role) is None
    assert sourcing.remedy_for("role_short", role=role) is None
    assert sourcing.short_roles() == []


def test_short_roles_are_worst_first():
    sourcing = Sourcing(
        _focus(),
        [],
        {"ramp": _band(8, 10, 12), "card_draw": _band(2, 10, 12)},
    )
    assert sourcing.short_roles() == ["card_draw", "ramp"]


def test_a_near_miss_short_a_generic_requirement_sources_nothing():
    """A missing template ("a Persist creature") isn't one card to add."""
    issues = top_issues(
        efficiency_r={"verdict": "ok"},
        focus_r=_focus(),
        template_r={"short": {}, "over": {}},
        wincons_r={"status": "ok"},
        protection_r={"status": "ok"},
        commander_r=None,
        sourcing=Sourcing(_focus(), [], {}),
        near_misses=[{"cards": ["A"], "result": ["x"], "missing_template": "B"}],
    )
    assert not [i for i in issues if i.kind == "near_miss_combo"]


def test_an_over_row_that_is_the_commanders_lane_is_advisory_and_unsourced():
    """Gimbal's rocks read "ramp over by 9": the row is the lane counted by
    another name — reported, never trimmed."""
    budgets = {"ramp": {**_band(21, 10, 12), "lane_row": True}}
    focus_r = _focus(viable=[{"label": "Artifacts"}], verdict="FOCUSED")
    issues = top_issues(
        efficiency_r={"verdict": "ok"},
        focus_r=focus_r,
        template_r={"short": {}, "over": {"ramp": budgets["ramp"]}},
        wincons_r={
            "status": "ok",
            "count": 4,
            "target": [2, 4],
            "life": 40,
            "voltron_needs_real_damage": False,
        },
        protection_r={"status": "ok", "count": 5, "target": 5},
        commander_r=None,
        sourcing=Sourcing(focus_r, [], budgets),
    )
    over = next(i for i in issues if i.kind == "role_over")
    assert over.advisory is True
    assert over.remedy is None
    assert "commander's own lane" in over.message


def test_interaction_is_sourced_only_where_the_role_counts_it():
    """An infect beater matches the ``creature-removal`` preset through its
    keyword, but ``role_of`` never counts it as interaction — so the interaction
    search's precision pass drops it, and a burn spell passes."""
    from mtg_utils._analysis.roles import _INTERACTION_PRESETS
    from mtg_utils._tuner.issues import ROLE_SEARCH
    from mtg_utils.testkit import test_card

    keep = ROLE_SEARCH["interaction"]["_filter"]
    assert ROLE_SEARCH["interaction"]["any_preset_names"] == _INTERACTION_PRESETS
    assert keep(test_card("Lightning Bolt"), deck_mana=None)
    assert not keep(test_card("Glistener Elf"), deck_mana=None)


def test_the_interaction_search_finds_any_of_its_presets():
    """The role counts a card matching ANY interaction preset, so the search must
    too: passed as ``preset_names`` the five presets combined with AND and the
    search found nothing — no removal fill or upgrade was sourced (2026-10-19)."""
    from mtg_utils._analysis.roles import _INTERACTION_PRESETS
    from mtg_utils.card_search import filter_records
    from mtg_utils.formats import FORMATS
    from mtg_utils.testkit import test_card

    names = ["Lightning Bolt", "Murder", "Counterspell", "Llanowar Elves"]
    records = [test_card(name) for name in names]

    def found(**presets):
        hits = filter_records(
            records, fmt=FORMATS["commander"], limit=10, sort="cmc-asc", **presets
        )
        return {c["name"] for c in hits}

    assert found(any_preset_names=_INTERACTION_PRESETS) == {
        "Lightning Bolt",
        "Murder",
        "Counterspell",
    }
    assert found(preset_names=_INTERACTION_PRESETS) == set()


def test_the_keep_is_sourced_only_under_a_commander_whose_tokens_go():
    """Saheeli, Radiant Creator's copies are sacrificed at the next end step: the
    keep page holds the instant-speed ends of the turn, held to the ones that keep
    them every turn (Sundial of the Infinite, not Time Stop — CR 724.1b, 608.2n).
    Krenko, Mob Boss's Goblins stay: nothing to keep."""
    assert keep_search([test_card("Krenko, Mob Boss")]) is None
    spec = keep_search([test_card("Saheeli, Radiant Creator")])
    assert spec is not None
    assert spec["_serve"].matches(test_card("Time Stop"))
    assert spec["_filter"](test_card("Sundial of the Infinite"))
    assert not spec["_filter"](test_card("Time Stop"))
    keep = Sourcing(_focus(), [], {}, keep=spec).remedy_for("commander_keeps")
    # One swap, which may take a jobless upgrade slot or a lane slot.
    assert (keep.spec, keep.lane_ok, keep.drain) == (spec, True, False)
    assert Sourcing(_focus(), [], {}).remedy_for("commander_keeps") is None


def test_a_tribe_the_commander_holds_shares_the_theme_whatever_its_tier():
    from mtg_utils._analysis.signal_specs import spec_for
    from mtg_utils._analysis.signals import Signal

    sigs = [
        Signal(key="graveyard_matters", scope="you", subject="", text="", source="x"),
        Signal(
            key="type_matters", scope="you", subject="Lhurgoyf", text="", source="x"
        ),
    ]
    main, tribe = (spec_for(s).label for s in sigs)
    src = Sourcing(
        _focus(
            viable=[
                {"label": main, "tier": "main", "depth": 28},
                {"label": tribe, "tier": "sub", "depth": 11},
            ],
            commander_tribes=[tribe],
        ),
        sigs,
        {},
    )
    assert [label for label, _d, _s in src.theme_avenues()] == [main, tribe]


def _held_sig(key, subject=""):
    from mtg_utils._analysis.signals import Signal

    return Signal(key=key, scope="you", subject=subject, text="", source="x")


def test_a_token_making_commander_also_searches_the_token_doublers_once():
    # Gimbal makes a Gremlin token each end step (Tinker Time): the token
    # doublers are the other side of that lane (CR 614.1a), one theme add,
    # asked by the depth of the deck's creature-token makers.
    from mtg_utils._analysis.signal_specs import _TOKEN_DOUBLER_EXTRA, spec_for

    main, gremlins = _held_sig("artifacts_matter"), _held_sig("token_maker", "Gremlin")
    focus = _focus(
        viable=[{"label": spec_for(main).label, "tier": "main", "depth": 49}]
    )
    emitters = {
        ("token_maker", "you", "Gremlin"): frozenset({"Gimbal", "Gremlin Maker"}),
        ("token_maker", "you", "Thopter"): frozenset({"Thopter Maker"}),
    }
    held = Sourcing(
        focus,
        [main, gremlins],
        {},
        commander_idents={("token_maker", "you", "Gremlin")},
        emitters=emitters,
    )
    label, depth, spec = held.theme_avenues()[-1]
    assert (label, depth) == (_TOKEN_DOUBLER_EXTRA.label, 3)
    assert (spec["_serve"], spec["_avenue"], spec["_cap"]) == (
        _TOKEN_DOUBLER_EXTRA.serve,
        label,
        1,
    )
    # Creature tokens: a doubler of every token or of creature tokens doubles them.
    assert spec["_filter"](test_card("Doubling Season"))
    assert spec["_filter"](
        test_card("Ojer Taq, Deepest Foundation // Temple of Civilization")
    )
    # The same lane, not the commander's own: no page.
    unheld = Sourcing(focus, [main, gremlins], {}, emitters=emitters)
    assert unheld.multiplier_avenue() is None
    assert [lbl for lbl, _d, _s in unheld.theme_avenues()] == [spec_for(main).label]


def test_a_polymorph_commanders_trim_is_a_cheap_token_spell():
    # Jace's -3 exiles a creature you control: two tokens for two mana are two
    # bodies. The lane's serve holds them, but as a sub it pages no theme add.
    from mtg_utils._analysis.signal_specs import spec_for

    cheat, fodder = _held_sig("cheat_into_play"), _held_sig("wants_fodder")
    focus = _focus(
        viable=[{"label": spec_for(cheat).label, "tier": "main", "depth": 19}],
        commander_avenues=[spec_for(cheat).label],
    )
    held = Sourcing(
        focus,
        [cheat, fodder],
        {},
        commander_idents={("wants_fodder", "you", "")},
    )
    spec = held.remedy_for("role_over", role="ramp").spec
    assert spec["_avenue"] == spec_for(fodder).label
    assert spec["_serve"].matches(test_card("Raise the Alarm"))
    # One body at a time, and three mana.
    assert not spec["_serve"].matches(test_card("Loyal Apprentice"))
    assert not spec["_serve"].matches(test_card("Hordeling Outburst"))
    # A printed mana value counts X as 0 (CR 202.3e).
    assert spec["_serve"].matches(test_card("Secure the Wastes"))
    assert not spec["_filter"](test_card("Secure the Wastes"))
    assert spec["_filter"](test_card("Raise the Alarm"))
    # The same lane on a deck card, not the commander's: its lane, as before.
    unheld = Sourcing(focus, [cheat, fodder], {})
    assert unheld.fodder_spec() is None
    assert unheld.remedy_for("role_over", role="ramp").spec["_avenue"] == (
        spec_for(cheat).label
    )


def test_a_clue_making_commander_gets_the_doublers_that_double_a_clue():
    # Morska investigates (Deep Clue Sea): a Clue maker's payoff side names the
    # token doublers (``metrics._cares_keys``), and a Clue is an artifact token
    # (CR 111.10f), so a creature-token doubler doubles none of it.
    src = Sourcing(
        _focus(),
        [_held_sig("clue_makers")],
        {},
        commander_idents={("clue_makers", "you", "")},
        emitters={("clue_makers", "you", ""): frozenset({"Morska", "Clue Maker"})},
    )
    _label, depth, spec = src.multiplier_avenue()
    assert depth == 2
    assert spec["_filter"](test_card("Doubling Season"))
    assert spec["_filter"](test_card("Primal Vigor"))
    assert not spec["_filter"](
        test_card("Ojer Taq, Deepest Foundation // Temple of Civilization")
    )


def test_a_token_copier_commander_takes_any_token_doubler():
    # Hazel copies a token each end step (Squirreled Away): whatever it copies,
    # a doubler of tokens doubles it, so the page is not filtered.
    src = Sourcing(
        _focus(),
        [_held_sig("token_copy_makers")],
        {},
        commander_idents={("token_copy_makers", "you", "")},
        emitters={("token_copy_makers", "you", ""): frozenset({"Hazel"})},
    )
    _label, depth, spec = src.multiplier_avenue()
    assert depth == 1
    assert "_filter" not in spec
