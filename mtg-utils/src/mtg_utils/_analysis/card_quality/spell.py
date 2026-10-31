"""Spell quality: how strong an instant or sorcery is on its own text and cost.

Fitted on the guide pairs (``docs/plans/precon-audit/quality_fit_noncreature.py``,
2026-10-31): 965 pairs, 37 guide adds in 16 design precons, each pair a guide add
and an on-plan spell the reads-first order ranked above it, weighted so each guide
add counts once per guide. An L2 logistic regression on feature differences
(L2 = 3), hand-rounded. Leave-one-deck-out pair accuracy 0.734, against play-rate's
0.723 and mana value's 0.553 on the same pairs: level with play-rate within the
noise of 16 decks (0.68-0.73 across the L2 strengths tried).

Features and weights (in logit units of "the guide prefers this card"):

* ``cost`` -0.2 a mana — what it costs to cast (``noncreature_permanent.read_cost``:
  nothing under a free alternative cost, CR 118.9 — Fierce Guardianship with a
  commander; else the curve cost).
* ``tutor`` +0.6 — it searches a library (CR 701.23a: find a card that matches the
  description): it is the card the deck needs most. Gamble, Buried Alive, Entomb,
  Crop Rotation, Diabolic Intent and Savage Order are guide adds; the pairs' most
  reliable feature (the guide add is the tutor in 93% of the pairs a tutor splits).
* ``answer`` +0.35 — it counters a spell, or does removal or a board wipe by
  ADR-0060's reads: it deals with what the deck can't otherwise.
* ``per_cast`` +0.6 each (cap 4) — the distinct things one cast does: the
  recognized effects of its richest ability, none a drawback of the caster's (a
  discard, a sacrifice, life lost, damage to you); for a modal spell that lets you
  choose more modes under a condition (CR 700.2; Jeska's Will's "If you control a
  commander ... choose both", which any commander satisfies, per its rulings),
  every mode's. Jeska's Will adds mana and exiles three to play; Fact or Fiction
  only moves cards.
* ``abilities`` -0.35 each (cap 3) — its abilities beyond the first that work on
  the stack: a charm's or command's other modes, a split card's other half. One
  cast gets one mode, and each is costed as a part of the card.

Rejected by the fit (each lowered the cross-validated accuracy, in the first
fit): cards drawn or
exiled to play, a cheap line at one mana, an instant or flash, tokens made, mana
made, a scaling amount, a recast keyword (flashback, buyback), and the best job
score of ADR-0060's reads.

A card the read can't see — not an instant or sorcery, or no ability of its own
on phase's trees (Throes of Chaos) — scores ``None``, never a low number. Pure:
no deck, no play-rate, no price.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtg_utils._analysis.card_quality.noncreature_permanent import (
    QualityRead,
    own_units,
    read_cost,
)
from mtg_utils._analysis.job_quality import READS as JOB_READS
from mtg_utils._analysis.job_quality._common import faces
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._analysis.write_back import WriteBackSidecar, content_key

if TYPE_CHECKING:
    from pathlib import Path

    from mtg_utils._card_ir.crosswalk import ConceptNode

#: What a spell asks of its caster rather than does for them: a discard, a
#: sacrifice, life lost or damage dealt to you.
_DRAWBACKS = frozenset({"discard", "sacrifice", "lose_life", "deal_damage"})
#: ADR-0060's reads of an answer to a permanent.
_ANSWER_JOBS = ("interaction", "board_wipe")


def _does(e: ConceptNode) -> bool:
    """An effect the spell does: a recognized concept (phase's ``other`` is
    structure — a shuffle, a choice) that is no drawback of the caster's."""
    return e.concept != "other" and not (e.concept in _DRAWBACKS and e.scope == "you")


def features(card: dict) -> dict[str, float] | None:
    """The read's features for ``card``, or ``None`` when it is not an instant
    or sorcery or phase gives it no ability of its own."""
    front = faces(card)[0]
    if "Instant" not in front and "Sorcery" not in front:
        return None
    trees = signal_trees_for(card, bulk=card)
    units = own_units(trees, "Stack")
    if not units:
        return None
    concepts = [{e.concept for e in u.effects if _does(e)} for u in units]
    per_cast = max(len(c) for c in concepts)
    modes = [c for u, c in zip(units, concepts, strict=True) if u.kind == "Spell"]
    if modes and any(t.card_modal_conditions for t in trees):
        per_cast = max(per_cast, len(set().union(*modes)))
    every = set().union(*concepts)
    answer = "counter_spell" in every or any(
        JOB_READS[j].score(card) is not None for j in _ANSWER_JOBS
    )
    return {
        "cost": read_cost(card),
        "tutor": float("tutor" in every),
        "answer": float(answer),
        "per_cast": float(min(per_cast, 4)),
        "abilities": float(min(len(units) - 1, 3)),
    }


#: Hand-rounded from the 2026-10-31 fit (see the module docstring).
WEIGHTS: dict[str, float] = {
    "cost": -0.2,
    "tutor": 0.6,
    "answer": 0.35,
    "per_cast": 0.6,
    "abilities": -0.35,
}

#: Bumped for a change in what a persisted score means that the module's
#: content hash doesn't see (a data file it loads).
SIDECAR_VERSION = 1


def _content_key() -> str:
    """The content hash of the code a score is computed by: this module's
    import closure (the permanent read's helpers, the job reads and the signal
    path with it)."""
    return content_key(
        f"quality_spell:{SIDECAR_VERSION}", "mtg_utils._analysis.card_quality.spell"
    )


#: ``<bulk>.quality-spell.pkl``: the read's per-card scores.
SIDECAR = WriteBackSidecar(".quality-spell.pkl", _content_key)

READ = QualityRead("spell", features, WEIGHTS, SIDECAR.memo("score"))


def attach_sidecar(bulk_path: Path | None) -> bool:
    """Serve the read's scores from ``<bulk_path>.quality-spell.pkl`` and write
    back what this process computes, at exit."""
    return SIDECAR.attach(bulk_path)
