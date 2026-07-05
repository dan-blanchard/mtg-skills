# 36. Lane mirrors fold to Tier-1 structural reads

Date: 2026-07-04

Status: Accepted

Relates to: [0035](0035-lossless-phase-mirror-ir.md) (the phase-mirror substrate
+ concept overlay these lanes read — completes its crosswalk),
[0034](0034-matters-sweep-doer-payoff-wants-lane-naming.md) (role-aware
adjudication of moved signals), [0027](0027-card-ir-replaces-regex-detection.md)
(the regex→IR cutover this finishes *inside* the crosswalk).

## Context

After the Stage-4 default-ON flip (ADR-0035), the deck-forge signal crosswalk
dispatches IR-first, but a subset of its live lanes still run **regex over oracle
text** — a `clauses(oracle)` split plus `.search`/`.finditer`, imported from
`_signals_regex` / `_sweep_detectors`. These **lane mirrors** are Tier-0 reads:
blind to tree structure, carrying the card-level cross-clause false-positive class
that structural reads eliminate. They are transitional tech-debt, not a sanctioned
permanent path.

## Decision

Fold every lane mirror to a **Tier-1 structural read** — touching only typed
Concept-node fields (`subject`/`scope`/`zones`/`kind`), zero oracle text, zero
regex, at lane time. **Tier-1-only:** a lane never falls back to a node-`raw`
regex. Where phase's parse is lacking, we *supplement the parse* so the typed
field exists, then read it — the three routes being **direct** (tree already
carries it → rewrite the lane), **bucket-A** (phase parsed, projection dropped →
structural overlay arm, no oracle text), and **bucket-B** (genuine phase gap →
projection-time true-synthesis supplement arm that regexes text *once* and emits a
typed node, gap logged). Every mirror is folded this session, including niche and
brand-new-mechanic lanes; the only carve-out is a genuinely un-synthesizable
mechanic, which gets a logged phase gap and stays a mirror (expected empty).

A fold may **improve** signals, not merely reproduce them: movement is adjudicated
role-aware (ADR-0034) — tight per-card for budgets / cut_check / metrics /
bracket, lenient "not grossly broken" for ranking — never forced signal-neutral.

## Considered options

- **Tier-2 (node-scoped `node.raw` regex in the lane) as an accepted waypoint** —
  rejected. The plan has always been to supplement phase's parse where it is
  lacking; relocating the regex *into* the lane, even node-scoped, contradicts
  that and leaves a per-lane text dependency. (Also moot: per-node `raw` is
  populated on only ~15.5% of substrate nodes.)
- **Signal-neutral folds** (forbid any movement; split every correctness fix into
  its own commit) — rejected. The structural read is frequently more correct than
  the regex it replaces; forcing neutrality either strands those wins or
  multiplies commits. We allow improvements and adjudicate them instead.
- **Defer the bucket-B tail** (fold only direct + bucket-A now) — rejected.
  "Niche ≠ skip": every mirror gets its supplement arm this session.

## Consequences

- **flag-OFF stays byte-identical.** Overlay/supplement arms run on the tree and
  are consumed only under `crosswalk_enabled()`; the legacy `old_ir_for` path
  never reads the tree, so flipping the flag off reproduces legacy exactly.
- **bucket-B arms are shrinking bridges** (ADR-0035 convergence check): a
  projection-time regex today, retired when phase parses the clause upstream.
- **Execution is bucket-ordered** (direct → bucket-A → bucket-B → import cleanup),
  ~10–20-lane batches, gated per batch by the Stage-3b consumer-diff harness +
  substrate-purity + `exit_master` signal diff.
- **Done** = no crosswalk lane calls a text-regex mirror: the `_signals_regex` /
  `_sweep_detectors` text imports removed and `clauses(oracle)` / `get_oracle_text`
  gone from lane bodies, modulo logged-gap carve-outs.
