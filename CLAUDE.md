# CLAUDE.md

## Commands

### commander-tuner

```bash
cd commander-tuner
uv sync                              # Install dependencies
uv run pytest ../tests/commander-tuner/ -v  # Run tests
uv run ruff check src/ ../tests/commander-tuner/  # Lint
uv run ruff format src/ ../tests/commander-tuner/  # Format
```

### commander-builder

```bash
cd commander-builder
uv sync                              # Install dependencies (follows symlink to commander-tuner/src)
uv run pytest ../tests/commander-builder/ -v  # Run smoke tests
```

### deck-tuner

```bash
cd deck-tuner
uv sync                              # Install dependencies (follows symlink to commander-tuner/src)
uv run pytest ../tests/deck-tuner/ -v  # Run tests
```

### deck-builder

```bash
cd deck-builder
uv sync                              # Install dependencies (follows symlink to commander-tuner/src)
uv run pytest ../tests/deck-builder/ -v  # Run smoke tests
```

## Architecture

Mono-repo for MTG-related Claude Code skills. Each skill lives in its own directory matching the `name` field in its SKILL.md frontmatter.

### commander-tuner

Sixteen CLI scripts backed by library modules, orchestrated by SKILL.md:

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

Shared library module (not a CLI script):

- **`card_classify.py`** — Card classification helpers: `is_land()`, `is_creature()`, `is_ramp()`, `color_sources()`.

### commander-builder

SKILL.md-only workflow (no Python scripts of its own). Shares `commander_utils` via symlink to `commander-tuner/src`. Guides users through commander selection and deck skeleton generation, then hands off to commander-tuner for refinement.

### deck-tuner

Shares `commander_utils` via symlink to `commander-tuner/src`. Tunes 60-card constructed decks with sideboards for Standard, Alchemy, Historic, Pioneer, Timeless, Modern, Legacy, and Vintage.

### deck-builder

Shares `commander_utils` via symlink to `commander-tuner/src`. Builds 60-card constructed decks with sideboards for the same formats as deck-tuner, then hands off to deck-tuner for refinement.

## Supported Formats

| Format | Deck Size | Copy Limit | Sideboard | Arena | Legality Key |
|--------|-----------|------------|-----------|-------|-------------|
| commander | 100 | 1 (singleton) | No | No | commander |
| brawl | 60 | 1 (singleton) | No | Yes | standardbrawl |
| historic_brawl | 100 | 1 (singleton) | No | Yes | brawl |
| standard | 60 | 4 | 15 | Yes | standard |
| alchemy | 60 | 4 | 15 | Yes | alchemy |
| historic | 60 | 4 | 15 | Yes | historic |
| timeless | 60 | 4 | 15 | Yes | timeless |
| pioneer | 60 | 4 | 15 | No | pioneer |
| modern | 60 | 4 | 15 | No | modern |
| legacy | 60 | 4 | 15 | No | legacy |
| vintage | 60 | 4 (restricted=1) | 15 | No | vintage |

## Testing

Tests live in `tests/commander-tuner/` and `tests/deck-tuner/` (outside the skill directories so they aren't installed). Use `unittest.mock` for HTTP calls. No real network calls in tests.
