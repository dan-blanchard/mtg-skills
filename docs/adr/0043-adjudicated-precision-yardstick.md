# Adjudicated precision replaces crowd recall as the discovery yardstick

ADR-0042's acceptance bar graded the deliberately crowd-independent ranker
(ADR-0009) on recall of EDHREC crowd picks, with thresholds (10%/15%) invented
before any measurement existed. The 2026-07-16 four-way eval showed why that
regime fails: it punishes discover-before-popular (11/75 of the ranker's
"misses" had previously been adjudicated genuine hidden gems), it graded Rate
v1 on crowd mimicry, and its absolute thresholds had no derivation. Meanwhile
the project already owns the honest unit: the never-dismiss-without-a-hook law,
which is checkable per pick.

**Decision** (grilled session, 2026-07-17). The primary discovery metric is
**Adjudicated precision@20**: for each commander on a fixed 10-commander panel
(spanning tokens / aristocrats / spellslinger / tribal / X-spells / enchantress
/ artifacts / reanimator / attack triggers / wheels), every top-20 out-of-deck
pick gets a written **Hook** — the candidate's machine-readable evidence (its
idents, matched Pair read, or cluster readout) plus the deck-context reason —
and three independent refuters attack it (cheap-tier per the model-tiering
rule; session-model tiebreak on degenerate splits). Precision = the share of
picks whose Hooks survive the majority. Popularity arguments are banned on
BOTH sides — the judges inherit ADR-0009. The user spot-audits ~10% of
survivals and kills on the first run to calibrate refuter strictness.

The bar is a **ratchet, never an invented absolute**: measure today's baseline
first; each subsequent iteration must beat the previous precision@20 and hold
the (demoted, free) EDHREC-recall drift indicator within noise. The iteration
— not the row — is the measured unit for pair-ledger growth (~10 mined rows
per iteration, sourced from both failure surfaces: clustered study misses and
refuted hooks; a failing iteration is bisected, never shipped). Rate v2 is
gated on a pairs plateau AND a written design note that solves v1's two
falsifiers (per-event cost basis for triggered engines; the measured-median
asymmetry that sank below-median measured cards under unmeasured neutrals);
curated ability-quality entries may land earlier for individually-adjudicated
offenders.

**Alternatives rejected.** Playtest win-rate deltas as primary (automated and
crowd-free, but 10-card deltas drown in simulator noise and grade the
simulator's meta); keeping recall with re-derived thresholds (permanently
grades crowd-independence on crowd mimicry); single-verifier adjudication (a
third the cost, but single-judge drift is how plausible-but-wrong hooks
survive — the review workflows use majority verification for the same reason);
mandatory CR citations on every Hook (most genuine synergy hooks are strategic,
not rules-boundary claims — CR grounding stays mandatory where a rules boundary
is actually claimed).

**Consequences.** CONTEXT.md gains **Hook** and **Adjudicated precision**.
ADR-0042's 10%/15% bar is superseded; its named pins (Empty the Warrens >
Fires of Mount Doom; Mana Reflection top-250 movement) remain as CI mechanism
tests, not gates. The precision panel's refuted hooks become a standing data
source for ledger mining and, later, for what Rate v2 must actually catch.
Measurement cost is priced by the panel: ~200 adjudications per run, batched
per commander (one hook-writer + three refuters each) to stay within sane
agent budgets.

## Amendment: paired-delta acceptance + verdict ledger (2026-07-18)

The first full measurement cycle exposed a sensitivity flaw in the original
acceptance rule (panel-mean must beat the bar): between any two configs,
55-70% of picks are SHARED, yet every run re-rolled their hooks and verdicts.
Measured noise — 22-27% of picks decided by one swing refuter vote; a
re-adjudicated UNCHANGED Zaxara panel swung -0.15 on four
fabricated-evidence hook kills; Sythis swung +/-0.10 with zero pick changes
— puts run-to-run sigma on the panel mean (~0.015-0.025) at or above the
deltas being adjudicated (0.010-0.015). The panel-mean ratchet was flipping
coins at the margin, and the drift indicator had no formal role at accept
time.

**Refined acceptance (decided with Dan, 2026-07-18):**

1. **Paired delta test.** An iteration is judged ONLY on its changed picks:
   survival(new picks) vs survival(displaced picks), as a paired binomial
   comparison. Accept when non-inferior (within 5 points) AND the crowd
   drift indicator (r@250) improves; reject on clear regression (worse by
   more than 5 points). Shared picks carry their verdicts and contribute no
   re-roll variance.
2. **Cumulative anti-leak floor.** Repeated non-inferior steps must not
   compound downward: the carried-verdict panel mean must stay within 0.02
   of the v2 baseline (0.940) across ALL accepted iterations, or the next
   iteration must first recover it.
3. **Verdict ledger, unanimous-only.** Verdicts cache per (commander, card)
   at protocol version v2 (grounded prompts: schema-required verbatim
   oracle_quote; rules-level claims need a cited rules-lookup rule number;
   DFC face-joined panel text). Unanimous verdicts (0 or 3 kills) freeze
   permanently; split verdicts (1-2 kills) re-adjudicate the next time the
   pick appears, then freeze at the majority of both runs. Only
   same-protocol numbers are ever compared — the v1-era 0.790 baseline is
   retired as a measurement artifact (blind DFC adjudications).

**Retroactive consequence.** Iteration-1 (8 mined rows +
scoped_subject_gate + the untap-scope/anthem-core lane fixes) is ACCEPTED
under the refined rule: new picks 92.3% vs displaced 93.7% (-1.4pt, within
the 5pt margin; binomial se ~3pt), drift r@250 10.4% -> 13.4%, carried mean
0.930 (0.010 of the 0.020 allowance consumed). Under the superseded
panel-mean rule it had failed 0.930 vs 0.940 — the rule choice was made
knowing it decided this verdict.
