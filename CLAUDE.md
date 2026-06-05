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
uv run download-bulk                 # First-run only; downloads Scryfall bulk data
uv run deck-forge                    # Launch the backend hub + open the browser UI
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

Shared Python package (`mtg_utils`). 34 CLI script modules (20 deck + 9 cube + 3 rules-lawyer + 2 proxy-printer) exposed as 35 entry points — `combo-search` and `combo-discover` both live in `combo_search.py`. `cube-wizard/pyproject.toml` re-declares 12 deck-side CLIs it reuses (card-search, card-summary, combo-search/combo-discover, download-bulk, download-rules, rules-lookup, rulings-lookup, mark-owned, price-check, scryfall-lookup, web-fetch); `rules-lawyer/pyproject.toml` re-declares 5 reused CLIs (card-search, card-summary, download-bulk, scryfall-lookup, web-fetch) alongside its three rules-lawyer-specific entry points; `proxy-printer/pyproject.toml` re-declares parse-deck and download-bulk alongside its `proxy-print` and `fetch-art` entries; `deck-strat/pyproject.toml` re-declares 16 reused entries (parse-deck, set-commander, scryfall-lookup, legality-audit, deck-stats, mana-audit, card-summary, archetype-audit, combo-search/combo-discover, edhrec-lookup, card-search, web-fetch, download-bulk, download-rules, rules-lookup, rulings-lookup) and ships none of its own; the remaining deck-only entry points live in `deck-wizard/pyproject.toml`.

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
- **`playtest.py`** — Six entry points sharing one module:
  - `playtest-goldfish` — Solo deck simulator (mulligan, curve, color-screw,
    combo timing). Pure Python. Mana model counts lands + every cast nonland
    permanent with a non-empty Scryfall `produced_mana` (rocks tap on entry,
    dorks the next turn). Keying off `produced_mana` means it also counts
    mana-token makers (Treasure/Gold/Eldrazi-Spawn generators like Pitiless
    Plunderer, Awakening Zone) — approximated as a rough ~1-mana/turn source
    rather than simulating their creation triggers and one-shot sacrifice. A
    multi-color `produced_mana` ([W,U,B,R,G]) is 1 mana/turn of any color, not
    5; only explicit symbols (Sol Ring's {C}{C}) exceed 1. Token ramp is thus
    captured roughly, not precisely. `playtest-draft` shares this model.
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

**Proxy-printer scripts:**

- **`proxy_print.py`** — Render printable PDF proxies from a parsed deck JSON. One CLI with `--kind cards|tokens`. Cards mode: one proxy per copy of every card in the deck (commanders + cards + sideboard, latter optional). Tokens mode: walks each card's `all_parts`, dedupes by `oracle_id`, renders one proxy per kind with a `from: <source>` footer. Both modes share one render template (name banner / ASCII art / type banner / oracle text / P/T) with body proportions that adapt to oracle text length. Two-tier art lookup: `attributed/<slug>.txt` (user-populated, carries an artist credit) interleaved per-slug with the local `data/card_art/<slug>.txt` catalog (~480 hand-curated files). Lookup walks each subtype slug as `(attributed → local)`, then each card-type slug the same way, then `local/_generic.txt`. Attributed hits propagate the artist's name into a lower-left "art by X" footer on the P/T row, ellipsized to fit.
- **`art_fetcher.py`** — `fetch-art` CLI. Populates the attributed catalog at `$MTG_SKILLS_CACHE_DIR/attributed-art/` from two sources: asciiart.eu (hardcoded curated category list, optional `/search?q=` fallback) and Christopher Johnson's collection at asciiart.website (**tags** auto-discovered from `browse.php?show=tags`, ~1148 of them; each tag.php page carries JSON-LD metadata and inline `<pre data-artwork-id=N>` art bodies that we zip by ID, fetched with a `toolbar_settings` cookie pinning the narrowest-sort so page 1 carries the smallest in-budget pieces). Tags are preferred over categories because they map directly to MTG concepts — a clean "Lion" tag is distinct from "Lion King", "Panther" from "Pink Panther", "Dragon" from "Dragon Ball". `--from-deck deck.json` narrows the fetch to subtypes the deck actually uses (plus the subtypes of every token the deck generates via Scryfall's `all_parts`) — ~30 tag fetches vs ~185 for the full sweep. `--by-name` adds a second pass that tries `asciiart.eu /search?q=<full card name>` for each distinct card name and falls back to per-word `asciiart.website` POSTs (CSRF + form, `sort_order=narrowest`) when the full-name search misses — populates `<name-slug>.txt` files for `proxy_print`'s differentiation pass. Scores candidates by target 20×10 / max 30×18, 7-day on-disk cache, fail-loud on HTTP errors (with linear-backoff retry on 429 / ConnectionError). Each written file's 3-line header points at the per-source attribution terms — `_parse_cards` returns dicts tagged `_source: "eu"` or `"website"` and `write_art` formats the header accordingly; asciiart.website headers note "personal-use proxy" rather than asserting a non-existent license. A `SKIP_SUBTYPES` set deliberately excludes MTG-only mechanics (Saga, Treasure, …) and plane / setting names (Innistrad, Ravnica, …); a `SYNONYMS` map provides per-subtype fallback queries (`ape → gorilla, monkey`); a `_FRANCHISE_SKIP_TAGS` denylist drops broad media franchises (Disney, Star Wars, Anime, …) and specific MTG-keyword-polluting tags (Lion King, Donald Duck, …); a `_FORCE_KEEP_TAGS` allowlist overrides the keyword filter for franchise tags whose content the user wants (Tolkien — user has LOTR MTG cards).

