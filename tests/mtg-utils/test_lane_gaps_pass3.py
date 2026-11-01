"""The lane recall gaps the 2026-10-31 third pass closed (``docs/plans/backlog.md``:
"Lane gaps still open", Pass D's lane follow-ups and "Our reads still missing a
v0.118.0 shape"). Real cards only (ADR-0056): each closed gap, and the near miss
that stays out."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keyed(name: str, *keys: str) -> set[tuple[str, str, str]]:
    return {i for i in _idents(name) if i[0] in keys}


# ── edict_makers: a forced sacrifice (CR 701.21a) ────────────────────────────


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # "Choose two target creatures controlled by the same player. That
        # player sacrifices one of them of their choice."
        ("Incriminate", "opponents"),
        # "For each creature, its controller sacrifices it unless they pay X life."
        ("Killing Wave", "each"),
        # "When you cast this spell, each player sacrifices X creatures." (parked)
        ("Gluttonous Hellkite", "each"),
        # a granted "Whenever this creature deals combat damage to a player, that
        # player sacrifices a creature of their choice" (read like a printed one)
        ("Demon of Wailing Agonies", "each"),
        # an emblem's "At the beginning of each opponent's upkeep, that player
        # sacrifices a creature of their choice"
        ("Sorin, Solemn Visitor", "opponents"),
        # the secretly chosen creature's sacrifice (a ledgered bridge)
        ("Malik, Grim Manipulator", "opponents"),
    ],
)
def test_a_forced_sacrifice_is_an_edict(name, scope):
    assert ("edict_makers", scope, "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # "that player chooses up to two creatures they control, then sacrifices
        # the rest": the kept set, keep_n_wrath's (Incriminate's shape otherwise)
        "Archfiend of Depravity",
        # "Each player chooses up to two creatures they control, then sacrifices
        # the rest"
        "Covetous Elegy",
        # you choose a permanent of each type for each player, the rest go
        "Tragic Arrogance",
    ],
)
def test_a_keep_n_wrath_stays_off_the_edict_page(name):
    assert not _keyed(name, "edict_makers")
    assert _keyed(name, "keep_n_wrath")
