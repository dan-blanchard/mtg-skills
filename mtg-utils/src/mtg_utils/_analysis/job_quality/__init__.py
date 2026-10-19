"""Job quality — how well a card does a template job, read off its own trees.

The tuner's upgrade trades a card for one doing the same job better. "Better"
is play-rate (EDHREC rank); these reads are the first step to taking it from the
card instead — what its effect does, what it costs, what conditions it carries —
so the tuner can land on the upgrade guides' cards from first principles.
Play-rate is the yardstick each read is measured against, never an input, and a
read replaces it only where it predicts the guides' picks as well.

One module per job, each a small set of features off phase's concept trees and a
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

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from mtg_utils._analysis.job_quality import (
    board_wipe,
    card_draw,
    protection,
    ramp,
    removal,
)
from mtg_utils._card_ir.trees import trees_for


@dataclass(frozen=True)
class JobRead:
    """One job's card read: its module's ``features`` and ``WEIGHTS``, and
    whether it also ORDERS an upgrade's candidates (blended with play-rate) or
    only gates them."""

    job: str
    features: Callable[[dict], dict[str, float] | None]
    weights: Mapping[str, float]
    orders: bool

    def score(self, card: dict) -> float | None:
        """How well ``card`` does the job (higher is better): the weighted sum of
        its features, or ``None`` when it does none of the job."""
        oid = card.get("oracle_id")
        key = (self.job, oid or "")
        if oid and key in _SCORE_MEMO:
            return _SCORE_MEMO[key]
        feats = self.features(card)
        score = (
            None
            if feats is None
            else round(sum(self.weights[k] * v for k, v in feats.items()), 3)
        )
        if oid and (feats is not None or trees_for(card, bulk=card)):
            _SCORE_MEMO[key] = score  # never a None read before phase data is there
        return score


#: (job, oracle_id) -> score: a read walks every unit of every face, and an
#: upgrade pass asks it for each candidate of a several-hundred-card page.
_SCORE_MEMO: dict[tuple[str, str], float | None] = {}


#: Each job's read, by ``issues.upgrade_job``'s job names. ``orders`` was
#: measured on the 25 precons' guide adds, ranked among the cards of their color
#: identity the read scores (2026-10-19): the blend with play-rate found more
#: guide adds near the top than play-rate alone for board wipes (11 vs 7 in the
#: top thirty, n=19) and card draw (11 vs 6 in the top ten); fewer for
#: protection (top three 11 vs 12, top thirty 24 vs 29), removal (7 vs 9 in the
#: top ten) and ramp (3 vs 4), which gate only. The read alone did worse than
#: play-rate for every job. (Measured over the whole identity, not the tuner's
#: 600-card page above its fit floor.)
_READS: dict[str, JobRead] = {
    r.job: r
    for r in (
        JobRead("interaction", removal.features, removal.WEIGHTS, orders=False),
        JobRead("protection", protection.features, protection.WEIGHTS, orders=False),
        JobRead("board_wipe", board_wipe.features, board_wipe.WEIGHTS, orders=True),
        JobRead("ramp", ramp.features, ramp.WEIGHTS, orders=False),
        JobRead("card_draw", card_draw.features, card_draw.WEIGHTS, orders=True),
    )
}


def read_for(job: str | None) -> JobRead | None:
    """``job``'s card read, or ``None`` when the job has none yet."""
    return _READS.get(job or "")


def job_score(card: dict, job: str | None) -> float | None:
    """How well ``card`` does ``job``, or ``None`` when the job has no read yet or
    the card does none of it."""
    read = read_for(job)
    return read.score(card) if read is not None else None
