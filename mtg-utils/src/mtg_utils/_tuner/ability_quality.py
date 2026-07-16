"""ADR-0040 §2/§5 (task #97): the curated ability-quality table.

A Granter's value is its granted-ability quality relative to its cost —
never its body or playrate (a Sliver deck is Granter-dense; the tuner
condemned Bonescythe-class cards as weak bodies with fringe ranks). The
table is the pragmatic spine; anti-synergy predicates are added only for
OBSERVED misleads (long-term direction: grow the predicates, shrink the
table).

Grades:
* ``premium`` — defines combats or ends games when granted team-wide.
* ``solid`` — a real ability worth a slot; also the DEFAULT for anything
  the table doesn't know (an ungraded keyword or a quoted ability grant
  must never condemn a Granter on table absence alone).
* ``weak`` — conditional/marginal enough that the Granter is an upgrade
  candidate: outlast is tap-gated sorcery-speed growth (CR 702.107a — the
  benchmark's one correct cut, Enduring Sliver); defender prohibits
  attacking (CR 702.3); reach and landwalk are opponent-dependent
  (CR 702.17 / 702.14).

Closer flags per ADR-0040 §5's adjudication: double strike (CR 702.4) and
team-unblockable-class evasion (shadow, CR 702.28 — blockable only by
shadow) close games; mass infect is lethal at ten poison (CR 702.90b /
104.3d); vigilance, first strike, and haste-on-its-own are not closers.
Exalted stays solid (CR 702.83a — a real attacks-alone boost; First
Sliver's Chosen is NOT a correct cut, per the ADR's motivating session).
"""

from __future__ import annotations

from collections.abc import Iterable

from mtg_utils._deck_forge.crosswalk_signals import GrantPayload

# keyword -> (grade, closer). Keys are extract_grant_payloads' normalized
# form (CamelCase split, lowercased; a MirrorVariant contributes its key
# name — "protection", "ward", "landwalk").
GRANT_QUALITY: dict[str, tuple[str, bool]] = {
    "double strike": ("premium", True),
    "infect": ("premium", True),
    "shadow": ("premium", True),
    "cant be blocked": ("premium", True),
    "flying": ("premium", False),
    "indestructible": ("premium", False),
    "hexproof": ("premium", False),
    "haste": ("solid", False),
    "trample": ("solid", False),
    "menace": ("solid", False),
    "lifelink": ("solid", False),
    "deathtouch": ("solid", False),
    "first strike": ("solid", False),
    "vigilance": ("solid", False),
    "ward": ("solid", False),
    "protection": ("solid", False),
    "shroud": ("solid", False),
    "flash": ("solid", False),
    "fear": ("solid", False),
    "intimidate": ("solid", False),
    "skulk": ("solid", False),
    "exalted": ("solid", False),
    "prowess": ("solid", False),
    "outlast": ("weak", False),
    "defender": ("weak", False),
    "reach": ("weak", False),
    "landwalk": ("weak", False),
}

_GRADE_RANK = {"premium": 2, "solid": 1, "weak": 0}

# Hellbent-style gate (the §2 first observed mislead, Bladeback Sliver):
# under a draw-engine commander the hand never empties, so the grant's
# condition is effectively unreachable and the payload reads weak.
_HELLBENT_GATE = "no cards in hand"


def grade_of(keyword: str) -> tuple[str, bool]:
    """(grade, closer) for a normalized granted keyword; ungraded → solid."""
    return GRANT_QUALITY.get(keyword, ("solid", False))


def _payload_grade(pay: GrantPayload, *, draw_engine_commander: bool) -> str:
    if draw_engine_commander and _HELLBENT_GATE in pay.raw.lower():
        return "weak"
    if pay.kind in ("ability", "anthem"):
        # "ability": a quoted granted ability the table can't grade at all.
        # "anthem" (verified-review Fix 3): a raw AddPower/AddToughness
        # stat-boost payload — no keyword, so no table row could ever grade
        # it; it IS the Granter's value (Goblin King), never table-weak.
        return "solid"
    return grade_of(pay.keyword)[0]


def has_closer_grant(payloads: Iterable[GrantPayload]) -> bool:
    """ADR-0040 §5 (task #100): True when any payload grants a closer-grade
    keyword — the Granter counts as ONE closer regardless of recipients."""
    return any(pay.kind == "keyword" and grade_of(pay.keyword)[1] for pay in payloads)


def grant_grade(
    payloads: Iterable[GrantPayload],
    *,
    draw_engine_commander: bool = False,
) -> str | None:
    """The card's Granter grade: its BEST payload's grade (a card granting
    outlast AND double strike is judged by the double strike), or ``None``
    for a non-Granter (no payloads)."""
    best: str | None = None
    for pay in payloads:
        g = _payload_grade(pay, draw_engine_commander=draw_engine_commander)
        if best is None or _GRADE_RANK[g] > _GRADE_RANK[best]:
            best = g
    return best
