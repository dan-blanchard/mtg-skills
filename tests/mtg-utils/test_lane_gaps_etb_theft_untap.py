"""Phase B lane gaps, the ETB / theft / untap slice
(``tree_synthesis/value_engines.py``, ``lanes/removal_tutors.py``).

A self-ETB value trigger reaches ``self_etb_payload`` whatever concept carries
its value, and a drawback-only one does not; a borrow-and-cast steal (an
opponent's card exiled, then cast by you) reaches ``theft_makers``; the untap
of a creature the card names itself (the enchanted creature, "untap it" after
a pump) reaches ``untap_engine``. Real cards only (``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {k for k, _s, _su in _idents(name)}


# ── self_etb_payload: the real concept vocabulary ───────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Siege-Gang Commander",  # make_token
        "Gravedigger",  # change_zone (graveyard to hand)
        "Flametongue Kavu",  # deal_damage (the old set named "damage")
        "Man-o'-War",  # bounce
        "Thragtusk",  # gain_life
        "Craterhoof Behemoth",  # a temporary dynamic pump (static role)
        "Inner-Flame Acolyte",  # pump + haste grant on a target
        "Peregrine Drake",  # an untap, not a tap
        "Sandsteppe Scavenger",  # bolster, a keyword action phase types as other
        "Manic Scribe",  # an opponent mill stays value
        "Mulldrifter",  # draw (unchanged)
        "Shriekmaw",  # destroy (unchanged)
    ],
)
def test_self_etb_value_is_a_payload(name):
    assert ("self_etb_payload", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Karoo",  # sacrifice it unless you bounce a land: a drawback
        "Hecatomb",  # sacrifice it unless you sacrifice four creatures
        "Foul Imp",  # you lose 2 life
        "Pale Rider of Trostad",  # discard a card
        "Ornery Kudu",  # a -1/-1 counter on your own creature
        "Indentured Djinn",  # each other player may draw: a gift
        "Hunted Troll",  # the opponent's Faerie tokens
    ],
)
def test_drawback_etb_is_not_a_payload(name):
    assert "self_etb_payload" not in _keys(name)


# ── theft_makers: exile what you don't own, then cast it ─────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Court of Locthwain",  # a target opponent's library
        "Brainstealer Dragon",  # each opponent's library (wrapper scope)
        "Daxos of Meletis",  # the damaged player's library
        "Gonti, Lord of Luxury",  # a dig into an opponent's library
        "Psychic Theft",  # a card picked out of a revealed hand
        "Hostage Taker",  # a battlefield permanent you may then cast
        "Spelljack",  # the countered spell
        "Ornate Kanzashi",  # the regex never read it
    ],
)
def test_borrow_and_cast_is_theft(name):
    assert ("theft_makers", "opponents", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Valakut Exploration",  # your own library: impulse draw
        "Release to the Wind",  # its OWNER may cast it
        "Savvy Trader",  # a card from your own graveyard
        "Possibility Storm",  # the caster's own spell, cast by that player
    ],
)
def test_self_impulse_and_owner_casts_are_not_theft(name):
    assert "theft_makers" not in _keys(name)


# ── untap_engine: the enchanted creature, and "untap it" after a pump ────────


@pytest.mark.parametrize(
    "name",
    [
        "Freed from the Real",  # {U}: Untap enchanted creature.
        "Pemmin's Aura",
        "Instill Energy",
        "Bull's Strength",  # +2/+2 and trample ... Untap it.
        "Shore Up",
        "Stony Strength",  # a +1/+1 counter, then untap that creature
    ],
)
def test_named_creature_untap_is_an_untap_engine(name):
    assert ("untap_engine", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Thermo-Alchemist",  # untaps only itself
        "Abduction",  # untaps the creature it steals
        "Threaten",  # untaps the creature it steals
    ],
)
def test_self_untap_and_steal_untap_are_not_untap_engines(name):
    assert "untap_engine" not in _keys(name)
