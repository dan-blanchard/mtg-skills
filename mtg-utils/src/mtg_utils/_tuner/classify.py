"""Per-card Spine / Engine / Filler classification (the tuner's shared substrate).

The tri-partition (deck-forge CONTEXT.md): every nonland, non-commander card is
**Spine** (mandatory scaffolding — ramp / draw / interaction / wipes), **Engine**
(serves an avenue), or **Filler** (serves no avenue here). Lands and commanders are
their own buckets. No new matchers: Spine roles come from ``budgets.role_of`` and
avenue-serving from ``ranking.score_candidate``/``serves`` — both bottoming out in
``theme_presets`` (ADR-0023).
"""

from __future__ import annotations

from dataclasses import dataclass

from mtg_utils._deck_forge.budgets import protects, role_of
from mtg_utils._deck_forge.ranking import score_candidate
from mtg_utils.card_classify import is_land
from mtg_utils.hydrated_deck import HydratedDeck

# The hard-counted Spine roles; ``lands`` is its own bucket (the curve gate's domain).
_SPINE_ROLES = frozenset({"ramp", "card_draw", "interaction", "board_wipe"})


@dataclass(frozen=True)
class CardClass:
    """One deck card's classification, used by every downstream metric."""

    name: str
    bucket: str  # "commander" | "land" | "spine" | "engine" | "filler"
    roles: tuple[str, ...]  # template roles filled (sorted)
    served: tuple[str, ...]  # avenue labels this card serves (deduped)
    dual_purpose: bool  # Spine AND serves an avenue (a "win-win" card)
    cmc: float
    record: dict


def classify_deck(
    hd: HydratedDeck, deck_signals: list, commander_names: set[str]
) -> list[CardClass]:
    """Classify every distinct deck card (all zones, one record per name).

    ``served`` is the set of avenue labels the card feeds — the same
    ``score_candidate`` machinery the Find ranker uses, so a card's tuner
    classification can never drift from how the rest of deck-forge scores it.
    """
    out: list[CardClass] = []
    for rec in hd.records:
        name = rec.get("name", "")
        roles = role_of(rec)
        served = tuple(score_candidate(rec, active_signals=deck_signals)["served"])
        if name in commander_names:
            bucket = "commander"
        elif is_land(rec):
            bucket = "land"
        elif roles & _SPINE_ROLES:
            bucket = "spine"
        elif served:
            bucket = "engine"
        elif protects(rec):
            bucket = "spine"  # protection is conditional Spine (Tier-2), never filler
        else:
            bucket = "filler"
        out.append(
            CardClass(
                name=name,
                bucket=bucket,
                roles=tuple(sorted(roles)),
                served=served,
                dual_purpose=(bucket == "spine" and bool(served)),
                cmc=float(rec.get("cmc", 0.0) or 0.0),
                record=rec,
            )
        )
    return out
