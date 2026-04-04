# CLAUDE.md

## Commands

Run all commands from the `commander-tuner/` directory:

```bash
cd commander-tuner
uv sync                              # Install dependencies
uv run pytest ../tests/commander-tuner/ -v  # Run tests
uv run ruff check src/ ../tests/commander-tuner/  # Lint
uv run ruff format src/ ../tests/commander-tuner/  # Format
```

## Architecture

Mono-repo for MTG-related Claude Code skills. Each skill lives in its own directory matching the `name` field in its SKILL.md frontmatter.

### commander-tuner

Eight CLI scripts backed by library modules, orchestrated by SKILL.md:

- **`parse_deck.py`** — Multi-format deck list parser. Strips Moxfield set code suffixes.
- **`scryfall_lookup.py`** — Card lookup against Scryfall bulk data with API fallback and persistent caching.
- **`edhrec_lookup.py`** — EDHREC JSON endpoint client for commander recommendations.
- **`download_bulk.py`** — Scryfall bulk data downloader with 24h freshness check.
- **`web_fetch.py`** — Web page fetcher with browser headers and curl fallback.
- **`deck_stats.py`** — Deck statistics: land/ramp/creature counts, avg CMC, curve, color sources, total card count.
- **`card_summary.py`** — Compact human-readable card table with filter flags (`--lands-only`, `--nonlands-only`, `--type`).
- **`deck_diff.py`** — Deck comparison: added/removed cards, count/CMC/land/ramp deltas.

Shared library module (not a CLI script):

- **`card_classify.py`** — Card classification helpers: `is_land()`, `is_creature()`, `is_ramp()`, `color_sources()`.

## Testing

Tests live in `tests/commander-tuner/` (outside the skill directory so they aren't installed). Use `unittest.mock` for HTTP calls. No real network calls in tests.
