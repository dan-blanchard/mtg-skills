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
uvx ty check src/                    # Type check (CI runs it; unpinned by design, see ci.yml)
uv run download-mtgjson              # Card-data source: MTGJSON AllPrintings + AllPricesToday (ADR-0033; ~609MB; first-run only)
uv run build-card-snapshot           # Regen the committed test card snapshot (gated; needs local MTGJSON bulk + phase card-data — auto-fetched via the phase release-server manifest, no cargo; NEVER CI)
uv run bump-phase-pin <tag>          # The scripted phase-rs pin bump (ADR-0049): edits PHASE_TAG + the generated Effect rosters, regenerates substrate / fixtures / snapshot / sidecar / signals index, writes one triage report (work it with docs/phase-pin-bump.md); --from-step N resumes; NEVER CI
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

## Working conventions

- **Ground rules claims in the rules, not memory: use the rules-lawyer skill.** Any rules-boundary decision (is X ramp, a blink, an edict, a sacrifice outlet?), any claim about how a specific card behaves, and any CR number written into code, comments, tests, ADRs or commit messages goes through `/rules-lawyer` or its CLIs first. The skill checks both sources: the Comprehensive Rules (statute) and the per-card rulings MTGJSON ships (case law).
  - For a claim about a named card, run `rulings-lookup --card "<name>"` first, then resolve any CR numbers its rulings cite with `rules-lookup --rule <n>`.
  - For a bare rule number, `rules-lookup --rule <n>` (or `--grep`) is enough; batch the lookups.
  - For interactions, layers or timing, invoke the skill itself, which escalates past a single lookup.

  Cite what the CLI returned, and check your *description* of what a rule or keyword does against its text, not just the number. Write from the defining subrule (`rules-lookup --rule 702.NNa`). An ability word has no rules text of its own (CR 207.2c), so describe it from what its cards share. When the rule text doesn't support the claim, call it the lane's own decision instead of borrowing a rule number. Numbers recalled from memory are often wrong. Tell parallel agents the same, and spot-check their citations.
- **Review before committing.** For a change built by several parallel agents, or one touching many signal lanes, run `/simplify` over the combined diff, then `/code-review` against the uncommitted tree, fix, and only then commit. A review after the commit means an amend and a second pass.
- **Run CI's checks the way CI sees the machine before pushing.** CI has no card data. Your local MTGJSON bulk and phase cache hide failures that only appear without them, such as a test that silently reads the bulk or a memo that only fills correctly when phase data exists. Run every step in `.github/workflows/ci.yml` (ruff, `uvx ty check src/`, all eight pytest suites, the frontend checks), with the test suites under `HOME=<empty dir> MTG_SKILLS_CACHE_DIR=<empty dir>`. Keep `UV_CACHE_DIR` pointing at the real uv cache so `uv` still works.
- **Extend the shared walks; don't clone them.** A read over phase's Card IR first checks `_card_ir/crosswalk/` (`reads.py`, `core.py`) for an existing walk and parameterises it, rather than writing a lane-local copy. When briefing parallel agents, say so explicitly: each one can't see the helpers the others are writing.
- **Check the backlog before proposing work.** `docs/plans/backlog.md` lists open follow-ups and the verdicts past reviews already reached ("don't re-suggest"). Add what you find but don't finish; delete an entry when it ships.
- **Every phase-misparse workaround can retire itself.** It is either a bridge-ledger row (ADR-0048) or code guarded by a `retirement_canary`-marked test that fails once phase fixes the parse. `bump-phase-pin`'s graduation step runs both.

## Architecture

Mono-repo for MTG-related Claude Code skills. Each skill lives in its own directory matching the `name` field in its SKILL.md frontmatter.

**Source layout.** The canonical source lives in `mtg-utils/src/mtg_utils/`. `deck-wizard/src`, `cube-wizard/src`, `rules-lawyer/src`, `deck-strat/src`, `lgs-search/src`, and `proxy-printer/src` are **symlinks** to that directory. Editing a file through any skill's `src/` edits the shared source — there is exactly one copy. Each skill's `pyproject.toml` re-declares only the CLI entry points it ships; the Python package is installed once per skill `.venv` but all six point at the same files.

