# Bumping the phase-rs pin: the triage guide

`bump-phase-pin <tag>` (ADR-0049) does the mechanical work: it edits the live pin sites
(dated history mentions survive), regenerates the Effect rosters and every artifact, and
writes `$MTG_SKILLS_CACHE_DIR/phase-bump/<tag>/report.md`. This guide covers what the
report leaves to a person. Work its sections top to bottom.

```bash
cd mtg-utils
uv run bump-phase-pin <tag>                 # the whole bump
uv run bump-phase-pin <tag> --from-step 6   # after a lane fix: rebuild + signal diff + graduation
uv run bump-phase-pin <tag> --install-phase # also move the cargo clone (playtesting only)
```

## Report sections

- **Impostor census.** Rows come classified: LIKELY IMPOSTOR (the record's text is
  another oracle id's face text, and the row names that card) or errata drift. A likely
  impostor whose (oracle id, exact text) is already in `_phase._IMPOSTOR_RECORDS` is
  marked "already recorded" and sorts after the new ones: it's dropped at ingestion, so
  it needs no decision. Decide each *new* LIKELY IMPOSTOR for `_IMPOSTOR_RECORDS`, keyed
  by (oracle id, exact text) so it retires itself. A **DEAD** row line means the
  upstream join was fixed *or flipped*: the Fast // Furious mis-join has changed
  direction between pins, so look for the flipped record before deleting the row.
- **Signal diff.** Every lost card lands in exactly one bucket, the first that applies:
  1. **PINNED:** a test module, a theme-preset fixture or a bridge-ledger pin names the
     card (by full name or any face), the same sources the card snapshot is built from.
  2. **Dropped upstream:** the card had a phase record at the old tag and has none at
     the new one (e.g. the Alchemy A- cards MTGJSON removed when Arena did).
  3. **Variant churn:** the bulk holds several oracle ids under the name *and* the same
     name also gained the key, so the signal moved to a sibling printing (Un-set
     variants).
  4. **Needs verdict:** everything else.

  Dropped-upstream and variant-churn losses collapse to a count per key; they need no
  verdict. A gain is tagged [check] when phase parsed the card at both tags (a record
  at each), unless it's a multi-variant name that also lost the key. A card with no
  old signals still counts: phase parsed it, so a new key on it is a new read, not a
  newly parsed card (v0.94.0: Clash of Elements' `direct_damage`).
- **Needs a verdict.** Every PINNED and needs-verdict loss. Write a verdict for each
  into the commit message.
  - PINNED means the test suite decides: a failing pin is a regression, and a passing
    near-miss pin sanctions the loss. Don't overrule a pin by reading the card text. At
    v0.94.0 Phyrexian Arena's lost `lifegain_matters` looked like a false positive
    leaving, but the lane deliberately counts a draw-and-lose-life engine as wanting
    lifegain (pinned by `test_lifegain_broadened_draw_bleed_recovered`).
  - For a needs-verdict loss, diff the raw record: `card-data-<old>.json` vs
    `card-data-<new>.json` in `~/.cache/mtg-skills/phase/card-data/`. A histogram of a
    field's values across both files finds a rename fast. Residue-backed losses are
    bridge candidates (ADR-0048); silent ones are usually a shape rename a read must
    learn.
- **Gains to check.** Each [check] gain is a candidate false positive. New wording in
  phase's newer MTGJSON is a common source (v0.94.0: base-P/T "become equal to" leaked
  into `toughness_combat` and `self_counter_grow`).
- **Graduation.** RETIRE-READY bridges and `retirement_canary` workarounds. Before
  deleting a row, confirm each pin still fires its key through `extract_signals`: at
  v0.86.0 Nimble Hobbit's gap closed upstream but the overlay didn't read the new shape.
  **Bridge reach** evaluates every row over the whole corpus and flags a DEAD row (fires
  on no card: stale pins, or a drifted gap and match). The rest is informational, split
  at 5% of the corpus:
  - A **narrow** gap (true on at most 5% of cards) is a residue or hollow-static read,
    so the cards where it holds but the match doesn't are near misses worth a look; up
    to five are sampled. Confirm the gap keys on the row's own clause.
  - A **wide** gap (true on more than 5%) is an absence read ("no typed sacrifice
    node") that holds on almost every card by design, so sampling its gap-only cards
    says nothing. Each gets one summary line (gap count, fires count) so no row is
    hidden; a wide gap only matters if its fires count moves unexpectedly.
- **Roster counts.** The hard-coded counts in `tests/mtg-utils/test_card_ir_mirror.py`
  still bump by hand.

## Fixing what the report finds

Follow CLAUDE.md's working conventions: check rules claims with `/rules-lawyer`, extend
the shared `_card_ir/crosswalk/` walks rather than copying them, and make every
workaround able to retire itself. When several parallel agents take the fixes, give each
an explicit set of files and tell them never to run the rebuild steps. Finish with
`--from-step 6`, then `/simplify` and `/code-review` before committing.

## Shape renames so far

Each has a comment at the read that learned it.

- **v0.66.0:** `Aggregate` → `PropertyAggregate{source: Objects}`; `DealDamage` →
  `EachSourceDealsDamage`; `SetTapState` → `PayCost{TapCreatures}`.
- **v0.86.0:** `TargetPlayer` → `TargetOpponent` for "target opponent"; self-blink return
  `TrackedSet` → `SelfRef`; `Unimplemented.name` head word → category; opponent-library
  `ChangeZone` → `ExileTop{Controller}` plus wrapper `player_scope`;
  `ParentTargetController` → `EventTargetController` off a trigger event; reflexive
  payment → `PayCost{OneOf}` + `WhenYouDo`; `PreventDamage` → `replacements[]` with
  `PreventionMinus`.
- **v0.94.0:** "Otherwise" branches → `else_ability` (the shared walk doesn't follow it;
  reads opt in via `walk_effects_with_else`); d20 tables → `results[]` rows (the walker
  doesn't read them yet); bare-recipient `LoseLife` after the "you draw N and lose M"
  errata; `ChooseAndSacrificeRest` + `player_scope` for keep-N wraths; `TrackedSet`
  "those creatures" grants; static prevention lines → `replacement_structure` residue
  (bridged).
