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

**The ship bar from here on** (replaces the ±1-2 add gates): page-level
recall@30 rises on the 25 and does not fall on the held-out 20; plan-consistency
does not fall on either; the tune's guide-add count does not fall held-out;
guide cuts fall ≤2 on the 25 and ≤1 held-out; consensus adds do not fall. Read
fixes still ship on correctness with the deltas recorded.

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
