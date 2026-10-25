"""Job quality — how well a card does a template job, read off its own trees.

The tuner's upgrade trades a card for one doing the same job better. "Better"
is play-rate (EDHREC rank); these reads are the first step to taking it from the
card instead — what its effect does, what it costs, what conditions it carries —
so the tuner can land on the upgrade guides' cards from first principles.
Play-rate is the yardstick each read is measured against, never an input, and a
read replaces it only where it predicts the guides' picks as well.

One module per job, each a small set of features off the card's signal trees
(``signal_trees_for`` — the trees the lanes read, so a clause the tree-synthesis
stage adds reaches the read as it reaches the signal and the role) and a
hand-rounded weight per feature in units of log10 play-rate (fitted by ridge
regression on the commander-legal pool, 2026-10-19, kept only where a feature
reads the card correctly). A card the read can't see — none of that job's shape —
scores ``None``, never a low number. ``docs/plans/precon-audit/job_reads.py``
re-measures every read against play-rate and the precon guides; the results are
in the audit report (eighth pass) and ADR-0060.

Every read GATES an upgrade's candidates: the add must do the job by the read
(a looter is no card-draw upgrade, Animate Dead no removal); "better than the
cut" stays play-rate's, since against the guides' cuts every read found the
weaker card less often. A read that also ORDERS them (``JobRead.orders``) does
it blended with play-rate — each candidate's read percentile plus its play-rate
percentile — because at the top of the list, the one card the tuner takes, the
read alone found the guides' adds less often than play-rate did, for every job
(the measurement below).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from mtg_utils._analysis.job_quality import (
    board_wipe,
    card_draw,
    protection,
    ramp,
    removal,
)
from mtg_utils._analysis.job_quality._common import JOB_READS
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._analysis.write_back import MISSING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class JobRead:
    """One job's card read: its module's ``features`` and ``WEIGHTS``, whether it
    also ORDERS an upgrade's candidates (blended with play-rate) or only gates
    them, and an optional deck ``fit``: the share of the card's job its deck can
    fuel, in [0, 1] (card draw's ``deck_fit`` — Skullclamp needs bodies to die)."""

    job: str
    features: Callable[[dict], dict[str, float] | None]
    weights: Mapping[str, float]
    orders: bool
    fit: Callable[[dict, Sequence[dict]], float] | None = None
    #: Whether the read covers the whole job. Removal is part of the
    #: ``interaction`` job (counterspells are the rest), so it gates only a
    #: card it reads as removal: a counterspell's upgrade, and an interaction
    #: fill, are play-rate's.
    whole_job: bool = True
    #: Whether theme fit breaks a near tie on this read in an upgrade's order
    #: (``swaps._theme_ties``): an on-theme card scoring about as well goes
    #: before an off-theme staple. Card draw and ramp, by measurement.
    theme_ties: bool = False
    #: Whether this read orders the job's Spine fill ("board wipes short")
    #: ahead of the fill's mana-value band. Board wipes, by measurement.
    fill_orders: bool = False

    def deck_fit(self, card: dict, deck: Sequence[dict] | None) -> float:
        """The share of ``card``'s job ``deck`` (its cards' records) can fuel;
        1.0 without a deck, or for a job with no deck read."""
        if self.fit is None or not deck:
            return 1.0
        return self.fit(card, deck)

    def score(self, card: dict, deck: Sequence[dict] | None = None) -> float | None:
        """How well ``card`` does the job (higher is better): the weighted sum of
        its features, or ``None`` when it does none of the job. Given ``deck``,
        lowered by the share of the job the deck can't fuel (:meth:`deck_fit`):
        by that fraction of its size, whichever its sign. The card part is
        memoized per oracle_id, the deck part read per call."""
        base = self._card_score(card)
        if base is None or deck is None or self.fit is None:
            return base
        f = self.deck_fit(card, deck)
        return round(base - abs(base) * (1 - f), 3)

    def _card_score(self, card: dict) -> float | None:
        """The card's own score, deck-free: memoized per oracle_id, and persisted
        by the job-read sidecar when one is attached, for the job's own read in
        :data:`READS` only (another read, with its own features or weights, is
        scored live)."""
        oid = card.get("oracle_id")
        key = (self.job, oid or "")
        memoized = bool(oid) and READS.get(self.job) is self
        if memoized and (hit := _SCORES.get(key)) is not MISSING:
            return cast("float | None", hit)
        feats = self.features(card)
        score = (
            None
            if feats is None
            else round(sum(self.weights[k] * v for k, v in feats.items()), 3)
        )
        if memoized and (feats is not None or signal_trees_for(card, bulk=card)):
            _SCORES.put(key, score)  # never a None read before phase data is there
        return score


#: (job, oracle_id) -> score: a read walks every unit of every face, and an
#: upgrade pass asks it for each card of a job's match set (thousands).
_SCORES = JOB_READS.memo("score")


def attach_job_read_sidecar(bulk_path: Path | None) -> bool:
    """Serve the reads' deck-free per-card values (each job's score, card draw's
    fuel) from ``<bulk_path>.job-reads.pkl`` and write back, at process exit,
    what this process computes (``_common.JOB_READS``). An entry holds for the
    same signal path, reads and bulk only; a served value is the one a live
    read computes. ``False`` (no bulk) leaves the reads live-only."""
    return JOB_READS.attach(bulk_path)


#: Each job's read, by ``issues.upgrade_job``'s job names. ``orders`` was
#: measured on the 25 precons' guide adds, ranked among the cards of their color
#: identity the read scores (2026-10-19): the blend with play-rate found more
#: guide adds near the top than play-rate alone for board wipes (11 vs 7 in the
#: top thirty, n=19) and card draw (11 vs 6 in the top ten); fewer for
#: protection (top three 11 vs 12, top thirty 24 vs 29), removal (7 vs 9 in the
#: top ten) and ramp (3 vs 4). Removal and ramp gate only. Protection orders by
#: Dan's call (2026-10-19) despite trailing: its picks (Flawless Maneuver,
#: Deflecting Swat, Teferi's Protection over Swiftfoot Boots) read right to a deck
#: builder, and the gap is small. The read alone did worse than play-rate for
#: every job. (Measured over the whole identity the read scores; the tuner
#: ranks the job's whole match set in that identity.)
#:
#: Re-measured on the tuner itself (2026-10-24, the 25 precons at their own
#: budgets, guide-matching adds and cuts against 39 / 158): the read alone
#: ordering an upgrade, play-rate breaking ties, matched 40 / 159 for wipes
#: (no wipe add gained; 47 against 50 beside the changes kept), 43 / 164 for
#: card draw (one draw add fewer: River Kelpie and Ghostly Pilferer, the read's
#: top engines, over Kindred Discovery and Deadly Dispute), 35 for removal and
#: ramp, and no change for protection — so each keeps the order above. Theme
#: fit breaking a near tie (``theme_ties``) took card draw to 42 and ramp to 41;
#: the wipe read ordering the wipe fill (``fill_orders``), to 40.
READS: dict[str, JobRead] = {
    r.job: r
    for r in (
        JobRead(
            "interaction",
            removal.features,
            removal.WEIGHTS,
            orders=False,
            whole_job=False,
        ),
        JobRead("protection", protection.features, protection.WEIGHTS, orders=True),
        JobRead(
            "board_wipe",
            board_wipe.features,
            board_wipe.WEIGHTS,
            orders=True,
            fill_orders=True,
        ),
        JobRead("ramp", ramp.features, ramp.WEIGHTS, orders=False, theme_ties=True),
        JobRead(
            "card_draw",
            card_draw.features,
            card_draw.WEIGHTS,
            orders=True,
            fit=card_draw.deck_fit,
            theme_ties=True,
        ),
    )
}


def read_for(job: str | None) -> JobRead | None:
    """``job``'s card read, or ``None`` when the job has none yet."""
    return READS.get(job or "")


def job_score(
    card: dict, job: str | None, deck: Sequence[dict] | None = None
) -> float | None:
    """How well ``card`` does ``job`` (in ``deck``, when given: its cards'
    records), or ``None`` when the job has no read yet or the card does none of
    it."""
    read = read_for(job)
    return read.score(card, deck) if read is not None else None
