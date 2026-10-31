# Recursion and tutor rows for the Commander template, each with a job read: the reads ship, the rows measured and held back

The 2026-10-30 review's framework survey (`docs/plans/tuner-holistic-review-2026-10-30.md`
§6: Command Zone, Burgess, Tomer, Card Kingdom, SCG and the rest) distilled a
rule the Commander template did not carry: every deck wants about two
recursion cards and one or two tutors for its plan's key piece. On the 25
design precons the upgrade guides add 63 recursion cards and 40 tutors; the
tune, with no row to fill and no page of its own for either, added 5 and 5 —
most of the guides' cards sat on a theme page, outranked. Graveyard hate, the
third rule in that line, has no lane that reads it yet and waits.

**Decision** (grilled with Dan, 2026-10-31). Two rows were designed for the
Commander template (`_analysis/budgets.py`, after board wipes): **Recursion**,
floor 2, and **Tutors**, floor 1 — the frameworks' generic counts, for every
Commander deck, flat across shapes until a shape override is measured on its
own — with a job read for each built first. The reads shipped on their own
measurement; the rows failed the tune's gate (the measurement, below) and are
held as a patch. What follows is the design as built and measured.

- **Floor-only rows.** A `BudgetRow` band may have an open ceiling (`max`
  `None`): the tune fills the row when short and never trims it — a reanimator
  deck runs eight recursion cards on purpose. `slot_budgets` reports `max` null,
  a deviation only below the floor and the floor as `target`; the CLI and the
  deck-forge Budgets panel print "2+"; the swap engine treats such a job as
  never full.
- **Recursion is every recursion kind.** The `recursion` preset is the union of
  creature recursion to the battlefield or hand (`creature_recursion`,
  `reanimator`), any-card graveyard-to-hand (the graveyard-return concept:
  Regrowth, Eternal Witness) and a card returning itself (`dies_recursion`,
  `self_recurring`: Kitchen Finks, Bloodghast, flashback) — Dan's call over the
  narrower creature-only reading. `roles.is_recursion` is the one answer; the
  row counts by it and `ROLE_SEARCH` sources by the same preset (ADR-0051).
- **Tutors are nonland tutors.** `roles.is_tutor` is the `tutors` preset (the
  `tutor` key: a library search for a card, CR 701.23a) less a card whose
  searches find only lands — its tutor idents name no subject but `Land`
  (Sylvan Scrying, Expedition Map, Bushwhack): a land search is the mana
  base's business, as a land fetched to the battlefield is the ramp lane's.
  Demonic Tutor, Worldly Tutor and a two-mode search that can also find a land
  count.
- **Roles, not predicates.** Both are template roles (`roles.role_of`), so a
  recursion or tutor card is never filler and the roles show wherever roles do
  (scorecard, slot-budgets, deck-forge, cut-check). In the upgrade order a
  multi-role card reads as a tutor or recursion before draw and ramp
  (`issues.UPGRADE_ROLE_ORDER`: board wipe, interaction, tutor, recursion,
  card draw, ramp), so a cut tutor is replaced by a tutor.
- **A job read for each row, built first** (ADR-0060's method: features off
  the trees, weights fitted by ridge regression against play-rate, kept where a
  feature reads the card correctly, measured against the guides with
  `precon-audit/job_reads.py`). Recursion scores destination (battlefield over
  hand), what returns (any card over a creature over a type over itself), how
  many, repeatability, speed and cost, with a deck fit on the deck's creatures
  and graveyard fillers; tutors score breadth of search, destination, count,
  repeatability, speed and cost, no deck fit. Each read gates its page's
  membership; it orders, blended with play-rate, only where the guides' adds
  sit at least as high by the blend as by play-rate. The reads ship on that
  measurement, the rows on the tune's gate.
