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

1. Rewrite the live pin sites — `PHASE_TAG`, CLAUDE.md's "currently vX" mentions
   and the pin test. A dated history mention of the old tag ("the v0.66.0 pin bump
   found …") is left alone.
2. Fetch `ability.rs` at the tag and rewrite `EFFECT_VARIANTS` (order preserved).
3. Fetch and cache card-data for the tag.
4. Build the substrate; rewrite `ZERO_INSTANCE_EFFECTS` from the population zeros.
5. Rewrite the crosswalk fixture from the new card-data, matching each pinned record
   by oracle id and casefolded name; a pin with no record is kept and reported.
6. Impostor census.
7. Copy the old signals index aside; build snapshot, sidecar, signals index.
8. Signal diff per key, each lost card marked residue-backed (a bridge candidate)
   or silent.
9. Run the bridge ledger test, then every `@pytest.mark.retirement_canary` test
   (a canary guards a phase-misparse workaround that has no ledger row), and
   collect both runs' RETIRE-READY rows.

**Amended (ADR-0056).** Step 5 is gone. The crosswalk fixture merged into the card
snapshot, which the rebuild step already regenerates; the snapshot builder's summary,
unresolved names included, goes into the report's notes. Steps 6–9 are now 5–8.

The two rosters in `variants.py` are generated blocks between marker comments, edited
only by the CLI. Downstream builders run as subprocesses of the same interpreter so
they import the edited pin; the process sets `_phase.PHASE_TAG` only for its own
fetches. The output is one markdown report under
`$MTG_SKILLS_CACHE_DIR/phase-bump/<tag>/`. Every judgment call stays human: the script
never edits `_IMPOSTOR_RECORDS`, a lane, or a bridge row.

**Amended (the v0.94.0 review).** The v0.94.0 triage was done by eye and missed a
real impostor (the Fast // Furious join had flipped back at v0.86.0, leaving the only
`_IMPOSTOR_RECORDS` row dead), called a pinned loss a false positive until its test
failed, and left losses unexplained in the commit. Decision: the report pre-sorts
everything data can decide, so the human judges only the rest. It classifies each
impostor-census row (marking the ones already recorded) and flags dead
`_IMPOSTOR_RECORDS` rows; puts every lost card in
one bucket, collapsing the ones that need no verdict; tags gains on already-parsed
cards; lists every loss that still needs a verdict; and measures every bridge row's
corpus reach. A strict "gap ⊆ match" check was rejected: a well-keyed gap still
holds on near misses, so breadth is reported, never failed.

The human decides which new LIKELY IMPOSTOR rows enter `_IMPOSTOR_RECORDS` (and what
replaces a DEAD row), a verdict for each "Needs a verdict" line (answered in the
bump's commit message), whether each "Gains to check" line is a false positive, and
what to do with a DEAD bridge row. The bucket definitions and how to make each call
live in the triage guide, `docs/phase-pin-bump.md`.

**Considered and rejected.** Three small CLIs for the unscripted steps only (the
ordering stays in a memory note); loading the rosters from a JSON fixture at import
(no source edits, but the roster leaves the code and every import pays a read);
rewriting `_IMPOSTOR_RECORDS` from the census (the v0.23.0 census had eight
errata-drift false positives a text gate would wrongly drop).
