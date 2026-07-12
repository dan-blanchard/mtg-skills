# 39. Legacy IR path deletion: the KEPT twelve, ledgered bridges, delete-then-sprint

Date: 2026-07-11

Status: Accepted

Relates to: [0035](0035-lossless-phase-mirror-ir.md) (this ADR schedules the
death of its Stage-4 flag and residual routing), [0038](0038-unimplemented-recovery-re-decorates-the-concept-overlay.md)
(the recovery/grammar machinery this ADR's endgame leans on),
[0027](0027-card-ir-replaces-regex-detection.md) (the strangler this ADR
completes — a supersession note lands there at execution).

## Context

The crosswalk now serves 323 signal keys; the residual grind is closing the
rest. Dan directed (2026-07-11): delete the legacy IR path after the currently
planned tasks — not an indefinite postponement. Scoping that deletion surfaced
four facts that forced real decisions:

1. **The legacy arm serves 30 keys, not the 18 the residual ledger tracks.**
   `_crosswalk_merge` re-supplies `MIGRATED_KEYS - PORTED_KEYS`: the 18
   `_STAGE4_RESIDUAL` keys *plus* 12 keys deliberately KEPT on legacy at the
   Stage-2 port and never entered in `_PORTED_KEYS_STAGE3` (the **KEPT
   twelve**: base_power_matters, big_mana, cheat_from_top, copy_limit,
   damage_redirect, excess_damage, extra_draw_step, free_cast,
   ki_counter_matters, kicked_spell_matters, land_destruction,
   named_synergy). Meanwhile the regex base uniquely serves nothing: zero
   regex-only keys across all 31,622 commander-legal oracle cards.
2. **The old builder is load-bearing beyond serving.** Production builds only
   the legacy sidecar (`ensure_card_ir` → `build_sidecar`), so `ir_for`
   degrades to `old_ir_for` for every Seam-B consumer; the commander
   membership floor reads the old projected `Card`; the committed test
   snapshot is 100% old projection, guarded by the legacy `SIDECAR_VERSION`;
   and `tests/mtg-utils/test_card_ir.py` pins `project_card` directly.
3. **Some remaining live_only members are genuine gaps with distinct causes**:
   Unimplemented residues (recovery rows reach them), grammar **stragglers**
   (raw text present, clause grammar lacks the verb), **dropped clauses**
   (phase emitted no node at all — bucket-(c) synthesis exists but lands only
   on the Seam-B compat Card today), and missing faces (closed by text-only
   face trees). None are "parser-blocked": the oracle text is always
   reachable by some principled mechanism.
4. **Grammar growth is slow *because* legacy exists.**
   `supplement._recover_by_verb` sets legacy categories from grammar tokens
   unconditionally, so every new verb moves legacy ground truth: both
   sidecars rebuild, legacy-shift diff, snapshot ceremony, serialized in the
   main session.

## Decision

Grilled with Dan 2026-07-11; four decisions, each with the alternative he
rejected:

1. **Extend the grind to all 30 legacy-served keys.** The KEPT twelve are
   treated exactly like residuals — re-measure, revisit each original KEPT
   rationale, build lanes under the same 0-genuine-lost gate — and promote by
   *addition* to the ported set (they were never in it). Rejected: per-key
   value adjudication that could retire low-value keys outright, and a
   mechanical parity port that skips the rationale revisit.
2. **Delete the old builder and its test estate, with a harvest pass.**
   `project_card`/`supplement_card` and `test_card_ir.py` die together, after
   one audit pass harvests behavior-level truths not already pinned by the
   crosswalk suite (ported as fixture pins). The snapshot regenerates from
   the crosswalk substrate and carries per-card phase records so `testkit`
   exercises the crosswalk path in CI; the version guard repoints. Rejected:
   keeping the builder as a frozen test-only reference (two substrates to
   keep green forever).
3. **Bridge, delete, then grammar-sprint.** Stragglers and dropped clauses
   that the grammar cannot express yet get **ledgered bridges** — gap-gated,
   corpus-bounded, self-retiring text reads, each tied to a named grammar
   TODO or upstream report (see `mtg-utils/CONTEXT.md` for the term). The
   deletion proceeds on schedule serving every card legacy served. A
   post-deletion **grammar sprint** then lands verbs cheaply — the double
   ceremony dies with the old builder — and each landing verb auto-retires
   its bridges via their gap-gates (the graduation pattern). The signal-side
   home for dropped clauses is the tree-side bucket-(c) follow-on
   `dropped_clauses.py` already names. Consequence: the grammar trio's two
   verbs (scaling-mana, land-animate) move into the sprint; their keys
   promote pre-deletion via bridges, and the trio's accessor items proceed
   as ordinary lane work. Rejected: grammar-first (deletion waits on the
   slowest serialized work under the expensive ceremony) and accepting
   documented signal losses at cutover.
4. **Fully autonomous, staged execution.** Eight steps, each gated green
   before the next (suites x3, the consumer-diff harness with tight gates for
   cut_check/budgets/tuner and the pre-approved light bar for ranking, final
   corpus re-measure), commits on main, a report per landing. Rejected: a
   review checkpoint before the two deletion commits — git history makes
   every step revertible and the harvest pass protects pinned knowledge.

The full consumer inventory and 8-step order (rehome shared symbols → drive
residual+KEPT to zero with the membership-floor rewire → crosswalk sidecar
becomes the production build → snapshot v2 → delete serving → delete builder
→ docs) lives with task #80; the shared symbols the crosswalk imports from
`project.py`/`supplement.py`/`_signals_ir.py` survive by rehoming, never by
keeping the old path alive.

## Consequences

- "Done" for the migration means all 30 keys crosswalk-served; the residual
  ledger alone no longer measures it.
- Ledgered bridges are an *accepted endgame instrument*, not a regression to
  regex serving: opposite scope and lifecycle to the deleted detectors, with
  the convergence check keeping unretired bridges visible. A bridge that
  outlives its grammar TODO is tech-debt made loud, not silent.
- Post-deletion, a grammar verb touches one path and one diff; the sprint is
  the forcing function that keeps "transitional" from becoming permanent.
- Keys still carrying unadjudicated live_only members when deletion reaches
  step 5 go to Dan explicitly before their serving path is removed.

## Amendment (2026-07-12): execution complete

Task #80 ran the plan to the end; every step landed green on main:

| Step | Commit | What landed |
|---|---|---|
| 1+2 | 4011de82 | unwired diff harnesses dropped; crosswalk text idioms rehomed |
| 3 | 9442fa0d | membership floor reads the crosswalk tree; merge drops `old_ir_for` |
| 4 | 1b5e606e | crosswalk sidecar is the production build; `ir_for` stops degrading |
| 5 | 7ec5a413 | snapshot v2 (raw phase face records); testkit on the crosswalk |
| 5.5 | 72762730 | compat fidelity pass (pump magnitude, drain/target/mass scope) |
| 6 | 5e57d585 | legacy serving arm + regex floor deleted; cutover flag retired |
| 7 | 779a64ff | builder deleted: `project.py`, `build_sidecar`/`build-card-ir`, legacy sidecar loader, ADR-0032 parse metrics |
| 8 | (this commit) | docs sweep |

**Final bar.** Step 6's corpus re-measure came in at exactly 75 card-level
changes: 6 recoveries from moving the membership floor to the merge level
(DFC faces previously floor-checked in isolation) and 69 adjudicated
`voltron_matters` sheds (legacy false positives, adjudicated per ADR-0034
role rules — sheds, not losses). Step 7 measured zero corpus change: the
builder deletion removed code no serving path still reached.

**Deviations from the written plan — survivors, with reasons.** "Delete
serving" did not mean deleting the two old extractor modules wholesale:

- `_signals_regex` survives as the home of `Signal` + the shared parsing
  primitives (imported by `_signals_ir`, `crosswalk_signals`,
  `tree_synthesis`, and the bridge ledger), as the tests' historical-baseline
  probe, and as `rank_deck_signals`' `ir_for=None` degradation — the one
  place `extract_signals` still executes.
- `_signals_ir.extract_signals_ir` survives as the tests' direct
  structural-engine probe (synthetic fixtures with no `oracle_id` can never
  resolve a crosswalk tree); its `_apply_membership_floor` and Group-C
  constants are imported by `crosswalk_signals` and do serve.
- The old `Card` dataclasses (`card_ir.py`) and `_card_ir/compat.py` were
  never deletion targets: they are Seam B — the five dataclass-API consumers
  read a compat `Card` now built FROM the crosswalk trees.

Neither module is a serving path; `extract_signals_hybrid` is crosswalk-only.

**Open tombstone (1).** Darksteel Garrison's `tap_untap_matters`: the
Unknown-mode becomes-tapped recovery was a `project.py`-only supplement arm
and died with the builder; the crosswalk has no equivalent yet. Pinned as a
textual tombstone in `tests/deck-forge/test_migrated_keys.py` (flip to a
positive pin when the recovery is ported).

**Follow-ups.** (1) The post-deletion **grammar sprint** this ADR's Decision
3 schedules: land clause-grammar verbs cheaply now that the double ceremony
is gone, auto-retiring the 77 ledgered bridges in
`_deck_forge/bridge_ledger.py` via their gap-gates. (2) The **preset
conversion**: retiring `theme_presets`' regex matchers in favor of
structural reads (the ADR-0027 Milestone-C tail).
