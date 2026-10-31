"""Noncreature permanent quality: how strong an artifact, enchantment,
planeswalker or battle is on its own text, cost and abilities.

Fitted on the guide pairs (``docs/plans/precon-audit/quality_fit_noncreature.py``,
2026-10-31): 7,973 pairs, 115 guide adds in 23 design precons, each pair a guide add
and an on-plan card the reads-first order ranked above it, weighted so each guide
add counts once per guide. An L2 logistic regression on feature differences
(L2 = 3), hand-rounded. Leave-one-deck-out pair accuracy 0.717 (0.71-0.73 across
the L2 strengths tried), against play-rate's 0.650 and mana value's 0.501 on the
same pairs.

Features and weights (in logit units of "the guide prefers this card"):

* ``cheap`` +0.45 — costs 2 or less (``read_cost``: a free alternative cost costs
  nothing, CR 118.9). A cheap permanent is out early and leaves mana for the turn
  it lands; Mind Stone, Skullclamp, Wild Growth and Hardened Scales are guide adds.
  Mana value past the cheap line fitted near zero (+0.13 a mana, the wrong sign for
  a cost) and is left out.
* ``doubler`` +0.55 — a replacement effect that increases a quantity: tokens
  created, counters put (CR 614.1: an effect that watches for an event and
  replaces it with a different one; ``reads.replacement_qty_mod`` with an
  ``INCREASE_QTY_MODS`` kind). It multiplies every other card of the plan:
  Doubling Season, Parallel Lives, Anointed Procession, Primal Vigor over another
  token maker.
* ``job`` +0.2 — the card's best template-job score (ADR-0060's reads: removal,
  protection, board wipe, ramp, card draw), 0 when it does none. A permanent that
  does a job well is the stronger card (Swiftfoot Boots, Mind Stone). Those reads
  are card reads too; only their weights were fitted on play-rate (ADR-0060).
* ``abilities`` -0.6 — each of its own abilities beyond the first that work on
  the battlefield (cap 4; ``own_units`` — not suspend's, which work from a hand
  and exile, CR 702.62a). The pairs' clearest verdict: a focused card beats one
  of many small abilities (Doubling Season over Elspeth, Storm Slayer; Swiftfoot
  Boots over Argentum Armor). Partly the order's own bias: a card of many
  abilities serves more of a deck's lanes, so the reads-first order ranks it
  high, and this weight corrects that.
* ``tokens`` -0.9 — it makes tokens. On a token deck's pages most cards make
  tokens; the guides add the card that multiplies them, or another payoff, over
  one more maker. The pairs' verdict, not a card-strength principle: the weight
  most likely to be the order's bias rather than the card's strength.
* ``scaling`` -0.7 — an amount phase reads as a count of something (X, "for
  each"), not a fixed number (``reads.amount_is_scaling``): only as big as the
  board makes it (Banner of Kinship, Door of Destinies, the "for each" engines),
  where a fixed effect is there the turn it lands. Also fitted, and like
  ``tokens`` partly the order's bias.

Rejected by the fit (each added under 0.01 or lowered the cross-validated
accuracy, in the first fit): mana value, an enters trigger, a recurring trigger,
an activated ability, a static ability, a cost reduction, a mana ability, being a
planeswalker.

A card the read can't see — not a noncreature permanent, or no ability of its own
on phase's trees — scores ``None``, never a low number. Pure: no deck, no
play-rate, no price.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from mtg_utils._analysis.job_quality import READS as JOB_READS
from mtg_utils._analysis.job_quality._common import (
    cast_cost,
    faces,
    free_cast,
    front_mana_cost,
)
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._analysis.write_back import (
    MISSING,
    WriteBackMemo,
    WriteBackSidecar,
    content_key,
)
from mtg_utils._card_ir.crosswalk import (
    INCREASE_QTY_MODS,
    amount_is_scaling,
    replacement_qty_mod,
    unit_zones,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree

#: The card types this read covers, on the front face, with no creature or land.
_TYPES = ("Artifact", "Enchantment", "Planeswalker", "Battle")


@dataclass(frozen=True)
class QualityRead:
    """One card type's quality read: its module's ``features`` and ``WEIGHTS``,
    with the score memoized in ``memo`` (persisted when the module's write-back
    sidecar is attached) per oracle_id and weights, so a read with other weights
    (``dataclasses.replace``) scores by its own."""

    type_name: str
    features: Callable[[dict], dict[str, float] | None]
    weights: Mapping[str, float]
    memo: WriteBackMemo

    def score(self, card: dict) -> float | None:
        """How strong ``card`` is (higher is stronger): the weighted sum of its
        features, or ``None`` when the read can't see it."""
        oid = card.get("oracle_id") or ""
        key = (oid, tuple(sorted(self.weights.items())))
        if oid and (hit := self.memo.get(key)) is not MISSING:
            return cast("float | None", hit)
        feats = self.features(card)
        score = (
            None
            if feats is None
            else round(sum(self.weights[k] * v for k, v in feats.items()), 3)
        )
        if oid and (feats is not None or signal_trees_for(card, bulk=card)):
            self.memo.put(key, score)  # never a None read before phase data is there
        return score