- **Gate.** The rows, roles and upgrade order are tune policy, measured once on
  the recipe against the C11 baseline (`~/mtg/tuner-work/w41/sb-*-C11b.json`)
  under the plan-primary gate (ADR-0061's second amendment), the scoreboard
  noting which row's fills landed. If they fail, the reads stay and the rows
  revert to a saved patch with the numbers recorded; each row is then
  re-measured alone.

**Consequences.** A deck short of recursion or a tutor gets a Spine slot with
its own search, ranked by the row's read where the read earned it; a guide's
Reanimate or Demonic Tutor has a page to land on where it had only the theme
page. A graveyard plan's many recursion cards are left alone. The 60-card and
limited templates are untouched (ADR-0054: every family decision keys off its
own template). The measurement is recorded below and in the audit report.

**The reads, as built (2026-10-31, two agents, ADR-0060's method).**

*Recursion* (`job_quality/recursion.py`; n = 1,802 commander-legal cards the
read scores): cross-validated Spearman 0.36 against play-rate. Weights kept, in
log10 play-rate: to the battlefield +0.19; cast or play from the graveyard
+0.23; top of library only −0.05; any or permanent card +0.09; only itself
−0.15; a capped mana value or power −0.10; mass +0.21; every player gets theirs
−0.13; repeats +0.10; activation mana −0.04 per mana; instant speed +0.03;
costs 2 or less +0.08; a discard cost −0.14; a spell with a land back face
+0.90. Dropped: a life cost and a sacrifice (the fit scored them as gains —
Reanimate's popularity), several targets, mana value, a body, flashback (about
0). The guides' 53 recursion adds sit at the 80th percentile by the read, 88th
by play-rate, 86th by the blend (top decile 30% / 47% / 45%), so the read
gates and does not order. Deck fit: a card returning only creature cards is
scaled by the deck's creature share (full at a third) and its graveyard
fillers (the last quarter); Reanimate runs 0.75–1.0 across the precons. The
read needed one shared walk the lanes lacked, `crosswalk.reads.
chosen_graveyard_recursion` (a return pointing back at a card an earlier
clause chose in the graveyard: Meren, Victimize, Daretti); it scores 90 cards
the lane keys miss and misses 20. Membership calls: shuffles into the library
and bottom-of-library puts are not recursion (Timetwister, Repopulate); a
spell's own flashback is not, a permanent cast from its graveyard is;
graveyard cast permissions count (Muldrotha, Lurrus, Crucible of Worlds).

*Tutors* (`job_quality/tutor.py`; n = 475): cross-validated Spearman 0.52.
Fitted weights: broad (any card or a card type) +0.40; cost −0.06 per mana;
cheap (2 or less) +0.07; instant speed +0.05; repeatable activation −0.10 per
mana; a creature body −0.07; an exile destination −0.30; a discard −0.10; a
land back face +0.44. Six features play-rate is silent or contrary on carry
hand-set weights under ADR-0060's 2026-10-20 amendment, each costing at most
0.01 of CV: any card over a type +0.1, battlefield or free cast +0.1, two or
more found +0.1, repeatable +0.1, a sacrifice −0.1, life paid or lost −0.05 —
set by the agreed design, confirmed by Dan as set (2026-10-31). The guides' 36 tutor adds sit
at the 76th percentile by the read, 84th by play-rate, 77th by the blend (top
ten 5 / 11 / 7): gates, does not order. A search to the graveyard counts
(Entomb, Buried Alive: the card goes where a reanimation deck uses it). The
read reuses the crosswalk's search walk (`self_searches`, now public, and
`search_count`).

What neither read can see is in the backlog's tuner entry (X tutors costed at
0, a Pact's upkeep, opponent-choice clauses, Cleansing Meditation's "return
all cards" parse, returns phase leaves unparsed).

**The rows' gate run (2026-10-31): the rows do not ship; the reads do.** Against
the C11 baseline (held-out 20: 582 / 257 / 102, plan 234; the 25: 732 / 338 /
118, plan 327), measured as agreed and then in parts:

| variant | held-out: swaps / cuts / adds | plan | the 25: swaps / cuts / adds | plan |
|---|---|---|---|---|
| T1: rows + roles + upgrade order (the design) | 559 / 247 / 87 (−23 / −10 / −15) | 203 (−31) | 720 / 338 / 105 (−12 / 0 / −13) | 298 (−29) |
| T4: rows + roles, old upgrade order | 557 / 246 / 97 (−25 / −11 / −5) | 221 (−13) | 718 / 338 / 112 | 317 (−10) |
| T5: predicate rows, no roles, old order | 557 / 246 / 97 (−25 / −11 / −5) | 221 (−13) | 716 / 337 / 113 | 318 (−9) |
| T3: the recursion row alone (predicate) | 580 / 254 / 100 (−2 / −3 / −2) | 232 (−2) | 732 / 339 / 118 (flat) | 324 (−3) |
| T2: the tutor row alone (predicate) | 558 / 246 / 100 (−24 / −11 / −2) | 225 (−9) | 716 / 336 / 113 | 320 (−7) |

What the attribution showed (`~/mtg/tuner-work/w41/sb-*-T*.json`, the swaps by
kind): in T1 the upgrade order did the most harm — 43 held-out adds were
"upgrade: recursion", a self-recurring plan card (Skeleton Crew, Jocasta,
Winter Soldier) cut and replaced off the recursion page (Reanimate, Sevinne's
Reclamation) instead of its plan's pages. With the order restored, the tutor
row's fills are the drag: 16 held-out fills (Pyre of Heroes, Diabolic Intent,
Wishclaw Talisman) with 2 guide hits, each taking a slot and a purse the plan's
issues then lack — a swap fewer per deck (−24), eleven guide cuts fewer. The
recursion row's fills are few (3 held-out, no guide hit) and roughly neutral.
The frameworks' generic floors are not what the guides do to a precon: the
guides' 40 tutor adds and 63 recursion adds are plan cards (a creature tutor in
a creature deck, Living Death under a reanimator), found on the plan's pages
when the plan reaches them, not as a template fill. The rows, roles, open
ceiling, upgrade order, preset and panel labels are kept as
`~/mtg/tuner-work/w41/rows-T1.patch`; the two reads are in the tree (gating no
page until a job names them — the deck-forge job pages can ask for them). The
sharper idea the measurement points at is a plan-conditional row (a tutor row
only when a main lane names a type a tutor can find; a recursion row only
under a graveyard plan), a separate decision.
