# The tuner plan (2026-10-30): measure first, then read the commander

Decided with Dan on 2026-10-30 (grilling), from the findings in
`tuner-holistic-review-2026-10-30.md`. Supersedes the completed 2026-10-29 adds
plan. Supporting data: `~/mtg/tuner-work/w40/` (guide quality, frameworks, the
miss taxonomy, the held-out candidates).

## Progress

- 2026-10-30: Phase A shipped (464d93e8, ADR-0061) and baselined (A1: the 25
  732 / 335 / 121, held-out 20 571 / 253 / 80). Phase B shipped the same day:
  need pages reached by routing a need-supplying cut (not by sharing the theme
  adds — measured and rejected, 3 and 1 shared adds) and the specificity-first
  primary with a builders floor (the held-lane share waiver measured and
  rejected). Phase B baseline: the 25 735 / 337 / 122, held-out 577 / 253 / 97;
  page recall@30 159 and 161; plan-consistent 288 and 174. Details in the audit
  report's "Phase B" section and ADR-0061's amendment.
- 2026-10-30, Phase C: item 9 (a lane cut's add from its own lane) is covered by
  Phase B's need routing (a cut that supplies a need is upgraded off that
  need's page); item 10 (incidental jobs) was tried as "route a need-supplying
  job cut to its need page" and rejected (held-out 17 swaps, 4 cuts and 3 adds
  lost), then as specified — a job carried only by a non-self-ETB trigger is a
  rider — and rejected too (held-out adds −1, page recall −3, consensus −1;
  Rhystic Study reads as incidental): open for a read that tells a payoff rider
  from an engine;
  item 11 (land swaps) is built (`_tuner/mana_base.py`, `--land-swaps`) and
  ships opt-in: measured on the recipe it costs the plan's issues their swaps
  (the 25 lose 7 guide adds and 4 consensus adds; the held-out 20 hold their
  adds, lose 4 consensus adds) for 3 of 73 and 3 of 58 guide land rows. Details
  in the audit report's "Phase C" section.
- 2026-10-30, Phase D: both levers measured and rejected — the marquee allowance
  (flat: the even share wasn't what kept the guides' marquee cards out) and the
  removal-MV upgrade slots (two guide cuts for one add on the 25, a consensus add
  lost). PLAN COMPLETE. Final baseline = Phase B's: the 25 735 / 337 / 122,
  held-out 20 577 / 253 / 97 (from 732 / 335 / 121 and 571 / 253 / 80). The
  audit report's "Phase D" section records the runs.
- 2026-10-30, the next round: E1 (need-fitting near ties on every job page)
  rejected (exact adds −3 / −3 for plan-consistency +43 / +33); E2 — the near
  tie narrowed to a card that supplies a commander need AND serves a main lane —
  shipped under the revised bar: held-out 97 → 101 guide adds, the 25 flat.
  Baseline: the 25 735 / 337 / 122, held-out 575 / 253 / 101. The taxonomy's
  lane fixes (aura_matters, typed enters payoffs, Clue engines as draw,
  Dispatch) merged with two tuner fixes they exposed (a lane's specificity is
  its broadest held ident; umbrella keys never test a need): the 25
  734 / 339 / 120, held-out 581 / 255 / 100. The bundle of every rejected lever
  (F1 / F2) was measured at Dan's request: they don't compound on the guide
  yardsticks (plan-consistency +34 / +37, exact adds −1 / −3, job-equivalents
  −14); the gate's exact-name anchor, not interaction effects, is the question.
- 2026-10-30, evening: the plan-primary gate (below) decided with Dan. A read fix
  found on the way (the token-consumers need took one token kind by hash order;
  now every kind, idents read sorted): held-out unchanged, the 25 118 adds
  (L3). E1 shipped in place of E2 against L3: held-out plan 180 → 198, adds
  100 → 99, job-equivalents −2, cuts +1 — passes. **Baseline (E1c): the 25
  739 / 342 / 117 (plan 306), held-out 20 581 / 256 / 99 (plan 198).**
