---
name: deck-builder
description: Build competitive 60-card constructed MTG decks with sideboards for Standard, Alchemy, Historic, Pioneer, Timeless, Modern, Legacy, and Vintage.
compatibility: Requires Python 3.12+ and uv. Shares commander_utils package via symlink.
license: 0BSD
---

# Deck Builder

Build 60-card constructed decks with 15-card sideboards for competitive MTG formats. Unlike Commander, these formats are metagame-driven (not commander-centric), allow 4 copies of a card, and revolve around archetypes, combos, and matchup planning.

## The Iron Rule

**Never assume what a card does.** Always look up oracle text via `scryfall-lookup` before recommending a card. Training data may be outdated, cards get errata, and memory conflates similar effects. Discovery (brainstorming candidates) may use training data; evaluation (deciding to include) must use verified oracle text.

---

## Supported Formats

| Format | Platform | Card Pool | Notes |
|--------|----------|-----------|-------|
| Standard | Arena + Paper | Recent sets (rotating) | Smallest card pool, most accessible |
| Alchemy | Arena only | Standard + digital-only rebalanced | Arena-specific format |
| Historic | Arena only | All Arena sets (non-rotating) | Broad Arena pool |
| Timeless | Arena only | All Arena sets, no bans | Arena's most powerful format |
| Pioneer | Paper + Arena (as Explorer) | Return to Ravnica forward | Non-rotating, paper-focused |
| Modern | Paper + MTGO | 8th Edition forward | Largest non-eternal paper pool |
| Legacy | Paper + MTGO | All sets, ban list | Eternal, powerful but accessible |
| Vintage | Paper + MTGO | All sets, restricted list | Restricted cards limited to 1 copy |

All formats: 60-card minimum mainboard, 15-card maximum sideboard, up to 4 copies of any non-basic card (basic lands unlimited). Vintage restricted cards are limited to 1 copy.

---

## Progress Tracking

Create these top-level todos at session start. Mark `in_progress` immediately when starting a step, `completed` immediately when finishing. Never batch updates.

1. Step 1: Interview
2. Step 2: Metagame Research
3. Step 3: Skeleton Generation
4. Step 4: Structural Verification
5. Step 5: Present Skeleton
6. Step 6: Hand Off to Deck-Tuner

**Step 3 expansion:** When starting Step 3, expand into sub-todos:
- 3a: Fill Creatures/Threats
- 3b: Fill Removal/Interaction
- 3c: Fill Card Advantage
- 3d: Fill Utility/Flex Slots
- 3e: Fill Mana Base
- 3f: Build Sideboard

**Combo-first variant:** If the user wants to build around a combo (Step 1), add/swap:
- 1b-alt: Combo/Build-Around Discovery
- 2-alt: Shell Construction (replaces Metagame Research)
- 3-alt: Skeleton with Combo Core (replaces standard Step 3)

---

## Setup and Tooling

### Script Invocation

All scripts are invoked via `uv run <script-name>` from the skill install directory. Examples in this document elide the `uv run` prefix for brevity.

### JSON File Writing

**Use the Write tool** for any JSON file containing card names. Apostrophes in names (e.g., "Ashnod's Altar") break shell quoting in heredocs and inline Python. Write tool permissions are cacheable across the session; `python3 -c "..."` re-prompts every time.

### Scratch File Paths

Reuse these stable paths within a session: `/tmp/cuts.json`, `/tmp/adds.json`, `/tmp/sideboard-cuts.json`, `/tmp/sideboard-adds.json`.

**Critical:** Files at `/tmp/` persist across sessions. Always `Read` a scratch file before the first `Write` in a new session to avoid clobbering prior work.

### Parsed Deck JSON Schema

```json
{
  "format": "pioneer",
  "deck_size": 60,
  "sideboard_size": 15,
  "commanders": [],
  "cards": [{"name": "Lightning Bolt", "quantity": 4}, ...],
  "sideboard": [{"name": "Roiling Vortex", "quantity": 3}, ...],
  "total_cards": 60,
  "total_sideboard": 15,
  "owned_cards": []
}
```

Constructed formats always have `"commanders": []`. The `sideboard` field holds sideboard entries separately from mainboard `cards`.

### Path Requirements

- **Absolute paths only.** `uv` rebases the working directory to the skill install; relative paths resolve against the wrong root.
- **Cache directory:** Always `<working-dir>/.cache`, not the skill install directory.
- **Re-hydration:** After every deck edit, re-run `scryfall-lookup --batch` on the new deck JSON. The hydrated cache is SHA-keyed; old caches go stale silently.

### Arena Rarity Warning

