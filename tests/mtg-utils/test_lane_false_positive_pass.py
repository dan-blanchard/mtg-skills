"""The lane false positives the 2026-10-31 pass closed (``docs/plans/backlog.md``)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keyed(name: str, *keys: str) -> set[tuple[str, str, str]]:
    return {i for i in _idents(name) if i[0] in keys}


_MAKER_KEYS = (
    "token_maker",
    "mass_token_makers",
    "treasure_makers",
    "food_makers",
    "clue_makers",
    "blood_makers",
)


@pytest.mark.parametrize(
    "name",
    [
        # "that player creates" on its own combat-damage trigger: the player it
        # attacked (CR 510.1b), another player
        "Varchild, Betrayer of Kjeldor",
        # "At the beginning of each opponent's end step, that player creates"
        "Goblin Spymaster",
        # "Its controller creates two Treasure tokens": the countered spell's
        "An Offer You Can't Refuse",
        # "enchanted opponent creates a Clue token, a Food token, and a Junk token"
        "Overencumbered",
    ],
)
def test_a_token_another_player_creates_is_not_yours(name):
    """CR 111.2: the player who creates a token is its owner, so a token
    another player creates makes no resource of yours
    (``crosswalk.token_creator_side``)."""
    assert not {i for i in _keyed(name, *_MAKER_KEYS) if i[1] == "you"}


def test_a_token_whoever_controls_the_object_creates_is_scoped_any():
    """March of Souls' "its controller creates" for each destroyed creature:
    every player gets Spirits, so the token maker is scoped "any", as
    Pharika's chosen graveyard card is."""
    assert _keyed("March of Souls", "token_maker") == {("token_maker", "any", "Spirit")}
    assert ("token_maker", "any", "Snake") in _idents("Pharika, God of Affliction")


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Raise the Alarm", ("token_maker", "you", "Soldier")),
        # "you may target yourself": a target player's Treasure stays yours
        ("Prismari Command", ("treasure_makers", "you", "")),
        # "When ~ leaves the battlefield, its owner creates": you own it
        ("Yes Man, Personal Securitron", ("token_maker", "you", "Soldier")),
    ],
)
def test_your_own_tokens_stay_yours(name, ident):
    assert ident in _idents(name)


def test_an_opponents_token_is_a_donation():
    """The same read hands Varchild's Survivors to the donate lane."""
    assert ("donate_makers", "you", "token") in _idents("Varchild, Betrayer of Kjeldor")


@pytest.mark.parametrize("name", ["Guerrilla Tactics", "Psychic Purge"])
def test_a_discard_an_opponent_causes_is_no_discard_payoff(name):
    """ "When a spell or ability an opponent controls causes you to discard this
    card": no outlet of yours triggers it (Guerrilla Tactics' ruling:
    discarding as a cost won't), so it pays off no discard theme."""
    assert not _keyed(name, "discard_matters")


def test_a_discard_payoff_of_your_own_stays():
    assert ("discard_matters", "you", "") in _idents("Archfiend of Ifnir")


@pytest.mark.parametrize("name", ["Balance", "Restore Balance"])
def test_discarding_down_to_the_fewest_hand_is_no_outlet(name):
    """Balance's "players discard cards … the same way" levels every hand to
    the smallest: whoever holds the fewest discards nothing."""
    assert not _keyed(name, "discard_outlet")


def test_a_wheel_stays_a_discard_outlet():
    assert ("discard_outlet", "you", "") in _idents("Wheel of Fortune")


@pytest.mark.parametrize(
    "name",
    [
        # "Only your opponents may activate this ability": "Gain control of this
        # creature" is the activating opponent's (CR 109.5)
        "Oft-Nabbed Goat",
        # "Put target card you don't own in exile … on the bottom of its
        # owner's library": the "don't own" names the card it hoses
        "Sentinel of Lost Lore",
    ],
)
def test_no_theft_where_no_card_is_stolen(name):
    assert not _keyed(name, "gain_control")


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Control Magic", ("gain_control", "you", "")),
        # "Whenever you cast a spell you don't own": the don't-own payoff tell
        ("Tasha, the Witch Queen", ("gain_control", "you", "")),
    ],
)
def test_theft_stays(name, ident):
    assert ident in _idents(name)
