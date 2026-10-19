# Job reads gate and blend the tuner's upgrades

The seventh precon pass (2026-10-19) gave the tuner its upgrade slots: an off-lane
card few decks play is traded for a better-played card doing the same job. "Better"
was EDHREC play-rate, the population's verdict. Dan's goal for the tuner is to land
on the cards upgrade guides recommend from first principles: what a card does, what
it costs, how it fits the deck. He also called the play-rate results "still very
useful info to building towards that goal". ADR-0042's Rate read tried
cost-effectiveness for tokens, damage and draw against crowd picks and was falsified.
It never covered removal, ramp, wipes or protection, and it was graded on commander
discovery, not same-job upgrades.

**Decision.** `_analysis/job_quality/` holds one read per template job: removal (the
`interaction` job), card draw, ramp, board wipes, protection. Each is a few features
read off phase's concept trees — what the effect reaches, its conditions, its real
cost, its magnitude, whether it repeats — with hand-rounded weights in units of
log10 play-rate, fitted by ridge regression on the commander-legal pool. A card the
read can't see scores `None`, never a low number. Play-rate is the yardstick a read
is measured against, never an input to it.

- **Every read gates membership.** An upgrade's add must do the job by the read
  (a looter is no card-draw upgrade, Animate Dead is no removal). "Better than the
  cut" stays play-rate's: against the precon guides' cuts every read found the
  weaker card less often than play-rate (bottom-two guide-cut hits, read vs
  play-rate: removal 16 vs 21, ramp 14 vs 19, draw 19 vs 20, wipes 9 vs 10).
- **Two reads also order, blended with play-rate** (`JobRead.orders`: board wipes,
  card draw). Each candidate's read percentile on the page plus its play-rate
  percentile decides (`swaps._blended_percentiles`). The tuner takes the top card,
  and at the top of the list the read alone found the guides' adds less often than
  play-rate did, for every job; the blend beat play-rate for wipes (11 vs 7 guide
  adds in the top thirty, n=19) and draw (11 vs 6 in the top ten), and trailed it
  for protection (top thirty 24 vs 29), removal and ramp, which gate only. These
  counts rank the whole color identity, not the tuner's 600-card page above its
  fit floor — an approximation of the shipped order.
- **The upgrade page reads deeper** (`_JOB_READ_PAGE`, 600 cards) when the job has a
  read, so the gate and blend reach past the 150 most-played matches.

Measured on the 25 precons (eighth pass, `docs/plans/precon-audit/job_reads.py`):

| job | fit on main-job cards: CV Spearman | production read over every card it scores: Spearman / guide adds, median percentile (read vs play-rate) | use |
|---|---|---|---|
| protection | 0.56 | 0.56 / 0.92 vs 0.97 | gate |
| board wipe | 0.50 | 0.49 / 0.79 vs 0.92 | gate + blend |
| removal | 0.40 | 0.16 / 0.49 vs 0.94 | gate |
| card draw | 0.33 | 0.33 / 0.76 vs 0.85 | gate + blend |
| ramp | 0.28 | 0.27 / 0.69 vs 0.89 | gate |

No read beats play-rate on its own; the gate and the blend are where each earns
its place (the top-of-list counts above).

**Alternatives rejected.** The read alone as the order: Sheltered by Ghosts became the
removal add in seven precons — the single top-scored card is where a read's errors
concentrate (the blend still lets Spiteful Banditry and Pyrohemia through as wipe
adds). The read deciding "better than the cut": it put Flawless Maneuver and
Deflecting Swat ahead of Swiftfoot Boots, which reads right, but the measured cut
side doesn't support it yet. Fitting to "is a
staple" (rank inside the top 300 or 1000) instead of the log rank lowered the add-side
fit. Commander-specific EDHREC pages are out: Dan's call, and it would be popularity
by another name.

**Consequences.** Play-rate still shapes the result four ways: as the page order, as
"better than the cut", as half of the blend, and as the upgrade-slot cut threshold
(`classify.UPGRADE_RANK`). The reads so far change which cards may be an upgrade
more than which one is chosen; a read takes over a decision only when it measures
as well as play-rate on it.
Each read's misreads are listed in its module docstring and the backlog. The next
lever is deck context: Skullclamp's draw depends on the deck's X/1 creatures and token
makers, and it is still the card-draw add in eleven precons.
