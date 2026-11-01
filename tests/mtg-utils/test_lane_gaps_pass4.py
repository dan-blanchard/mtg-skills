"""The lane gaps and false positives the 2026-11-01 fourth pass closed
(``docs/plans/backlog.md``: "Lane gaps still open" and the bump's policy
questions). Real cards only (ADR-0056): each closed gap, and the near miss that
stays out."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keyed(name: str, *keys: str) -> set[tuple[str, str, str]]:
    return {i for i in _idents(name) if i[0] in keys}


# ── edict_makers: a granted sacrifice is its holder's controller's ───────────


@pytest.mark.parametrize(
    ("name", "edicts"),
    [
        # "Enchanted creature has 'At the beginning of your upkeep, sacrifice a
        # creature.'" — the enchanted creature's controller sacrifices (CR
        # 603.3a); an any-creature Aura with a drawback is cast on an opponent's.
        ("Inevitable End", {("edict_makers", "opponents", "")}),
        # "sacrifice this creature": the holder itself, removal — no edict.
        ("Necrotic Plague", set()),
        # "Commander creatures you own have '… sacrifice a creature'": yours.
        ("Cultist of the Absolute", set()),
    ],
)
def test_granted_sacrifice_is_the_holders_controllers(name, edicts):
    assert _keyed(name, "edict_makers") == edicts


# ── "that player" after combat damage from your creature is an opponent ─────


@pytest.mark.parametrize(
    ("name", "edicts"),
    [
        # "Whenever ~ deals combat damage to a player, that player sacrifices a
        # creature of their choice": it attacked an opponent (CR 506.2, 802.2).
        ("Demon of Loathing", {("edict_makers", "opponents", "")}),
        ("Wasitora, Nekoru Queen", {("edict_makers", "opponents", "")}),
        # "… each player sacrifices a creature" stays every player's.
        ("Rankle, Master of Pranks", {("edict_makers", "each", "")}),
    ],
)
def test_combat_damaged_player_is_an_opponent(name, edicts):
    assert _keyed(name, "edict_makers") == edicts


# ── sacrifice_outlets: an opponent's sacrifice is no outlet of yours ─────────


@pytest.mark.parametrize(
    ("name", "outlet"),
    [
        # "Whenever an opponent sacrifices a creature, you create a Treasure
        # token": an edict payoff, not a sacrifice of yours.
        ("Malik, Grim Manipulator", False),
        ("Legate Lanius, Caesar's Ace", False),
        # "Whenever you sacrifice a creature, draw a card."
        ("Smothering Abomination", True),
        # "Whenever a player sacrifices a creature" counts yours too.
        ("Mortician Beetle", True),
    ],
)
def test_opponents_sacrifice_trigger_is_no_outlet(name, outlet):
    assert bool(_keyed(name, "sacrifice_outlets")) is outlet
