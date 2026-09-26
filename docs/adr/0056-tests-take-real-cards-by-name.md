# Tests take real cards by name from the snapshot; they never type card data

A test that needs what a real card says or is — its oracle text, type line, keywords,
mana cost, power/toughness, color identity, legalities — has two ways to get it: type it
in, or look it up. Typed-in card data is memory. It drifts from the card (errata, a
reprint's new wording, a legality change), and when it was never right to begin with it
hides a hallucination behind a green test. The repo already owns the lookup:
`mtg_utils.testkit` serves every card the tests name from the committed snapshot
(`tests/fixtures/card_snapshot.json`), and `build-card-snapshot` rebuilds that snapshot
by scanning the tests for the names they use. The signal and theme-preset suites moved
onto it (the preset `FIXTURE_CARDS` dict is gone). The rest of the suite did not: on
2026-09-23 about 80 test files still hand-built card records, some with real names and
paraphrased text. The price-check tests asserted a wrong Arena rule against a hand-typed
Hare Apparent.

**Decision.** A real card in a test comes from the testkit by name. Only what the test
varies is written by hand.

- **Real cards, by name.** `test_card(name)` (the minimal Scryfall record),
  `test_card_ir(name)`, `test_signals(name)` and `snapshot_records()`. The name is a
  literal at the call site, or on a module-local wrapper that forwards it, so the
  snapshot builder finds it. Adding a name means running `build-card-snapshot` and
  committing the snapshot. A name built in a comprehension or at runtime is invisible to
  the scan.
- **Per-printing facts are the test's variable.** The snapshot deliberately carries no
  rarity, set, availability (`games`), prices, collector number or ownership. A test
  about those overlays them on the real record (`{**test_card("Forest"), "rarity":
  "common", "games": ["arena"]}`), or builds an MTGJSON printing from it, as
  `test_card_pool._mtgjson_printing` does.
- **Synthetic records are for machinery only.** A record that tests the code's handling
  of a shape rather than a card is fine: name folding, price tie-breaks, a missing field,
  a malformed bulk. It uses an obviously fictional name ("Card A", "Dual Print Card") and
  never paraphrases a real card's text. If the assertion depends on what a real card
  does, it is not machinery.
- **Data mirrored from phase is exempt.** A test over phase's own data files (the
  `known-tokens.toml` entries `test_known_tokens.py` mirrors) may write that data by
  hand. It is phase's record, not a card's, and the snapshot doesn't carry it.
- **One store of real cards.** `tests/fixtures/crosswalk_fixture_cards.json` (the
  crosswalk and tree-synthesis suites' own real-cards-by-name file) merges into the
  snapshot, so every real card a test reads comes from `testkit`.
- **A test of a missing field strips it from the real record.** For example, the budget and
  ranking tests that exercise the text-only fallback take `test_card(name)` and drop
  `oracle_id`, with a comment saying why. They don't hand-type a record that lacks it.
- **Negatives are real near misses.** A `should_not_match` or "does not fire" case is a
  real card that resembles the thing without being it, not a generic stand-in:
  Lightning Bolt proves nothing about a creature keyword. Pick a card that grants,
  mentions or resembles the theme without having it. Find one by running the live
  matcher over the bulk, with the card's own name stripped from its text (so a
  self-reference isn't a mention) and joke sets (`set_type == "funny"`) skipped.

**Consequences.** Card-data drift fails loudly: the snapshot's `phase_tag` /
`crosswalk_sidecar_version` guard, plus a rebuild that shows exactly which records
changed. A hallucinated card can't pass, because the name must resolve in real bulk to
enter the snapshot. The snapshot grows with the suite; that is its job. `--prune` drops
names no test uses any more.
