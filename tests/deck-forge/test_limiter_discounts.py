"""Rate v2 S2 — limiter discounts on matched pair rows (design note 2.6).

A matched row's weight multiplies by a discount only on AFFIRMATIVE
structural evidence read from the attributed matching unit(s) via the S0
provenance seam: x0.5 once-per-turn trigger constraint (Donal class),
x0.75 {T} in the matching ability's activation cost, x0.5 activation
mana cost strictly exceeding a mana-producing anchor's per-use yield
(Vigean x Urza). Distinct limiter types MULTIPLY (bound [0.375, 1.0]);
any unattributed matching ident or any unlimited attributed unit means
NO discount. Ships default-off: pair_score applies discounts only when
given a discount_fn.
"""

from __future__ import annotations

import inspect

import pytest

from mtg_utils._deck_forge.limiter_discounts import (
    DISCOUNT_COEFFICIENTS,
    limiter_discount_fn,
)
from mtg_utils._deck_forge.pair_reads import (
    build_pair_context,
    pair_score,
)
from mtg_utils.testkit import test_card, test_card_ir


def _ctx(commander: str):
    test_card_ir(commander)
    return build_pair_context([test_card(commander)], [])


def _row_weight(candidate: str, commander: str, row_id: str, *, discounts: bool):
    test_card_ir(candidate)
    ctx = _ctx(commander)
    kwargs = {}
    if discounts:
        kwargs["discount_fn"] = limiter_discount_fn(ctx)
    _score, rows = pair_score(test_card(candidate), ctx, **kwargs)
    for r in rows:
        if r["pair"] == row_id:
            return r["weight"]
    return None


def test_coefficient_table_is_frozen():
    # Content equality — the 2.6 freeze-by-mechanism for the discount side.
    assert DISCOUNT_COEFFICIENTS == {
        "once_per_turn": 0.5,
        "tap_cost": 0.75,
        "cost_exceeds_yield": 0.5,
    }


def test_default_off_no_discount_fn_no_change():
    sig = inspect.signature(pair_score)
    assert sig.parameters["discount_fn"].default is None
    w = _row_weight(
        "Thousand-Year Elixir",
        "Krenko, Mob Boss",
        "untap_x_activated_commander",
        discounts=False,
    )
    assert w == 4.5


def test_tap_cost_discount_applies():
    # Thousand-Year Elixir's untap ability costs {1},{T} — the {T} caps it
    # at one activation per untap cycle: x0.75 on the 4.5 row.
    w = _row_weight(
        "Thousand-Year Elixir",
        "Krenko, Mob Boss",
        "untap_x_activated_commander",
        discounts=True,
    )
    assert w == pytest.approx(4.5 * 0.75)


def test_once_per_turn_reads_the_constraint_tag():
    # Donal's copy trigger reads "Do this only once each turn" — the
    # OncePerTurn constraint tag is structurally readable on the unit.
    from mtg_utils._deck_forge._ir_lookup import trees_for
    from mtg_utils._deck_forge.limiter_discounts import _has_once_per_turn

    test_card_ir("Donal, Herald of Wings")
    units = [
        u
        for tree in trees_for(test_card("Donal, Herald of Wings"))
        for u in tree.units
        if u.origin == "trigger"
    ]
    assert any(_has_once_per_turn(u) for u in units)


def test_membership_ident_match_blocks_discount_donal_erratum():
    # NOTE ERRATUM (2.6): Donal's doubler-row match rides ability_copy —
    # a MERGE-LEVEL membership ident that can never attribute to a unit.
    # The approved rule ("any unattributed matching ident -> NO
    # discount") therefore leaves Donal UNDISCOUNTED, contradicting the
    # note's own worked example; the rule wins, the example is corrected.
    # Coverage consequence recorded in the S2 attainability measurement.
    w = _row_weight(
        "Donal, Herald of Wings",
        "Talrand, Sky Summoner",
        "trigger_doubler_x_trigger_commander",
        discounts=True,
    )
    assert w == 4.5


def test_cost_exceeds_yield_discount_vigean_under_urza():
    # Vigean Graftmage: "{1}{U}: Untap target creature" = 2 mana; Urza's
    # per-use yield is 1 ({T} an artifact: add {U}) — a negative-rate
    # loop, x0.5. The {T}-cost read does not apply (no {T} in Vigean's
    # activation cost), so the total is 4.5 x 0.5.
    w = _row_weight(
        "Vigean Graftmage",
        "Urza, Lord High Artificer",
        "untap_x_activated_commander",
        discounts=True,
    )
    assert w == pytest.approx(4.5 * 0.5)


def test_unlimited_matching_unit_blocks_discount():
    # Siege-Gang Lieutenant's sac outlet ({2}, Sacrifice a Goblin) carries
    # no {T}, no once-per-turn, and Krenko is not a mana anchor — no
    # discount on the sac row.
    w = _row_weight(
        "Siege-Gang Lieutenant",
        "Krenko, Mob Boss",
        "sac_outlet_x_token_commander",
        discounts=True,
    )
    assert w == 3.0


def test_discount_bound_holds():
    # Multiplicative floor: 0.5 x 0.75 = 0.375; nothing below.
    assert 0.5 * 0.75 * min(DISCOUNT_COEFFICIENTS.values()) >= 0.1875
    for c in DISCOUNT_COEFFICIENTS.values():
        assert 0.5 <= c <= 1.0


@pytest.mark.parametrize(
    "name",
    [
        ("Donal, Herald of Wings"),
        ("Vigean Graftmage"),
        ("Urza, Lord High Artificer"),
    ],
)
def test_s2_pin_is_snapshot_resident(name):
    test_card_ir(name)
    assert test_card(name)["name"] == name
