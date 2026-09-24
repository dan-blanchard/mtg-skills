# The phase pin bump is one command

The last three phase-rs pin bumps touched 20, 35 and 47 files. Two of their steps had
builders (`build-card-ir-substrate`, `build-card-snapshot`, `build-card-ir-crosswalk`,
`build-signals-index`); three lived only in a memory note — regenerating
`tests/fixtures/crosswalk_fixture_cards.json` (no committed writer), the impostor
census (card-data records whose text matches no bulk face for their oracle id), and
the corpus-wide signal diff (copy the old signals index aside before the rebuild
overwrites it, then diff per key). The `Effect` enum roster and its zero-instance
subset were hand-grepped from phase's `ability.rs`. Rediscovering the unscripted steps
cost most of the v0.66.0 session, and the bump after it left CI red until a two-test
seeding fix landed. The 2026-09-12 architecture review listed scripting the bump.

**Decision.** `bump-phase-pin <tag>` (`mtg_utils.phase_bump`) runs the recipe in
order and stops at the first failure; `--from-step N` resumes.

1. Rewrite `PHASE_TAG`, the CLAUDE.md mentions and the pin test.
2. Fetch `ability.rs` at the tag and rewrite `EFFECT_VARIANTS` (order preserved).
3. Fetch and cache card-data for the tag.
4. Build the substrate; rewrite `ZERO_INSTANCE_EFFECTS` from the population zeros.
5. Rewrite the crosswalk fixture from the new card-data, matching each pinned record
   by oracle id and casefolded name; a pin with no record is kept and reported.
6. Impostor census.
7. Copy the old signals index aside; build snapshot, sidecar, signals index.
8. Signal diff per key, each lost card marked residue-backed (a bridge candidate)
   or silent.
9. Run the bridge ledger test and collect its RETIRE-READY rows.

**Amended (ADR-0056).** Step 5 is gone. The crosswalk fixture merged into the card
snapshot, which the rebuild step already regenerates; the snapshot builder's summary,
unresolved names included, goes into the report's notes. Steps 6–9 are now 5–8.

The two rosters in `variants.py` are generated blocks between marker comments, edited
only by the CLI. Downstream builders run as subprocesses of the same interpreter so
they import the edited pin; the process sets `_phase.PHASE_TAG` only for its own
fetches. The output is one markdown report under
`$MTG_SKILLS_CACHE_DIR/phase-bump/<tag>/`. Every judgment call stays human: the script
never edits `_IMPOSTOR_RECORDS`, a lane, or a bridge row.

**Considered and rejected.** Three small CLIs for the unscripted steps only (the
ordering stays in a memory note); loading the rosters from a JSON fixture at import
(no source edits, but the roster leaves the code and every import pays a read);
rewriting `_IMPOSTOR_RECORDS` from the census (the v0.23.0 census had eight
errata-drift false positives a text gate would wrongly drop).
