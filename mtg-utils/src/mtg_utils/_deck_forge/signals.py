"""Deterministic signal extraction — the discovery-engine keystone.

A ``Signal`` is a precisely-scoped fact pulled from a card's oracle text: what it
cares about / triggers on, and *whose* resource it concerns. Scope is part of the
signal's identity, which is how we avoid the Tinybones overgeneralization — a card
that benefits from an opponent's graveyard yields a signal scoped ``opponents``,
never a generic graveyard signal that would justify self-mill.

This is the keyless baseline; the session-agent refines/extends scoping in M3 (with
mandatory oracle-clause quotes), but the deterministic engine already scopes the
high-value cases correctly so the no-agent mode stays honest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mtg_utils.card_classify import get_oracle_text


@dataclass(frozen=True)
class Signal:
    """A scoped fact extracted from one card's oracle text."""

    key: str  # canonical signal id, e.g. "creature_etb"
    scope: str  # "you" | "opponents" | "each" | "any"
    subject: str  # optional qualifier (e.g. a creature subtype); "" if none
    text: str  # the matched oracle clause (the quote, for grounding/scoping)
    source: str  # the card name the signal came from


# Each detector: (key, clause-matcher, forced_scope|None). When forced_scope is
# None the clause's own scope is used (critical for creature_etb / graveyard_matters).
def _has(*needles: str):
    return lambda c: all(n in c for n in needles)


def _re(pattern: str):
    rx = re.compile(pattern)
    return lambda c: rx.search(c) is not None


_DETECTORS: tuple[tuple[str, object, str | None], ...] = (
    (
        "creature_etb",
        lambda c: (
            _re(r"\b(?:a|another|one or more|each)\b[^.]*\bcreature[s]?\b[^.]*\benter")(
                c
            )
            and ("whenever" in c or "when " in c)
        ),
        None,
    ),
    ("creatures_matter", _has("creatures you control"), "you"),
    (
        "lifegain_matters",
        lambda c: "whenever" in c and "gain" in c and "life" in c,
        "you",
    ),
    ("graveyard_matters", _has("graveyard"), None),
    ("spellcast_matters", _has("whenever you cast", "spell"), "you"),
    ("death_matters", lambda c: "whenever" in c and "dies" in c, None),
    ("sacrifice_matters", _re(r"sacrifice (?:a|an|another|two|three|x|\d)"), "you"),
    ("attack_matters", lambda c: "whenever" in c and "attack" in c, None),
    ("draw_matters", _has("whenever you draw"), "you"),
    (
        "landfall",
        lambda c: "landfall" in c or ("whenever a land" in c and "enter" in c),
        "you",
    ),
    (
        "counters_matter",
        lambda c: "+1/+1 counter" in c and ("for each" in c or "number of" in c),
        None,
    ),
)


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"(?<=[.;\n])\s+", text) if c.strip()]


def _scope(clause_lower: str) -> str:
    if "opponent" in clause_lower:
        return "opponents"
    if "each player" in clause_lower:
        return "each"
    if (
        "you control" in clause_lower
        or "your " in clause_lower
        or re.search(r"\byou\b", clause_lower)
    ):
        return "you"
    return "any"


def extract_signals(card: dict) -> list[Signal]:
    """Extract scoped signals from a card's oracle text (deterministic baseline)."""
    text = get_oracle_text(card) or ""
    name = card.get("name", "")
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()
    for clause in _clauses(text):
        cl = clause.lower()
        clause_scope = _scope(cl)
        for key, matches, forced_scope in _DETECTORS:
            if not matches(cl):
                continue
            scope = forced_scope or clause_scope
            ident = (key, scope, "")
            if ident in seen:
                continue
            seen.add(ident)
            out.append(
                Signal(
                    key=key, scope=scope, subject="", text=clause.strip(), source=name
                )
            )
    return out


def aggregate_signals(records: list[dict | None]) -> list[Signal]:
    """Union of signals across many cards, deduped by (key, scope, subject)."""
    seen: dict[tuple[str, str, str], Signal] = {}
    for record in records:
        if not record:
            continue
        for sig in extract_signals(record):
            ident = (sig.key, sig.scope, sig.subject)
            seen.setdefault(ident, sig)
    return list(seen.values())
