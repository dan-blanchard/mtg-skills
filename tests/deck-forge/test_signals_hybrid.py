"""Invariant for the ADR-0027 hybrid dispatch seam.

``extract_signals_hybrid`` routes each signal key to the Card IR path
(``MIGRATED_KEYS``) or the legacy regex path (everything else), then merges +
dedups. On the REGEX-SERVED keys (every key not in ``MIGRATED_KEYS``) the hybrid
must yield the SAME signal set as a pure ``extract_signals`` call for every
sampled card — for ANY ``ir`` argument, including ``None``, an unrelated IR, and
a fully-populated IR that itself fires IR signals. This is the behavior-neutrality
guarantee: the seam only ever re-serves a key once it is migrated, and it never
perturbs the keys still on the regex path. (Migrated keys' own proof — regex drops
them, the IR serves them — lives in ``test_migrated_keys.py``.)
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.signals import (
    MIGRATED_KEYS,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter

# Real cards (full oracle_text + type_line — no trimming/fabrication) spanning a
# spread of lanes: aristocrats death, ETB go-wide, an opponents-scoped graveyard
# payoff, tribal type_matters, lifegain, token-making, spellslinger, lands.
SAMPLE_CARDS: list[dict] = [
    {
        "name": "Tinybones, the Pickpocket",
        "oracle_id": "tinybones-oid",
        "type_line": "Legendary Creature — Skeleton Rogue",
        "oracle_text": (
            "Deathtouch\nWhenever Tinybones, the Pickpocket deals combat damage "
            "to a player, you may cast target nonland permanent card from that "
            "player's graveyard, and mana of any type can be spent to cast that "
            "spell."
        ),
    },
    {
        "name": "Purphoros, God of the Forge",
        "oracle_id": "purphoros-oid",
        "type_line": "Legendary Enchantment Creature — God",
        "oracle_text": (
            "Indestructible\nAs long as your devotion to red is less than five, "
            "Purphoros isn't a creature.\nWhenever another creature you control "
            "enters, Purphoros deals 2 damage to each opponent.\n{2}{R}: "
            "Creatures you control get +1/+0 until end of turn."
        ),
    },
    {
        "name": "Krenko, Mob Boss",
        "oracle_id": "krenko-oid",
        "type_line": "Legendary Creature — Goblin Warrior",
        "oracle_text": (
            "{T}: Create a number of 1/1 red Goblin creature tokens equal to the "
            "number of Goblins you control."
        ),
    },
    {
        "name": "Lier, Disciple of the Drowned",
        "oracle_id": "lier-oid",
        "type_line": "Legendary Creature — Zombie Wizard",
        "oracle_text": (
            "Players can't cast spells from graveyards.\nEach instant and sorcery "
            "card in your graveyard has flashback. Its flashback cost is equal to "
            "its mana cost.\nWhenever you cast an instant or sorcery spell, "
            "Lier, Disciple of the Drowned can't be the target of opponents' "
            "spells and abilities this turn."
        ),
    },
    {
        "name": "Lathiel, the Bounteous Dawn",
        "oracle_id": "lathiel-oid",
        "type_line": "Legendary Creature — Unicorn",
        "oracle_text": (
            "At the beginning of your end step, if you gained life this turn, "
            "distribute that many +1/+1 counters among any number of target "
            "creatures you control."
        ),
    },
    {
        "name": "Lord Windgrace",
        "oracle_id": "windgrace-oid",
        "type_line": "Legendary Planeswalker — Windgrace",
        "oracle_text": (
            "+2: Draw a card, then you may discard a card. If a land card is "
            "discarded this way, return it to the battlefield tapped.\n−3: "
            "Destroy target artifact or enchantment.\n−11: Search your library "
            "for any number of land cards, put them onto the battlefield, then "
            'shuffle. They gain "{T}: This land deals 6 damage to any target."'
        ),
    },
]


def _ids(sigs) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in sigs}


# A fully-populated IR that fires several IR-path signals on its own — proof that
# even a rich IR can't perturb the hybrid while MIGRATED_KEYS is empty.
_POPULATED_IR = Card(
    oracle_id="x",
    name="Test",
    faces=(
        Face(
            name="Test",
            abilities=(
                Ability(
                    kind="static",
                    effects=(
                        Effect(
                            category="pump",
                            subject=Filter(card_types=("Creature",), controller="you"),
                        ),
                        Effect(category="gain_life", scope="you"),
                    ),
                ),
            ),
        ),
    ),
)

# An unrelated, near-empty IR.
_EMPTY_IR = Card(
    oracle_id="y",
    name="Other",
    faces=(Face(name="Other", abilities=()),),
)

# Each IR variant the hybrid must be invariant to on the REGEX-served keys.
_IR_VARIANTS = [None, _EMPTY_IR, _POPULATED_IR]


def _regex_served(sigs) -> set[tuple[str, str, str]]:
    """Signal ids whose KEY is still served by the regex path (not migrated).

    The seam's behaviour-neutrality guarantee is scoped to the regex-served keys:
    a migrated key is intentionally re-served from the IR, so it must be excluded
    from the regex-vs-hybrid equality (these SAMPLE_CARDS fire none, but filtering
    keeps the invariant true as ``MIGRATED_KEYS`` grows). See ADR-0027."""
    return {(s.key, s.scope, s.subject) for s in sigs if s.key not in MIGRATED_KEYS}


@pytest.mark.parametrize("card", SAMPLE_CARDS, ids=lambda c: c["name"])
@pytest.mark.parametrize("ir", _IR_VARIANTS, ids=["none", "empty", "populated"])
def test_hybrid_matches_regex_on_regex_served_keys(card, ir):
    """Hybrid output == pure regex output on every non-migrated key, for any IR."""
    baseline = _regex_served(extract_signals(card))
    hybrid = _regex_served(extract_signals_hybrid(card, ir))
    assert hybrid == baseline


@pytest.mark.parametrize("card", SAMPLE_CARDS, ids=lambda c: c["name"])
def test_hybrid_forwards_include_membership_kwarg(card):
    """The hybrid forwards extract_signals kwargs (here include_membership)."""
    for membership in (True, False):
        baseline = _regex_served(extract_signals(card, include_membership=membership))
        hybrid = _regex_served(
            extract_signals_hybrid(card, _POPULATED_IR, include_membership=membership)
        )
        assert hybrid == baseline
