# 35. Lossless phase-mirror Card IR with a derived concept overlay

Date: 2026-06-29

Status: Accepted

Relates to: [0027](0027-card-ir-replaces-regex-detection.md) (the regex→IR
cutover — amends the *substrate*), [0032](0032-fully-parsed-ir-is-a-pull-based-measured-direction.md)
(pull-based fully-parsed direction — amends), [0028](0028-consume-phase-rs-not-fork.md)
(consume phase, contribute grammar upstream — references).

## Context

The Card IR (ADR-0027) is a **lossy** projection of phase-rs's parse:
`_card_ir/project.py` (~9,678 LOC) collapses phase's 682 emitted `Effect`
variants into ~80 closed categories and keeps selectively-chosen fields. Two
recurring failure classes result:

1. **bucket-A field-drop.** A field phase *did* parse is silently omitted by the
   projection. The committed `parse_metrics.json` counter `bucket_a_masking`
   reads 0 — but that counter measures regex-*masking* recoveries, a **different
   class** from a silent sub-field drop inside an already-categorized node. The
   real class is evidenced by the re-surfacing ledger in `card_ir.py` itself
   (`returns_to` v34, `recipient` v41, `mana_kind` v43, `duration` v44, `source`
   v48, `toughness` v74) — each a lane that went blind because a field phase
   carried was dropped, none of which moved the counter.
2. **silent version-bump drift.** The v0.8.0 episode: a phase bump restructured
   nodes, `project.py` silently stopped reading them → 8 regressions, 4 worktree
   recovery waves. `project.py` reads `node.get("type")` off raw dicts, so a
   renamed/relocated variant degrades to `None` rather than failing loudly.

ADR-0032 commits us to a *pull-based, measured* fully-parsed direction, names
bucket-A masking as first-class debt that "must become a native read," and names
two consumers that define "done": cheap derived synergy lanes, and a drift
detector. This ADR specifies the architecture that discharges the bucket-A debt
**by construction** and makes drift **loud** — without a big-bang rewrite, beneath
the frozen `Signal` contract. It was reached by a grilling session and validated
by an adversarial multi-agent stress-test (6 lenses, each concern independently
verified against the live code); the framing below is the post-verification one,
with four real corrections folded in.

## Decision

A three-layer model, a three-way-decomposed supplement, and a two-layer cache.

- **Layer 1 — substrate (lossless, strict).** A codegen'd typed mirror of phase's
  emitted `card-data.json`, **inferred from the data** (not phase's Rust source,
  not schemars), committed, regenerated as a gated dev step (never CI), and
  **strict-loaded** (`extra=forbid`) so a phase schema change fails *loudly* at
  load. It is a **shape-faithful structural mirror** — polymorphic fields
  dispatched on the data-visible discriminator keyed by `(parent_field_path,
  tag)` — **not** a claim to phase's nominal type graph. It retains every phase
  field verbatim, so bucket-A field-drop is impossible *at the substrate*. A cheap
  `ability.rs` variant-name grep enumerates the ~18 name-known/shape-unknown
  `Effect` variants (zero v0.9.0 instances — Cascade, Exploit, Miracle, …), which
  get a closed-union arm that fails loud on *first emission*. A committed
  per-variant population baseline guards the one residual the strict loader can't
  see: a node relocating between two *both-valid* variants (schema unchanged).

- **Supplement (bucket-B only), decomposed three ways.** The 46 `_recover_*` arms
  are not one operation:
  - **(a) re-categorizers** of phase's `other`/`Unimplemented` nodes → fold into
    the Layer-2 crosswalk as concept-mappings off the retained node; *no* Layer-1
    entry, not convergence-checkable.
  - **(b) overlay corrections** that mutate/append phase's correctly-parsed nodes
    (75 `replace(...)` calls today) → a **named Layer-2 overlay-correction stage**
    that runs *after* the pure substrate and *provably never writes into it*
    (dev-time invariant). Leaving these in the substrate would violate "Layer 1
    stays pure phase."
  - **(c) true dropped-clause synthesis** (facedown, devotion operand, base P/T,
    …) → a **separate parallel phase-shaped, codegen-typed collection**. The
    **convergence check** ("shrinking bridge") runs *only* on (c), is
    **input-side** — an arm retires when the `category="other"` clauses it fired
    on become phase-parsed (its `recovered_by_category` count drops), **not** when
    its output byte-matches phase's node — and **tolerates indefinite persistence**
    for mechanics phase never implements (a true negative). Long-term home of each
    (c) arm is upstreamed phase grammar (ADR-0028).

