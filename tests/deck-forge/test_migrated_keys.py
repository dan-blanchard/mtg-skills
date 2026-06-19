"""Durable invariant for the ADR-0027 regex→Card-IR strangler.

For EVERY key in ``MIGRATED_KEYS``, the migration must be real and complete:

  * ``extract_signals`` (the legacy regex path) must NO LONGER emit the key — its
    oracle-regex production (``_DETECTORS`` / ``_HAND_FLOOR`` / ``SWEEP_DETECTORS``
    rows + any ``add()``) is deleted.
  * ``extract_signals_hybrid(card, ir)`` (the production dispatcher) DOES emit it,
    served from the Card IR path (``extract_signals_ir``).

Each case is a real card (full oracle_text + type_line, never trimmed/fabricated)
paired with a hand-built IR that mirrors the structural source the IR path reads
for that key — so the proof holds without a phase dependency or the on-disk
sidecar. A new migration batch adds one ``(key, card, ir)`` row here; the
parametrization then guards it forever.
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.signals import (
    MIGRATED_KEYS,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face


def _ir(*abilities: Ability, keywords: tuple[str, ...] = ()) -> Card:
    return Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", keywords=keywords, abilities=tuple(abilities)),),
    )


# One representative real card per migrated key, paired with the IR that mirrors
# the structural source the IR path reads:
#   ki_counter_matters  ← Effect(place_counter, counter_kind="ki")  [_COUNTER_KIND_KEYS]
#   seek_matters        ← Effect(category="seek")                   [_DOER_EFFECT_KEYS]
#   specialize_matters  ← Scryfall "Specialize" keyword             [_IR_KEYWORD_MAP]
_CASES: dict[str, tuple[dict, Card]] = {
    "ki_counter_matters": (
        {
            "name": "Skullmane Baku",
            "type_line": "Creature — Spirit",
            "oracle_text": (
                "Whenever you cast a Spirit or Arcane spell, you may put a ki "
                "counter on this creature.\n{1}, {T}, Remove X ki counters from "
                "this creature: Target creature gets -X/-X until end of turn."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="place_counter",
                        counter_kind="ki",
                        scope="you",
                        raw="put a ki counter on ~",
                    ),
                ),
            )
        ),
    ),
    "seek_matters": (
        {
            "name": "Adherent's Heirloom",
            "type_line": "Artifact",
            "oracle_text": (
                "When this artifact enters, seek a creature card of the most "
                "prevalent creature type in your library.\n{T}: Add one mana of "
                "any color. Spend this mana only to cast a creature spell."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="seek",
                        scope="you",
                        raw="seek a creature card",
                    ),
                ),
            )
        ),
    ),
    "specialize_matters": (
        {
            "name": "Alora, Rogue Companion",
            "type_line": "Legendary Creature — Halfling Rogue",
            "oracle_text": (
                "Specialize {2}\nWhenever you attack, up to one target attacking "
                "creature can't be blocked this turn. At the beginning of the next "
                "end step, return that creature to its owner's hand."
            ),
            "keywords": ["Specialize"],
        },
        # specialize is read off the Scryfall keyword array, not the IR structure,
        # so a bare non-None IR is enough to route the hybrid to the IR path.
        _ir(),
    ),
}


def test_every_migrated_key_has_a_case():
    """No migrated key may be left unproven: the case table must cover the manifest."""
    assert set(_CASES) == set(MIGRATED_KEYS), (
        "every key in MIGRATED_KEYS needs a representative (card, ir) case here"
    )


@pytest.mark.parametrize("key", sorted(MIGRATED_KEYS))
def test_migrated_key_left_regex_and_is_ir_served(key):
    """Regex path drops the key; the hybrid (IR) path serves it."""
    card, ir = _CASES[key]
    regex_keys = {s.key for s in extract_signals(card)}
    hybrid_keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert key not in regex_keys, f"{key} still emitted by the legacy regex path"
    assert key in hybrid_keys, f"{key} not served by the hybrid IR path"