The `rarity` field in hydrated card data is the **default Scryfall printing's rarity**, which drifts from Arena's actual wildcard cost. Always use `price-check --format <fmt> --bulk-data <path>` for Arena wildcard budgeting.

### AskUserQuestion Cap

The AskUserQuestion tool supports at most 4 options. If you have more than 4 choices, either present the most relevant 4 (mention others exist) or present the information as text and ask a follow-up question.

### Decision Table

| Task | Tool |
|------|------|
| Find format-legal cards by oracle text, type, CMC | `card-search --format <fmt>` |
| Look up a specific card's oracle text | `scryfall-lookup "<Card Name>"` |
| Find combos involving specific cards | `combo-discover --card "<Name>"` |
| Find combos by outcome | `combo-discover --result "<outcome>"` |
| Check deck legality | `legality-audit <deck.json> <hydrated.json>` |
| Check mana base health | `mana-audit <deck.json> <hydrated.json>` |
| Price check (paper USD) | `price-check <deck.json> --bulk-data <path>` |
| Price check (Arena wildcards) | `price-check <deck.json> --format <fmt> --bulk-data <path>` |
| Research metagame/strategy | WebSearch + WebFetch (or `web-fetch` script for bot-blocked sites) |
| Export for Moxfield/Arena import | `export-deck <deck.json>` |

---

## Step 1: Interview

### Format Selection

Ask the user which format they want to build for. If they mention Arena, clarify:
- Standard, Alchemy, Historic, Timeless are Arena formats
- Pioneer exists on Arena as "Explorer" (subset); full Pioneer is paper
- Modern, Legacy, Vintage are paper/MTGO only

### Core Questions (ask in one message, not one at a time)

1. **Format** — Which format?
2. **Platform** — Arena or paper? (determines pricing mode and card pool filtering)
3. **Playstyle** — Aggro, midrange, control, combo, tempo? (brief explanations if user is unsure)
4. **Color preference** — Any color preference, or open to anything?
5. **Budget** — USD budget for paper, or wildcard budget for Arena?
6. **Archetype preference** — "Do you want to follow a proven metagame archetype, or build something original/off-meta?"
7. **Pet cards** — Any cards you definitely want to include?

### Experience Level Detection

Infer from answers. If unclear, ask directly: beginner, intermediate, or advanced?

| Level | Interview Depth | Explanation Style |
|-------|----------------|-------------------|
| Beginner | Explain format basics, define archetypes | Full sentences, analogies |
| Intermediate | Assume format knowledge | Concise, note key interactions |
| Advanced | Assume deep knowledge | Tables, shorthand, focus on novel angles |

### Pet Card Validation

If the user provides pet cards:
1. `scryfall-lookup --batch` to verify existence and oracle text
2. Check format legality (`legalities.<format>` field)
3. Note their role (threat, removal, engine, etc.) for skeleton slotting

### Combo-First Path

If the user says "build around a combo" or names a specific combo/build-around card, switch to the combo-first variant:

**Step 1b-alt: Combo/Build-Around Discovery**
- If user names a card: `scryfall-lookup` it, then `combo-discover --card "<Name>" --format <fmt>`
- If user names an outcome: `combo-discover --result "<outcome>" --format <fmt>`
- If user wants to explore: Ask about mechanics, outcomes, or colors, then search
- Present 3-5 combos with: cards, oracle text, result, color identity, popularity
- Batch-lookup all combo pieces via `scryfall-lookup --batch`
- Let user pick a combo or build-around card

---

## Step 2: Metagame Research

### Proven Archetype Path

1. **WebSearch** for `"<format> metagame 2026"` or `"<format> tier list"` to find current top archetypes
2. **WebFetch** (or `web-fetch` for bot-blocked sites) the top result to get archetype names and metagame share percentages
3. Present the top 5-8 archetypes with approximate metagame share
4. If user has color/playstyle preference, highlight matching archetypes
5. Let user pick an archetype
6. **WebSearch** for `"<archetype name> <format> decklist 2026"` to find a sample list
7. **WebFetch** the sample list — this becomes the skeleton foundation
8. If the sample list is found, parse it: `parse-deck --format <fmt> <path> --output <working-dir>/deck.json`
9. Hydrate: `scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <working-dir>/.cache`

### Original/Off-Meta Path

1. Use the user's playstyle, colors, and pet cards as starting constraints
2. `card-search --format <fmt> --oracle "<keyword>" --color-identity <colors>` to find build-around cards
3. `combo-discover` for combo shells in those colors
4. WebSearch for `"<format> <archetype/mechanic> deck"` for inspiration
5. Proceed to Step 3 without a sample list foundation

