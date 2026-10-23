"""Phase D lane fixes in ``lanes/removal_tutors.py`` (2026-10-23): one-shot land
destruction by kind, the creature-killing sweep and the mass creature return a
mass-death turn wants, colour hosers read off the cards' filters, granted
banding, and the side of a targeting cast trigger. Real cards via
``mtg_utils.testkit``."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


# ── (1) land_destruction: one-shot land answers, by kind ─────────────────────


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Stone Rain", "destroy"),
        ("Strip Mine", "destroy"),
        ("Armageddon", "destroy"),
        ("Crumble to Dust", "exile"),
        ("Aven Fogbringer", "bounce"),
        ("Plow Under", "tuck"),
        ("Wildfire", "sacrifice"),
    ],
)
def test_a_land_answer_carries_its_kind(name, kind):
    assert f"land_destruction|you|{kind}" in _idents(name)


def test_destroying_your_own_lands_is_not_land_destruction():
    """Return of the Nightstalkers destroys "all Swamps you control" — a cost of
    its own reanimation, not an answer to an opponent's land."""
    assert not any(
        i.startswith("land_destruction|")
        for i in _idents("Return of the Nightstalkers")
    )


def test_a_one_shot_land_answer_is_not_mass_land_denial():
    """Stone Rain takes one land; the brackets' read stays Armageddon's."""
    assert not any(i.startswith("mass_land_denial|") for i in _idents("Stone Rain"))
    assert "mass_land_denial|each|destroy" in _idents("Armageddon")


# ── (2) mass_death_payoff's serve: sweeps that kill, mass creature returns ────


@pytest.mark.parametrize("name", ["Wrath of God", "Damn", "Mass Calcify"])
def test_a_creature_killing_sweep_carries_the_creature_subject(name):
    idents = _idents(name)
    assert "mass_removal|you|" in idents
    assert "mass_removal|you|creature" in idents


@pytest.mark.parametrize("name", ["Shatterstorm", "Farewell"])
def test_a_sweep_no_creature_dies_to_has_no_creature_subject(name):
    """Shatterstorm kills no creature; Farewell exiles them, so none dies (CR
    700.4: dies means put into a graveyard from the battlefield)."""
    idents = _idents(name)
    assert "mass_removal|you|" in idents
    assert "mass_removal|you|creature" not in idents


def test_the_creature_subject_never_widens_mass_removal():
    """Massacre Wurm's one-sided -2/-2 is not a card the mass_removal lane reads,
    so it takes no subject of that key either."""
    assert not any(i.startswith("mass_removal|") for i in _idents("Massacre Wurm"))


@pytest.mark.parametrize("name", ["Storm of Souls", "Living Death"])
def test_a_whole_graveyard_creature_return_is_mass_recursion(name):
    assert "creature_recursion|you|mass" in _idents(name)


def test_a_single_reanimation_is_not_mass_recursion():
    idents = _idents("Reanimate")
    assert "creature_recursion|you|battlefield" in idents
    assert "creature_recursion|you|mass" not in idents


# ── (3) color_hoser: read off the cards' colour filters ──────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Mass Calcify",  # destroy all nonwhite creatures
        "Light of Day",  # black creatures can't attack or block
        "Crovax, Ascendant Hero",  # nonwhite creatures get -1/-1
        "Pyroblast",  # counter target spell if it's blue
        "Possessed Aven",  # a granted "Destroy target blue creature"
    ],
)
def test_a_color_hoser_is_read_off_its_filters(name):
    assert "color_hoser|you|" in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Eiganjo Free-Riders",  # returns a white creature YOU control
        "Call to the Netherworld",  # a black creature card from your graveyard
        "Terror",  # "nonblack" lets one target be almost anything
        "Akroma, Angel of Wrath",  # printed protection from black and red
    ],
)
def test_a_color_word_that_hoses_no_opponent_is_not_a_hoser(name):
    assert "color_hoser|you|" not in _idents(name)


# ── (4) has_banding: granted banding and "bands with other" ──────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Battering Ram",  # gains banding itself
        "Baton of Morale",  # target creature gains banding
        "Adventurers' Guildhouse",  # "bands with other legendary creatures"
    ],
)
def test_a_banding_grant_is_a_banding_card(name):
    assert "has_banding|you|" in _idents(name)


def test_removing_banding_is_not_banding():
    """Tolaria strips banding — a hoser of the theme, not a member."""
    assert "has_banding|you|" not in _idents("Tolaria")


# ── (5) targeting_matters: the side of a targeting cast trigger ──────────────


@pytest.mark.parametrize(
    "name",
    [
        "Feather, the Redeemed",  # a cast trigger on targeting your creature
        "Zada, Hedron Grinder",  # "targets only Zada"
        "Heartfire Hero",  # valiant: "a spell or ability you control"
    ],
)
def test_a_trigger_on_targeting_your_own_creature_takes_your_side(name):
    idents = _idents(name)
    assert "targeting_matters|any|you" in idents
    assert "targeting_matters|any|opponents" not in idents


@pytest.mark.parametrize(
    "name",
    [
        "Reparations",  # an opponent's spell targets you or your creature
        "Frost Titan",  # "a spell or ability an opponent controls"
        "Willbreaker",  # your targeting of an opponent's creature
    ],
)
def test_a_trigger_on_an_opponents_side_of_targeting_takes_their_side(name):
    idents = _idents(name)
    assert "targeting_matters|any|opponents" in idents
    assert "targeting_matters|any|you" not in idents


@pytest.mark.parametrize("name", ["Informed Inkwright", "Phantasmal Bear"])
def test_an_unsided_targeting_payoff_takes_no_side(name):
    """Repartee watches a spell targeting any creature; Phantasmal Bear's
    drawback fires on anyone's spell or ability."""
    idents = _idents(name)
    assert "targeting_matters|any|" in idents
    assert not {"targeting_matters|any|you", "targeting_matters|any|opponents"} & (
        idents
    )


# ── (6) self_etb_payload: payloads phase types with no concept row ───────────


@pytest.mark.parametrize(
    "name",
    [
        "Fervent Cathar",  # target creature can't block this turn
        "Fogwalker",  # target creature an opponent controls doesn't untap
        "Way of the Mind Sculptor",  # empower Jace 5
        "Cataclysmic Gearhulk",  # each player sacrifices all but four
        "Magister Sphinx",  # target player's life total becomes 10
        "Mirelurk Queen",  # target player gets two rad counters
    ],
)
def test_an_untyped_etb_payload_is_value_to_re_deliver(name):
    assert "self_etb_payload|you|" in _idents(name)


@pytest.mark.parametrize("name", ["Eater of Days", "Hecatomb"])
def test_an_etb_drawback_is_not_a_payload(name):
    """Eater of Days skips your turns; Hecatomb sacrifices your creatures."""
    assert "self_etb_payload|you|" not in _idents(name)
