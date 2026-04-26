# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### mtg-utils

```bash
cd mtg-utils
uv sync                              # Install dependencies
uv run pytest ../tests/mtg-utils/ -v  # Run tests
uv run ruff check src/ ../tests/mtg-utils/  # Lint
uv run ruff format src/ ../tests/mtg-utils/  # Format
```

### deck-wizard

```bash
cd deck-wizard
uv sync                              # Install dependencies (follows symlink to mtg-utils/src)
uv run pytest ../tests/deck-wizard/ -v  # Run smoke tests
```

### cube-wizard

```bash
cd cube-wizard
uv sync                              # Install dependencies (follows symlink to mtg-utils/src)
uv run pytest ../tests/cube-wizard/ -v  # Run smoke tests
```

### rules-lawyer

```bash
cd rules-lawyer
uv sync                              # Install dependencies (follows symlink to mtg-utils/src)
uv run pytest ../tests/rules-lawyer/ -v  # Run smoke tests
```

### Running a single test

```bash
cd mtg-utils
uv run pytest ../tests/mtg-utils/test_parse_deck.py -v            # one file
uv run pytest ../tests/mtg-utils/test_parse_deck.py::test_name -v # one test
uv run pytest -k "moxfield and sideboard" ../tests/mtg-utils/ -v  # filter
```

### Python / tooling

- Requires Python 3.12+ (`requires-python = ">=3.12"` in `mtg-utils/pyproject.toml`).
- All four `pyproject.toml` files use `uv` as the install/runtime driver.
- CI (`.github/workflows/ci.yml`) runs the exact commands listed above — it is the authoritative source of truth for which invocations must pass.

## Architecture

Mono-repo for MTG-related Claude Code skills. Each skill lives in its own directory matching the `name` field in its SKILL.md frontmatter.

**Source layout.** The canonical source lives in `mtg-utils/src/mtg_utils/`. `deck-wizard/src`, `cube-wizard/src`, and `rules-lawyer/src` are **symlinks** to that directory. Editing a file through any skill's `src/` edits the shared source — there is exactly one copy. Each skill's `pyproject.toml` re-declares only the CLI entry points it ships; the Python package is installed once per skill `.venv` but all four point at the same files.

### mtg-utils

Shared Python package (`mtg_utils`). 32 CLI script modules (20 deck + 9 cube + 3 rules-lawyer) exposed as 33 entry points — `combo-search` and `combo-discover` both live in `combo_search.py`. `cube-wizard/pyproject.toml` re-declares 12 deck-side CLIs it reuses (card-search, card-summary, combo-search/combo-discover, download-bulk, download-rules, rules-lookup, rulings-lookup, mark-owned, price-check, scryfall-lookup, web-fetch); `rules-lawyer/pyproject.toml` re-declares 5 reused CLIs (card-search, card-summary, download-bulk, scryfall-lookup, web-fetch) alongside its three rules-lawyer-specific entry points; the remaining deck-only entry points live in `deck-wizard/pyproject.toml`.

**Deck scripts:**

