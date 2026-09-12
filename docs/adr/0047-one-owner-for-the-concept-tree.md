# One owner for the decorated concept tree: two products, no stage re-applied

The 2026-09-12 architecture review found the Card IR pipeline — strict load, overlay
(with the ADR-0038 recovery stage at its tail), overlay corrections, tree synthesis,
predefined-token trees and text-only face trees — assembled in five places. The
resolver `_deck_forge/_ir_lookup.build_trees` composed strict load and overlay plus the
token and text-only trees but not the corrections or the synthesis; the lanes'
`extract_crosswalk_signals` re-applied both on every tree it was handed; `theme_presets`
re-applied both again over the resolver's output; the compat sidecar builder composed
its own strict load and overlay and applied corrections a second time inside
`compat_card_base`. Six structural readers (the tuner's commander cost and grant
coverage, the rate metric, ident provenance, the limiter discounts, the removal-answer
walk) read the resolver's *uncorrected* trees. `tree_synthesis` — a signals-only stage
by ADR-0038 — lived in `_card_ir` and imported 41 symbols from `_deck_forge` across 23
statements, against the substrate package's own no-back-edge rule. And the resolver
that every tuner module reached for sat inside the signals package, which is why eight
tuner modules import deck-forge internals.

**Decision.**

- **One owner, `mtg_utils._card_ir.trees`.** `face_tree(rec, schema, oracle_id=)` is the
  per-record core — strict load, overlay, overlay corrections — and the only place
  those stages are composed. `build_trees` is the pure per-oid product (face trees, the
  predefined-token trees, the text-only face trees when the bulk record is threaded,
  every one corrected); `trees_for` the memoized production resolver; `seed_trees` the
  testkit's CI-safe warm. The compat sidecar builder and `testkit.test_card_ir` build
  from `face_tree`; `compat_card_base` no longer re-applies corrections.
- **Two named products.** `trees_for` returns **corrected trees** — what every structural
  reader gets, the six former raw readers included. `_deck_forge.signal_trees.
  signal_trees_for` layers the signals-only tree-synthesis stage on top, memoized per
  oracle_id and validated against the owner's tuple by identity, and is what the lanes
  and the theme-preset concept predicates read. `as_signal_tree(tree)` is the same two
  stages for a caller holding a tree it built itself (tests over `build_concept_tree`;
  ident provenance's single-unit views). No lane, preset or reader re-applies a stage.
- **`tree_synthesis` lives in `_deck_forge`.** It reads lane vocabulary (`text_reads`,
  the sweep regexes, `signal_base.clauses`, the subtype table) and never runs for the
  compat `Card`, so it sits beside the lanes that consume it; the rule "the substrate
  never imports the signals package" holds by construction.
- **The gate.** A full-snapshot corpus dump — every card's signals, compat `Card`,
  grant coverage, rate metric, ident provenance, limiter yield, removal answers, theme
  presets and grant payloads — is byte-identical before and after. Handing corrected
  trees to the six raw readers changed nothing: they read typed phase fields off
  `.node`, which corrections never touch.

- **One gap-predicate vocabulary on the tree.** Every "does the substrate already
  carry X?" question a recovery row, a synthesis arm, a ledgered bridge or a lane asks
  is one of six reads on `ConceptTree`: `iter_typed()` (the whole-card deep walk),
  `has_typed(*tags)`, `has_concept(concept, role=, scope=, subject=)`,
  `has_static_mode(*tags)`, `has_trigger(*events)`, `residues(name)` /
  `has_residue(name)` (phase's `Unimplemented` residues by phase `name`), and
  `is_text_only`. The 71 hand-rolled deep walks across synthesis, the bridge ledger and
  the lanes, the ledger's five residue readers and its text-only gates, and the
  synthesis arms' mechanical presence gates now compose these; a gate that needs a
  semantic read (an operand shape, a sibling co-occurrence) keeps its hand-written
  half and calls the vocabulary for its presence half. The corpus dump is
  byte-identical after the migration.

**Considered and rejected.** One product with synthesis for everyone (text-derived
reference nodes reaching the structural readers, against ADR-0038's signals-only
wiring, with a six-consumer diff to prove no change); a third `raw_trees_for` to
preserve the six readers' uncorrected view exactly (keeps them blind to curated fixes
for no gain); moving the shared text primitives down into `_card_ir` instead of moving
synthesis up (drags lane vocabulary into the substrate package); keeping the owner in
`_deck_forge/_ir_lookup.py` (the tuner keeps importing the signals package to read a
tree).

**Amends.** ADR-0038's wiring sentence ("build tree + recovery → corrections →
synthesis, signals-only") is unchanged in order and now names where each stage is
applied: corrections in the owner, synthesis in `signal_trees`. `_ir_lookup` is the
compat-Card seam only (`ir_for`).