Shared library modules (not CLI scripts):

- **`card_classify.py`** — Card classification helpers: `is_land()`, `is_creature()`, `is_ramp()`, `color_sources()`, `classify_cube_category()` (9-category W/U/B/R/G/M/L/F/C classifier for cube draft slot allocation).
- **`cube_config.py`** — Cube format presets (9 formats: vintage, unpowered, legacy, modern, pauper, peasant, set, commander, pdh), size-to-drafters table, `PACK_TEMPLATES` defaults, `BALANCE_TARGETS` reference ranges, and curated `REFERENCE_CUBES` starting-point list per format.
- **`bulk_loader.py`** — Shared Scryfall bulk-data loader with a pickled sidecar cache (`<bulk>.idx.pkl`). ~5-10× faster on warm load; atomic-rename write so concurrent callers can't see a partial sidecar. Every script that touches Scryfall data goes through this. Also exposes `default_bulk_path()` (the cache-dir-aware path resolver) for CLIs that need to autodiscover the bulk file.
- **`deck.py`** — Deck-shape walks + card-record helpers: `walk_cards`, `discover_tokens`, `split_type_line`, `hydrate`, `slug`, `load_bulk_indexes`, plus the `CARD_TYPE_WORDS` constant. Extracted from `proxy_print.py` so other consumers (`art_fetcher.subtypes_in_deck`, eventual deck-wizard / cube-wizard inline walks) can `from mtg_utils.deck import …` without reaching into the renderer's privates.
- **`_fetch_*` and `Fetcher` protocol** — live in `art_fetcher.py`. `Fetcher` is the seam for HTTP-with-cache (`fetch(url, cache_key, *, throttle, max_retries)` + `fetch_uncached` + `post_form`). Production uses `HttpFetcher` (wraps a private `requests.Session`); tests use `FakeFetcher` in `tests/proxy-printer/_fake_fetcher.py`. Single-module scope today; lift to `mtg_utils/_fetcher.py` if another skill needs HTTP with the same caching/retry/throttle shape.
- **`format_config.py`** — `FORMAT_CONFIGS` dict: deck size, copy limit, sideboard size, life total, singleton flag, legality key per format. Ground truth for the "Supported Deck Formats" table below.
- **`theme_presets.py`** — Registry of named matchers for common MTG mechanics (keyword list + oracle-text regex). Each preset ships with `should_match` / `should_not_match` fixtures pinned in `tests/mtg-utils/test_theme_presets.py`. Used by archetype detection in deck-wizard and cube-wizard.
- **`names.py`** — Canonical card-name normalization shared across scripts that cross-reference sources (e.g. `find_commanders`, `mark_owned`). Centralized because drift in Unicode folding silently corrupts ownership intersection.
- **`_sidecar.py`** — Pickled-sidecar primitives reused by `bulk_loader` and `rules_lookup`.
- **`_phase.py`** — Phase-rs subprocess wrapper. Manages the cached phase
  install at `~/.cache/mtg-skills/phase/` (or `$MTG_SKILLS_CACHE_DIR/phase`),
  exposes `run_duel` / `run_commander` and the coverage gate. Pinned to
  phase tag `v0.1.19`; bump with care.
- **`_playtest_common.py`** — Schema-v1 JSON envelope and five markdown
  renderers (`render_goldfish_markdown`, `render_match_markdown`,
  `render_gauntlet_markdown`, `render_draft_markdown`,
  `render_custom_format_markdown`).
