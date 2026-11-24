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


# ── "Those creatures gain X" after a mass effect lands on that group ────────────


@pytest.mark.parametrize(
    ("name", "keyword"),
    [
        # "Put a +1/+1 counter on each creature you control. Those creatures
        # gain vigilance until end of turn."
        ("Ajani Goldmane", "vigilance"),
        # "Untap all creatures you control. They gain hexproof and
        # indestructible until end of turn."
        ("Join Shields", "hexproof"),
        # "Creatures you control get +1/+1 … those creatures gain indestructible"
        ("Break of Day", "indestructible"),
    ],
)
def test_a_grant_to_the_team_a_mass_effect_named_is_a_team_buff(name, keyword):
    idents = _idents(name)
    assert ("team_buff", "you", "") in idents
    assert ("team_buff", "you", keyword) in idents
    assert ("keyword_grant_target", "you", "") not in idents


def test_a_grant_to_part_of_the_team_names_its_keyword_only():
    # Sandstorm Salvager: "Put a +1/+1 counter on each creature token you
    # control. Those creatures gain trample" — your tokens, not the whole team.
    idents = _idents("Sandstorm Salvager")
    assert ("team_buff", "you", "trample") in idents
    assert ("team_buff", "you", "") not in idents


@pytest.mark.parametrize(
    "name",
    [
        # "Gain control of all creatures with power 4 or greater … Untap those
        # creatures. They gain haste": creatures you take, not your team.
        "Mob Rule",
        # "each attacking creature": no controller named.
        "Captain America, Skybound",
    ],
)
def test_a_grant_to_a_group_that_is_not_your_team_is_no_team_buff(name):
    assert not {i for i in _idents(name) if i[0] == "team_buff"}


def test_those_creatures_after_chosen_targets_stays_a_targeted_grant():
    # Arm the Cathars: three targeted pumps, then "Those creatures gain vigilance".
    idents = _idents("Arm the Cathars")
    assert ("keyword_grant_target", "you", "vigilance") in idents
    assert not {i for i in idents if i[0] == "team_buff"}


# ── A harm in a mode you need not choose is no drawback ─────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        # enters: "Choose one — • Exile … You gain 2 life. • Investigate. You
        # lose 2 life."
        "Commander Raffi Musiker",
        # dies: "Choose one — • Each opponent discards two cards and loses 2
        # life. • Put target non-Dragon creature card … You lose 2 life."
        "Junji, the Midnight Sky",
    ],
)
def test_a_harm_in_one_mode_of_several_is_no_drawback(name):
    assert not {i for i in _idents(name) if i[0] == "self_drawback"}


def test_modes_that_each_come_up_in_turn_keep_the_drawback():
    # Demonic Pact: "choose one that hasn't been chosen — … • You lose the game."
    assert ("self_drawback", "you", "harm") in _idents("Demonic Pact")


# ── A cast copy of a named card can be a permanent ──────────────────────────────


def test_a_cast_copy_of_a_named_card_is_a_battlefield_put():
    # Garth One-Eye: "Create a copy of the card with the chosen name. You may
    # cast the copy" — Shivan Dragon and Black Lotus among the names.
    assert ("permanent_etb", "you", "put") in _idents("Garth One-Eye")
