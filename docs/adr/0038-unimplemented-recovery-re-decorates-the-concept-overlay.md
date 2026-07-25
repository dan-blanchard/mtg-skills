# 38. Unimplemented recovery re-decorates the concept overlay via a shared clause grammar

Date: 2026-07-09

Status: Accepted

Relates to: [0037](archive/0037-tree-synthesis-stage-for-bucket-b-signal-folds.md)
(narrows its scope — tree synthesis remains only for cares-about *references*;
effect clauses move to this mechanism), [0036](archive/0036-lane-mirrors-fold-to-structural-reads.md)
(this is the durable form of its bucket-B "supplement arm"), [0035](0035-lossless-phase-mirror-ir.md)
(extends the Layer-2 overlay; the substrate-purity invariant is preserved
*unrelaxed* here).

## Context

~77 signal keys remain residual (`_STAGE4_RESIDUAL`): production serves them
from the legacy regex path because the crosswalk misses their cards. The root
cause is structural, not per-key: those cards' clauses land in phase as
`T_effect__Unimplemented`, and the two IR paths treat that differently.

- The **old-IR path** runs `supplement.py` — a real clause mini-parser (prefix
  peeling + an ~80-arm verb grammar) that turns Unimplemented text into
  structured `Effect` nodes. Legacy lanes therefore see structure.
- The **crosswalk path** (`build_concept_tree`) reads the raw phase mirror and
  never runs the supplement. An Unimplemented node decorates to
  `concept="other"`, the lanes see nothing, and the key stays residual. The
  compat projection likewise emits `category="other"` — a latent regression
  for the five Seam-B consumers the moment a key cuts over.

The interim bridge — ADR-0037 synthesis arms emitting `synth_<key>` *marker*
concepts that each lane special-cases — was flagged as the "regex-bridge now,"
not the parser substrate: it accretes one regex arm plus one lane special-case
per key, and its markers sit outside the node's true ability-unit position.

Two facts make a better mechanism possible:

1. supplement's parsing core is a **pure text → structure function** (it reads
   only the clause text; the old-IR `Effect` is just its envelope), so the
   grammar is portable.
2. The substrate-purity invariant asserts **object identity of phase L1
   nodes** — it constrains the `.node` slot, not the decoration. The
   `concept`/`scope`/`subject` fields of a `ConceptNode` are the overlay's own
   to write.

## Decision

Unimplemented recovery becomes a substrate-wide overlay stage that
**re-decorates in place**, powered by **one shared clause grammar**.

- **Re-decoration, not synthesis.** The stage walks `ConceptNode`s with
  `concept == "other"` whose `.node` is `T_effect__Unimplemented`, parses the
  clause text with the grammar, and rewrites the decoration —
  `replace(concept_node, concept=…, scope=…, subject=…)` — keeping the **same**
  `.node` object. Purity holds by construction, with no exemption. The
  recovered node keeps its real `AbilityUnit`/role position, so role gating and
  sibling co-occurrence reads work, and the lanes' existing typed arms fire
  unchanged — no `synth_*` special-casing.
- **One shared grammar core.** The pure clause-dispatch core (`_PREFIX`
  peeling, `_VERB`, `_EFFECT_CLAUSE`) is extracted from `supplement.py` into a
  shared module. supplement re-points at it (zero behavior change); each side
  keeps a thin emitter. The crosswalk emitter owns the token → concept mapping
  (`damage`→`deal_damage`; `reanimate`→`change_zone` + `zones=("graveyard",)`
  via the Stage-3b correction fields where the concept vocabulary collapses a
  distinction) and the scope-vocabulary translation. When the old path
  retires, supplement's envelope dies but the grammar core lives on as the
  substrate's gap-filler.
- **Substrate-wide wiring.** Recovery runs upstream of the signals/compat
  split, writing both `concept` (for lanes) and the compat-only `category`
  correction field (for the old-IR projection) — mirroring what supplement
  contributed on the legacy path, so the compat gap closes with the signal
  gap. Order: build tree + recovery → `apply_overlay_corrections` (curated,
  wins on conflict) → `apply_tree_synthesis` (references only, signals-only).
- **Provenance.** `ConceptNode` gains `recovered_by: str = ""`, written only
  by this stage, naming the grammar rule that fired. Per-rule corpus fire
  counts replace `SYNTHESIS_ARM_IDS` as the bridge-remaining metric; a phase
  bump that types the clause makes the gap-gate stop the rule automatically
  (fire count → 0 → retire).
- **Allowlist rollout.** The grammar may parse more than we trust; the emitter
  re-decorates only allowlisted tokens. The allowlist grows per-key with
  corpus crosswalk-vs-legacy measurement and pinned tests — never big-bang
  (batch promotion has already demonstrated why: it conflates hundreds of
  card-level changes needing role-aware adjudication).
