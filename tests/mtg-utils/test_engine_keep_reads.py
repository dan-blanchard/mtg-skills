"""The reads behind four signal gaps a precon guide review found (2026-10-30):
end-step sacrifices and the instant-speed end of the turn that keeps them (CR 603.7b,
724.1b), ability copiers that copy no spell (CR 707.10), and what a tutor finds (CR
701.23a). Every card is real (``mtg_utils.testkit``); each expectation follows its
oracle text and rulings."""

import pytest

from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils._card_ir.crosswalk import (
    end_step_sacrifices,
    ends_turn_at_instant_speed,
    self_tutor_found_types,
    unit_copied_ability_kind,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _trees(name):
    return trees_for(test_card(name))


def _idents(name):
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


@pytest.mark.parametrize(
    "name",
    [
        # Its own delayed trigger: "Sacrifice it at the beginning of the next end step."
        "Saheeli, Radiant Creator",
        "Kiki-Jiki, Mirror Breaker",
        "Satya, Aetherflux Genius",  # "… sacrifice that token unless you pay"
        "Sneak Attack",  # a creature card, not a token: the trigger is the same
        "Zurgo Stormrender",  # printed mobilize, CR 702.181a
        "Sliver Gravemother",  # printed and granted encore, CR 702.141a
        "Infantry Shield",  # granted mobilize: "Equipped creature has … mobilize X"
    ],
)
def test_a_one_shot_end_step_sacrifice_is_read(name):
    assert any(end_step_sacrifices(t) for t in _trees(name))
    assert "end_step_sacrifice|you|" in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # "At the beginning of the end step, sacrifice this creature" is printed on
        # the creature and fires every turn: ending one turn delays it a turn.
        "Ball Lightning",
        # Dash returns the permanent to its owner's hand (CR 702.109a).
        "Kolaghan, the Storm's Fury",
    ],
)
def test_a_recurring_trigger_or_a_return_to_hand_is_not(name):
    assert not any(end_step_sacrifices(t) for t in _trees(name))
    assert "end_step_sacrifice|you|" not in _idents(name)


def test_ending_the_turn_at_instant_speed():
    """Sundial's ability has no sorcery timing (CR 117.1b), Time Stop is an instant
    (CR 117.1a); Day's Undoing is a sorcery, cast only with the stack empty (CR
    307.1). Only an activated ability ends the turn again next turn: a spell is gone
    once it resolves (CR 608.2n)."""
    for name, instant, repeatable in (
        ("Sundial of the Infinite", True, True),
        ("Obeka, Brute Chronologist", True, True),
        ("Time Stop", True, False),
        ("Day's Undoing", False, False),
    ):
        trees = _trees(name)
        assert any(ends_turn_at_instant_speed(t) for t in trees) is instant, name
        assert (
            any(ends_turn_at_instant_speed(t, repeatable=True) for t in trees)
            is repeatable
        ), name
        assert ("end_the_turn|you|instant" in _idents(name)) is instant, name


def test_the_end_step_lane_pairs_its_makers_with_the_instant_endings():
    serve = spec_for(Signal("end_step_sacrifice", "you", "", "", "x")).serve
    assert serve.matches(test_card("Saheeli, Radiant Creator"))
    assert serve.matches(test_card("Sundial of the Infinite"))
    assert not serve.matches(test_card("Day's Undoing"))


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Strionic Resonator", "Triggered"),
        ("Lithoform Engine", "Any"),
        # "Whenever you activate an ability … copy that ability"
        ("Rings of Brighthearth", "Activated"),
        ("Illusionist's Bracers", "Activated"),
    ],
)
def test_an_ability_copier_copies_an_ability(name, kind):
    kinds = {
        unit_copied_ability_kind(u, n)
        for t in _trees(name)
        for u in t.units
        for n in u.iter_typed()
    }
    assert kind in kinds


@pytest.mark.parametrize(
    "name", ["Strionic Resonator", "Rings of Brighthearth", "Illusionist's Bracers"]
)
def test_a_copy_of_an_ability_is_no_spell_copy(name):
    """CR 707.10: a copy of an ability is an ability. These copy no spell, so they
    are no spell copiers and no spell-cast payoffs."""
    idents = _idents(name)
    assert "ability_copy|you|" in idents
    assert not {"spell_copy_makers|you|", "spellcast_matters|you|"} & idents


def test_a_spell_copier_still_is_one():
    # Twincast copies a spell; Lithoform Engine's {3} ability copies an instant or
    # sorcery spell beside its ability copy.
    assert "spell_copy_makers|you|" in _idents("Twincast")
    assert "spell_copy_makers|you|" in _idents("Lithoform Engine")


@pytest.mark.parametrize(
    ("name", "found"),
    [
        ("Fabricate", ("Artifact",)),
        ("Enlightened Tutor", ("Artifact", "Enchantment")),
        ("Call the Gatewatch", ("Planeswalker",)),
        ("Arena Rector", ("Planeswalker",)),  # its dies trigger's search
        ("Expedition Map", ("Land",)),
        ("Demonic Tutor", ()),  # "a card": any card
    ],
)
def test_a_tutor_names_what_it_finds(name, found):
    assert (
        tuple(sorted({f for t in _trees(name) for f in self_tutor_found_types(t)}))
        == found
    )
    idents = _idents(name)
    assert "tutor|you|" in idents
    assert {i for i in idents if i.startswith("tutor|you|") and i != "tutor|you|"} == {
        f"tutor|you|{f}" for f in found
    }


def test_superfriends_pages_its_planeswalker_tutors():
    serve = spec_for(Signal("superfriends_matters", "you", "", "", "x")).serve
    assert serve.matches(test_card("Call the Gatewatch"))
    assert not serve.matches(test_card("Fabricate"))


def test_a_found_type_opens_no_avenue_of_its_own():
    """The subject is a refinement of the Tutors lane: ``tutor|you|Planeswalker``
    resolves to no avenue apart from it."""
    from mtg_utils._analysis.signal_specs import avenue_spec_for

    assert avenue_spec_for(Signal("tutor", "you", "Planeswalker", "", "x")) is None


def test_a_tribe_page_holds_its_changelings_and_type_changers():
    """Changeling Outcast is every creature type (CR 702.73a), and Conspiracy makes
    your creatures and creature cards the chosen type: both are on Disa the
    Restless's Lhurgoyf page."""
    serve = spec_for(Signal("type_matters", "you", "Lhurgoyf", "", "x")).serve
    assert serve.matches(test_card("Changeling Outcast"))
    assert serve.matches(test_card("Conspiracy"))
    assert not serve.matches(test_card("Fabricate"))
