# Rate and Pair reads enter the deterministic ranking (per-card cost-effectiveness + scored two-card interactions)

The 20-commander EDHREC discovery study (2026-07-16, fixed harness) put the
deterministic ranker's whole-pool recall of crowd targets at ~6%/~10% (@100/@250)
after the stacking-decay/breadth fix and the seven adjudicated extraction lanes —
while an agent baseline using only mechanical reasoning recovered 53%. Two verified
structural ceilings explain most of the gap. (1) At equal synergy the ranker cannot
tell a well-costed effect from an overpriced one: junk text walls (Fires of Mount
Doom) and staples (Siege-Gang Lieutenant) differ mostly in what the mana buys.
(2) Per-lane additive scoring cannot price multiplicative interactions: after the
mana_amplifier serve fix, Mana Reflection *correctly serves* Zaxara's X-spells lane
and still ranks ~13,600 of 17,375 — one lane of credit — when the crowd plays it
precisely because amplifier × X-commander multiplies. deck-forge's glossary
previously recorded "no card-quality model and won't fake one" on its Efficiency
(curve) panel; ADR-0040 already breached that line deliberately with the curated
ability-quality table for Granters.

**Decision.** Two new deterministic reads, designed and confirmed in a grilled
session (2026-07-16), both crowd-independent by construction (no playrate, no
EDHREC — ADR-0009's actual line):

1. **Rate** — a per-card cost-effectiveness percentile: effect-per-mana within the
   card's peer group (the signal lane its highest-weight cluster serves, over the
   whole pool; spine-role fallback; neutral 0.5 when unmeasurable — Rate never
   punishes what it can't measure). Effect measured by structural formulas where
   the IR gives clean numbers, extended by the ADR-0040 curated table where it
   doesn't. It enters the sort as a **multiplier** — `synergy_score × (0.5 +
   rate)` — so an off-plan card can never leapfrog on Rate alone, and it becomes
   the internal ordering of the always-on Staples avenue (generic goodstuff stays
   findable *because it is good*, deterministically). Add-side only in v1: cut
   selection keeps today's readouts (no cut-quality measurement harness exists).
   The Efficiency gloss's "no card-quality model" line is superseded; the term
   "Efficiency" stays with the curve panel (CONTEXT.md defines both).

2. **Pair reads** — a central curated ledger (`pair_reads.py`, the bridge-ledger
   discipline: pins, hygiene test, CR-grounded rationale per row) of candidate
   ident-pattern × deck-anchor interactions. Two anchor kinds from v1: a
   **commander-anchor** (fires on the commander's own idents — the commander is
   reliably in play, so the interaction reliably assembles) and a
   **density-anchor** (≥N deck cards emitting an ident). Matched rows carry flat
   payoff-scale weights (3.0–4.5), **sum without decay** (curation bounds
   stacking, unlike open-ended clusters), land in a separate additive
   `pair_score` readout — never injected into the synergy clusters (no coupling
   with prominence/decay/gate machinery) and never Rate-multiplied (the row
   already priced the interaction). Final sort: `-(synergy_score × (0.5 + rate) +
   pair_score)`.

Acceptance bar (both features): study recall@100 ≥ 10%, recall@250 ≥ 15%, median
target rank < 2500, plus named TDD pins — Empty the Warrens > Fires of Mount Doom
under Krenko signals (needs Rate), Mana Reflection in Zaxara's top 250 (needs the
amplifier pair row) — with every existing ranking invariant green. Rate lands and
is measured alone before Pair reads stack on top.

**Alternatives rejected.** Additive Rate term (any λ lets zero-synergy staples
flood the top-N — the box-ticker disease the cluster model exists to kill);
tiebreak-only Rate (no recall impact — the junk-vs-staple inversions are not
ties); lane × MV-band peer groups (thins small lanes into noisy percentiles and
re-does the curve panel's job); `pairs_with` declarations scattered on specs (an
ident-pattern × ident-pattern table doesn't fit (key,scope)-keyed specs, and
bidirectional rows would be ambiguous); auto-deriving pairs from serve-ident
overlaps (no weights, no rationale, uncontrolled blast radius); synthetic
role="pair" clusters inside synergy (couples pairs to the decay/gate machinery
the verified review just showed is easy to get wrong).

**Consequences.** The sort key changes twice (multiplier, then pair term) — each
lands behind its measured gate. A Rate sidecar (percentiles are whole-pool facts)
follows the signals-index content-hash discipline, and the discovery-cache
serve-fingerprint (verified-review F8) picks up both features' definition changes.
The ident-serve structural-bucket undercount (structurally-proven serves ranking
at 0.5) is deliberately left to Pair reads rather than patched into clause
attribution — the pair row is where that value actually lives. Formula-resistant
lanes inherit curated-table maintenance; the table stays small and adjudicated,
never crowd-derived.

**Measured outcome (v1, 2026-07-16).** Both mechanisms landed TDD-complete with
the named pins validated at the mechanism level: Empty the Warrens > Fires of
Mount Doom under Krenko holds with Rate + the subject-matched tribal-fodder
pair row (neither alone suffices — the bounded multiplier cannot close a 2.5x
synergy gap, refining the bar's original attribution), and Mana Reflection
under Zaxara moved 13,605 → 389 of 17,375 on the amplifier row (a 35x jump,
short of the stated top-250 pin). The four-way aggregate eval (one pool pass,
offline re-sorts) read: baseline 6.4%/9.5% (r@100/r@250), +Rate 5.7%/8.9%,
+Pairs 6.0%/10.4%, +both 5.6%/10.0% — Rate's v1 formula classes (tokens /
damage / draw, trigger-origin effects already excluded after a first cut
under-rated every triggered engine at 4.3% r@100) carry no crowd-predictive
signal at aggregate, in ANY variant tried (multiplier, pure-lift). Per the
bar's own measure-C-alone discipline: Rate ships as readout + plumbing with
the production default NEUTRAL (no index built by deck-rank; opt-in via
`rank_candidates(rate_index=...)`) pending a formula v2; Pair reads ship
default-on (+0.9pt r@250 from six rows — ledger growth toward the designed
20-40 rows is the identified lever, each row needing its own adjudication).
The 10%/15% aggregate bar is NOT met; accepting, iterating the ledger, or
revisiting Rate's formulas is the recorded open decision.

## Measured outcome addendum II: Rate v2 (2026-07-24)

Rate v2 was designed under ADR-0043's amended protocol (design note,
six adversarial review cycles, Dan-approved revision 2.6 — archived in
the session's durable store), implemented in two slices, measured, and
TERMINATED by its own program rule (two consecutive slice REJECTs):

* **S1 (same-row slot permutation)** — implemented with the
  anti-chaining parallel-pass construction, default-off
  (`row_class_permutation`). Measured: ledger ordering score 0.464 ->
  0.464 (+0.000 vs a +0.010 gate; ownership fragmentation cut reach
  53 -> 31 pairs and the rider/cmc keys proved uncorrelated with
  adjudicated quality in the classes where mis-ordering lives). REJECT.
* **S2 (limiter discounts)** — implemented on the ident->ability
  provenance seam, default-off (`pair_score(discount_fn=None)`).
  Measured: held-out ordering score 0.433 -> 0.380 (a DECLINE; 858
  cards discounted — the {T}-cost and cost-vs-yield reads generalized
  three adjudicated kill anecdotes onto whole classes the panels
  adjudicate as good). REJECT.

Both mechanisms remain in the tree, tested and inert, as the measured
record. The program's lasting yield is real and shipped: the falsified
v1 multiplier is STRUCTURALLY DISARMED (rate is a readout; CI asserts
sort invariance to any rate_index), the ranking sort is TOTAL (name
final key — stable-sort input-order leakage closed), the
ident->ability provenance seam exists for any future consumer, and the
ledger ordering instrument (docs/adr/assets/0043-instrument/, 380
frozen verdicts) turned "within-class ordering" from unfalsifiable
into a number. The within-class ordering headroom (0.464) remains
unclaimed — any future attempt starts from a better instrument and a
worked falsification record.
