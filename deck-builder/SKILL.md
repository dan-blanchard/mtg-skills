---
name: deck-builder
description: Build competitive 60-card constructed MTG decks from scratch for Standard, Alchemy, Historic, Pioneer, Timeless, Modern, Legacy, and Vintage.
---

# Deck Builder

Guides users through building 60-card constructed decks with 15-card sideboards for competitive MTG formats.

## Supported Formats

Standard, Alchemy, Historic, Pioneer, Timeless, Modern, Legacy, Vintage.

## Workflow (Skeleton)

Full workflow documentation will be added in a follow-up. The general flow is:

1. **Interview** -- Format, playstyle, colors, budget, pet cards, archetype preference
2. **Metagame Research** -- WebSearch + web-fetch for top archetypes and sample lists
3. **Skeleton Generation** -- 60-card main deck + 15-card sideboard
4. **Structural Verification** -- legality-audit, price-check, mana-audit, deck-stats
5. **Present Skeleton** -- Mainboard by category + sideboard with matchup notes
6. **Hand Off to Deck-Tuner** -- Invoke deck-tuner skill with carry-forward context

## Shared Tooling

Uses the same CLI scripts as commander-tuner via symlinked `src/` directory. Key tools:

- `parse-deck --format <format>` -- Parse deck lists with sideboard support
- `card-search --format <format>` -- Find format-legal cards
- `combo-discover` -- Find combos by outcome or card name
- `scryfall-lookup --batch` -- Hydrate card data
- `legality-audit` -- Check format legality, 4-of limits, sideboard size
- `mana-audit` -- Constructed land count formula
- `price-check` -- USD or Arena wildcard budget
- `export-deck` -- Moxfield-importable text with sideboard
