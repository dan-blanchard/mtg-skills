"""The Signal value type and clause/subject parsing primitives.

Extracted 2026-07-25 from the retired regex/IR signal engines; every symbol
here is production-serving (imported by signals.py, structural lanes,
bridges, or the membership floor)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from mtg_utils._deck_forge._subtypes import (
    CARD_TYPE_SUBJECTS,
    IRREGULAR_SINGULAR,
    NON_CREATURE_TOKEN,
    NON_SUBJECT_WORDS,
)


@dataclass(frozen=True)
class Signal:
    """A scoped fact extracted from one card's oracle text."""

    key: str  # canonical signal id, e.g. "creature_etb"
    scope: str  # "you" | "opponents" | "each" | "any"
    subject: str  # subtype qualifier (e.g. "Goblin"); "" if none
    text: str  # the matched oracle clause (the quote, for grounding/scoping)
    source: str  # the card name the signal came from
    confidence: str = (
        "high"  # "high" | "low" — low = a scope guess the agent should confirm
    )


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"(?<=[.;\n])\s+", text) if c.strip()]


def clauses(text: str) -> list[str]:
    """Public alias for the sentence-scoped clause splitter the extractor uses.

    Ranking clusters served lanes by which clause matched them (one physical
    property = one synergy credit), so it must split on the SAME boundaries the
    detectors do — a shared splitter keeps spans aligned with detector scope.
    """
    return _clauses(text)


def _singularize(raw: str) -> str:
    """Lowercase + best-effort singularize a captured noun. The (\\w+?)s? capture
    can emit a partial plural ("Elve", "Dwarve"), so we map those explicitly."""
    w = raw.lower().strip(",.")
    if w in IRREGULAR_SINGULAR:
        return IRREGULAR_SINGULAR[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ves") and len(w) > 4:
        return w[:-3] + "f"
    if w.endswith("ve") and len(w) > 3 and w not in ("cave", "wave", "brave"):
        return w[:-2] + "f"
    # Never strip the trailing "s" of an "-us" word: Fungus / Octopus / Pegasus /
    # Homunculus are SINGULAR subtypes (their plurals are "Fungi" etc., mapped above).
    if w.endswith("s") and len(w) > 1 and not w.endswith(("ss", "us")):
        return w[:-1]
    return w


def _resolve_subject(raw: str, vocab: frozenset[str]) -> str:
    """Resolve a raw capture to a canonical kindred subject, or "" (silent drop).

    Card-type words ("creature"/"permanent") and card-type subjects
    ("artifact"/"land", handled by the floor detectors) never become a kindred
    subject — they fall through to the generic / floor keys. This is the precision
    gate: an unparseable or non-kindred noun produces zero false positives.
    """
    w = _singularize(raw)
    if w in NON_SUBJECT_WORDS or w in CARD_TYPE_SUBJECTS:
        return ""
    # NON_CREATURE_TOKEN denylist (CR 111.10 / 205.3g): Treasure / Clue / Food / … are
    # ARTIFACT-token subtypes, not creature kindred — a few leak into CREATURE_SUBTYPES
    # from the bulk harvest. Deny BEFORE the vocab so "Treasures you control" / "each
    # Clue" never mints a false-positive tribal subject (they feed the dedicated
    # clue/food/treasure + artifacts_matter lanes instead).
    if w in NON_CREATURE_TOKEN:
        return ""
    if w in vocab:
        return w.capitalize()
    return ""


_COMBAT_DAMAGE_TO_PLAYER = re.compile(r"deals combat damage to a player", re.IGNORECASE)


_THAT_PLAYERS_ZONE = re.compile(
    r"that player's (?:graveyard|hand|library)", re.IGNORECASE
)


def _tinybones_scope(clause: str) -> str | None:
    """combat-damage-to-a-player + that-player's-zone → opponents. Kept narrow: a
    broad "its owner's hand → opponents" rule misfires on self-blink/self-bounce."""
    if _COMBAT_DAMAGE_TO_PLAYER.search(clause) and _THAT_PLAYERS_ZONE.search(clause):
        return "opponents"
    return None


_GENERIC_KEYS = frozenset({"creatures_matter"})
