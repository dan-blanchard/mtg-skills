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

## Architecture

Mono-repo for MTG-related Claude Code skills. Each skill lives in its own directory matching the `name` field in its SKILL.md frontmatter.

### commander-tuner

Sixteen CLI scripts backed by library modules, orchestrated by SKILL.md:

- **`parse_deck.py`** — Multi-format deck list parser. Strips Moxfield set code suffixes.
- **`scryfall_lookup.py`** — Card lookup against Scryfall bulk data with API fallback and persistent caching.
- **`edhrec_lookup.py`** — EDHREC JSON endpoint client for commander recommendations.
- **`download_bulk.py`** — Scryfall bulk data downloader with 24h freshness check.
- **`web_fetch.py`** — Web page fetcher with browser headers and curl fallback.
- **`deck_stats.py`** — Deck statistics: land/ramp/creature counts, avg CMC, curve, color sources, total card count.
- **`card_summary.py`** — Compact human-readable card table with filter flags (`--lands-only`, `--nonlands-only`, `--type`).
- **`deck_diff.py`** — Deck comparison: added/removed cards, count/CMC/land/ramp deltas.
- **`set_commander.py`** — Move cards from cards list to commanders list in parsed deck JSON.
- **`mana_audit.py`** — Mana base health audit: land count (Burgess/Karsten), color balance (pip demand vs. land production), PASS/WARN/FAIL gates, comparison mode.
- **`cut_check.py`** — Mechanical pre-grill: trigger detection and multiplied values, keyword interaction detection, self-recurring card detection.
- **`build_deck.py`** — Apply cuts/adds to a deck, output new deck JSON + merged hydrated data.
- **`price_check.py`** — Price validation against budget using Scryfall bulk data with API fallback.
- **`combo_search.py`** — Commander Spellbook API wrapper: combo detection and near-miss identification.
- **`export_deck.py`** — Export parsed deck JSON to Moxfield import format (`N CardName` lines).
- **`card_search.py`** — Search Scryfall bulk data with filters: color identity, oracle text regex, type, CMC range, price range. Compact table or JSON output.

Shared library module (not a CLI script):

- **`card_classify.py`** — Card classification helpers: `is_land()`, `is_creature()`, `is_ramp()`, `color_sources()`.

### commander-builder

SKILL.md-only workflow (no Python scripts of its own). Shares `commander_utils` via symlink to `commander-tuner/src`. Guides users through commander selection and deck skeleton generation, then hands off to commander-tuner for refinement.

## Testing

Tests live in `tests/commander-tuner/` (outside the skill directory so they aren't installed). Use `unittest.mock` for HTTP calls. No real network calls in tests.
