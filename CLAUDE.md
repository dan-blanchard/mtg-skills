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
uv run download-mtgjson              # Card-data source: MTGJSON AllPrintings + AllPricesToday (ADR-0033; ~609MB; first-run only)
uv run build-card-snapshot           # Regen the committed test card snapshot (gated; needs local MTGJSON bulk + phase card-data — auto-fetched via the phase release-server manifest, no cargo; NEVER CI)
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

### deck-strat

```bash
cd deck-strat
uv sync                              # Install dependencies (follows symlink to mtg-utils/src)
uv run pytest ../tests/deck-strat/ -v  # Run smoke tests
```

### lgs-search

```bash
cd lgs-search
uv sync                              # Install dependencies (follows symlink to mtg-utils/src)
uv run playwright install chromium  # First-run only; downloads Chromium
uv run pytest ../tests/lgs-search/ -v  # Run smoke tests
```

### proxy-printer

```bash
cd proxy-printer
uv sync                              # Install dependencies (follows symlink to mtg-utils/src)
uv run pytest ../tests/proxy-printer/ -v  # Run smoke tests
```

### deck-forge

```bash
cd deck-forge
uv sync                              # Install deps (FastAPI/uvicorn; follows symlink to mtg-utils/src)
uv run pytest ../tests/deck-forge/ -v  # Run backend tests
uv run download-mtgjson              # First-run only; card-data source (MTGJSON AllPrintings, ADR-0033). loader auto-discovers it
uv run deck-forge                    # Launch the backend hub + open the browser UI
uv run deck-forge-phase-crosscheck <cards.json>  # Read-only audit: diff detectors vs phase-rs parse (auto-fetches phase card-data via the pinned-PHASE_TAG release-server manifest — no cargo)
# Frontend (only to develop the UI; the built bundle is committed under frontend/dist):
cd frontend && npm install && npm run build
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
- All eight `pyproject.toml` files use `uv` as the install/runtime driver.
- CI (`.github/workflows/ci.yml`) runs the exact commands listed above — it is the authoritative source of truth for which invocations must pass.

## Architecture

Mono-repo for MTG-related Claude Code skills. Each skill lives in its own directory matching the `name` field in its SKILL.md frontmatter.

**Source layout.** The canonical source lives in `mtg-utils/src/mtg_utils/`. `deck-wizard/src`, `cube-wizard/src`, `rules-lawyer/src`, `deck-strat/src`, `lgs-search/src`, and `proxy-printer/src` are **symlinks** to that directory. Editing a file through any skill's `src/` edits the shared source — there is exactly one copy. Each skill's `pyproject.toml` re-declares only the CLI entry points it ships; the Python package is installed once per skill `.venv` but all six point at the same files.

### mtg-utils

Shared Python package (`mtg_utils`). 39 CLI script modules (25 deck + 9 cube + 3 rules-lawyer + 2 proxy-printer) exposed as 40 entry points — `combo-search` and `combo-discover` both live in `combo_search.py`. `download-mtgjson` (the card-data source) is declared in every skill's `pyproject.toml`. The deck CLIs `deck-signals`, `slot-budgets`, and `deck-rank` are thin wrappers over the deterministic `_deck_forge` signal / budget / ranking core; `deck-tune` is the holistic **spine** over that core (`_tuner.tune`) — one call returns the scorecard + candidate swaps, the same engine deck-forge runs at `POST /api/tune`, and the deterministic basis for deck-wizard's Step-6 tuning (Commander family). deck-wizard's analysis pipeline reuses these instead of guessing. Each other skill's `pyproject.toml` re-declares only the subset of these CLIs it reuses (cube-wizard 12, rules-lawyer 5, proxy-printer 2, deck-strat 16); the remaining deck-only entry points live in `deck-wizard/pyproject.toml`.

**Deck scripts:**

- **`parse_deck.py`** — Multi-format deck list parser with sideboard support. Strips Moxfield set code suffixes from names but retains them as optional entry keys (`set`, `collector_number`, `finish`). Routes Arena/MTGO/Moxfield `Companion` sections into a top-level `companion` zone excluded from `total_cards` (CR 702.139a-b: a companion is neither deck nor sideboard).
- **`scryfall_lookup.py`** — Card lookup against Scryfall bulk data with API fallback and persistent caching.
- **`edhrec_lookup.py`** — EDHREC JSON endpoint client for commander recommendations.
- **`download_mtgjson.py`** — Card-data downloader (ADR-0033): MTGJSON `AllPrintings` + `AllPricesToday` (gzip stream-decompressed) to `~/.cache/mtg-skills/mtgjson/`, 24h freshness, eager translated-sidecar build. The card-data source of record.
- **`web_fetch.py`** — Web page fetcher with browser headers and curl fallback.
- **`deck_stats.py`** — Deck statistics: land/ramp/creature counts, avg CMC, curve, color sources, total card count.
- **`card_summary.py`** — Compact human-readable card table with filter flags (`--lands-only`, `--nonlands-only`, `--type`).
- **`deck_diff.py`** — Deck comparison: added/removed cards, count/CMC/land/ramp deltas.
- **`set_commander.py`** — Move cards from cards list to commanders list in parsed deck JSON.
- **`mana_audit.py`** — Mana base health audit: land count (Burgess/Karsten for commander, constructed formula for 60-card), color balance (pip demand vs. land production), PASS/WARN/FAIL gates, comparison mode.
- **`cut_check.py`** — Mechanical pre-grill: trigger detection and multiplied values, keyword interaction detection, self-recurring card detection, commander copy/ability multiplication detection.
- **`build_deck.py`** — Apply cuts/adds (mainboard and sideboard) to a deck, output new deck JSON + merged hydrated data.
- **`deck_signals.py`** / **`slot_budgets.py`** / **`deck_rank.py`** — `deck-signals` (the deck's signal lanes via `_deck_forge.signals`), `slot-budgets` (role-density bands vs the Command-Zone template via `_deck_forge.budgets`), and `deck-rank` (rank candidate records by synergy, then price, then curve via `_deck_forge.ranking`, never EDHREC popularity). All deterministic; reused by deck-wizard.
- **`price_check.py`** — Price validation against budget using Scryfall bulk data with API fallback.
- **`combo_search.py`** — Commander Spellbook API wrapper: `combo-search` for deck combo detection and near-miss identification; `combo-discover` for discovering combos by outcome, card name, or color identity.
- **`export_deck.py`** — Export parsed deck JSON to Moxfield import format (`N CardName` lines) with sideboard and companion sections.
- **`card_search.py`** — Search Scryfall bulk data with filters: color identity, oracle text regex, type, CMC range, price range. Compact table or JSON output. Applies a **commander-legality filter by default** (not only under `--format`), so cards from spoiled-but-unreleased sets — which MTGJSON marks `not_legal` in every format until release day — are hidden; `--include-unreleased` admits exactly those (via `unreleased_oracle_ids`, which requires EVERY printing to be future-dated, so an always-illegal card reprinted into a future set stays out). Banned/restricted and never-legal cards are unaffected.
- **`legality_audit.py`** — Format legality, copy limits, sideboard size, Vintage restricted-list, and companion audit via `mtg_utils.companion`, wired into `--cite-rules`.
- **`find_commanders.py`** — Search owned collection for commander-eligible cards.
- **`mark_owned.py`** — Populate a deck's `owned_cards` field from a collection CSV/JSON.
- **`mtga_import.py`** — Extract Arena collection and wildcard counts from `Player.log`. Name-level totals stay playset-capped; per-printing quantities are retained uncapped (Player.log carries no foil info).
- **`playtest.py`** — Six entry points sharing one module. `playtest-goldfish` (and `playtest-draft`, which shares its model) is a pure-Python solo deck simulator (mulligan, curve, color-screw, combo timing); its mana model counts lands plus every cast nonland permanent with a non-empty Scryfall `produced_mana`, approximating token-mana generators as a rough ~1-mana/turn source. It ALSO resolves land-search effects via `card_classify.land_fetch_profile` — fetch lands (Evolving Wilds, Hobbit Hole) produce the colors of the deck's own basics rather than nothing, and an *enters*-triggered fetcher (Wood Elves) moves a land from library to battlefield; both respect an `enters tapped` clause. Fetches behind an activation cost (Knight of the Reliquary's `{T}, Sacrifice`) are deliberately NOT credited, since the cost isn't modeled. `playtest-match` runs a phase-rs `ai-duel` batch. `playtest-gauntlet` builds N archetype decks from a cube and round-robins them via phase for a win-rate matrix. `playtest-draft` runs a heuristic 8-player draft plus per-deck goldfish. `playtest-install-phase` does a one-time `cargo build` of the phase binaries at the `_phase.PHASE_TAG` pin (currently v0.45.0, governing both the playtest binaries and the Card IR card-data) — only playtesting needs this; the Card IR build path instead fetches phase's `card-data.json` via a sha256-verified release manifest, so non-playtest users never pay the Rust compile. `playtest-custom-format` runs a multiplayer custom-format simulator with one module per format under `_custom_format/`.

**Rules-lawyer scripts:**

- **`download_rules.py`** — Downloader for the MTG Comprehensive Rules TXT. Scrapes the Wizards rules landing page for the newest `MagicCompRules*.txt` link, writes to `comprehensive-rules-YYYYMMDD.txt` in the output dir, 24h freshness check via the shared `_http.is_fresh`.
- **`rules_lookup.py`** — Parser + CLI. Parses the CR into `{sections, rules, glossary}` with rule numbers as keys and cross-references pre-extracted; caches the parsed result as a pickled sidecar next to the TXT. CLI modes: `--rule <n>` (exact-number), `--term <keyword>` (glossary), `--grep "<regex>"` (rule-text search).
- **`rulings_lookup.py`** — Per-card rulings fetcher, local-first: resolves card name → `oracle_id` via `scryfall_lookup.lookup_single`, serves rulings from the MTGJSON bulk's oracle-keyed sidecar (`_mtgjson.rulings_index`) when present, and falls back to Scryfall's `/cards/:id/rulings` (cached one JSON per oracle_id under `$TMPDIR/scryfall-rulings/`, 30-day TTL) only on a local miss or when no bulk is configured.

**Cross-cutting:** `cut_check.py` and `legality_audit.py` accept a `--cite-rules` flag that auto-attaches CR citations to their JSON output (trigger/keyword interactions → glossary-cited rules; violation reasons → a curated reason→CR map in `legality_audit._REASON_TO_CR_RULES`).

**Cube scripts:**

- **`cubecobra_fetch.py`** — Fetch a cube from CubeCobra. Priority: `cubeJSON` endpoint → `cubelist` → CSV; curl fallback for 403s.
- **`parse_cube.py`** — Parse CubeCobra JSON, CubeCobra CSV, plain text, or deck JSON into canonical cube JSON.
- **`cube_stats.py`** — Informational cube metrics: size, per-color distribution, curve, type breakdown, rarity breakdown, commander pool by color identity.
- **`cube_balance.py`** — Informational checks (not pass/fail): color balance, curve, removal density, fixing density, commander pool.
- **`cube_legality_audit.py`** — Hard-constraint validation: rarity filters (Pauper, Peasant, PDH), Scryfall legality keys, explicit ban lists, commander-pool rarity.
- **`archetype_audit.py`** — Cross-reference user-supplied oracle-text theme regexes against color pairs; flag orphan signals; surface bridge cards that span multiple themes.
- **`cube_diff.py`** — Two-cube comparison with optional `--metrics` balance-metric deltas.
- **`pack_simulate.py`** — Seeded pack generation with configurable slot templates (sizes 9/11/15); optional dedicated commander packs; multi-draft aggregation.
- **`export_cube.py`** — Export canonical cube JSON to CubeCobra-compatible CSV or plain text.

**Proxy-printer scripts:**

- **`proxy_print.py`** — Renders printable PDF proxies from a parsed deck JSON. One CLI, `--kind cards|tokens`. Cards mode: one proxy per copy of every card in the deck (commanders + cards + optional sideboard). Tokens mode: walks each card's `all_parts`, dedupes by `oracle_id`, renders one proxy per kind with a `from: <source>` footer. Both modes share one render template (name banner / ASCII art / type banner / oracle text / P/T). Two-tier art lookup: a user-populated `attributed/<slug>.txt` catalog (carries an artist credit) interleaved per-slug with the local `data/card_art/<slug>.txt` catalog (~480 hand-curated files); lookup walks each subtype slug, then each card-type slug, then `local/_generic.txt`. Attributed hits propagate an "art by X" footer credit.
- **`art_fetcher.py`** — `fetch-art` CLI. Populates the attributed art catalog at `$MTG_SKILLS_CACHE_DIR/attributed-art/` from asciiart.eu and asciiart.website (tag-based discovery, ~1148 tags, preferred over categories because they map cleanly to MTG concepts). `--from-deck deck.json` narrows the fetch to the subtypes a deck actually uses (plus token subtypes); `--by-name` adds a full-card-name search pass that populates `<name-slug>.txt` files for `proxy_print`'s differentiation pass. 7-day on-disk cache; fail-loud on HTTP errors with retry on 429/connection errors. Denylist/allowlist tables filter out MTG-keyword-polluting franchise tags while keeping ones the user wants (e.g. Tolkien).

Shared library modules (not CLI scripts):

- **`card_classify.py`** — Card classification helpers: `is_land()`, `is_creature()`, `is_ramp()`, `color_sources()`, `classify_cube_category()` (9-category W/U/B/R/G/M/L/F/C classifier for cube draft slot allocation).
- **`companion.py`** — Pure validators for the ten Ikoria companion deckbuilding conditions (CR 702.139a-d). Starting deck includes commanders (CR 702.139b); `deck_minimum=None` = exact-size format. Consumed by `legality_audit.check_companion` and deck-forge's audit warnings.
- **`cube_config.py`** — Cube format presets (9 formats: vintage, unpowered, legacy, modern, pauper, peasant, set, commander, pdh), size-to-drafters table, `PACK_TEMPLATES` defaults, `BALANCE_TARGETS` reference ranges, and curated `REFERENCE_CUBES` starting-point list per format.
- **`bulk_loader.py`** — Shared card-data loader with a pickled sidecar cache (`<bulk>.idx.pkl`), ~5-10× faster on warm load. `_read_source` translates an `AllPrintings.json` through the `_mtgjson` adapter into the Scryfall record shape the rest of the code reads (a legacy Scryfall bulk loads as-is); the sidecar caches the *translated* records. `default_bulk_path()` is MTGJSON-only (the legacy Scryfall bulk fallback was deleted); an explicitly-passed Scryfall-shaped file still loads via the `_read_source` seam.
- **`_mtgjson/`** — MTGJSON → Scryfall-record adapter. `adapter.py` does the per-card translation (legalities, price join, DFC/token/meld handling); `load.py` flattens the set-keyed `AllPrintings` document into the flat list `bulk_loader` caches.
- **`deck.py`** — Deck-shape walks + card-record helpers (`walk_cards`, `discover_tokens`, `split_type_line`, `hydrate`, `slug`, `load_bulk_indexes`), shared by `proxy_print.py` and `art_fetcher.py`.
- **`_fetch_*` and `Fetcher` protocol** — live in `art_fetcher.py`; the seam for HTTP-with-cache. Production uses `HttpFetcher`; tests use `FakeFetcher` in `tests/proxy-printer/_fake_fetcher.py`.
- **`format_config.py`** — `FORMAT_CONFIGS` dict: deck size, copy limit, sideboard size, life total, singleton flag, legality key per format. Ground truth for the "Supported Deck Formats" table below.
- **`theme_presets.py`** — Registry of named matchers for common MTG mechanics (keyword list + oracle-text regex), used by archetype detection in deck-wizard and cube-wizard. Its structural-view `signal_keys` arm can bulk-seed from the persisted signals index (`_deck_forge/signals_index.py`) instead of paying a live per-card compute.
- **`names.py`** — Canonical card-name normalization shared across scripts that cross-reference sources (e.g. `find_commanders`, `mark_owned`). Centralized because drift in Unicode folding silently corrupts ownership intersection.
- **`_sidecar.py`** — Pickled-sidecar primitives reused by `bulk_loader` and `rules_lookup`.
- **`_phase.py`** — Phase-rs subprocess wrapper. Manages the cached phase install at `~/.cache/mtg-skills/phase/` (or `$MTG_SKILLS_CACHE_DIR/phase`), exposes `run_duel` / `run_commander` and the coverage gate. The single `PHASE_TAG` pin (currently `v0.45.0`) governs both the playtest binaries and the Card IR card-data. `ensure_known_tokens` fetches phase's `known-tokens.toml` — the data source for predefined-token ability text phase's own Token effect nodes don't carry — and, unlike `ensure_card_data`, never raises (`None` on any failure; a pure enhancement, never a hard dependency).
- **`_playtest_common.py`** — Schema-v1 JSON envelope and five markdown renderers (`render_goldfish_markdown`, `render_match_markdown`, `render_gauntlet_markdown`, `render_draft_markdown`, `render_custom_format_markdown`).
- **`_gauntlet_build.py`** — Heuristic gauntlet deckbuilder used by `playtest-gauntlet` (over the full cube) and `playtest-draft` (over each player's drafted pool). `score_card` combines theme-match predicates (sourced from the cube's `stated_archetypes`) with a deck-shape prior (`aggro|midrange|control|combo`); `build_gauntlet_deck` greedy-fills curve buckets then adds basics by color demand.
- **`_draft_ai.py`** — Heuristic drafter. `score_pick` picks by raw power before pick 3 and by archetype/color commitment after; `draft_pod` runs an N-player pod.
- **`_custom_format/`** — Per-format multiplayer cube simulators. A shared harness (`_common.py`) provides the library-effect classifier, archetype commitment heuristic, pick decision, simulation loop, and cross-game aggregation; each format is one module implementing `setup()` / `run_turn()` / `is_terminal()`, dispatched via `FORMAT_REGISTRY`.

### deck-wizard

Shares `mtg_utils` via symlink to `mtg-utils/src`. Builds decks from scratch or tunes existing ones across all formats (Commander/Brawl/Historic Brawl and 60-card constructed). Two-phase workflow: Phase 1 acquires a deck (parse existing or build from scratch), Phase 2 runs a 13-step tuning pipeline (Step 13 is optional empirical playtest). See `docs/adr/README.md` for related design decisions.

### cube-wizard

Shares `mtg_utils` via symlink to `mtg-utils/src`. Builds and tunes MTG cubes (curated card pools of 360–720 cards designed for drafting). Two-phase workflow: Phase 1 acquires a cube (parse an existing CubeCobra cube, or clone a well-known reference cube from `cube_config.REFERENCE_CUBES` and customize). Phase 2 runs a 10-step tuning pipeline (baseline metrics → designer intent → balance dashboard → archetype audit → power-level review → self-grill → propose changes → pack simulation → export → optional empirical playtest). Balance checks are informational, not pass/fail, so a mono-color or skewed-by-design cube is never flagged as broken. See `cube-wizard/CONTEXT.md` for its vocabulary and `docs/adr/README.md` for related design decisions.

### rules-lawyer

Shares `mtg_utils` via symlink to `mtg-utils/src`. Answers MTG rules questions by citing the Comprehensive Rules and Scryfall per-card rulings — CR as statute, Scryfall rulings as case law. Usable standalone or invoked by deck-wizard / cube-wizard via the Skill tool. Every answer MUST cite at least one specific CR rule number that came from the CLI output, not from training data. Four phases: classify the question → run one `rules-lookup` CLI call → escalate (wider search, section Read, or subagent) only when the first call misses → write the answer with verdict, CR citations, and edge cases. See `docs/adr/README.md` for related design decisions.

### deck-strat

Shares `mtg_utils` via symlink to `mtg-utils/src`. Produces **Strategy Guides** for finished Commander / Brawl / Historic Brawl decks. Read-only on the deck (no cuts/adds; for tuning, run `/deck-wizard` first). Three-phase pipeline: Phase 1 acquires a deck (parse + hydrate, same as deck-wizard Path A), Phase 2 analyzes (baseline diagnostics, commander interaction audit, archetype detection, combo detection, EDHREC research), Phase 3 authors (rules verification pass via `rules-lookup`, draft, parallel Rules Audit subagent, present + iterate). Output is one markdown file at `<working-dir>/STRATEGY-GUIDE.md` with a fixed core spine plus archetype-conditional sections (politics / voltron / combo execution / aristocrats / token doubling). Re-declares ~16 CLIs from `mtg-utils` and ships none of its own. Integrates with rules-lawyer via a hybrid model: CLI for routine claim verification, Skill-tool invocation for multi-rule timing/layer/stack reasoning. See `deck-strat/CONTEXT.md` for its vocabulary and `docs/adr/README.md` for related design decisions.

### lgs-search

Shares `mtg_utils` via symlink to `mtg-utils/src`. Sources MTG card lists across at most three carts: The Gathering Place + Atomic Empire (LGS) and one of TCGPlayer or Mana Pool (Marketplace), whichever's cheaper for the spillover. Per-Storefront adapters live in `mtg_utils/_stores/`; each implements a synchronous Protocol — `LGSAdapter` for the per-item search/add flow, `MarketplaceAdapter` for the bulk-submit-and-optimize flow, both extending a shared `StoreSession` base for the lifecycle methods. See `lgs-search/CONTEXT.md` for its vocabulary. Persistent Playwright profiles per Storefront under `~/.cache/mtg-skills/lgs-profiles/`.

### proxy-printer

Shares `mtg_utils` via symlink to `mtg-utils/src`. Renders printable PDF proxies from a parsed deck JSON: `proxy-print --kind cards` emits one proxy per copy of every card in the deck; `proxy-print --kind tokens` emits one proxy per distinct token kind the deck produces (deduped by Scryfall `oracle_id`). Both modes share one render template — name banner / ASCII art / type banner / oracle text / P/T — split into `compute_layout()` (pure geometry, canvas-free) and `_emit_proxy()` (drawing only). Two-tier ASCII art: a hand-curated local catalog at `mtg-utils/src/mtg_utils/data/card_art/*.txt` plus an optional attributed catalog at `$MTG_SKILLS_CACHE_DIR/attributed-art/` that propagates an `art by <Name>` credit to the proxy footer. `build_pdf` runs a two-pass differentiation step so same-type cards with different names get distinct art where available. The attributed catalog ships empty; populate it with `fetch-art`. See `proxy-printer/CONTEXT.md` for the catalog / lookup chain / artist credit vocabulary, and `docs/adr/README.md` for related design decisions. Callable standalone or by deck-wizard / cube-wizard at the end of a build session.

### deck-forge

Shares `mtg_utils` via symlink to `mtg-utils/src`. A **collaborative, visual** deckbuilder for the Commander family (commander / brawl / historic_brawl, paper + Arena): an interactive Claude Code **skill** supplies the reasoning; it spawns a local **FastAPI backend** (`mtg_utils.deck_forge_server`, entry `deck-forge`) that hosts the deterministic core + canonical session state and serves a committed **Svelte SPA** (`deck-forge/frontend/dist`). The user builds in the browser; the session reasons. Backend internals live in `mtg_utils/_deck_forge/` (mirrors `_stores/` / `_custom_format/`) — `signals.py` (signal extraction, over `signal_base` / `text_reads` / `membership_floor` primitives), `_ir_lookup.py` (concept-tree + compat-Card resolvers), `lanes/` (the structural signal lanes, one module per family; `lanes/manifest.py` holds `SERVED_SIGNAL_KEYS`), `signal_specs/` (serve/search specs + the key-agreement gate), `budgets.py`, `ranking.py`, `agent_bridge.py` / `events.py` (browser↔session messaging), `persistence.py`, `exporters.py`, `app.py` (the FastAPI factory), `state.py`, and `phase_crosscheck.py` (read-only audit harness, entry `deck-forge-phase-crosscheck`, diffing detector firings against phase-rs's own parse — a second opinion, never ground truth) — see `deck-forge/CONTEXT.md` for what each module owns. **Load-bearing contract: the session-agent never names a card from memory** — it proposes patterns/searches/judgments; the deterministic core (`card_search` + `theme_presets` + Commander Spellbook) names real cards. Billing-safe by being an interactive skill, never Agent-SDK/ACP/`claude -p`. The deterministic core also runs agent-less (search/curve/combos/budgets/finalize) for non-Claude-Code users. See `docs/adr/README.md` for related design decisions.

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

Tests live in `tests/mtg-utils/` (package tests), `tests/deck-wizard/` (deck skill smoke tests), `tests/cube-wizard/` (cube skill smoke tests), `tests/rules-lawyer/` (rules-lawyer skill smoke tests), and `tests/deck-strat/` (deck-strat skill smoke tests), outside the skill directories so they aren't installed. Use `unittest.mock` for HTTP calls. No real network calls in tests.

**Real-card test fixtures.** Signal tests evaluate the SAME Card IR real cards parse into — not a hand-built `_ir(Ability(...))` shape that drifts from production. `mtg_utils.testkit` serves `test_card(name)` (minimal Scryfall record), `test_card_ir(name)` (the compat `Card`, built on demand from the snapshot's stored raw phase face records — the same shape `ir_for` serves in production), and `test_signals(name)` (the production `extract_signals`, with the concept-tree memo pre-seeded from those records) from a committed snapshot at `tests/fixtures/card_snapshot.json` (schema 2) — so real crosswalk trees run in CI with **no** sidecar/bulk/phase/network. The snapshot is usage-derived: `build-card-snapshot` AST-scans the tests for testkit usage — direct literals, `parametrize` columns, literal loop tuples, `_REAL_CASES` name-table values, and any module-local wrapper that forwards a name into the testkit core (derived per module, never hand-listed) — resolves each name to its gameplay printing, stores its minimal Scryfall record plus its raw phase face records (the INPUT, never a baked IR), and self-validates that the minimal record loses no signal vs the full bulk record. It carries the `crosswalk_sidecar_version` and `phase_tag` it was captured at; loading asserts both match, so a schema / compat / phase bump fails loudly until the snapshot is regenerated. The card-data source is MTGJSON: `build-card-snapshot` sources the minimal records from the MTGJSON-backed `bulk_loader`; the stored phase records are phase's own parse either way. The flagship consumer is `tests/deck-forge/test_signal_keys_real_cards.py` (every served key proven against a real card via `_REAL_CASES`, plus a corpus test asserting every emitted key is manifest-served).
