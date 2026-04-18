# MTG Skills

Claude Code skills for Magic: The Gathering.

## Installation

```bash
npx skills add dan-blanchard/mtg-skills
```

## Available Skills

### deck-wizard

Build MTG decks from scratch or tune existing ones across all formats — Commander/EDH, Brawl, Historic Brawl, Standard, Alchemy, Historic, Pioneer, Timeless, Modern, PreModern, Legacy, and Vintage. Two-phase workflow: Phase 1 acquires a deck (parse an existing list or build from scratch via interview + research + skeleton generation), Phase 2 runs a 12-step tuning pipeline with mana auditing, combo detection, archetype coherence analysis, a two-agent debate, and impact verification.

### cube-wizard

Build and tune MTG cubes — curated card pools designed for drafting. Supports Vintage, Unpowered, Legacy, Modern, Pauper, Peasant, Set, Commander, and PDH cubes. Two-phase workflow: Phase 1 acquires a cube (parse an existing CubeCobra cube or clone a well-known reference cube), Phase 2 runs a 9-step tuning pipeline covering designer intent, balance dashboards, archetype signal density, power-level review, a two-agent self-grill, cube-diff impact verification, pack simulation, and CubeCobra CSV export.

## Tooling

Both skills share CLI scripts via the `mtg_utils` package (`mtg-utils/`).

### Deck tooling

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

### Cube tooling

- **cubecobra-fetch** — Pull a cube from CubeCobra (`cubeJSON` → `cubelist` → CSV fallback, with curl fallback for 403s)
- **parse-cube** — Parse CubeCobra JSON / CubeCobra CSV / plain text / deck JSON into canonical cube JSON
- **cube-stats** — Informational metrics: size, per-color distribution, curve, types, rarity, commander pool by color identity
- **cube-balance** — Informational checks (not pass/fail) for color balance, curve, removal density, fixing density, and commander-pool composition
- **cube-legality-audit** — Hard-constraint validation: rarity filters (Pauper, Peasant, PDH), format legality, ban list, commander-pool rarity
- **archetype-audit** — Cross-reference user-supplied theme regexes against color pairs; surface bridge cards and orphan signals
- **cube-diff** — Compare two cube revisions with optional balance-metric deltas
- **pack-simulate** — Seeded pack generation (sizes 9/11/15) with configurable slot templates; optional dedicated commander packs
- **export-cube** — Export canonical cube JSON to CubeCobra-compatible CSV (for the "Replace with CSV Import" round-trip) or plain text

## Supported Deck Formats

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

## Supported Cube Formats

| Format | Default Size | Card Pool | Rarity Filter | Commander Pool |
|--------|-------------:|-----------|---------------|----------------|
| vintage | 540 | Full eternal | — | No |
| unpowered | 540 | Full eternal (Power 9 banned) | — | No |
| legacy | 540 | Legacy-legal | — | No |
| modern | 540 | Modern-legal | — | No |
| pauper | 540 | Full eternal | Commons only | No |
| peasant | 540 | Full eternal | Commons + uncommons | No |
| set | 360 | Single set | — | No |
| commander | 540 | Commander-legal | — | Yes |
| pdh | 540 | Full eternal | Commons (main) | Yes (uncommons) |

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

On first use, the skill runs `uv sync` to install Python dependencies and downloads Scryfall bulk data (~500MB).

## License

[0BSD](LICENSE)
