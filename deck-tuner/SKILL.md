---
name: deck-tuner
description: Tune and optimize 60-card constructed MTG decks for Standard, Alchemy, Historic, Pioneer, Timeless, Modern, Legacy, and Vintage.
---

# Deck Tuner

Analyzes and optimizes existing 60-card constructed decks with sideboards for competitive MTG formats.

## Supported Formats

Standard, Alchemy, Historic, Pioneer, Timeless, Modern, Legacy, Vintage.

## Workflow (Skeleton)

Full workflow documentation will be added in a follow-up. The general flow is:

1. **Parse Deck List** -- `parse-deck --format <format>`
2. **Hydrate Card Data** -- `scryfall-lookup --batch`
3. **Baseline Metrics** -- legality-audit, deck-stats, card-summary, mana-audit
4. **User Intake** -- Experience, budget, max swaps, pain points, matchup complaints
5. **Research** -- WebSearch for archetype guides, metagame data, sideboard guides
6. **Strategy Alignment** -- Game plan, win conditions, metagame positioning
7. **Analysis** -- Mana base, interaction suite, archetype coherence, sideboard plan
8. **Self-Grill** -- Two-agent debate on proposed changes
9. **Propose Changes** -- Mainboard + sideboard swaps with rationale
10. **Impact Verification** -- deck-diff, combo-search on built deck
11. **Close Calls** -- User decisions on borderline swaps
12. **Finalize** -- export-deck with sideboard, budget summary

## Shared Tooling

Uses the same CLI scripts as commander-tuner via symlinked `src/` directory. All tools support constructed formats via `--format` flag.