- **`parse_deck.py`** — Multi-format deck list parser with sideboard support. Strips Moxfield set code suffixes.
- **`scryfall_lookup.py`** — Card lookup against Scryfall bulk data with API fallback and persistent caching.
- **`edhrec_lookup.py`** — EDHREC JSON endpoint client for commander recommendations.
- **`download_bulk.py`** — Scryfall bulk data downloader with 24h freshness check.
- **`web_fetch.py`** — Web page fetcher with browser headers and curl fallback.
- **`deck_stats.py`** — Deck statistics: land/ramp/creature counts, avg CMC, curve, color sources, total card count.
- **`card_summary.py`** — Compact human-readable card table with filter flags (`--lands-only`, `--nonlands-only`, `--type`).
- **`deck_diff.py`** — Deck comparison: added/removed cards, count/CMC/land/ramp deltas.
- **`set_commander.py`** — Move cards from cards list to commanders list in parsed deck JSON.
- **`mana_audit.py`** — Mana base health audit: land count (Burgess/Karsten for commander, constructed formula for 60-card), color balance (pip demand vs. land production), PASS/WARN/FAIL gates, comparison mode.
- **`cut_check.py`** — Mechanical pre-grill: trigger detection and multiplied values, keyword interaction detection, self-recurring card detection, commander copy/ability multiplication detection.
- **`build_deck.py`** — Apply cuts/adds (mainboard and sideboard) to a deck, output new deck JSON + merged hydrated data.
- **`price_check.py`** — Price validation against budget using Scryfall bulk data with API fallback.
- **`combo_search.py`** — Commander Spellbook API wrapper: `combo-search` for deck combo detection and near-miss identification; `combo-discover` for discovering combos by outcome, card name, or color identity.
- **`export_deck.py`** — Export parsed deck JSON to Moxfield import format (`N CardName` lines) with sideboard section.
- **`card_search.py`** — Search Scryfall bulk data with filters: color identity, oracle text regex, type, CMC range, price range. Compact table or JSON output.
- **`legality_audit.py`** — Format legality, copy limits, sideboard size, Vintage restricted-list audit.
- **`find_commanders.py`** — Search owned collection for commander-eligible cards.
- **`mark_owned.py`** — Populate a deck's `owned_cards` field from a collection CSV/JSON.
- **`mtga_import.py`** — Extract Arena collection and wildcard counts from `Player.log`.
- **`playtest.py`** — Five entry points sharing one module:
  - `playtest-goldfish` — Solo deck simulator (mulligan, curve, color-screw,
    combo timing). Pure Python.
  - `playtest-match` — phase-rs `ai-duel` batch (deck vs deck).
  - `playtest-gauntlet` — Cube round-robin: build N archetype decks from the
    cube, run round-robin via phase, report win-rate matrix.
  - `playtest-draft` — Heuristic 8-player draft + per-deck goldfish.
  - `playtest-install-phase` — One-time `cargo build` of phase v0.1.19 binaries
    into `~/.cache/mtg-skills/phase/`.
  - `playtest-custom-format` — Multiplayer custom-format simulator (e.g.,
    shared-library marketplace draft). Pure Python; per-format module in
    `_custom_format/`.

**Rules-lawyer scripts:**

- **`download_rules.py`** — Downloader for the MTG Comprehensive Rules TXT. Scrapes the Wizards rules landing page for the newest `MagicCompRules*.txt` link, writes to `comprehensive-rules-YYYYMMDD.txt` in the output dir, 24h freshness check matching `download_bulk`.
- **`rules_lookup.py`** — Parser + CLI. Parses the CR into `{sections, rules, glossary}` with rule numbers as keys and cross-references pre-extracted; caches the parsed result as a pickled sidecar next to the TXT. CLI modes: `--rule <n>` (exact-number), `--term <keyword>` (glossary), `--grep "<regex>"` (rule-text search).
- **`rulings_lookup.py`** — Scryfall per-card rulings fetcher. Resolves card name → `oracle_id` via the existing `scryfall_lookup.lookup_single`, then hits `/cards/:id/rulings`. Caches one JSON per oracle_id under `$TMPDIR/scryfall-rulings/` with a 30-day TTL.

**Cross-cutting:** `cut_check.py` and `legality_audit.py` accept a `--cite-rules` flag that auto-attaches CR citations to their JSON output (trigger/keyword interactions → glossary-cited rules; violation reasons → a curated reason→CR map in `legality_audit._REASON_TO_CR_RULES`).

**Cube scripts:**

