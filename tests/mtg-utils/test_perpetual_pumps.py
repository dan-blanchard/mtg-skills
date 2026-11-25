"""``_card_ir.crosswalk.perpetual``: a perpetual power/toughness change read as the
pump it is when it lands on a creature on the battlefield (the lane's own
decision: "perpetually" is an Arena-only mechanic with no Comprehensive Rules
entry)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import tag_of
from mtg_utils._card_ir.crosswalk.reads import ability_zones
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_card_ir, test_signals


def _units(name: str) -> list:
    test_card_ir(name)  # seeds the card's trees from the snapshot
    return [u for t in trees_for(test_card(name)) for u in t.units]


def _pump_targets(name: str) -> list[str | None]:
    """The target tag of each pump the card's units decorate."""
    return [
        tag_of(getattr(c.node, "target", None))
        for u in _units(name)
        for c in u.effects
        if c.concept == "pump"
    ]


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


@pytest.mark.parametrize(
    ("name", "target"),
    [
        # "~ perpetually gets +1/+1" in a trigger it has on the battlefield
        ("Steady Tortoise // Harried Dash", "SelfRef"),
        # "Return ~ from your graveyard to the battlefield tapped. It perpetually
        # gets +1/+1": the card the return put onto the battlefield
        ("Vladimir and Godfrey", "SelfRef"),
        # "target creature an opponent controls perpetually gets -1/-2"
        ("Davriel's Withering", "Typed"),
        # "that creature perpetually gets -2/-0": the creature blocking it
        ("Wizened Githzerai", "ParentTarget"),
    ],
)
def test_a_perpetual_change_on_the_battlefield_is_a_pump(name, target):
    assert target in _pump_targets(name)


@pytest.mark.parametrize(
    "name",
    [
        # "choose a creature card in your hand. It perpetually gets +2/+2"
        "Veteran Charger",
        # "When ~ dies, it perpetually gets +2/+2": the card in the graveyard
        "Tomakul Phoenix",
        # "Activate only if ~ is in your graveyard"
        "Diminished Returner",
        # "Return target card from your graveyard to your hand. If it's a
        # creature card, it perpetually gets +3/+3"
        "Giant Regrowth",
        # a Vehicle that isn't a creature has no power or toughness (CR 301.7a)
        "Soul Shredder",
    ],
)
def test_a_perpetual_change_off_the_battlefield_is_no_pump(name):
    assert _pump_targets(name) == []


def test_the_typed_change_stays_in_the_tree():
    """Only the unit's effect decoration changes: the reads of the change's other
    parts (a keyword it grants, a graveyard return) walk the typed node."""
    assert any(
        tag_of(n) == "ApplyPerpetual"
        for u in _units("Steady Tortoise // Harried Dash")
        for n in u.iter_typed()
    )


def test_the_lanes_read_a_perpetual_pump_with_no_special_case():
    assert ("combat_trigger_boost", "you", "") in _idents(
        "Steady Tortoise // Harried Dash"
    )
    assert ("self_pump", "you", "") in _idents("Scion of Shiv")
    assert ("debuff_makers", "any", "") in _idents("Davriel's Withering")
    assert not {k for k, _s, _sub in _idents("Veteran Charger")} & {
        "self_pump",
        "effect_boost",
        "debuff_makers",
    }


def test_an_activation_restricted_to_the_graveyard_names_its_zone():
    """ "Activate only if ~ is in your graveyard and its toughness is 2 or
    greater": the ``SourceInZone`` conjunct of the condition."""
    zones = [
        ability_zones(u.node)
        for u in _units("Diminished Returner")
        if any(tag_of(n) == "ApplyPerpetual" for n in u.iter_typed())
    ]
    assert zones == [frozenset({"Graveyard"})]


def test_a_perpetual_pump_of_the_card_itself_is_no_pump_maker():
    """Ichor Aberration only grows itself: no ``effect_boost``, though a sibling
    effect of its trigger ("you may cast it from your graveyard this turn") is
    timed (Dan's call, 2026-11-25)."""
    assert ("effect_boost", "you", "") not in _idents("Ichor Aberration")
    assert any(
        c.perpetual
        for u in _units("Ichor Aberration")
        for c in u.effects
        if c.concept == "pump"
    )


def test_a_perpetual_pump_of_a_chosen_creature_is_a_pump_maker():
    """ "Target creature you control perpetually gets +1/+0" (Prairie
    Survivalist): a permanent pump of one chosen creature of yours is a pump
    maker, the targeted kind, as a pump until end of turn is."""
    idents = _idents("Prairie Survivalist")
    assert ("effect_boost", "you", "") in idents
    assert ("effect_boost", "you", "target") in idents


def test_a_chosen_players_creatures_keep_their_controller():
    """ "~ deals 2 damage to each creature target player controls. Those
    creatures perpetually get +2/+0" (Chaos Balor's attack mode): the player can
    be you, so it is a combat buff of yours; the view is a ``PumpAll`` over that
    filter, ``TargetPlayer`` kept."""
    assert ("combat_trigger_boost", "you", "") in _idents("Chaos Balor")
    views = [
        c.node
        for u in _units("Chaos Balor")
        for c in u.effects
        if c.concept == "pump" and c.perpetual
    ]
    assert views
    assert all(tag_of(v) == "PumpAll" for v in views)
    assert {getattr(v.target, "controller", None) for v in views} == {"TargetPlayer"}


@pytest.mark.parametrize(
    ("controller", "raises", "yours"),
    [
        ("Opponent", True, False),  # "each creature your opponents control"
        ("Opponent", False, True),  # a shrink of theirs is still read
        ("TargetPlayer", True, True),  # Chaos Balor: the player can be you
        ("You", True, True),
        (None, True, True),
    ],
)
def test_a_raise_on_only_an_opponents_population_is_no_pump_of_yours(
    controller, raises, yours
):
    """No real card at v0.131.0 has a perpetual change over a population only
    opponents control (Chaos Balor's is the one tracked population), so the rule
    is tested on its own."""
    from mtg_utils._card_ir.perpetual_rules import population_pump_is_yours

    assert population_pump_is_yours(controller, raises=raises) is yours


def test_a_returned_card_growing_is_no_firebreather():
    """ "{2}{W}: Return ~ from your graveyard to the battlefield tapped. It
    perpetually gets +1/+1" (Vladimir and Godfrey): the pump lands on the card
    only because the ability put it onto the battlefield — recursion that grows
    it, no mana sink of a creature already there (Dan's call, 2026-11-25).
    Scion of Shiv's "{2}{R}: ~ perpetually gets +1/+0" is one."""
    assert ("self_pump", "you", "") not in _idents("Vladimir and Godfrey")
    assert ("self_pump", "you", "") in _idents("Scion of Shiv")
    assert ("self_pump", "you", "") in _idents("Longtusk Stalker")
