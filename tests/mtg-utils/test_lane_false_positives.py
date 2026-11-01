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