### mtg-utils

Shared Python package (`mtg_utils`). 40 CLI script modules (26 deck + 9 cube + 3 rules-lawyer + 2 proxy-printer) exposed as 47 entry points — `playtest.py` holds six, `combo-search` and `combo-discover` both live in `combo_search.py`, and `set-scan` and `pool-colors` both live in `set_scan.py`. Beside them `mtg-utils/pyproject.toml` declares `download-mtgjson` (the card-data source, declared in every skill's `pyproject.toml`) and the five repo build tools (`build-card-snapshot`, `bump-phase-pin`, the substrate / crosswalk / signals-index builders). The deck CLIs `deck-signals`, `slot-budgets`, and `deck-rank` are thin wrappers over the deterministic `_analysis` signal / budget / ranking core (ADR-0050); `deck-tune` is the holistic **spine** over that core (`_tuner.tune`) — one call returns the scorecard + candidate swaps, the same engine deck-forge runs at `POST /api/tune`, and the deterministic basis for deck-wizard's Step-6 tuning (every format family; the template and floors are the family's — ADR-0054). deck-wizard's analysis pipeline reuses these instead of guessing. Each other skill's `pyproject.toml` re-declares, beside its own entry points, only the ones it reuses (cube-wizard 18, rules-lawyer 4, proxy-printer 1, deck-strat 19); the remaining deck-only entry points live in `deck-wizard/pyproject.toml`.

**Deck scripts:**

- **`parse_deck.py`** — Multi-format deck list parser with sideboard support. Strips Moxfield set code suffixes from names but retains them as optional entry keys (`set`, `collector_number`, `finish`). Routes Arena/MTGO/Moxfield `Companion` sections into a top-level `companion` zone excluded from `total_cards` (CR 702.139a-b: a companion is neither deck nor sideboard). For a pool-bounded format (`--format sealed` / `draft`, ADR-0055) fills the `pool` zone with every card the list holds across Deck + Sideboard; `--pool-only` (or a bare list) is all pool, no deck yet.
- **`deck_hydrate.py`** — `deck-hydrate <deck.json>`: the explicit warm step over the deck-acquisition seam (ADR-0046). Builds or validates `<deck>.hydrated.json` beside the deck (full adapter records for every zone, companion included; keyed inside the file by deck content + bulk identity + payload version, so a stale sidecar is unreadable by construction; the one carve-out is a names-only CLI with no bulk on disk, which reads a same-deck sidecar whatever bulk wrote it) and prints the envelope — sidecar path, card count, missing names, type/curve digest.
- **`scryfall_lookup.py`** — Card lookup against the card pool with Scryfall's per-card endpoint as the cache-miss fallback (`fetch_card`). `scryfall-lookup "<name>"` prints a terminal projection (`display_fields`); `scryfall-lookup --batch <names.json>` hydrates a name list (candidate verification) into a SHA-keyed cache file.
- **`edhrec_lookup.py`** — EDHREC JSON endpoint client for commander recommendations.
- **`download_mtgjson.py`** — Card-data downloader (ADR-0033): MTGJSON `AllPrintings` + `AllPricesToday` (gzip stream-decompressed) to `~/.cache/mtg-skills/mtgjson/`, 24h freshness, eager translated-sidecar build. The card-data source of record.
- **`web_fetch.py`** — Web page fetcher with browser headers and curl fallback.
- **`deck_stats.py`** — Deck statistics: land/ramp/creature counts, avg CMC, curve, color sources, total card count. The ramp count is `_analysis.roles.is_ramp` (ADR-0051: the signal path, with an oracle-text degrade when no card-data is available) — the same read `mana-audit`, `slot-budgets` and the tuner use.
- **`card_summary.py`** — Compact human-readable card table with filter flags (`--lands-only`, `--nonlands-only`, `--type`).
- **`deck_diff.py`** — Deck comparison: added/removed cards, count/CMC/land/ramp deltas.
- **`set_commander.py`** — Move cards from cards list to commanders list in parsed deck JSON.
- **`mana_audit.py`** — Mana base health audit: ONE `land_band` readout per deck (`floor` gate / `top` target / `flood` line / `status` PASS·WARN·FAIL·FLOOD; Burgess/Karsten for the Commander family, the constructed formula for 60-card — ADR-0041, finished), color balance (pip demand vs. land production), comparison mode. Every land-count surface (budgets row, finalize gate, SPA pill, tuner) reads the band; none re-derives it. The Burgess term is the **effective commander cost** from `commander_cost.py` (ADR-0044): for a self-discounting commander it is the earliest turn the deck expects to afford it (closed-form, from the commander's phase-IR operand and the deck's own cards); otherwise the printed mana value, with the degrade reason reported in the `commander_cost` block.
- **`commander_cost.py`** — The ADR-0044 estimator: reads a commander's own `ModifyCost{Reduce}`/`SelfRef` operand from the Card IR (battlefield-population shapes only), matches the deck's hydrated records against the population filter, and returns the affordable turn plus a per-turn table. Every other shape degrades to printed mana value with a status.
- **`cut_check.py`** — Mechanical pre-grill: trigger detection and multiplied values, keyword interaction detection, self-recurring card detection, commander copy/ability multiplication detection.
- **`build_deck.py`** — Apply cuts/adds (mainboard and sideboard) to a deck, writing `new-deck.json` and its `new-deck.hydrated.json` sidecar (ADR-0046; no separate hydrated-output flag).
- **`deck_signals.py`** / **`slot_budgets.py`** / **`deck_rank.py`** — `deck-signals` (the deck's signal lanes via `_analysis.signals`), `slot-budgets` (role-density bands vs the deck family's template via `_analysis.budgets` — the Command Zone rows for Commander, interaction / card draw / an advisory creature count for 60-card), and `deck-rank` (rank candidate records by synergy, then price, then curve via `_analysis.ranking`, never EDHREC popularity). All deterministic; reused by deck-wizard.
- **`price_check.py`** — Price validation against budget using Scryfall bulk data with API fallback. Every slot charges the copies `Format.copies_short` leaves short (ADR-0058). The medium picks the cost mode (ADR-0052): `--medium digital|paper`, else the deck JSON's `medium`, else the format's default — Arena wildcards for digital, USD for paper; Standard and Pioneer default to paper.
- **`combo_search.py`** — Commander Spellbook API wrapper: `combo-search` for deck combo detection and near-miss identification; `combo-discover` for discovering combos by outcome, card name, or color identity.
- **`export_deck.py`** — Export parsed deck JSON to import text (`N CardName` lines) with sideboard and companion sections. `--style auto|moxfield|arena` (default `auto`): Arena formats (per `FORMATS[fmt].is_arena`) get Arena's `Commander` / `Companion` / `Deck` / `Sideboard` section headers, which Arena's importer needs to zone the commander and Moxfield also reads; paper formats get bare Moxfield lines.
- **`card_search.py`** — Search Scryfall bulk data with filters: color identity, oracle text regex, type, CMC range, price range, `--set` (one set's printings). `filter_records` is the ONE filter implementation over an explicit record list (`search_cards` runs it after its bulk scan; a pool-bounded deck-forge build runs it over its opened pool). Compact table or JSON output. Applies a **commander-legality filter by default** (not only under `--format`), so cards from spoiled-but-unreleased sets — which MTGJSON marks `not_legal` in every format until release day — are hidden (their reprints stay visible, since `_mtgjson/adapter.py` takes the most permissive legality across printings, so a half-visible new set is not a corrupt download; after downloading a just-spoiled set, check its `releaseDate` and say the new cards appear once a `download-mtgjson` runs after that date, rather than loosening the filter); `--include-unreleased` admits exactly those (via `unreleased_oracle_ids`, which requires EVERY printing to be future-dated, so an always-illegal card reprinted into a future set stays out). Banned/restricted and never-legal cards are unaffected.
- **`legality_audit.py`** — Format legality, copy limits (`card_copy_limit` is the one exemption ladder the hub reads too), sideboard size, Vintage restricted-list, pool containment for a limited deck (`check_pool_containment`, CR 100.2b), and companion audit via `mtg_utils.companion`, wired into `--cite-rules`.
- **`set_scan.py`** — The two limited readouts (ADR-0055), pure and agent-free: `set-scan --set CODE` (what a set holds — removal by rarity, sweepers, evasion, the biggest bodies, the curve; over `CardPool.set_records`) and `pool-colors <deck.json>` (every mono colour and colour pair an opened pool supports on equal footing). Roles via `_analysis.roles`; evasion via `card_classify.EVASION_KEYWORDS`.
- **`find_commanders.py`** — Search owned collection for commander-eligible cards.
- **`mark_owned.py`** — Populate a deck's `owned_cards` field from a collection CSV/JSON (with each row's per-printing detail); its "N of M owned" summary counts cards `Format.coverage` covers in the deck's medium (ADR-0058).
- **`mtga_import.py`** — Extract Arena collection and wildcard counts from `Player.log`. Name-level totals stay playset-capped; per-printing quantities are retained uncapped (Player.log carries no foil info). Its `collection.json` carries `"source": "mtga-import"`; it refuses to overwrite a `collection.json` without that marker (a `parse-deck` collection from an Untapped CSV, the more reliable source) unless `--force`. Basic lands aren't recorded: the ownership rule already counts them as owned.
- **`playtest.py`** — Six entry points sharing one module. `playtest-goldfish` (and `playtest-draft`, which shares its model) is a pure-Python solo deck simulator (mulligan, curve, color-screw, combo timing); its mana model counts lands plus every cast nonland permanent with a non-empty Scryfall `produced_mana`, approximating token-mana generators as a rough ~1-mana/turn source. It ALSO resolves land-search effects via `card_classify.land_fetch_profile` — fetch lands (Evolving Wilds, Hobbit Hole) produce the colors of the deck's own basics rather than nothing, and an *enters*-triggered fetcher (Wood Elves) moves a land from library to battlefield; both respect an `enters tapped` clause. Fetches behind an activation cost (Knight of the Reliquary's `{T}, Sacrifice`) are deliberately NOT credited, since the cost isn't modeled. `playtest-match` runs a phase-rs `ai-duel` batch. `playtest-gauntlet` builds N archetype decks from a cube and round-robins them via phase for a win-rate matrix. `playtest-draft` runs a heuristic 8-player draft plus per-deck goldfish. `playtest-install-phase` does a one-time `cargo build` of the phase binaries at the `_phase.PHASE_TAG` pin (currently v0.94.0, governing both the playtest binaries and the Card IR card-data) — only playtesting needs this; the Card IR build path instead fetches phase's `card-data.json` via a sha256-verified release manifest, so non-playtest users never pay the Rust compile. `playtest-custom-format` runs a multiplayer custom-format simulator with one module per format under `_custom_format/`.

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

- **`card_classify.py`** — Card classification helpers: `is_land()`, `is_creature()`, `color_sources()`, `ramp_by_text()` (the no-coverage text degrade ONLY — `_analysis.roles.is_ramp` owns the ramp answer, ADR-0051), `classify_cube_category()` (9-category W/U/B/R/G/M/L/F/C classifier for cube draft slot allocation).
- **`companion.py`** — Pure validators for the ten Ikoria companion deckbuilding conditions (CR 702.139a-d). Starting deck includes commanders (CR 702.139b); `deck_minimum=None` = exact-size format. Consumed by `legality_audit.check_companion` and deck-forge's audit warnings.
- **`cube_config.py`** — Cube format presets (9 formats: vintage, unpowered, legacy, modern, pauper, peasant, set, commander, pdh), size-to-drafters table, `PACK_TEMPLATES` defaults, `BALANCE_TARGETS` reference ranges, and curated `REFERENCE_CUBES` starting-point list per format.
- **`bulk_loader.py`** — Shared card-data loader with a pickled sidecar cache (`<bulk>.idx.pkl`), ~5-10× faster on warm load. `_read_source` translates an `AllPrintings.json` through the `_mtgjson` adapter into the Scryfall record shape the rest of the code reads (a legacy Scryfall bulk loads as-is); the sidecar caches the *translated* records. `default_bulk_path()` is MTGJSON-only (the legacy Scryfall bulk fallback was deleted); an explicitly-passed Scryfall-shaped file still loads via the `_read_source` seam.
- **`_mtgjson/`** — MTGJSON → Scryfall-record adapter. `adapter.py` does the per-card translation (legalities, price join, DFC/token/meld handling); `load.py` flattens the set-keyed `AllPrintings` document into the flat list `bulk_loader` caches.
- **`deck.py`** — Deck-shape walks + card-record helpers (`walk_cards`, `discover_tokens`, `split_type_line`, `hydrate`, `slug`, `load_bulk_indexes`), shared by `proxy_print.py` and `art_fetcher.py`.
- **`Fetcher` protocol** — lives in `_http.py` beside `HttpFetcher`, consumed by `art_fetcher.py`; the seam for HTTP-with-cache. Production uses `HttpFetcher`; tests use `FakeFetcher` in `tests/proxy-printer/_fake_fetcher.py`.
- **`arena_card_db.py`** — The local MTG Arena card database (ADR-0057): finds `Raw_CardDatabase_*.mtga` (`$MTG_SKILLS_ARENA_CARD_DB` path or `none`, then the download folder `Player.log` records, then standard installs) and reads each card's lowest rarity among its primary (craftable) printings. `CardPool.rarity_index(arena_only=True)` uses it for the exact wildcard cost, with MTGJSON as the fallback. `tests/conftest.py` sets the variable to `none`, so an installed Arena never changes a test.
- **`card_pool.py`** — The card pool (ADR-0046): `CardPool.load(bulk_path)` (`None` auto-discovers the MTGJSON bulk; `NoBulkError` names `download-mtgjson`) owns every index over the bulk — `by_name` (ONE policy: cheapest priced game-layout printing, text-bearing preferred, tokens never), `by_id` (every printing, tokens included), `rarity_index(fmt)`, `unreleased_ids`, `name_aliases`, `printings_by_oracle` / `printing_by_id`, `resolve_object`. Lazily built, memoized per process. Every deck-domain bulk reader (hydration, price-check, find-commanders, mark-owned, proxy-print, the hub) reads through it.
- **`deck_cli.py`** — The deck CLIs' shared acquisition adapter (ADR-0046): the `--bulk-data` option and `acquire_for_cli(deck_path, bulk_data)`, which calls `HydratedDeck.acquire`, turns a missing bulk into an actionable exit, and warns once about names the join dropped.
- **`formats.py`** — The format module (ADR-0045): one frozen `Format` value per format (`FORMATS[name]`, `get_format`, `Format.for_deck(deck_json)`) that owns legality (`legality` / `is_legal` / `commander_eligibility`, with the Competitive Brawl override and the Arena-pool gate folded in), medium (`media` / `resolve_medium` / `cost_mode` / `paper_only` — what a medium means for currency and candidate pool; the tuner and the hub's Find ask, no caller derives it, ADR-0052), ownership (`coverage` / `copies_short` — how far a collection covers a deck entry in a medium, ADR-0058: basic lands are free in every medium — on Arena always, in paper unless the entry asks for a special printing (`is_special_basic_request`: foil / etched, full-art, borderless, a showcase or other special frame, a promo, a visual promo type), which only that exact printing covers; Snow-Covered basics are ordinary cards; on Arena four owned copies cover any quantity; otherwise you have what you own. Every wildcard cost, shortfall, owned flag and "owned = free" read asks it), size (`size_choices` / `resolve_deck_size` / `size_rule`), and the SPA table (`format_options`). `HydratedDeck.format` returns it. Ground truth for the "Supported Deck Formats" table below; no caller re-derives a format fact from the table.
- **`theme_presets.py`** — Registry of named matchers for common MTG mechanics (keyword list + oracle-text regex), used by archetype detection in deck-wizard and cube-wizard. Its structural-view `signal_keys` arm can bulk-seed from the persisted signals index (`_analysis/signals_index.py`) instead of paying a live per-card compute.
- **`ownership.py`** — Printing-level ownership, shared by the CLIs and the hub (ADR-0058): a collection pile's per-printing detail (`printing_index` / `printing_rows`, the shape `mark-owned` writes and `price-check` reads), a deck entry's printing request (`printing_request`), and `requested_printing_owned` — the copies of a special basic printing a collection holds, the input to `Format.coverage`.
- **`names.py`** — Canonical card-name normalization shared across scripts that cross-reference sources (e.g. `find_commanders`, `mark_owned`). Centralized because drift in Unicode folding silently corrupts ownership intersection.
- **`_sidecar.py`** — Pickled-sidecar primitives reused by `bulk_loader` and `rules_lookup`.
- **`_phase.py`** — Phase-rs subprocess wrapper. Manages the cached phase install at `~/.cache/mtg-skills/phase/` (or `$MTG_SKILLS_CACHE_DIR/phase`), exposes `run_duel` / `run_commander` and the coverage gate. The single `PHASE_TAG` pin (currently `v0.94.0`) governs both the playtest binaries and the Card IR card-data. `ensure_known_tokens` fetches phase's `known-tokens.toml` — the data source for predefined-token ability text phase's own Token effect nodes don't carry — and, unlike `ensure_card_data`, never raises (`None` on any failure; a pure enhancement, never a hard dependency).
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

Shares `mtg_utils` via symlink to `mtg-utils/src`. Produces **Strategy Guides** for finished Commander / Brawl / Historic Brawl decks. Read-only on the deck (no cuts/adds; for tuning, run `/deck-wizard` first). Three-phase pipeline: Phase 1 acquires a deck (parse + hydrate, same as deck-wizard Path A), Phase 2 analyzes (baseline diagnostics, commander interaction audit, archetype detection, combo detection, EDHREC research), Phase 3 authors (rules verification pass via `rules-lookup`, draft, parallel Rules Audit subagent, present + iterate). Output is one markdown file at `<working-dir>/STRATEGY-GUIDE.md` with a fixed core spine plus archetype-conditional sections (politics / voltron / combo execution / aristocrats / token doubling). Re-declares 19 CLIs from `mtg-utils` and ships none of its own. Integrates with rules-lawyer via a hybrid model: CLI for routine claim verification, Skill-tool invocation for multi-rule timing/layer/stack reasoning. See `deck-strat/CONTEXT.md` for its vocabulary and `docs/adr/README.md` for related design decisions.

### lgs-search

Shares `mtg_utils` via symlink to `mtg-utils/src`. Sources MTG card lists across at most three carts: The Gathering Place + Atomic Empire (LGS) and one of TCGPlayer or Mana Pool (Marketplace), whichever's cheaper for the spillover. Per-Storefront adapters live in `mtg_utils/_stores/`; each implements a synchronous Protocol — `LGSAdapter` for the per-item search/add flow, `MarketplaceAdapter` for the bulk-submit-and-optimize flow, both extending a shared `StoreSession` base for the lifecycle methods. See `lgs-search/CONTEXT.md` for its vocabulary. Persistent Playwright profiles per Storefront under `~/.cache/mtg-skills/lgs-profiles/`.

### proxy-printer

Shares `mtg_utils` via symlink to `mtg-utils/src`. Renders printable PDF proxies from a parsed deck JSON: `proxy-print --kind cards` emits one proxy per copy of every card in the deck; `proxy-print --kind tokens` emits one proxy per distinct token kind the deck produces (deduped by Scryfall `oracle_id`). Both modes share one render template — name banner / ASCII art / type banner / oracle text / P/T — split into `compute_layout()` (pure geometry, canvas-free) and `_emit_proxy()` (drawing only). Two-tier ASCII art: a hand-curated local catalog at `mtg-utils/src/mtg_utils/data/card_art/*.txt` plus an optional attributed catalog at `$MTG_SKILLS_CACHE_DIR/attributed-art/` that propagates an `art by <Name>` credit to the proxy footer. `build_pdf` runs a two-pass differentiation step so same-type cards with different names get distinct art where available. The attributed catalog ships empty; populate it with `fetch-art`. See `proxy-printer/CONTEXT.md` for the catalog / lookup chain / artist credit vocabulary, and `docs/adr/README.md` for related design decisions. Callable standalone or by deck-wizard / cube-wizard at the end of a build session.

### deck-forge

Shares `mtg_utils` via symlink to `mtg-utils/src`. A **collaborative, visual** deckbuilder for every format family — the Commander family (commander / brawl / historic_brawl / competitive_brawl), 60-card constructed, and limited (sealed / draft from an opened pool: the pool zone, a derived sideboard, pool-scoped Find and Tune, the Pool panel — ADR-0055), paper + Arena (ADR-0054: every family decision keys off a served `Format` fact; the Commander-only surfaces are gated by `has_commander`): an interactive Claude Code **skill** supplies the reasoning; it spawns a local **FastAPI backend** (`mtg_utils.deck_forge_server`, entry `deck-forge`) that hosts the deterministic core + canonical session state and serves a committed **Svelte SPA** (`deck-forge/frontend/dist`). The user builds in the browser; the session reasons. The hub lives in `mtg_utils/_deck_forge/` (ADR-0050: the hub ONLY — `app.py` the FastAPI factory, `engine.py`, `discovery.py` (Commander discovery + its locked cache, ADR-0053), `views.py`, `state.py`, `production.py`, `persistence.py`, `collection.py`, `agent_bridge.py` / `events.py` (browser↔session messaging), `images.py`, and `phase_crosscheck.py` (read-only audit harness, entry `deck-forge-phase-crosscheck`, diffing detector firings against phase-rs's own parse — a second opinion, never ground truth)); the deck-analysis substrate it reads is the neutral `mtg_utils/_analysis/` package shared with the tuner and the CLIs — `signals.py` (signal extraction, over `signal_base` / `text_reads` / `membership_floor` primitives), `signal_trees.py` (the signals-only synthesis stage over the concept-tree owner `mtg_utils/_card_ir/trees.py` — ADR-0047; the compat-Card resolver `ir_for` is `_card_ir/compat_lookup.py`), `tree_synthesis/` (the reference-arm synthesis stage), `lanes/` (the structural signal lanes, one module per family; `lanes/manifest.py` holds `SERVED_SIGNAL_KEYS`), `bridge_ledger.py` (the ledgered bridges, ADR-0048), `signal_specs/` (serve/search specs + the key-agreement gate), `roles.py` (the template-role facts — `role_of` / `is_ramp` / `protects`, each a view over the signal path; ADR-0051), `budgets.py` (the per-family `Template` rows), `ranking.py`, `rate.py`, `staples.py` (the hand-curated Commander staples list — the Commander family only) — see `deck-forge/CONTEXT.md` for what each module owns. **Load-bearing contract: the session-agent never names a card from memory** — it proposes patterns/searches/judgments; the deterministic core (`card_search` + `theme_presets` + Commander Spellbook) names real cards. Billing-safe by being an interactive skill, never Agent-SDK/ACP/`claude -p`. The deterministic core also runs agent-less (search/curve/combos/budgets/finalize) for non-Claude-Code users. See `docs/adr/README.md` for related design decisions.

## Supported Deck Formats

| Format | Deck Size | Copy Limit | Sideboard | Arena | Legality Key |
|--------|-----------|------------|-----------|-------|-------------|
| commander | 100 | 1 (singleton) | No | No | commander |
| brawl | 60 | 1 (singleton) | No | Yes | standardbrawl |
| historic_brawl | 100 | 1 (singleton) | No | Yes | brawl |
| competitive_brawl | 100 | 1 (singleton) | No | Yes | brawl + own ban list |
| standard | 60 | 4 | 15 | Yes | standard |
| alchemy | 60 | 4 | 15 | Yes | alchemy |
| historic | 60 | 4 | 15 | Yes | historic |
| timeless | 60 | 4 | 15 | Yes | timeless |
| pioneer | 60 | 4 | 15 | Yes | pioneer |
| modern | 60 | 4 | 15 | No | modern |
| premodern | 60 | 4 | 15 | No | premodern |
| legacy | 60 | 4 | 15 | No | legacy |
| vintage | 60 | 4 (restricted=1) | 15 | No | vintage |
| sealed | 40 (minimum) | none | the unused pool | Yes | pool containment (no key) |
| draft | 40 (minimum) | none | the unused pool | Yes | pool containment (no key) |

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

**Deck-CLI tests and the acquisition seam (ADR-0046).** A deck CLI test exercises the tool by passing a small Scryfall-shaped bulk JSON via `--bulk-data` (the `sample_bulk_data` fixture from `tests/mtg-utils/conftest.py`) alongside a deck JSON, rather than constructing a hand-built hydrated-card list — `HydratedDeck.acquire` does the join and sidecar bookkeeping itself, the same seam production uses.

**Real-card test fixtures (ADR-0056).** Every test that needs a real card's data — oracle text, type line, keywords, cost, P/T, legalities — gets it by name from `mtg_utils.testkit`, never by typing it in. Only per-printing facts the snapshot omits (rarity, set, `games`, prices, ownership) are written by hand, overlaid on the real record (`{**test_card("Forest"), "rarity": "common", "games": ["arena"]}`). Synthetic records are for testing machinery only and use obviously fictional names. A new name is a literal `test_card("…")` argument plus a `build-card-snapshot` run. Signal tests evaluate the SAME Card IR real cards parse into — not a hand-built `_ir(Ability(...))` shape that drifts from production. `mtg_utils.testkit` serves `test_card(name)` (minimal Scryfall record), `test_card_ir(name)` (the compat `Card`, built on demand from the snapshot's stored raw phase face records — the same shape `ir_for` serves in production), `test_signals(name)` (the production `extract_signals`, with the concept-tree memo pre-seeded from those records), and `test_phase_records(name)` (the raw phase face records themselves, for a test of the strict-load / overlay / correction layer below the trees — the crosswalk suites' old `crosswalk_fixture_cards.json` merged in here) from a committed snapshot at `tests/fixtures/card_snapshot.json` (schema 2) — so real crosswalk trees run in CI with **no** sidecar/bulk/phase/network. The snapshot is usage-derived: `build-card-snapshot` AST-scans the tests (and their `conftest.py` modules) for testkit usage — direct literals, `parametrize` columns, literal loop tuples, `_REAL_CASES` name-table values, and any module-local wrapper that forwards a name into the testkit core (derived per module, never hand-listed) — plus every theme preset's `should_match` / `should_not_match` name read straight from the registry (a preset fixture is proven against the snapshot's real record, never hand-typed oracle text) and every bridge-ledger pin, resolves each name to its gameplay printing, stores its minimal Scryfall record plus its raw phase face records (the INPUT, never a baked IR), and self-validates that the minimal record loses no signal vs the full bulk record. It carries the `crosswalk_sidecar_version` and `phase_tag` it was captured at; loading asserts both match, so a schema / compat / phase bump fails loudly until the snapshot is regenerated. The card-data source is MTGJSON: `build-card-snapshot` sources the minimal records from the MTGJSON-backed `bulk_loader`; the stored phase records are phase's own parse either way. The flagship consumer is `tests/deck-forge/test_signal_keys_real_cards.py` (every served key proven against a real card via `_REAL_CASES`, plus a corpus test asserting every emitted key is manifest-served).
