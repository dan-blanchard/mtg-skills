# MTG Skills

Claude Code skills for Magic: The Gathering.

## Installation

```bash
npx skills add dan-blanchard/mtg-skills
```

## Available Skills

### commander-builder

Guided workflow for building Commander/EDH, Brawl, and Historic Brawl decks from scratch. Walks through commander selection (or discovery from your collection), strategy research via EDHREC, and skeleton generation with structural verification. Hands off to commander-tuner for refinement.

### commander-tuner

Structured 10-step process for analyzing and tuning Commander/EDH, Brawl, and Historic Brawl decks. Includes mana base auditing, combo detection, mechanical cut analysis, a two-agent debate to stress-test proposals, and impact verification before finalizing changes.

### deck-builder

Guided workflow for building 60-card constructed decks with sideboards. Supports Standard, Alchemy, Historic, Pioneer, Timeless, Modern, PreModern, Legacy, and Vintage. Covers metagame research, archetype selection (or combo-first building), Companion evaluation, and Bo1/Bo3 awareness for Arena. Hands off to deck-tuner for refinement.

### deck-tuner

Structured 12-step process for analyzing and tuning 60-card constructed decks with sideboards. Includes archetype coherence analysis, sideboard evaluation against the metagame, a two-agent debate, and a matchup-by-matchup sideboard guide. Supports all competitive constructed formats.

## Shared Tooling

All four skills share the same Python CLI scripts via symlinks:

- **parse-deck** — Multi-format deck list parser with sideboard support
- **scryfall-lookup** — Card lookup against local Scryfall bulk data with API fallback
- **card-search** — Search bulk data with filters: format legality, oracle text, type, CMC, price
- **combo-search / combo-discover** — Commander Spellbook API for combo detection and discovery
- **legality-audit** — Format legality, copy limits (singleton or 4-of), sideboard size, Vintage restricted
- **mana-audit** — Land count formulas (Burgess for commander, constructed formula for 60-card) and color balance
- **build-deck** — Apply mainboard and sideboard cuts/adds
- **price-check** — USD pricing or Arena wildcard budgeting
- **deck-stats** — Deck statistics with sideboard reporting
- **deck-diff** — Compare deck versions including sideboards
- **export-deck** — Moxfield/Arena import format with sideboard section
- **card-summary** — Compact card table with sideboard display
- **edhrec-lookup** — EDHREC JSON endpoint client (commander skills only)
- **cut-check** — Mechanical pre-grill for commander trigger/synergy analysis
- **mark-owned** — Collection intersection with Arena name aliasing
- **mtga-import** — Extract Arena collection and wildcard counts

## Supported Formats

| Format | Deck Size | Copy Limit | Sideboard | Platform |
|--------|-----------|------------|-----------|----------|
| Commander/EDH | 100 | Singleton | No | Paper |
| Brawl (Standard Brawl on Arena) | 60 | Singleton | No | Arena + Paper |
| Historic Brawl (Brawl on Arena) | 60 or 100 | Singleton | No | Arena + Paper |
| Standard | 60 | 4-of | 15 | Arena + Paper |
| Alchemy | 60 | 4-of | 15 | Arena |
| Historic | 60 | 4-of | 15 | Arena |
| Timeless | 60 | 4-of | 15 | Arena |
| Pioneer | 60 | 4-of | 15 | Paper + Arena |
| Modern | 60 | 4-of | 15 | Paper |
| PreModern | 60 | 4-of | 15 | Paper + MTGO |
| Legacy | 60 | 4-of | 15 | Paper |
| Vintage | 60 | 4-of (restricted=1) | 15 | Paper |

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

On first use, each skill runs `uv sync` to install Python dependencies and downloads Scryfall bulk data (~500MB).

## License

[0BSD](LICENSE)