- **Layer 2 — overlay (derived, tree-preserving).** One crosswalk derives the
  ~80-concept synergy vocabulary from both collections uniformly. **Totally
  lossless:** every node → a recognized concept-node *or* an `other` concept
  **carrying the verbatim structured node** (categorically different from today's
  verbatim-*text* `raw` hatch, which forces re-regex). A concept-node is a
  **per-node decoration hanging off the preserved Layer-1 tree position** (face +
  ability), **not** a flattening into a node bag — the query surface exposes the
  three join granularities lanes already depend on: per-ability sibling
  co-occurrence (`discard_makers` needs a `draw` sibling in the *same* ability),
  per-ability effect/raw aggregation (the animate-land split-subject
  reconstruction), and whole-card / cross-face merged-key joins (the four
  `signals.py` reconciliations). Derived fields (`counter_kind`, `mana_kind`,
  `returns_to`, `toughness`-sign, `trigger.event`) carry phase-node provenance
  assertions. `project.py`'s field-shape skeleton dissolves into codegen; its
  semantic concept-derivation **relocates** here (ported with fixtures, not
  deleted).

- **Layer 3 — lanes + the second seam.** Lanes/presets emit the unchanged
  `Signal(key, scope, subject)` contract. **Two consumer seams are acknowledged,
  not one:** `Signal` (lanes/presets) *and* the **Effect/Ability/Card dataclass
  API** (`.category/.scope/.counter_kind/.toughness/.amount/.zones/.subject/.raw`,
  `ab.trigger.event`, `ir.all_abilities()`) read directly by `ranking.py`,
  `budgets.py`, `cut_check.py`, and the tuner (`_tuner/metrics.py`,
  `_tuner/bracket.py`). Layer 2 exposes the concept overlay *as* that stable
  compatibility surface (or the five files are line-item migrated). Both seams are
  gated.

- **Storage — two-layer cache.** substrate-cache (rebuilt on phase bump /
  supplement change) + overlay-cache (rebuilt on crosswalk edit, reads the
  *materialized* substrate-cache). Runtime hot-path loads **overlay-cache only**
  (dict-by-`oracle_id`, as fast as today — raw lookup speed was a deliberate fix
  after live computation was too slow). "Substrate loaded lazily" = a **deferred
  whole-file load cached in the existing `_MEM_CACHE`** for the rare fall-through,
  *not* a new random-access engine; the lossless `other` tail (~0.5 MB of lean
  stubs) inlines into the overlay, making fall-through rare-to-never.

- **Migration gate.** Adjudicated fixtures + full-corpus shadow `Signal`-diff
  **plus** new corpus output-diff harnesses for the four non-signal consumers
  (cloned from `signal_diff.py::diff_corpus`). Gate = **adjudicated improvement**,
  not byte parity against the known-lossy old IR; each divergence logged with a
  verdict; net regressions block the stage. The committed CI fixture lives at
  Layer 2, never the strict substrate.

## Considered options

- **Parse phase's Rust source.** Rejected: must reimplement serde (720
  `skip_serializing_if`, 1960 `serde(default)`, 10 `flatten`, 8 `untagged`, 27
  `rename`) to predict the JSON — silent-misread risk. Reading the *emitted* JSON
  has all serde transforms already applied; it is grounded in what we consume.
- **Upstream `schemars` from a patched phase.** Rejected: re-couples builds to a
  cargo build of phase, undoing the no-Rust-compile decoupling (the card-data
  fetch was deliberately decoupled from the repo at v0.8.0).
- **Band-aid: add a verbatim `raw_node` to `Effect`, keep `project.py`.** Rejected
  *as the whole answer*: no loud drift detection (project.py still silently
  misreads restructured nodes on a bump — the actual v0.8.0 pain), dual
  representations to keep in sync, and no shared schema for the supplement
  convergence check. It is the *embryo* of Layer 1, not an alternative to it.
- **Push the substrate to completion.** Not the push ADR-0032 forbids: verbatim
  *retention* leaves parse-fidelity untouched (a retention axis, not a completion
  axis). Infrastructure is still *pulled* per stage (cache at Stage 4, convergence
  check at Stage 3), not built ahead of a consumer.
- **Treat `Signal` as the only consumer seam.** Rejected: five files read the
  Effect/Ability dataclass API directly and are invisible to a Signal-only gate.
- **Flat per-node overlay.** Rejected: `discard_makers` (sibling co-occurrence),
  the animate-land split-subject reconstruction, and four whole-card
  reconciliations are not per-node-expressible.

## Consequences

- bucket-A field-drop becomes impossible at the substrate; the v0.8.0 silent-drift
  mode becomes a loud load-time failure forcing a gated regen.
- `project.py`'s field-shape skeleton dissolves into codegen; its semantic
  derivation (~138 regex constants, 52 recover arms, 81 concept-collapse rules)
  **relocates** to the crosswalk with its own fixtures — tracked as *LOC deleted
  vs relocated*, so the codegen win is not oversold.
- **Honest scope:** Layer 1 kills storage-level loss and silent drift. It does
  **not** by itself retire the lane-level raw sub-discriminator regexes (that is
  the in-flight IR-fanout, *redirected* into crosswalk queries) nor shrink the
  consumer surface to `Signal` alone.
- The migration gate widens beyond `Signal` to cover the four non-signal consumers
  via new corpus output-diff harnesses.
- ADR-0028 remains the only sanctioned "feed phase" path: each (c) supplement
  arm's long-term home is upstreamed phase grammar; the convergence check
  *measures* that bridge shrinking.