- **`cubecobra_fetch.py`** — Fetch a cube from CubeCobra. Priority: `cubeJSON` endpoint → `cubelist` → CSV; curl fallback for 403s; rejects HTML-404-with-200 error shells.
- **`parse_cube.py`** — Parse CubeCobra JSON (v1 and current v2 shapes), CubeCobra CSV, plain text, or deck JSON into canonical cube JSON.
- **`cube_stats.py`** — Informational cube metrics: size, per-color distribution, curve, type breakdown, rarity breakdown, commander pool by color identity.
- **`cube_balance.py`** — Informational checks (not pass/fail): color balance, curve, removal density, fixing density (with Lucky Paper band + maindeck-efficiency curve), commander pool.
- **`cube_legality_audit.py`** — Hard-constraint validation: rarity filters (Pauper, Peasant, PDH), Scryfall legality keys, explicit ban lists, commander-pool rarity. Emits errors for clear violations and warns for ambiguous cases (default-printing rarity, missing legality data).
- **`archetype_audit.py`** — Cross-reference user-supplied oracle-text theme regexes against color pairs; flag orphan signals; surface bridge cards that span multiple themes.
- **`cube_diff.py`** — Two-cube comparison with optional `--metrics` balance-metric deltas.
- **`pack_simulate.py`** — Seeded pack generation with configurable slot templates (ported from cube-utils, sizes 9/11/15); optional dedicated commander packs; multi-draft aggregation.
- **`export_cube.py`** — Export canonical cube JSON to CubeCobra-compatible CSV (for the "Replace with CSV Import" round-trip) or plain text.

Shared library modules (not CLI scripts):

- **`card_classify.py`** — Card classification helpers: `is_land()`, `is_creature()`, `is_ramp()`, `color_sources()`, `classify_cube_category()` (9-category W/U/B/R/G/M/L/F/C classifier for cube draft slot allocation).
- **`cube_config.py`** — Cube format presets (9 formats: vintage, unpowered, legacy, modern, pauper, peasant, set, commander, pdh), size-to-drafters table, `PACK_TEMPLATES` defaults, `BALANCE_TARGETS` reference ranges, and curated `REFERENCE_CUBES` starting-point list per format.
- **`bulk_loader.py`** — Shared Scryfall bulk-data loader with a pickled sidecar cache (`<bulk>.idx.pkl`). ~5-10× faster on warm load; atomic-rename write so concurrent callers can't see a partial sidecar. Every script that touches Scryfall data goes through this.
- **`format_config.py`** — `FORMAT_CONFIGS` dict: deck size, copy limit, sideboard size, life total, singleton flag, legality key per format. Ground truth for the "Supported Deck Formats" table below.
- **`theme_presets.py`** — Registry of named matchers for common MTG mechanics (keyword list + oracle-text regex). Each preset ships with `should_match` / `should_not_match` fixtures pinned in `tests/mtg-utils/test_theme_presets.py`. Used by archetype detection in deck-wizard and cube-wizard.
- **`names.py`** — Canonical card-name normalization shared across scripts that cross-reference sources (e.g. `find_commanders`, `mark_owned`). Centralized because drift in Unicode folding silently corrupts ownership intersection.
- **`_sidecar.py`** — Pickled-sidecar primitives reused by `bulk_loader` and `rules_lookup`.
- **`_phase.py`** — Phase-rs subprocess wrapper. Manages the cached phase
  install at `~/.cache/mtg-skills/phase/` (or `$MTG_SKILLS_CACHE_DIR/phase`),
  exposes `run_duel` / `run_commander` and the coverage gate. Pinned to
  phase tag `v0.1.19`; bump with care.
- **`_playtest_common.py`** — Schema-v1 JSON envelope and four markdown
  renderers (`render_goldfish_markdown`, `render_match_markdown`,
  `render_gauntlet_markdown`, `render_draft_markdown`).