- **An Unimplemented clause is three cases, not one, and re-decoration handles
  only the first.** (1) **Full residue** — the raw text carries the clause →
  re-decorate per this mechanism (examples: discover-again, evasion-denial,
  end-the-turn). (2) **No residue** — phase dropped the clause without
  emitting a node at all → nothing exists to re-decorate; the key stays an
  ADR-0037 synthesis arm, but now emits the real concept so lanes read it
  through their typed arm. (3) **Partial residue** — a node exists but phase
  consumed the datum the lane needs (e.g. Grothama's "each player" subject
  survives only in the card's oracle text) → synthesis with real vocabulary
  (concept + the missing decoration), never a fabricated re-decoration —
  recovery must not write a datum the clause text does not contain. The
  `synth_*` marker namespace retires across all three classes.
- **Text-only face trees are a fourth case (W2c).** Phase emits **no record at
  all** — not even a drifted or Unimplemented one — for some multi-face card
  halves, so there is no `ConceptNode` to re-decorate in the first place. This
  is corpus-wide for the `aftermath` layout (96/96 second halves) plus exactly
  one two-face `split` gap ("Fast // Furious"'s "Furious" face); adventure,
  transform, modal_dfc, flip, and prepare are fully covered by phase. The bulk
  (MTGJSON) record is the text source of record for a phase-missing face:
  `_ir_lookup.trees_for` synthesizes one additional **zero-unit ConceptTree**
  per phase-missing face when its production caller threads the bulk record
  in (`units=()`, `oracle` set to the bulk face's text verbatim,
  `card_types`/`card_subtypes`/`card_supertypes`/`cmc`/`power` parsed from the
  bulk face). `extract_crosswalk_signals` already runs
  `apply_overlay_corrections` + `apply_tree_synthesis` over every tree it is
  handed, so a text-only tree's `oracle` field feeds the same lanes a
  phase-built tree's would. Scope is real two-face gameplay splits only:
  `len(card_faces) != 2` excludes the Unglued/Unstable/Unfinity three-/
  five-way joke splits, and `art_series` / `double_faced_token` /
  `reversible_card` are excluded by layout name. Whole-oid-missing cards (no
  phase group at all) stay out of scope — they already degrade to the legacy
  IR path via `trees_for`'s existing empty return. Corpus quantification
  (PORTED_KEYS, all affected cards): only 5 of 97 affected card names actually
  gain a new signal from their text-only face — `fight_makers` (Prepare //
  Fight), `stax_taxes` (Failure // Comply), plus `pump_makers` /
  `evasion_self` / `spellcast_matters` on one further card apiece — every gain
  matching `extract_signals_ir` (legacy) ground truth exactly. The Seam-B
  compat sidecar (`build_crosswalk_sidecar`) is NOT threaded with text-only
  faces: no Seam-B consumer reads `Card.faces` directly (all five go through
  `Card.all_abilities()`, which already only ever saw the phase face(s) that
  exist), so this is unchanged pre/post behavior, not a regression — threading
  bulk data into the sidecar builder is deferred until a Seam-B consumer diff
  shows it matters.

`tree_synthesis` (ADR-0037) shrinks to its irreducible remainder: cares-about
**references** that are not effect clauses at all (e.g. a card that names a
token subtype without making one). Effect-like marker arms are re-expressed as
grammar rules and deleted.

## Considered options

- **Synthesize typed mirror nodes from text** (`T_effect__Draw` built by the
  grammar) — rejected: the mirror is verbatim-phase; a text-derived node
  impersonating a phase parse poisons every tag-keyed structural read.
- **Keep append-a-marker synthesis but emit real concept names** — rejected:
  solves lane special-casing but loses the node's true unit/role position and
  keeps recovery a bolt-on rather than the substrate's parser.
- **Fork the grammar into the crosswalk** — rejected: crosswalk-vs-legacy
  corpus diffs are the promotion evidence; a forked grammar makes that diff
  measure grammar drift instead of representation differences, and doubles
  parser maintenance during the strangler period.
- **Signals-only wiring (like tree_synthesis)** — rejected: legacy runs
  supplement for *all* consumers; a signals-only recovery leaves every
  residual card a compat regression and blocks retiring the old path.

## Consequences

- Residual-key recovery stops accreting per-key regex arms + lane
  special-cases; it becomes grammar coverage plus an allowlist entry, and the
  recovered card is indistinguishable from a typed one at the concept layer.
- The five Seam-B consumers converge toward legacy as the allowlist grows —
  retirement of the old-IR path becomes honest instead of deferred.
- The purity invariant needs no second exemption; re-decoration is provably
  inert to the phase fingerprint (same `.node` objects).
- Rules-firing decisions that hinge on rules semantics remain CR-grounded
  (rules-lawyer) at adjudication time, per the established discipline.
- The 5 effect-like marker arms from the interim bridge must be re-expressed
  and their `synth_*` lane reads deleted, key promotions and pinned tests
  intact, before the per-key grind resumes on the new mechanism.

*Amended 2026-07-10 (twice); original decision revised in place.*
