"""Structured clause mini-parser — the gap-filler for phase's Unimplemented tail.

phase parses *what a card does* into a mechanics-shaped IR, but it only adds a
grammar rule for a mechanic once it implements the *engine* for it, so its parse
coverage is structurally bounded by its engine roadmap and trails the live card
pool. A **synergy** parser only ever needs to PARSE, never to play — so this
module is decoupled from that roadmap: it walks the English clauses phase
collapsed into ``category="other"`` (a ``GenericEffect`` / ``Unimplemented``) and
emits real :mod:`mtg_utils.card_ir` nodes (Effect category + scope + subject +
amount), so the synergy lanes derive from structure rather than a card-level
oracle regex.

The recovery is a registry of :class:`ClauseRule`s. A *simple* rule re-categorizes
an ``other`` effect whose English is unambiguous (e.g. "cast … from … graveyard"
→ a graveyard-cast). A *rich* rule (``build``) parses a real subject/amount out of
the clause (e.g. a created token's type and count). Two scope holes phase leaves
(it carries structured scope on only a sliver of abilities) are closed by a final
pass: the narrow Tinybones rule (combat-damage-to-a-player + that-player's-zone →
opponents) and the broader third-party-possessive guess.

The Tinybones regexes are inlined (not imported from ``_deck_forge.signals``) on
purpose: ``signals`` imports the IR, so a back-edge would be a cycle.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from mtg_utils.card_ir import Card, Effect

# ── scope recovery (phase structures scope on only a sliver of abilities) ──────
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

# ── clause patterns for the recovery rules ────────────────────────────────────
# Cast-from-graveyard (Tinybones / graveyard-cast payoffs): "cast … from …
# graveyard". The structural parse loses the zone, so recover the reanimation
# shape from the clause.
_GRAVEYARD_CAST = re.compile(r"\bcast\b[^.]*\bfrom\b[^.]*\bgraveyard\b", re.IGNORECASE)

# Voting (CR 701.38) — phase leaves the vote itself Unimplemented even when it
# structures the consequence ("each player votes …, exile/sacrifice …"). The vote
# clause carries no operand worth binding, so a simple re-category to "vote"
# (scope each: every player votes) is the right structured node; signals derives
# voting_matters from it instead of a card-level oracle regex.
_VOTE = re.compile(
    r"will of the council|council's dilemma|each player votes?|\bvotes?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClauseRule:
    """One recovery: a clause pattern → a structured Effect.

    A *simple* rule sets ``category`` (and optionally overrides ``scope``) on the
    matched ``other`` effect. A *rich* rule supplies ``build(match, effect)`` to
    parse a real subject/amount out of the clause and return a new Effect.
    """

    name: str
    pattern: re.Pattern[str]
    category: str = ""
    scope: str | None = None
    build: Callable[[re.Match[str], Effect], Effect] | None = None

    def apply(self, m: re.Match[str], e: Effect) -> Effect:
        if self.build is not None:
            return self.build(m, e)
        return replace(e, category=self.category, scope=self.scope or e.scope)


# The recovery registry. Order matters: the first matching rule wins, so put the
# most specific clauses first. Grow this as the fan-out owns more of the tail —
# each rule is a structured node, not a card-level boolean.
_RECOVERY_RULES: tuple[ClauseRule, ...] = (
    ClauseRule("graveyard_cast", _GRAVEYARD_CAST, category="reanimate"),
    ClauseRule("vote", _VOTE, category="vote", scope="each"),
)


def supplement_card(card: Card) -> Card:
    """Return *card* with each effect's category/scope recovered from its raw."""
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
    out = e
    # 1. recover a buried effect from its clause (the first matching rule wins).
    if e.category == "other":
        for rule in _RECOVERY_RULES:
            m = rule.pattern.search(e.raw)
            if m:
                out = rule.apply(m, e)
                break

    # 2. scope recovery → opp. The narrow Tinybones rule overrides any prior
    # scope; the broad third-party guess only fills an unscoped ("any") effect.
    tinybones = _COMBAT_DMG_TO_PLAYER.search(out.raw) and _THAT_PLAYERS_ZONE.search(
        out.raw
    )
    if tinybones or (out.scope == "any" and _BROAD_THIRD_PARTY.search(out.raw)):
        out = replace(out, scope="opp")

    return out
