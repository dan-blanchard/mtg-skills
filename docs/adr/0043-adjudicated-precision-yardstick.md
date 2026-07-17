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