- **`_gauntlet_build.py`** — Heuristic gauntlet deckbuilder (used by
  `playtest-gauntlet` over the full cube and by `playtest-draft` over
  each player's drafted pool). `score_card(card, *, colors, matchers,
  shape)` combines two optional scoring layers: theme-match predicates
  (each match adds +3.0; sourced from the cube's `stated_archetypes`
  via `_archetype_resolver.matcher_for`) and a canonical deck-shape
  prior (`aggro|midrange|control|combo`, hardcoded). `build_gauntlet_deck(
  pool, spec)` greedy-fills curve buckets, then adds basics by color
  demand. `infer_archetype_colors` and `infer_curve_target` derive the
  build spec from the cube's actual card pool when stated_archetypes is
  the source of truth.
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

Shares `mtg_utils` via symlink to `mtg-utils/src`. Builds decks from scratch or tunes existing ones across all formats (Commander/Brawl/Historic Brawl and 60-card constructed). Two-phase workflow: Phase 1 acquires a deck (parse existing or build from scratch), Phase 2 runs a 13-step tuning pipeline (Step 13 is optional empirical playtest).

### cube-wizard

Shares `mtg_utils` via symlink to `mtg-utils/src`. Builds and tunes MTG cubes (curated card pools of 360–720 cards designed for drafting). Two-phase workflow: Phase 1 acquires a cube (Path A: parse an existing CubeCobra cube; Path B: clone a well-known reference cube from `cube_config.REFERENCE_CUBES` and customize). Phase 2 runs a 10-step tuning pipeline (baseline metrics → designer intent → balance dashboard → archetype audit → power-level review → self-grill → propose changes → pack simulation → export → optional empirical playtest). Balance checks are informational, not pass/fail, so a mono-color or skewed-by-design cube is never flagged as broken.

### rules-lawyer

Shares `mtg_utils` via symlink to `mtg-utils/src`. Answers MTG rules questions by citing the actual Comprehensive Rules and Scryfall per-card rulings — the project's "legal database": CR = statute, Scryfall rulings = case law. Usable standalone or invoked by deck-wizard / cube-wizard via the Skill tool for trigger-interaction, timing, replacement-effect, and layer questions during tuning. The skill's Iron Rule: every answer MUST cite at least one specific CR rule number that came from the CLI output, not from training data. Four phases: classify the question → run one `rules-lookup` CLI call → escalate (wider search, section Read, or subagent) only when the first call misses → write the answer with verdict, CR citations, and edge cases.

### deck-strat

Shares `mtg_utils` via symlink to `mtg-utils/src`. Produces **Strategy Guides** for finished Commander / Brawl / Historic Brawl decks. Read-only on the deck (no cuts/adds; for tuning, run `/deck-wizard` first). Three-phase pipeline: Phase 1 acquires a deck (parse + hydrate, same as deck-wizard Path A), Phase 2 analyzes (baseline diagnostics, commander interaction audit, archetype detection, combo detection, EDHREC research), Phase 3 authors (rules verification pass via `rules-lookup`, draft, parallel Rules Audit subagent, present + iterate). Output is one markdown file at `<working-dir>/STRATEGY-GUIDE.md` with a fixed core spine of sections plus archetype-conditional sections (politics / voltron / combo execution / aristocrats / token doubling) rendered based on signals from `archetype-audit` and commander oracle patterns. Re-declares ~16 CLIs from `mtg-utils` and ships none of its own (see ADR-0004). Hybrid rules-lawyer integration (see ADR-0008): CLI for routine claim verification, Skill-tool invocation for multi-rule timing/layer/stack reasoning. See `deck-strat/CONTEXT.md` for the Strategy Guide / core spine / conditional section / role grouping / Rules Audit vocabulary.

### lgs-search

Shares `mtg_utils` via symlink to `mtg-utils/src`. Sources MTG card lists across at most three carts: The Gathering Place + Atomic Empire (LGS) and one of TCGPlayer or Mana Pool (Marketplace), whichever's cheaper for the spillover. Per-Storefront adapters live in `mtg_utils/_stores/` (mirrors `_custom_format/`); each implements a synchronous Protocol — `LGSAdapter` for the per-item search/add flow, `MarketplaceAdapter` for the bulk-submit-and-optimize flow, both extending a shared `StoreSession` base for the lifecycle methods (auth, cart inspection, clear, handoff). See `lgs-search/CONTEXT.md` for the LGS / Marketplace / StoreSession domain language. Persistent Playwright profiles per Storefront under `~/.cache/mtg-skills/lgs-profiles/`.

### proxy-printer

Shares `mtg_utils` via symlink to `mtg-utils/src`. Renders printable PDF proxies from a parsed deck JSON: `proxy-print --kind cards` emits one proxy per copy of every card in the deck; `proxy-print --kind tokens` emits one proxy per distinct token kind the deck produces (deduped by Scryfall `oracle_id`). Both modes share one render template — name banner / ASCII art / type banner / oracle text / P/T. **Non-token cards pin the type-banner bottom at `y + CARD_H/3`** (matches real MTG layout); tokens keep dynamic positioning. The render path splits into `compute_layout(card, ..., measure_width) -> ProxyLayout` (pure geometry + fitting, canvas-free) and `_emit_proxy(canvas, layout)` (drawing only) — see `tests/proxy-printer/test_compute_layout.py` for unit-level layout assertions without booting reportlab. Two-tier ASCII art: a hand-curated **local catalog** at `mtg-utils/src/mtg_utils/data/card_art/*.txt` (one file per card subtype with card-type and ultimate-generic fallbacks) plus an optional **attributed catalog** at `$MTG_SKILLS_CACHE_DIR/attributed-art/` whose files carry a license header and propagate an `art by <Name>` credit to the proxy footer. Lookup is per-slug interleaved (`attributed/<sub>` → `local/<sub>` → next slug), then card-type, then `local/_generic.txt`. Token proxies render the artist credit in the footer slot — the legacy `from: <source>` line is no longer drawn. `build_pdf` runs a **two-pass differentiation step**: pass 1 resolves type-keyed art for every card; pass 2 groups by `(tier, key)` and for any group containing multiple distinct card names retries each via `lookup_art_by_name(name)`, swapping to a name-keyed file when one exists (same-name cards keep shared art for table-scanning). The attributed catalog ships empty; populate it with `fetch-art`, which mines asciiart.eu + asciiart.website for one candidate per Scryfall subtype; pass `--by-name` to also populate `<name-slug>.txt` files for the differentiation pass. Art is P/T-independent — every Soldier shares `soldier.txt`. See `proxy-printer/CONTEXT.md` for the catalog / lookup chain / signature / artist credit / differentiation-pass vocabulary, and `docs/adr/0006-attributed-art-catalog.md` for the ship-empty + per-slug interleaving rationale. The skill is callable standalone or by deck-wizard / cube-wizard at the end of a build session; `parse-deck` runs upstream to produce the deck JSON.

### deck-forge

Shares `mtg_utils` via symlink to `mtg-utils/src`. A **collaborative, visual** deckbuilder for the Commander family (commander / brawl / historic_brawl, paper + Arena): a Claude Code **skill** run in a normal **interactive** session is the reasoning brain; it spawns a local **FastAPI backend** (`mtg_utils.deck_forge_server`, entry `deck-forge`) that hosts the deterministic core + canonical session state and serves a committed **Svelte SPA** (`deck-forge/frontend/dist`). Two surfaces (D13): the user builds in the browser, the session reasons. Backend internals live in `mtg_utils/_deck_forge/` (mirrors `_stores/` / `_custom_format/`): `signals.py` (scoped signal extraction — the Tinybones guard), `signal_specs.py` (signal → serve/search specs, scope-discriminating), `budgets.py` (slot budgets vs the soft Command Zone template), `ranking.py` (transparent multi-axis scoring — synergy/curve/price, never EDHREC popularity), `agent_bridge.py` (browser↔session long-poll queue), `events.py` (SSE hub), `persistence.py` (autosave + build library), `exporters.py`, `app.py` (the FastAPI factory `build_app(state)`), `production.py` (`default_state()` — real bulk or graceful no-bulk), and `state.py` (`DeckSession` + the injectable `ForgeState`). **Load-bearing contract (ADR-0009): the session-agent never names a card from memory — it proposes patterns/searches/judgments; the deterministic core (`card_search` + `theme_presets` + Commander Spellbook) names real cards.** Billing-safe by being an interactive skill, never Agent-SDK/ACP/`claude -p` (ADR-0010). Autosave/resume departs from ADR-0003 (ADR-0011). See `deck-forge/CONTEXT.md` for vocabulary (signal / synergy package / avenue / candidate / slot budget / curve gate / no-listing card). The deterministic core also runs agent-less (search/curve/combos/budgets/finalize) for non-Claude-Code users.

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