- 2026-10-30, late: the need read deepened (R1, on correctness): mana-value
  bounds (Zhulodok, Rootha, Bello), spells-per-turn conditions and "activate
  only if" restrictions (Stella Lee, Bumbleflower), opponents drawing
  (Bumbleflower). Held-out adds 99 → 100, cuts 0; the plan line re-based
  198 → 225. **Baseline (R1): the 25 739 / 342 / 116 (plan 315), held-out 20
  581 / 256 / 100 (plan 225).**
- 2026-10-31: two more read fixes (R2, on correctness): a `tokens_matter`
  payoff asks for token makers (Hazel, Zurgo); a self-scoped life loss is no
  resource (Hazel's payment, Tegwyll's drawback). Held-out unchanged; the 25
  736 / 340 / 118 (plan 318). Disa's graveyard trigger is a phase parse gap
  (backlog).
- 2026-10-31: the deck-aware incidental-job read (C11: a trigger-rider job on
  a card serving a main lane is no job) measured against R1 — held-out plan
  +9, adds +2, cuts +1, job-equivalents −1 — one short of the +10 bar; not
  shipped at first. Re-measured on R2: identical held-out numbers, still +9;
  Dan passed it (every floor line rising). **Baseline (C11): the 25
  732 / 338 / 118 (plan 327), held-out 20 582 / 257 / 102 (plan 234).** The
  plan's work is complete; what remains is in the backlog.
- 2026-10-31, after the plan (grilled): recursion and tutor template rows with
  job reads (ADR-0062). The two reads shipped (two agents; recursion CV 0.36,
  tutors 0.52; both gate, neither orders). The rows failed the gate every way
  they were cut (held-out plan −31 as designed; the tutor row alone −9 with
  eleven guide cuts lost; recursion alone flat) and are held as
  `w41/rows-T1.patch`; the baseline stays C11. Next idea: plan-conditional
  rows (backlog).
- 2026-10-31, after the plan (grilled): reads first, play-rate last. Theme
  pages (S1: need, lanes, synergy, then play-rate; S2: synergy with a need
  bonus) — held-out plan +70 / +43 but guide adds −17 / −16: on-plan but
  obscure picks over the guides' fit-plus-quality staples. Job pages (J1: each
  read's score first) — held-out plan −34, adds −16. All held back
  (`w41/theme-order-S2.patch`, `w41/job-order-J1.patch`); the baseline stays
  C11. Finding: play-rate carries quality the theme pages have no read for;
  the way to Dan's stance is a theme-card quality read, not a reorder.
- 2026-10-31, next steps (grilled): the theme-card quality read is the next
  stretch (three per-type reads fitted on guide pairs from the design 25's S1
  theme pages, `docs/plans/precon-audit/theme_pairs.py`; a read ships when its
  leave-one-deck-out pair accuracy beats play-rate's; then the reorders V1 /
  V2 and the job blend, each gated alone; ADR-0063 at read-ship time). First
  the Disa workaround, which turned up a crosswalk read bug: a graveyard
  arrival with no origin ("from anywhere": Gitrog, Titania, Sefris, Yuma; 49
  cards) read as a death. Fixed on correctness (ADR-0061, fourth amendment)
  with Disa's `Unknown`-mode trigger rewritten by `misparsed_shapes`; the fill
  need is mill and discard, never the umbrella key. **Baseline re-based as
  C12** (`w41/sb-*-C12b.json`): the 25 732 / 338 / 118 (plan 335; Graveyard
  Overdrive 0 → 7), held-out 582 / 257 / 101 (plan 234; adds −1, the floor
  holds). Tutor weights confirmed; plan-conditional rows parked.
