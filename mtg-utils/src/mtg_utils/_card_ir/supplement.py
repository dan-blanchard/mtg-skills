"""Oracle-text gap-filler for the projection.

phase parses *what a card does* into a mechanics-shaped IR; deck-forge needs
*payoff/scope* semantics. Two holes the structural projection can't close on its
own, recovered here from each effect's ``raw`` clause:

1. **Buried effects** — a clause phase collapsed into a ``GenericEffect`` /
   ``Unimplemented`` (so the projection emitted ``category="other"``) but whose
   English is unambiguous, e.g. "cast … from … graveyard" → a graveyard-cast.

2. **Scope** — phase carries structured scope on only a tiny fraction of
   abilities, so "that player's graveyard" (Tinybones) stays unscoped. The narrow
   Tinybones rule (combat-damage-to-a-player + that-player's-zone → opponents) and
   the broader third-party-possessive rule run here on ``Effect.raw``.

The Tinybones regexes are inlined (not imported from ``_deck_forge.signals``) on
purpose: ``signals`` will import the IR in Milestone A2, so a back-edge would be a
cycle.
"""

from __future__ import annotations

import re
from dataclasses import replace

from mtg_utils.card_ir import Card, Effect

# Narrow Tinybones rule: combat-damage-to-a-player + that-player's-zone → opp.
# Kept narrow on purpose (a broad "its owner's hand → opp" misfires on
# self-blink/self-bounce). Ported verbatim from signals._tinybones_scope.
_COMBAT_DMG_TO_PLAYER = re.compile(r"deals combat damage to a player", re.IGNORECASE)
_THAT_PLAYERS_ZONE = re.compile(
    r"that player's (?:graveyard|hand|library)", re.IGNORECASE
)
# Broader third-party possessive (an opponents guess), deliberately excluding
# "its owner's" so it never flips self-blink/self-bounce.
_BROAD_THIRD_PARTY = re.compile(
    r"that player's (?:graveyard|hand|library)"
    r"|each opponent's (?:graveyard|hand|library)"
    r"|target opponent's (?:graveyard|hand|library)"
    r"|their (?:graveyard|hand|library)\b",
    re.IGNORECASE,
)

# Cast-from-graveyard (Tinybones / graveyard-cast payoffs): "cast … from …
# graveyard". The structural parse loses the zone, so recover the reanimation
# shape from the clause.
_GRAVEYARD_CAST = re.compile(r"\bcast\b[^.]*\bfrom\b[^.]*\bgraveyard\b", re.IGNORECASE)


def supplement_card(card: Card) -> Card:
    """Return *card* with each effect's category/scope recovered from its raw text."""
    faces = tuple(
        replace(
            face,
            abilities=tuple(
                replace(ab, effects=tuple(_supplement_effect(e) for e in ab.effects))
                for ab in face.abilities
            ),
        )
        for face in card.faces
    )
    return replace(card, faces=faces)


def _supplement_effect(e: Effect) -> Effect:
    category = e.category
    scope = e.scope
    low = e.raw.lower()

    # 1. recover a buried graveyard-cast (reanimation-shaped for synergy).
    if category == "other" and _GRAVEYARD_CAST.search(low):
        category = "reanimate"

    # 2. scope recovery → opp. The narrow Tinybones rule overrides any prior
    # scope; the broad third-party guess only fills an unscoped ("any") effect.
    tinybones = _COMBAT_DMG_TO_PLAYER.search(e.raw) and _THAT_PLAYERS_ZONE.search(e.raw)
    if tinybones or (scope == "any" and _BROAD_THIRD_PARTY.search(e.raw)):
        scope = "opp"

    if category != e.category or scope != e.scope:
        return replace(e, category=category, scope=scope)
    return e
