# 37. A tree-synthesis stage for bucket-B signal-lane folds

Date: 2026-07-05

Status: Accepted

Relates to: [0036](0036-lane-mirrors-fold-to-structural-reads.md) (implements its
bucket-B mechanism — the "projection-time supplement arm that emits a typed
ConceptNode"), [0035](0035-lossless-phase-mirror-ir.md) (extends the Stage-3b
Layer-2 overlay stages + the substrate-purity invariant).

## Context

Folding a lane mirror to a Tier-1 structural read (ADR-0036) requires, for the
**bucket-B** tail (a genuine phase parse gap — the clause survives only in oracle
text), that a typed node the *signal lane* reads be synthesized. No existing stage
can do that:

- `overlay_corrections` (bucket b) only **decorates** existing concept-nodes; its
  substrate-purity invariant forbids adding nodes.
- `dropped_clauses` (bucket c) synthesizes, but onto the **compat Card** (Seam B,
  the five dataclass consumers). Its own docstring defers *"tree-node synthesis
  for the few clauses a Signal lane could read"* as a follow-on.

The death_matters recall-fold pilot (ADR-0036) proved this the hard blocker: 136
of 190 mirror-only drops recover via added Tier-1 reads and ~35 are correct
over-fire sheds, but 24 are genuine members phase emits no typed node for — and
they cannot be recovered without this follow-on.

## Decision

Add a new flag-ON Layer-2 stage, `tree_synthesis.apply_tree_synthesis(tree)`,
that **adds** synthetic concept-nodes to the crosswalk tree for genuine
phase-parse gaps, each from a projection-time regex-over-oracle-text run **once**
that emits a typed `ConceptNode` the signal lane then reads structurally.

- **Signal-path-only wiring.** It runs after `apply_overlay_corrections` in the
  `extract_crosswalk_signals` path **only** — never in `compat_card`. So the
  compat Card, the five Seam-B consumer views, and the flag-OFF `old_ir_for` path
  are all unaffected: a bucket-B fold moves *signals* and nothing else.
- **Synthetic nodes are a distinct type.** A synthesized `ConceptNode` carries a
  `SynthesizedNode` marker in its `.node` slot (not a phase `TypedMirrorNode`),
  tagged with the arm id that produced it. Its `concept` / `subject` / `scope`
  are what the lane reads; its `.node` is provenance, not phase substrate.
- **The purity invariant relaxes, precisely.** It changes from "the L1 node
  fingerprint is unchanged" to "every *phase* L1 node present before is present
  after with the same identity (no mutation, no removal); `SynthesizedNode`
  additions are allowed." `l1_nodes` filters out synthetic nodes, so the phase
  fingerprint is still asserted exactly. Adding a node is now legal *only* for
  this stage and *only* as a tagged synthetic node.
- **Convergence-tracked.** Each arm is keyed by id so the input-side convergence
  check retires it when phase begins parsing the clause (ADR-0035 shrinking
  bridge). A synthesis arm is a bridge, not a permanent home.

## Considered options

- **Reuse `overlay_corrections`** — rejected: purity forbids adding nodes, and a
  concept-flip on an existing node moves the wrong seam.
- **Synthesize on the compat Card like `dropped_clauses`** — rejected: the signal
  lanes read the *tree*, not the compat Card, so a compat-seam synthesis does not
  feed them (its own docstring says so).
- **Keep the (narrowed) lane mirror for the bucket-B tail** — rejected: that is
  the Tier-0 text-read tech-debt ADR-0036 retires; a narrowed mirror is still a
  mirror.

## Consequences

- Bucket-B folds become possible: the lane goes fully Tier-1 (reads the
  synthesized typed node), the regex runs once at the projection seam (shared, not
  per-lane), and the arm retires when phase upstreams the mechanic.
- The synthesis is signal-only, so it can never regress the Seam-B consumers or
  flag-OFF — the gate for a bucket-B fold is the per-card SIGNAL diff alone.
- A new non-vacuity test must prove the relaxed purity check still catches a
  phase-node mutation/removal (only tagged synthetic *additions* are exempt).