- 2026-10-31, the quality reads (ADR-0063): three per-type reads built by two
  Opus agents on the guides' pairs (creature 0.66 vs play-rate 0.58, noncreature
  permanent 0.72 vs 0.65, spell 0.73 vs 0.72, leave-one-deck-out pair accuracy)
  and shipped; the agents found the pairs teach what the S1 order overrates, not
  strength. Measured alone against C12: theme orders V1 / V2 held-out plan
  +63 / +66 but guide adds −22 / −20 — held back (patches in w41/); quality as
  a third term in the job pages' blend (J2) held-out plan +19, adds −2, cuts −1
  — **shipped; baseline J2** (`w41/sb-*-J2.json`). The theme order stays
  play-rate first; Dan's stance there waits on a strength read whose pairs the
  tuner's order didn't choose.
- 2026-10-31, evening (Dan: keep iterating alone until real improvements): a
  reach profile of the held-out misses, with `misses.py` recording every page
  hit (and, under `PRECON_DEEP_PAGES=1`, each theme page's whole match set):
  the largest bucket is 152 theme guide adds no theme page holds — 100 the
  serve never admits, 52 cut off by the 150-card page. Of the 100: Zimone's
  counter payoffs (15), Ahoy Mateys' theft cards (15), tutors (~10), trigger
  copiers and clones (~8). Read fix N1 (on correctness): a commander whose text
  counts the counters on itself (Zimone's `CountersOn` scoped to the source) and
  grows only itself opens a "counters on the commander" need (proliferate,
  doublers, counter movers, counter payoffs); the self-grow skip no longer
  applies to a commander that also grows others (Captain America, Team Leader
  keeps "plus one consumers"). Held-out adds +3, plan +8 (Quandrix: Branching
  Evolution, Evolution Sage, The Earth Crystal), the 25 unchanged — **baseline
  N1** (`w41/sb-*-N1.json`). The audit script's page kinds were also fixed (a
  ramp or interaction page read "other"), so page recall rose on paper only.
- 2026-10-31, night, three read fixes off the job-page profile (N3, on
  correctness): a library search before a "put that card on top" is card
  selection, not a tuck (Insatiable Avarice read as removal); the quality reads
  cost an X spell its X (`X_ASSUMED` 3 — Martial Coup read as two mana); the
  interaction read sees counterspells (`removal._counter_answers`), so one can
  replace a removal cut. The 25 adds +2, cuts +1; held-out adds −2, cuts −2,
  job-equivalents +9 (the counterspells themselves, Fierce Guardianship being
  outside most budgets), plan +1 — **baseline N3** (`w41/sb-*-N3.json`).

## Target

Every tune aims at **bracket 3 or higher**; nobody tunes a bracket-2 deck. The
audit recipe runs with `target_bracket=3` (the existing gate in
`_tuner/bracket.py`: at most 3 Game Changers, no mass land denial, no cheap
two-card infinite combos). The guides' Game Changer adds (59 across 26 guides)
count as hits, and the plan-consistency metric treats a GC add like any other.

## Phase A — measurement before any policy change

1. **The commander-need predicate.** A pure, tested function in `_analysis`:
   `commander_need(commander records) → predicate(card record)`, read off the
   commander's concept trees:
   - **events** it triggers on (`S_triggers.mode`: Surveil, Attacks, an
     enchantment entering, a token leaving) → does the card make that event;
   - **conditions** it reads (`condition=QuantityComparison(...)` over
     `DistinctCardTypes`, power, toughness, counters, zone counts) → does the
     card raise that quantity (adds a card type to the graveyard under Winter;
     toughness > power under Felothar);
   - **resources** it produces (tokens of a kind, energy, counters, Treasure)
     → does the card consume them (the token-doubler lever, generalised).
   Partner / background commanders contribute the union of their needs; a
   transform commander is read across all faces. It is built as the **metric
   first** (step 2) and reused as the reach pages in Phase B; it is the only
   fit test — never a loose "shares an ident with the commander" reorder,
   which the audit rejected (orders A/B, 3b, (s)).
2. **Plan-consistency metric.** Per deck: the share of a tune's adds satisfying
   any of the commander's needs; the guides' own share reported beside it as
   the ceiling (the review measured 44-83% for guides vs 0-10% for the tuner
   on Death Toll / Revenant Recon / Silverquill).
3. **Page-level recall@k.** Per deck and per kind (theme, each template job):
   where each guide add sits on the page the tuner would ask for it (or "no
   page"), reported as recall@10 / @30. Independent of cuts, budget and the
   swap cascade; seconds per deck after one tune.
4. **Scoreboard rescoring** (`precon-audit/scoreboard.py`):
   - consensus adds (2+ guides) become a gated number;
   - generic guide rows score **job-equivalently** on a separate line, using
     the near-miss "job" pairing already there (same `upgrade_job`, same
     subtype: removal mode and reach, ramp kind, draw kind, wipe shape,
     protection cover) — exact matches stay the headline;
   - a **mana-base line**: a guide land row scores on the same land or an
     untapped land producing the same colour pair / a utility land of the
     same function; lands reach the gates only through this line;
   - GC rows stay in recall; no per-source down-weighting.
5. **Ten more held-out precons** (never used to design a rule; the 25 stay the
   only design set): Temur Roar (TDC), Counter Intelligence (EOC), Ahoy Mateys
   (LCC), Quandrix Unlimited (SOC), Dance of the Elements (ECC), Jeskai Striker
   (TDC), Eternal Might (DRC), Deadly Disguise (MKC), Most Wanted (OTC), Blight
   Curse (ECC). Guide summaries by a Sonnet agent with the existing method
   (2-3 guides each, Card Kingdom / EDHREC first). Candidates and URLs:
   `~/mtg/tuner-work/w40/heldout-candidates.md`.
6. **Four parse fixes as their own correctness commit**, each with a retirement
   canary: Solar Blaze in `field_corrections` ("each creature deals damage to
   itself" read as untargeted damage — the one general shape), Sower of
   Discord as a bridge-ledger row, Serra Paragon in `recovery`, Helm of
   Obedience in `dropped_clauses`.

**The ship bar, as first set** (replaced the ±1-2 add gates): page-level
recall@30 rises on the 25 and does not fall on the held-out 20 — for a REACH
change (a new or deeper page; a ranking or cut-side rule moves no page and is
judged on the rest); plan-consistency does not fall on either; the tune's
guide-add count does not fall held-out; guide cuts fall ≤2 on the 25 and ≤1
held-out; consensus adds fall by at most 2 on the 25 and 1 held-out (revised
2026-10-30: a −1 of 137 is the swap cascade's own noise). Read fixes still ship
on correctness with the deltas recorded.

**The ship bar from 2026-10-30 (evening; the plan-primary gate).** Decided with
Dan after the bundle runs (F1 / F2) showed plan-consistency and exact-name
matching pulling in different directions: every rejected lever moved the tune's
adds onto the commander's plan by tens and off the guides' exact names by a few,
and the exact-name anchor, not interaction effects, was throwing them away.

- **Primary: plan-consistency.** A tune-policy change ships when the held-out
  20's plan-consistent adds (the scoreboard's PLAN line: adds supplying a
  SPECIFIC commander need, at most 10% of the pool, umbrella keys out) rise by
  **10 or more** (of ~580).
- **Floor: the guides.** Held-out guide adds + job-equivalent adds fall by at
  most **5 together**; held-out guide cuts by at most **1**.
- **Reported, not gated:** consensus adds, page recall, and every number on the
  25 (the design set; the held-out 20 is the only gating set).
- **Reads vs policy.** A change to the need read itself (a new kind of need, a
  guard) ships on correctness — each new need checked against the commander's
  text with rules-lawyer, the floor still holding — and re-bases the PLAN line.
  A read change and a policy change are never measured in one run.
- **Guardrail.** The PLAN line reports the credit by need (the needs crediting
  the most of the tune's adds); no per-need cap unless a run shows one need
  swallowing a deck's adds.

Re-verdicts under it: E1 (the wide need near tie on the job pages; held-out
plan +33, adds −3, job-equivalents −1) ships in place of E2 after one confirming
run against L2. The incidental-job read (C10: job-equivalents −12), the marquee
(D1: plan +3), the removal-MV slots (D2: plan +4) and default-on land swaps
(plan −3 / −5) stay rejected.

## Phase B — reach

7. **Need pages.** Each commander need is a main-tier avenue sharing the theme
   adds by depth beside the umbrella main (`Sourcing.theme_avenues`); depth is
   the deck's current count of cards satisfying the need, so a thin need asks
   early. Inside a page the order stays play-rate then price, with the even
   share and near tie as today (the predicate is the read).
8. **Specificity-first primary.** In `metrics.focus` the commander's primary
   lane is its rarest held ident (pool base rate from the signals index) whose
   avenue is at least emerging-deep with two or more carers; below that, the
   next rarest. The umbrella lane stays a second main so its page is still
   asked. Acceptance: the review's §5 table flips Silverquill to Auras/Goad,
   Revenant Recon to surveil, Mardu Surge to Warrior tokens, Grand Larceny to
   theft, and the five graveyard decks to their specific mechanic.

## Phase C — slots and lands

9. **A lane cut gets a lane add.** A `lane_upgrade` slot's replacement comes
   from the need page or lane the cut card itself satisfies (a weak Aura → a
   better Aura), then the main.
10. **Incidental jobs.** `upgrade_job` returns no job for a permanent whose job
    unit is incidental (the job read scores it low and the card's main unit is
    a body or a plan trigger), so the slot goes to the theme / need pages.
    Measured with the page metric before shipping.
11. **Land swaps in the tune** — a `mana_base` issue ranked **first** in the
    issue order (fixing the mana is usually the biggest buff), built here:
    - cuts: lands that enter tapped unconditionally and only make mana (read
      off the land's trees, not a name list — Guildgates, tapped duals,
      Thriving lands, bounce lands), then basics beyond `mana_audit`'s colour
      demand; never a land the need predicate or a main lane counts (Deserts
      under Yuma), a land that fixes a colour the deck would otherwise lack,
      or any land at the band floor;
    - adds: untapped on-colour duals and on-plan utility lands at the same
      land count, ranked by colour coverage (two needed colours over one),
      then play-rate, then price; priced from the same purse and counted
      against max-swaps;
    - purse: at most 25% of the budget in total and twice the even share per
      land (budget / 30 × 2), so pain / check / Pathway / bond / slow lands
      qualify and shocks, fetches and true duals only on a large budget;
    - deck-forge's `balance_lands` (basic-count rebalance) stays as is.

## Phase D — budget and thresholds

12. **One marquee slot:** up to ~40% of the budget for the single best
    need-fitting add; the rest even as today. Built once the page metric shows
    ranking, not reach, is the remaining blocker for job adds.
13. **Removal MV thresholds** as a removal job-read feature: single-target
    removal at MV ≥ 5 is a cut, MV ≥ 4 an upgrade target for an instant at
    1-3. The framework rules the need read gives for free (redundancy of the
    commander's key effect; the on-plan version of a role beats the generic
    one) need no separate work.

## Deferred to a later plan

Graveyard-hate / recursion / tutor template rows; multiplayer scaling of
one-shot effects; ramp MV ≤ commander MV − 2; the off-plan MV ≥ 6 cut; per-source
guide down-weighting; alternate-commander plans.

## Pace and hygiene

At most two agents at a time (Opus for design, Sonnet for guide summaries and
other mechanical stages); misses runs serial under the flock; durable files in
`~/mtg/tuner-work/`; every rules or card-behaviour claim through
`rules-lawyer`'s CLIs; `/simplify` and `/code-review` before each commit; every
policy change measured on the Phase A bar with both deltas recorded.