### Combo-First Path (Step 2-alt)

1. From the combo chosen in Step 1b-alt, identify the minimum shell:
   - Combo pieces (must-haves)
   - Tutors that find combo pieces (format-legal tutors via `card-search`)
   - Protection for combo assembly (counterspells, discard, hexproof)
2. Identify the best colors (combo colors + support card availability)
3. Proceed to Step 3-alt

---

## Step 3: Skeleton Generation

### Starting Point

- **Proven archetype with sample list:** Customize the sample list based on user preferences, budget, and pet cards. This is modification, not from-scratch building.
- **Original/off-meta or combo-first:** Build from scratch using the template below.

### Category Template (60-card mainboard)

| Category | Typical Count | Notes |
|----------|--------------|-------|
| Threats/Creatures | 12-28 | Varies hugely by archetype (aggro: 28, control: 4-8) |
| Removal/Interaction | 4-12 | Format-dependent; more in slower formats |
| Card Advantage | 4-8 | Draw spells, planeswalkers, selection |
| Utility/Flex | 2-8 | Archetype-specific support |
| Lands | 20-27 | Constructed land formula (see below) |

**These counts are guidelines, not rules.** Aggressive decks skew toward threats; control decks skew toward interaction and card advantage. The archetype defines the balance.

### Land Count Formula

Use the constructed land target formula:
- **Baseline:** 24 lands for a 60-card deck
- **Ramp adjustment:** -1 land per 2 ramp/mana-acceleration cards
- **Curve adjustment:** Low curve (avg CMC < 2.5) → fewer lands; high curve (avg CMC > 3.5) → more lands
- **Clamp:** Never below 20, never above 27

Run `mana-audit` after building to verify.

### Land Base Composition

| Land Type | Budget | Mid-Range | High-End |
|-----------|--------|-----------|----------|
| Basics | 10-16 | 6-10 | 2-6 |
| Dual lands (shock, fast, check) | 4-8 | 8-12 | 8-12 |
| Fetch lands | 0 | 0-4 | 8-12 |
| Utility lands | 0-2 | 2-4 | 2-4 |

For Arena formats: fetch lands don't exist on Arena (except Pioneer/Explorer via Khans fetches). Use the Arena-available mana base (shock lands, fast lands, pathway lands, triomes).

### Filling Process

For each category:
1. If starting from a sample list, evaluate what's already there
2. `card-search --format <fmt> --oracle "<pattern>" --color-identity <colors>` for candidates
3. `scryfall-lookup --batch` to verify oracle text of all candidates
4. Filter by budget (paper: price; Arena: wildcard rarity)
5. Include pet cards in their appropriate categories
6. Prioritize format staples and proven performers

### 4-of vs. Fewer Copies

- **4 copies:** Cards you want every game, core to the strategy
- **3 copies:** Strong cards you want most games but don't need multiples
- **2 copies:** Situational cards, legendary permanents, curve-toppers
- **1 copy:** Silver bullets, tutored targets, high-impact singletons

### Step 3f: Build Sideboard

The sideboard is 15 cards designed to improve matchups after Game 1.

**Process:**
1. Identify the top 3-5 archetypes in the metagame (from Step 2 research)
2. For each bad matchup, allocate 2-4 sideboard slots:
   - Anti-aggro: life gain, cheap removal, board wipes
   - Anti-control: cheap threats, counterspells, card advantage
   - Anti-combo: disruption, counterspells, graveyard hate
   - Anti-graveyard: `card-search --format <fmt> --oracle "exile.*graveyard"`
   - Anti-artifact/enchantment: `card-search --format <fmt> --oracle "destroy.*artifact"`
3. Prefer versatile cards that help in multiple matchups
4. Verify all sideboard cards are format-legal via `scryfall-lookup`

**Sideboard card counts:**
- 2-3 copies of narrow hate cards (graveyard hate, artifact removal)
- 3-4 copies of flexible answers (extra removal, counterspells)
- 1-2 copies of alternative win conditions or transformative cards

---

## Step 4: Structural Verification

Run all four checks in order. If any fail, fix and re-check from the top. Re-hydrate after any deck edit.

### 1. Legality Audit (must PASS)

```
legality-audit <deck.json> <hydrated.json>
```

Checks: format legality, copy limits (4-of rule + Vintage restricted), sideboard size (max 15), deck minimum (60+). Fix any violations before proceeding.

### 2. Price Check (must be within budget)

```
# Paper
price-check <deck.json> --bulk-data <path>

# Arena
price-check <deck.json> --format <fmt> --bulk-data <path>
```

