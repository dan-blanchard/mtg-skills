"""Lane decisions taken after the phase v0.131.0 pin bump (2026-11-24): reads
that changed which cards carry a signal, each by a rule of the lane's own."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import iter_static_defs, static_def_scales_up
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _static_defs(name: str) -> list:
    return [
        sdef
        for tree in trees_for(test_card(name))
        for unit in tree.units
        for sdef in iter_static_defs(unit.node)
    ]


# ── A counted pump is a pump, whichever way phase writes it ─────────────────────


@pytest.mark.parametrize(
    ("name", "targeted"),
    [
        # "gets +1/+0 for each card you've drawn this turn"
        ("Fists of Flame", True),
        # "gets +X/+0, where X is its power"
        ("Berserk", True),
        # "creatures you control … get +X/+X … where X is the number of creatures"
        ("Craterhoof Behemoth", False),
    ],
)
def test_a_counted_pump_is_a_pump_maker(name, targeted):
    idents = _idents(name)
    assert ("pump_makers", "you", "") in idents
    assert (("pump_makers", "you", "target") in idents) is targeted


@pytest.mark.parametrize(
    "name",
    [
        # begin combat: "+1/+1 for each card type among cards in your graveyard"
        "Ursine Monstrosity",
        # begin combat: "another target creature you control … gets +X/+X"
        "Xenagos, God of Revels",
        # attacks: "creatures you control … get +X/+X"
        "Pathbreaker Ibex",
    ],
)
def test_a_counted_combat_pump_is_a_combat_buff(name):
    assert ("combat_buff_engine", "you", "") in _idents(name)


def test_a_counted_shrink_is_no_raise():
    # Toxrill, the Corrosive: "Creatures you don't control get -1/-1 for each
    # slime counter on them" — a ``Multiply`` by a negative factor.
    assert not any(
        static_def_scales_up(d) for d in _static_defs("Toxrill, the Corrosive")
    )
    assert any(static_def_scales_up(d) for d in _static_defs("Craterhoof Behemoth"))
