"""ADR-0025 folded objects: a commander's signals extend to the game-objects
its plan deterministically brings into play — the dungeon its oracle NAMES,
its meld result, the Ring, the Initiative's Undercity.

The fold is structural (restored 2026-07-25 after the regex-era
append-and-re-extract mechanism died with the engines): ``_deck_signal_stats``
unions ``extract_signals(object_record)`` into the commander's signal set,
commander-only. Every card here — commanders AND objects — is a real snapshot
record, so the fold runs the same structural parses production serves; the
resolver is a test stub over snapshot records (production wires
``state.object_resolver``, built from bulk).
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.signals import (
    folded_object_records,
    rank_deck_signals,
)
from mtg_utils.testkit import test_card

_OBJECTS = (
    "Tomb of Annihilation",
    "The Ring",
    "Undercity",
    "Brisela, Voice of Nightmares",
)


@pytest.mark.parametrize(
    "name",
    [
        "Tomb of Annihilation",
        "The Ring",
        "Undercity",
        "Brisela, Voice of Nightmares",
    ],
)
def test_folded_object_is_snapshot_resident(name):
    # Doubles as the snapshot scanner's harvest point for the object names —
    # `_resolver` below passes them through a function reference the
    # usage-derived scan cannot trace (literal rows required, not `_OBJECTS`).
    assert test_card(name)["name"]


def _resolver(name: str) -> dict | None:
    try:
        return test_card(name) if name in _OBJECTS else None
    except KeyError:  # pragma: no cover — snapshot regen pending
        return None


def _idents(records, commanders, *, fold: bool):
    return {
        (s.key, s.scope, s.subject)
        for s in rank_deck_signals(
            records, commanders, resolve_object=_resolver if fold else None
        )
    }


def test_acererak_folds_only_his_named_dungeon():
    # all_parts lists ALL rules-legal dungeons; only the oracle-NAMED one is
    # the deterministic plan (ADR-0025's popularity-free gate).
    names = [o["name"] for o in folded_object_records(test_card("Acererak the Archlich"), _resolver)]
    assert names == ["Tomb of Annihilation"]


def test_generic_venturer_folds_nothing():
    # Nadaar ventures generically — no dungeon named, nothing folds.
    assert folded_object_records(test_card("Nadaar, Selfless Paladin"), _resolver) == []


def test_meld_commander_folds_its_result():
    names = [o["name"] for o in folded_object_records(test_card("Bruna, the Fading Light"), _resolver)]
    assert names == ["Brisela, Voice of Nightmares"]


def test_ring_tempts_folds_the_ring():
    names = [o["name"] for o in folded_object_records(test_card("Frodo, Sauron's Bane"), _resolver)]
    assert any(n.startswith("The Ring") for n in names)  # DFC full name


def test_initiative_folds_undercity():
    names = [o["name"] for o in folded_object_records(test_card("Caves of Chaos Adventurer"), _resolver)]
    assert any(n.startswith("Undercity") for n in names)  # DFC full name


def test_fold_extends_the_commander_signal_set():
    # The whole point: with the resolver wired, Acererak's ranked signals are a
    # strict superset of his own-text signals — the dungeon's effects joined.
    ace = test_card("Acererak the Archlich")
    with_fold = _idents([ace], {ace["name"]}, fold=True)
    without = _idents([ace], {ace["name"]}, fold=False)
    assert with_fold > without


def test_the_99_never_fold():
    # Folded objects belong to the COMMANDER's plan: the same venturer sitting
    # in the 99 gains nothing from the resolver.
    ace = test_card("Acererak the Archlich")
    other_commander = test_card("Krenko, Mob Boss")
    with_fold = _idents([other_commander, ace], {other_commander["name"]}, fold=True)
    without = _idents([other_commander, ace], {other_commander["name"]}, fold=False)
    assert with_fold == without


def test_no_resolver_means_no_fold_and_no_crash():
    ace = test_card("Acererak the Archlich")
    assert rank_deck_signals([ace], {ace["name"]}) == rank_deck_signals(
        [ace], {ace["name"]}, resolve_object=None
    )