If over budget, substitute expensive cards with budget alternatives. Re-run after changes.

### 3. Deck Stats (verify counts)

```
deck-stats <deck.json> <hydrated.json>
```

Verify: total card count (60+ mainboard), land count (matches formula target), category distribution looks reasonable, sideboard count (0-15).

### 4. Mana Audit (must PASS or WARN)

```
mana-audit <deck.json> <hydrated.json>
```

Uses the constructed land formula. Checks land count and color balance. FAIL means the mana base needs fixing before proceeding.

---

## Step 5: Present Skeleton

### Mainboard Presentation

Present as a categorized list with brief synergy notes:

```
## Creatures (24)
4 Monastery Swiftspear — hasty one-drop, prowess triggers off spells
4 Eidolon of the Great Revel — punishes low-curve opponents
...

## Instants/Sorceries (16)
4 Lightning Bolt — premium removal + face damage
...

## Lands (20)
8 Mountain
4 Inspiring Vantage — untapped on turns 1-3
...
```

### Sideboard Presentation

Present with matchup notes:

```
## Sideboard (15)
3 Roiling Vortex — vs. free spells, lifegain decks
2 Rampaging Ferocidon — vs. token/lifegain strategies
3 Smash to Smithereens — vs. artifact-heavy decks
...
```

### Summary Block

```
Mainboard: 60 cards | Lands: 20 | Avg CMC: 1.85
Sideboard: 15 cards
Budget: $45.20 / $50.00 (paper) or 2M/4R/8U/12C (Arena wildcards)
```

### Ask for Adjustments

Present the skeleton and ask: "Any adjustments before I hand this off for tuning?" Apply changes, re-run structural verification if anything changes.

---

## Step 6: Hand Off to Deck-Tuner

### Write Output Files

1. Deck JSON: `<working-dir>/<deck-name>.json`
2. Moxfield export: `export-deck <deck.json>` → `<working-dir>/<deck-name>-moxfield.txt`
3. Hydrated cache already at `<working-dir>/.cache/hydrated-<sha>.json`

### Invoke Deck-Tuner

Invoke via the Skill tool (not by telling the user to type `/deck-tuner`):

```
Skill(skill: "deck-tuner", args: "<carry-forward context>")
```

### Carry-Forward Context

Include in the args:
- **Format** and platform (Arena/paper)
- **Budget:** total budget, skeleton cost, remaining for upgrades
- **Owned cards** (if collection was provided; don't count toward budget)
- **Experience level**
- **Suggested max swaps:** 15-20 for a fresh skeleton (user can adjust)
- **Pain points:** "Freshly generated skeleton — general optimization" or specific concerns
- **Archetype:** name and brief description of the deck's game plan
- **File paths:** deck JSON, hydrated cache, Moxfield export

---

## Red Flags

| Thought | Reality |
|---------|---------|
| "I know what this card does" | Look it up. Training data drifts. |
| "This is a format staple, auto-include" | Verify format legality + oracle text + price |
| "The sideboard can wait" | Sideboard is half the competitive advantage. Build it now. |
| "The user said aggro, so 20 lands" | Run the formula. Verify with mana-audit. |
| "I'll just use the sample list as-is" | Customize for budget, pet cards, and user preferences |
| "Skip structural verification, it looks right" | Tools catch errors humans miss. Run them. |
| "This card is cheap on paper so it's fine for Arena" | Paper price != Arena rarity. Use price-check. |

---

## Script Reference

See commander-tuner/SKILL.md for the full script input/output reference. Key scripts for constructed deck building:

- `parse-deck --format <fmt> <path>` — Parse deck list, route sideboard separately
- `scryfall-lookup --batch <deck.json>` — Hydrate all card data
- `card-search --format <fmt> [--oracle <pattern>] [--color-identity <CI>] [--type <type>] [--cmc-max <N>]` — Search for candidates
- `combo-discover [--card "<name>"] [--result "<outcome>"] [--format <fmt>]` — Find combos
- `legality-audit <deck.json> <hydrated.json>` — Check legality, 4-of, sideboard, deck minimum
- `mana-audit <deck.json> <hydrated.json>` — Land count and color balance
- `price-check <deck.json> [--format <fmt>] --bulk-data <path>` — Budget check
- `deck-stats <deck.json> <hydrated.json>` — Baseline stats
- `export-deck <deck.json>` — Moxfield/Arena import format with sideboard
- `build-deck <deck.json> <hydrated.json> [--cuts <cuts.json>] [--adds <adds.json>] [--sideboard-cuts <sb-cuts.json>] [--sideboard-adds <sb-adds.json>]` — Apply changes
