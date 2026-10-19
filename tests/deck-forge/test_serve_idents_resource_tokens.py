"""Serve-ident pass A: the Treasure and Food serves (docs/plans/serve-idents-and-
avenue-support.md §2), and the resource-token maker / payoff reads that let them
drop their regexes.

``_resource_token_makers`` reads granted and nested makers, a target player's
token, a token replacement that creates a kind it doesn't watch, and an
"are Foods in addition to their other types" granter; ``treasure_matters`` reads
any filter naming Treasures (the "if mana from a Treasure was spent" condition
included); ``food_matters`` reads a forage (CR 701.61a). Every card is a real
snapshot record (ADR-0056).
"""

import pytest

from mtg_utils._analysis.signal_specs import Serve, spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir, test_signals


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record for *name*, with its crosswalk trees memo seeded
    first so the serve's ``signal_idents`` arm reads its real idents in CI."""
    test_card_ir(name)
    return test_card(name)


def _keys(name):
    return {s.key for s in test_signals(name)}


def _ident_serve(key: str, *idents: str) -> Serve:
    spec = spec_for(_sig(key))
    assert spec is not None
    assert spec.serve.oracle is None
    for ident in idents:
        assert ident in spec.serve.signal_idents, ident
    return spec.serve


@pytest.mark.parametrize("key", ["treasure_makers", "treasure_matters"])
def test_treasure_serve_rides_the_lanes(key):
    serve = _ident_serve(key, "treasure_makers|you|", "treasure_matters|you|")
    assert serve.matches(_card("Smothering Tithe"))
    assert serve.matches(_card("Dockside Extortionist"))
    # Granted makers: an Aura's trigger, a token's own trigger.
    assert serve.matches(_card("Sticky Fingers"))
    assert serve.matches(
        _card("Fable of the Mirror-Breaker // Reflection of Kiki-Jiki")
    )
    # "Target player creates a Treasure token": you may target yourself.
    assert serve.matches(_card("Prismari Command"))
    # "If mana from a Treasure was spent to cast it."
    assert serve.matches(_card("Hired Hexblade"))
    # Only an opponent gets the Treasure (CR 111.2).
    assert not serve.matches(_card("Wanted Scoundrels"))
    # A treasure counter is no Treasure token.
    assert not serve.matches(_card("Legacy's Allure"))


@pytest.mark.parametrize("key", ["food_makers", "food_matters"])
def test_food_serve_rides_the_lanes(key):
    serve = _ident_serve(key, "food_makers|you|", "food_matters|you|")
    assert serve.matches(_card("Bake into a Pie"))
    # Forage (CR 701.61a): a bare forage action, a forage rider, an
    # additional cost.
    assert serve.matches(_card("Corpseberry Cultivator"))
    assert serve.matches(_card("Treetop Sentries"))
    assert serve.matches(_card("Feed the Cycle"))
    # A token's "when this dies, create a Food token".
    assert serve.matches(_card("Wolf's Quarry"))
    # A replacement that adds a Food to any token; a Food granter.
    assert serve.matches(_card("Tippy-Toe, Terrific Partner"))
    assert serve.matches(_card("Gourmand's Talent"))
    # Gift a Food: the opponent creates it.
    assert not serve.matches(_card("Crumb and Get It"))


def test_granted_investigate_is_a_clue_maker():
    # Curious Inquiry grants "Whenever this creature deals combat damage to a
    # player, investigate" (CR 701.16a: investigate creates a Clue token).
    assert "clue_makers" in _keys("Curious Inquiry")


def test_token_replacement_watching_its_own_kind_is_a_payoff():
    # Xorn adds a Treasure only when you'd create Treasures: it multiplies the
    # deck's Treasure makers, it isn't one.
    xorn = _keys("Xorn")
    assert "treasure_matters" in xorn
    assert "treasure_makers" not in xorn
    # Academy Manufactor creates only kinds it watches (its rulings: "that many
    # Clue tokens, that many Food tokens, and that many Treasure tokens").
    manufactor = _keys("Academy Manufactor")
    assert {"clue_matters", "food_matters", "treasure_matters"} <= manufactor
    assert not {"clue_makers", "food_makers", "treasure_makers"} & manufactor


def test_token_replacement_creating_another_kind_is_its_maker():
    # Bilbo watches Food and adds a Treasure: a Treasure maker, a Food payoff.
    bilbo = _keys("Bilbo, Fellow Conspirator")
    assert {"treasure_makers", "food_matters"} <= bilbo
    assert "food_makers" not in bilbo


def test_treasure_payoffs_read_off_filters():
    # "Whenever you sacrifice a Treasure" (a watched sacrifice) and the
    # mana-source condition both name Treasures in a filter.
    assert "treasure_matters" in _keys("Captain Lannery Storm")
    hexblade = _keys("Hired Hexblade")
    assert "treasure_matters" in hexblade
    assert "treasure_makers" not in hexblade


def test_opponents_tokens_are_not_yours():
    # "Whenever an opponent casts a spell, that player creates a Blood token",
    # and "for each Blood token defending player controls" (CR 506.2).
    keys = _keys("Bloodvial Purveyor")
    assert "blood_makers" not in keys
    assert "blood_matters" not in keys
    # The chosen permanents an opponent controls become Treasures: removal.
    assert "treasure_makers" not in _keys("Kitesail Larcenist")
