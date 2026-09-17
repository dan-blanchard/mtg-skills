"""Tuning issues carry their own remedy (``_tuner.issues``): ``Sourcing`` is the one
owner of "is this actionable, and how" for all three swap-sourcing paths."""

import pytest

from mtg_utils._tuner.issues import (
    CUT_FILLER,
    CUT_GENERIC,
    PROTECTION_SEARCH,
    ROLE_SEARCH,
    WINCON_SEARCH,
    Sourcing,
    cut_over,
    top_issues,
)


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
        sourcing=Sourcing(focus_r, [], budgets),
    )


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
    assert issues["wincon_short"].remedy.spec == WINCON_SEARCH
    assert issues["wincon_short"].remedy.spine is False
    # A trim cuts from THAT role's excess; dead weight drains the filler pool.
    assert issues["role_over"].remedy.cut_from == cut_over("interaction")
    dead = issues["dead_weight"].remedy
    assert (dead.cut_from, dead.drain) == (CUT_FILLER, True)
    assert not any(
        i.remedy.drain for k, i in issues.items() if i.remedy and k != "dead_weight"
    )
    # A curve fix asks for the missing CMC band.
    assert issues["efficiency"].remedy.spec.get("cmc_min") == 6


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