def own_units(trees: Sequence[ConceptTree], zone: str) -> list[AbilityUnit]:
    """The card's own abilities across its faces that function in ``zone``:
    every unit but the ones tree synthesis adds (ADR-0047), which read a clause
    again rather than add one, and the ones that say they work from another zone
    (``reads.unit_zones``, CR 113.6b) — suspend's (CR 702.62a: a static ability
    in hand, two triggers in exile), cycling's from a hand."""
    return [
        u
        for t in trees
        for u in t.units
        if u.origin != "synth" and (not (z := unit_zones(u)) or zone in z)
    ]


#: What an X in the mana cost is cast for, beyond the printed cost. A printed
#: mana value counts X as 0 (CR 202.3e), so Martial Coup ({X}{W}{W}) read as a
#: two-mana spell and topped the wipe page's blend over Wrath of God, Cataclysmic
#: Prospecting as two mana over Starfall Invocation. The reads' own line, not a
#: rule's: three is the smallest X most X spells do something for.
X_ASSUMED = 3.0


def read_cost(card: dict) -> float:
    """The mana the card costs to cast: none when an alternative cost lets it be
    cast for no mana (``_common.free_cast``; CR 118.9), else its curve cost
    (``_common.cast_cost``) plus :data:`X_ASSUMED` for an X in its mana cost."""
    if free_cast(card):
        return 0.0
    cost = cast_cost(card)
    if "{X}" in front_mana_cost(card):
        cost += X_ASSUMED
    return cost


def best_job(card: dict) -> float:
    """The card's best template-job score (ADR-0060), 0 when it does no job."""
    scores = [s for r in JOB_READS.values() if (s := r.score(card)) is not None]
    return max(scores, default=0.0)


def features(card: dict) -> dict[str, float] | None:
    """The read's features for ``card``, or ``None`` when it is not a
    noncreature permanent or phase gives it no ability of its own."""
    front = faces(card)[0]
    if "Creature" in front or "Land" in front or not any(t in front for t in _TYPES):
        return None
    units = own_units(signal_trees_for(card, bulk=card), "Battlefield")
    if not units:
        return None
    effects = [e for u in units for e in u.effects]
    doubler = any(
        u.origin == "replacement"
        and (q := replacement_qty_mod(u.node)) is not None
        and q[0] in INCREASE_QTY_MODS
        for u in units
    )
    return {
        "cheap": float(read_cost(card) <= 2),
        "doubler": float(doubler),
        "job": best_job(card),
        "abilities": float(min(len(units) - 1, 4)),
        "tokens": float(any(e.concept == "make_token" for e in effects)),
        "scaling": float(
            any(
                amount_is_scaling(e.node) or amount_is_scaling(e.node, "count")
                for e in effects
            )
        ),
    }


#: Hand-rounded from the 2026-10-31 fit (see the module docstring).
WEIGHTS: dict[str, float] = {
    "cheap": 0.45,
    "doubler": 0.55,
    "job": 0.2,
    "abilities": -0.6,
    "tokens": -0.9,
    "scaling": -0.7,
}

#: Bumped for a change in what a persisted score means that the module's
#: content hash doesn't see (a data file it loads).
SIDECAR_VERSION = 1


def _content_key() -> str:
    """The content hash of the code a score is computed by: this module's
    import closure (the job reads and the signal path with it)."""
    return content_key(
        f"quality_noncreature_permanent:{SIDECAR_VERSION}",
        "mtg_utils._analysis.card_quality.noncreature_permanent",
    )


#: ``<bulk>.quality-noncreature-permanent.pkl``: the read's per-card scores.
SIDECAR = WriteBackSidecar(".quality-noncreature-permanent.pkl", _content_key)

READ = QualityRead("noncreature_permanent", features, WEIGHTS, SIDECAR.memo("score"))


def attach_sidecar(bulk_path: Path | None) -> bool:
    """Serve the read's scores from ``<bulk_path>.quality-noncreature-
    permanent.pkl`` and write back what this process computes, at exit."""
    return SIDECAR.attach(bulk_path)
