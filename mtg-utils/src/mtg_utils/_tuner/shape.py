"""Deterministic Shape inference — aggro / midrange / control / combo.

Nothing in the repo classifies a deck's Shape (``score_card`` only *scores cards
given* a shape). This is the clean inverse of those priors, fed by composition
features the snapshot already computes, and it is transparent (returns the per-shape
scores + evidence) and overridable (deck-forge CONTEXT.md, "Shape"; ADR-0024 scales
the conditional floors by it).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mtg_utils._tuner.classify import CardClass

SHAPES = ("aggro", "midrange", "control", "combo")


@dataclass(frozen=True)
class ShapeResult:
    shape: str
    scores: dict[str, float]
    evidence: list[str]
    inferred: bool  # False when the user overrode the inference


def _is_creature(card: dict) -> bool:
    return "creature" in (card.get("type_line") or "").lower()


def infer_shape(
    classes: Sequence[CardClass],
    *,
    avg_cmc: float,
    combo_present: bool,
    override: str | None = None,
) -> ShapeResult:
    """Score the four shapes from deck composition and pick the best fit.

    midrange carries a baseline so it wins on a featureless/ambiguous deck (the genre
    mean). An ``override`` in :data:`SHAPES` wins outright and marks ``inferred=False``.
    """
    nonland = [c for c in classes if c.bucket not in ("land", "commander")]
    n = max(1, len(nonland))
    creatures = sum(1 for c in nonland if _is_creature(c.record))
    interaction = sum(1 for c in nonland if "interaction" in c.roles)
    draw = sum(1 for c in nonland if "card_draw" in c.roles)
    low_drops = sum(1 for c in nonland if c.cmc <= 2.0)

    creat = creatures / n
    inter = interaction / n
    drw = draw / n
    lowf = low_drops / n

    scores = {
        "aggro": max(0.0, 2.8 - avg_cmc) * 2.0 + creat * 3.0 + lowf * 2.0,
        "control": inter * 6.0
        + drw * 3.0
        + max(0.0, avg_cmc - 3.0) * 2.0
        - creat * 1.5,
        "combo": (4.0 if combo_present else 0.0) + max(0.0, 0.35 - creat) * 6.0,
        "midrange": 1.0
        + (1.0 if 2.8 <= avg_cmc <= 3.6 else 0.0)
        + (creat if 0.30 <= creat <= 0.62 else 0.0),
    }

    if override in SHAPES:
        shape, inferred = override, False
    else:
        # max() ties break by dict order (aggro→midrange→control→combo); midrange's
        # baseline keeps a featureless deck out of the extremes.
        shape, inferred = max(scores, key=lambda s: scores[s]), True

    evidence = [
        f"avg MV {avg_cmc:.1f}",
        f"{creatures} creatures ({creat * 100:.0f}%)",
        f"{interaction} interaction",
        f"{draw} card draw",
    ]
    if combo_present:
        evidence.append("combo line present")
    return ShapeResult(shape=shape, scores=scores, evidence=evidence, inferred=inferred)
