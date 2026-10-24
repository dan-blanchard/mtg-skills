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
- **Three reads also order, blended with play-rate** (`JobRead.orders`: board
  wipes, card draw, protection). Each candidate's read percentile on the page plus its play-rate
  percentile decides (`swaps._blended_percentiles`). The tuner takes the top card,
  and at the top of the list the read alone found the guides' adds less often than
  play-rate did, for every job; the blend beat play-rate for wipes (11 vs 7 guide
  adds in the top thirty, n=19) and draw (11 vs 6 in the top ten), and trailed it
  for protection (top thirty 24 vs 29), removal and ramp. Removal and ramp gate
  only; protection orders by Dan's call — its picks (Flawless Maneuver, Deflecting
  Swat over Swiftfoot Boots) read right to a deck builder and the gap is small. These
  counts rank the whole color identity the read scores; the tuner ranks the job's
  match set in that identity.
- **The upgrade search reads the job's whole match set** (`_JOB_READ_PAGE`) when the
  job has a read, so the gate and blend reach past the most-played matches and the
  blend's percentiles don't move with a page's depth (a 600-card page until
  2026-10-23).

Measured on the 25 precons (eighth pass, `docs/plans/precon-audit/job_reads.py`):

| job | fit on main-job cards: CV Spearman | production read over every card it scores: Spearman / guide adds, median percentile (read vs play-rate) | use |
|---|---|---|---|
| protection | 0.56 | 0.56 / 0.92 vs 0.97 | gate + blend (Dan's call) |
| board wipe | 0.50 | 0.49 / 0.79 vs 0.92 | gate + blend |
| removal | 0.40 | 0.16 / 0.49 vs 0.94 | gate |
| card draw | 0.33 | 0.33 / 0.76 vs 0.85 | gate + blend |
| ramp | 0.28 | 0.27 / 0.69 vs 0.89 | gate |

The board-wipe row's production column was re-measured on 2026-10-23, after the read
took its sweeps from the lanes (one-sided and static shrinks counted, a graveyard
exile no longer read as a sweep): 803 cards, 0.49 / 0.79 vs 0.92, unchanged. Its fit
column is the original fit's. Every production row was re-measured again the same
day, after the reads moved onto the signal trees (the amendment below): unchanged at
two decimals; removal scores 6,595 cards (6,592 before) and 125 guide adds (124).

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
Each read's misreads are listed in its module docstring and the backlog.

**Amendment (2026-10-19): deck fit.** A read may carry a deck-context fit
(`JobRead.fit`): card draw's names the fuel an engine needs from the deck
(`card_draw.draw_fuel` — Skullclamp's X/1 creatures and token makers, Archmage
Emeritus's instants and sorceries) and scores the share of it the deck runs
(`deck_fit`, 0-1; one record per copy). The tuner passes the deck to the gate,
which rejects a card-draw add the deck fuels below half (`swaps._DECK_FIT_FLOOR` —
the middle of the gap between Abzan Armor's 0.39 and Quick Draw's 0.58, where every
guide that adds Skullclamp sits, not a tuned value), and to the blend, where the
fit lowers a score by the unfueled share of its size. The Spine fills ("card draw
short") read the gate too. A read of part of a job (removal, of interaction) gates
only a cut it reads as that part (`JobRead.whole_job`): an interaction fill may be
a counterspell. On the 25 precons Skullclamp went from the card-draw add in eleven
to seven, with no guide match lost (230 / 109 / 30).

**Amendment (2026-10-20): a hand-set feature.** A read may override a fitted
weight where play-rate scores a card for a reason the card itself contradicts,
by Dan's call and documented at the feature. The first: a permanent with
cumulative upkeep (CR 702.24a: its upkeep cost climbs every turn until it is
sacrificed) gets none of a lasting engine's credit in the card-draw read
(`card_draw._ends_itself`), only its draw rate. Mystic Remora read above Rhystic
Study; it now reads below Phyrexian Arena.

**Amendment (2026-10-23): signal trees and the whole match set.** The reads walk
the card's signal trees (`signal_trees_for`), the trees the lanes read, not the
corrected trees: the board-wipe read runs the lanes' own sweep walks, and a clause
the tree-synthesis stage adds (ADR-0047) now reaches the read as it reaches the
signal and the role. Over the commander-legal pool three cards change: the fights
synthesis adds make Tolsimir, Friend to Wolves, Prepare // Fight and Mythos of
Illuna removal. The synthesis unit is no ability of the card's (ramp's count of a
card's other abilities skips it), and a synthesized clause carries no kind or
trigger, so ramp reads its extra land at the conditional rate, the rate its
signal-key fallback gave, which the walk now replaces. The upgrade search reads the
job's whole match set (6,056 removal cards for a five-colour deck; the most-played
600 before). A blend percentile is now the share of cards strictly below, so tied
cards share one; before, a tie took the synergy ranking's order. Synergy is scored
only for the candidates a tie leaves level, so the deeper search costs about 2-3 s
on a five-colour tune. On the 25 precons: 417 swaps, 159 cuts and 39 adds matching
a guide (420 / 161 / 40). Fae Dominion takes Kindred Discovery, a guide add, over
Skullclamp, and the dearer draw add leaves Spellstutter Sprite, another, over
budget; Sultai Arisen's draw add becomes Vanquisher's Banner ($2.94, not Morbid
Opportunist's $0.22), and its last four upgrades, two of them guide cuts, no longer
fit its $132.

**Amendment (2026-10-24): where a read leads.** Dan's calls: try each read as the
order of its upgrades (the score first, play-rate breaking ties) and as "better than
the cut", allow a job upgrade one mana-value band more, and let theme fit break a near
tie between a staple and an on-theme card. Each was measured alone against the 25
precons at their own budgets, then the kept ones together; one ships only where the
guide-matching adds rise and the guide-matching cuts fall by two at most (baseline
407 swaps / 158 cuts / 39 adds, after the read fixes below; 417 / 162 / 39 before them):

| change, alone | swaps / cuts / adds | |
|---|---|---|
| the read orders the upgrades: wipes / draw / removal / ramp / protection | 412/159/40 · 422/164/43 · 413/163/35 · 397/161/35 · unchanged | rejected (see below) |
| "scores better than the cut" in play-rate's place: removal / ramp / draw / wipes / protection | 407/159/38 · 406/158/38 · 407/157/39 · 404/158/39 · 408/158/39 | rejected |
| a job upgrade one band higher / every upgrade | 417/161/43 · 414/161/41 | job upgrades |
| theme fit breaks a near tie: draw / ramp / removal / wipes / protection | 435/167/42 · 409/159/41 · 405/157/38 · 412/159/39 · unchanged | draw, ramp |
| the wipe read orders the wipe fill | 413/160/40 | kept |
| protection fills skip the avenue guard | 407/158/40 | kept |
| all kept | **434 / 168 / 50** | shipped |

- **The order stays as it was** for every job. The wipe read leading matched one
  more add alone but no wipe add (Final Showdown, Spiteful Banditry and Winds of
  Abandon over Blasphemous Act and Toxic Deluge: the read rates them highest), and
  with the kept changes it took the total from 50 to 47. Card draw's read leading
  matched more adds overall but fewer draw adds (River Kelpie and Ghostly Pilferer,
  its top engines, over Kindred Discovery and Deadly Dispute); with theme fit as well
  it matched 39.
- **"Better than the cut" stays play-rate's.** No read found more guide adds there.
- **A job upgrade may cost one band more** (`swaps.over_band`): Blame Game trades
  Winds of Rath (five mana) for Blasphemous Act. A theme upgrade keeps its band.
- **Theme fit breaks a near tie** for card draw and ramp (`JobRead.theme_ties`): in
  the upgrade's order, an off-theme card gives its place to the first later card that
  serves a viable avenue and scores within 0.1 of it on the read. Upgrades are still
  not held to theme fit. Garruk's Uprising is the draw add in 7 precons (10 before).
- **The wipe read orders the board-wipe fill** (`JobRead.fill_orders`), ahead of the
  mana-value band: Death Toll's fill is Find // Finality (read 0.28), not Wail of War
  (0.07).
- **A protection fill skips the ADR-0040 avenue guard** (`swaps._GUARD_EXEMPT_JOBS`):
  protection guards the deck's threats whatever avenue they serve. Animated Army's fill
  is Swiftfoot Boots again, not the $36 Sword of Feast and Famine.
- **Rejected: protection for every deck.** ADR-0024 asks for protection only in a combo
  or control deck or a voltron plan, which is why 18 guide protection adds had no
  search (the `protects-board` preset reads all 18). A target of 5 or 3 for every shape
  matched 38 and 39.

The read fixes in the same pass: removal reads an exile that lasts until the card
leaves as weaker when the card leaves by itself (an Aura, CR 704.5m; a card that
sacrifices itself, Static Prison) — hand-set weights −0.3 and −0.5; a free alternative
cost phase carries in `casting_options` costs nothing (Deadly Rollick, Snuff Out —
phase parses both; the crosswalk never read them); and the `removal` preset takes only
the debuffs that lower toughness (`lanes.toughness_debuff`), so Animate Dead's −1/−0
and Jace, Architect of Thought's are no interaction. Alone they cost Planeswalker Party
four guide cuts: Jace no longer counts as interaction, so its dead-weight fills could
take Elspeth, Storm Slayer, which spent the budget its upgrades had used.