- **`_gauntlet_build.py`** — Heuristic gauntlet deckbuilder (used by
  `playtest-gauntlet` over the full cube and by `playtest-draft` over
  each player's drafted pool). `score_card(card, archetype, colors)`
  returns an internal-scale fit score; `build_gauntlet_deck(pool, spec)`
  greedy-fills curve buckets, then adds basics by color demand.
- **`_draft_ai.py`** — Heuristic drafter. `score_pick(card, state)` picks
  by raw power before pick 3 and by archetype/color commitment after.
  `draft_pod(pool, players, packs, pack_size, rng)` runs an N-player pod.
- **`_custom_format/`** — Per-format multiplayer cube simulators. Shared
  harness (`_common.py`) provides library-effect classifier, archetype
  commitment heuristic, pick decision, library-target heuristic, per-game
  state types, simulation loop, and cross-game aggregation. Each format is
  one module (`shared_library.py`, etc.) implementing `setup()` /
  `run_turn()` / `is_terminal()`. `FORMAT_REGISTRY` in `__init__.py` maps
  format name → module for CLI dispatch.

### deck-wizard

Shares `mtg_utils` via symlink to `mtg-utils/src`. Builds decks from scratch or tunes existing ones across all formats (Commander/Brawl/Historic Brawl and 60-card constructed). Two-phase workflow: Phase 1 acquires a deck (parse existing or build from scratch), Phase 2 runs a 12-step tuning pipeline.

### cube-wizard

Shares `mtg_utils` via symlink to `mtg-utils/src`. Builds and tunes MTG cubes (curated card pools of 360–720 cards designed for drafting). Two-phase workflow: Phase 1 acquires a cube (Path A: parse an existing CubeCobra cube; Path B: clone a well-known reference cube from `cube_config.REFERENCE_CUBES` and customize). Phase 2 runs a 9-step tuning pipeline (baseline metrics → designer intent → balance dashboard → archetype audit → power-level review → self-grill → propose changes → pack simulation → export). Balance checks are informational, not pass/fail, so a mono-color or skewed-by-design cube is never flagged as broken.

### rules-lawyer

Shares `mtg_utils` via symlink to `mtg-utils/src`. Answers MTG rules questions by citing the actual Comprehensive Rules and Scryfall per-card rulings — the project's "legal database": CR = statute, Scryfall rulings = case law. Usable standalone or invoked by deck-wizard / cube-wizard via the Skill tool for trigger-interaction, timing, replacement-effect, and layer questions during tuning. The skill's Iron Rule: every answer MUST cite at least one specific CR rule number that came from the CLI output, not from training data. Four phases: classify the question → run one `rules-lookup` CLI call → escalate (wider search, section Read, or subagent) only when the first call misses → write the answer with verdict, CR citations, and edge cases.

## Supported Deck Formats

| Format | Deck Size | Copy Limit | Sideboard | Arena | Legality Key |
|--------|-----------|------------|-----------|-------|-------------|
| commander | 100 | 1 (singleton) | No | No | commander |
| brawl | 60 | 1 (singleton) | No | Yes | standardbrawl |
| historic_brawl | 100 | 1 (singleton) | No | Yes | brawl |
| standard | 60 | 4 | 15 | Yes | standard |
| alchemy | 60 | 4 | 15 | Yes | alchemy |
| historic | 60 | 4 | 15 | Yes | historic |
| timeless | 60 | 4 | 15 | Yes | timeless |
| pioneer | 60 | 4 | 15 | Yes | pioneer |
| modern | 60 | 4 | 15 | No | modern |
| premodern | 60 | 4 | 15 | No | premodern |
| legacy | 60 | 4 | 15 | No | legacy |
| vintage | 60 | 4 (restricted=1) | 15 | No | vintage |

## Supported Cube Formats

| Format | Default Size | Card Pool | Rarity Filter | Commander Pool |
|--------|-------------:|-----------|---------------|----------------|
| vintage | 540 | Full eternal | — | No |
| unpowered | 540 | Full eternal (Power 9 banned) | — | No |
| legacy | 540 | Legacy-legal | — | No |
| modern | 540 | Modern-legal | — | No |
| pauper | 540 | Full eternal | commons only | No |
| peasant | 540 | Full eternal | commons + uncommons | No |
| set | 360 | Single set | — | No |
| commander | 540 | Commander-legal | — | Yes |
| pdh | 540 | Full eternal | commons (main) | Yes (uncommons) |

## Testing

Tests live in `tests/mtg-utils/` (package tests), `tests/deck-wizard/` (deck skill smoke tests), `tests/cube-wizard/` (cube skill smoke tests), and `tests/rules-lawyer/` (rules-lawyer skill smoke tests), outside the skill directories so they aren't installed. Use `unittest.mock` for HTTP calls. No real network calls in tests.
