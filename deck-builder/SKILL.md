---
name: deck-builder
description: Build MTG decks from scratch for all formats — Commander/EDH, Brawl, Historic Brawl, Standard, Alchemy, Historic, Pioneer, Timeless, Modern, PreModern, Legacy, and Vintage.
compatibility: Requires Python 3.12+ and uv. Shares mtg_utils package via symlink. Recommend installing deck-tuner alongside for refinement.
license: 0BSD
---

# Deck Builder

Build MTG decks from scratch for every supported format: Commander/EDH, Brawl, Historic Brawl (singleton formats with commanders) and Standard, Alchemy, Historic, Pioneer, Timeless, Modern, PreModern, Legacy, Vintage (60-card constructed formats with sideboards). The workflow branches after the initial interview based on the chosen format family, then converges for structural verification, presentation, and handoff to the appropriate tuner skill.

## The Iron Rule

**NEVER assume what a card does.** Before including any card in the skeleton, look up its oracle text via the helper scripts. Training data is not oracle text.

**Exception (Commander/Brawl only):** During commander *discovery* (recommending commanders to a user who doesn't know what to build), you may use training data to generate a shortlist of candidates. But every recommended commander MUST be verified before presenting — write all candidate names to a JSON list and batch-lookup in one call: `scryfall-lookup --batch <candidates.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`.

For 60-card constructed: discovery (brainstorming candidates) may use training data; evaluation (deciding to include) must use verified oracle text.

---

## Supported Formats

| Format | Deck Size | Copy Limit | Sideboard | Platform | Legality Key | Notes |
|--------|-----------|------------|-----------|----------|-------------|-------|
| commander | 100 | 1 (singleton) | No | Paper + MTGO | commander | 40 life, multiplayer |
| brawl | 60 | 1 (singleton) | No | Arena | standardbrawl | 25/30 life, Standard pool |
| historic_brawl | 100 | 1 (singleton) | No | Arena (+ paper) | brawl | 25/30 life, all Arena sets |
| standard | 60 | 4 | 15 | Arena + Paper | standard | Rotating |
| alchemy | 60 | 4 | 15 | Arena only | alchemy | Digital mechanics |
| historic | 60 | 4 | 15 | Arena only | historic | All Arena sets |
| timeless | 60 | 4 | 15 | Arena only | timeless | No bans |
| pioneer | 60 | 4 | 15 | Paper + Arena | pioneer | RTR forward |
| modern | 60 | 4 | 15 | Paper + MTGO | modern | 8th Edition forward |
| premodern | 60 | 4 | 15 | Paper + MTGO | premodern | 4th Edition through Scourge |
| legacy | 60 | 4 | 15 | Paper + MTGO | legacy | Eternal, ban list |
| vintage | 60 | 4 (restricted=1) | 15 | Paper + MTGO | vintage | Restricted cards limited to 1 copy |

---

## Progress Tracking

Create these top-level todos at session start. Mark `in_progress` immediately when starting a step, `completed` immediately when finishing. Never batch updates.

### 60-Card Constructed

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

### Commander/Brawl/Historic Brawl

1. Step 1: Interview
2. Step 2: Commander Analysis
3. Step 3: Skeleton Generation
4. Step 4: Present Skeleton
5. Step 5: Hand Off to Commander-Tuner

**Step 3 expansion:** When starting Step 3, expand into sub-todos:
1. Fill Lands
2. Fill Ramp
3. Fill Card Draw
4. Fill Targeted Removal & Board Wipes
5. Fill Protection/Utility
6. Fill Engine/Synergy Pieces
7. Fill Win Conditions
8. Structural Verification (deck-stats, mana-audit, price-check)

If you draft the whole skeleton in a single batch instead of walking the fill order category-by-category, you still must not batch the sub-todo completions. Either (a) skip creating the fill-order sub-todos entirely for that session (mark only the top-level Step 3 as it starts and completes) or (b) close each sub-todo individually at draft time as you mentally finish that category. Leaving eight sub-todos open the whole session and then collapsing them into a batch "all done" when Step 3's parent closes is the failure mode — it silently hides the stale progress indicator from the user until they notice.

**If the user takes the "Outside the Box" workflow**, add or swap todos as you reach each alt step, leaving any already-completed standard steps in place. The alt steps are Step 1b-alt (Mechanics/Outcome Interview), Step 2-alt (Combo Discovery), Step 2b-alt (Commander Fitting — skip if commander already known), and Step 3-alt (Skeleton with Combo Core); Steps 4 and 5 are shared with the standard flow. Step 3-alt expands into the same fill-order sub-todos as Step 3.

Do NOT create per-card sub-todos inside any fill step — that's execution detail and would flood the list.

---

## Setup (First Run)

```bash
uv sync --directory <skill-install-dir>
download-bulk --output-dir <skill-install-dir>
```

Subsequent runs skip if `.venv` exists and bulk data is fresh (24h).

---

## Tooling Notes

### JSON File Writing

**Use the Write tool** for any JSON file containing card names. Apostrophes in names (e.g., "Ashnod's Altar") break shell quoting in heredocs and inline Python. Write tool permissions are cacheable across the session; `python3 -c "..."` re-prompts every time.

Do NOT write JSON via Bash heredocs (`cat > /tmp/foo.json << 'JSONEOF' ... JSONEOF`). Heredocs are functionally fine but they produce un-cacheable Bash permission patterns: Claude Code's permission engine bakes the heredoc body into the allow pattern, so every invocation with different content re-prompts the user. The Write tool generates a single `Write(/tmp/**)` permission that can be granted once and reused.

**The same caching trap applies to `python3 -c "..."`, `awk '...'`, `jq '...'`, and any other Bash pattern where the code body varies between invocations.** Each unique body is a fresh permission pattern. If you need to extract one field from a JSON file, prefer: (a) passing the file directly to a script that already knows how to parse it, (b) `Read` with `offset`/`limit` on the JSON file, or (c) `Grep` on the file. Reach for `python3 -c` only when those options genuinely don't cover the case, and accept the re-prompt cost when you do.

### Scratch File Paths

Reuse these stable paths within a session: `/tmp/cuts.json`, `/tmp/adds.json`, `/tmp/sideboard-cuts.json`, `/tmp/sideboard-adds.json`, `/tmp/candidates.json`, `/tmp/pet-cards.json`.

**Critical:** Files at `/tmp/` persist across sessions. Always `Read` a scratch file before the first `Write` in a new session to avoid clobbering prior work. Never batch `Write(/tmp/foo.json)` + `Bash(tool reading /tmp/foo.json)` in a single message — if the Write errors, the Bash silently consumes stale prior-session content. Run `Write` sequentially and verify success before the dependent Bash call.

### Parsed Deck JSON Schema

**60-card constructed:**

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

**Commander/Brawl/Historic Brawl:**

```json
{
  "format": "commander",
  "deck_size": 100,
  "commanders": [{"name": "...", "quantity": 1}, ...],
  "cards":      [{"name": "...", "quantity": 1}, ...],
  "total_cards": 100,
  "owned_cards": [{"name": "...", "quantity": 1}, ...]
}
```

All three card lists (`commanders`, `cards`, `owned_cards`) are the same shape — `[{name, quantity}]` dicts. `owned_cards` starts empty and is populated by `mark-owned` or by hand. `price-check` reads it to subtract owned copies from the budget; entries with `quantity < 1` are treated as "not owned."

**Parsed deck JSON is the canonical pipeline intermediate.** Once you have a parsed deck JSON from `parse-deck`, pass it **directly** to `scryfall-lookup --batch` and `price-check` — both scripts accept a parsed deck JSON as `<path>`, not just a JSON list of name strings. Do NOT extract card names into a separate `/tmp/*.json` via `python3 -c` or similar.

### Script Invocation

All scripts are invoked via `uv run <script-name>` from the skill install directory. Examples in this document elide the `uv run` prefix for brevity.

### Path Requirements

- **Absolute paths only.** `uv` rebases the working directory to the skill install; relative paths resolve against the wrong root.
- **Cache directory:** Always `<working-dir>/.cache`, not the skill install directory. Keeping the cache in the working directory avoids outside-workspace permission prompts.
- **Re-hydration:** After every deck edit, re-run `scryfall-lookup --batch` on the new deck JSON. The hydrated cache is SHA-keyed; old caches go stale silently.

**Always pass `--format <format>` to `parse-deck` once the format is established in Step 1.** Without this, `parse-deck` defaults to `commander` and every downstream tool sees the wrong format.

### Arena Rarity Warning

The `rarity` field in hydrated card data is the **default Scryfall printing's rarity**, which drifts from Arena's actual wildcard cost. Always use `price-check --format <fmt> --bulk-data <path>` for Arena wildcard budgeting — it reports the lowest Arena-legal rarity per card by walking every Arena printing.

### Alchemy Card Warning

Alchemy includes two categories of digital-only cards beyond the Standard pool: (1) **Rebalanced cards** prefixed with `A-` (e.g., `A-Teferi, Time Raveler`) that have different oracle text from their paper counterparts, and (2) **Digital-only originals** with mechanics that only work on Arena (conjure, seek, perpetually, etc.). When building Alchemy decks, search for both `"<Card Name>"` and `"A-<Card Name>"` via `scryfall-lookup` to verify which version is legal and what its current oracle text says.

### Licensed IP Card Warning

Some crossover sets use different card names on Arena than in paper/Scryfall: Through the Omenpaths (OM1) uses `printed_name`, Godzilla/Dracula/Avatar variants use `flavor_name`. **Always pass `--bulk-data` to `mark-owned`** when working with Arena collections — this enables name aliasing so collection entries match correctly.

### AskUserQuestion Cap

The AskUserQuestion tool supports at most 4 options. If you have more than 4 choices, either present the most relevant 4 (mention others exist) or present the information as text and ask a follow-up question. When you have 5+ candidates, list **every** option in the preceding text message, then use AskUserQuestion with the top 3 as buttons plus a 4th "Other (specify in notes)" option, or skip AskUserQuestion entirely.

### Card Count Verification

After writing or editing a deck text file by hand, always parse it immediately and verify the total card count matches the format's expected size. Off-by-one errors from manual edits are common and silent. **Preventive:** before writing the deck file, tally your categories visibly in the narrative:
> - **100-card** (Commander / Historic Brawl): e.g., "Lands 36 + Ramp 10 + Draw 10 + Removal 10 + Wipes 3 + Utility 8 + Engine 18 + Wincons 4 = 99 + 1 commander = 100"
> - **60-card singleton** (Brawl): scale each category by 0.6 and round. E.g., "Lands 22 + Ramp 6 + Draw 6 + Removal 6 + Wipes 2 + Utility 5 + Engine 11 + Wincons 1 = 59 + 1 commander = 60"
> - **60-card constructed**: "Creatures 24 + Instants/Sorceries 16 + Lands 20 = 60"

### Populating `owned_cards`

When building from a user's collection, use the dedicated helper rather than inline `python3 -c`:

```
mark-owned <deck.json> <collection.json> [--bulk-data <bulk-data-path>]
```

**Always pass `--bulk-data` for Arena collections** — this enables `printed_name` and `flavor_name` aliasing so crossover cards match correctly. The script is idempotent and safe to chain after every `parse-deck` / `set-commander` call.

### Decision Table

| Task | Tool |
|------|------|
| Find format-legal cards by oracle text, type, CMC | `card-search --format <fmt> --bulk-data <path>` |
| Look up a specific card's oracle text | `scryfall-lookup "<Card Name>"` |
| See every card's oracle text / type / CMC | `card-summary <hydrated.json> [--nonlands-only\|--lands-only\|--type X]` |
| Scan the skeleton for cards matching an oracle pattern | `Grep '<regex>' <hydrated.json>` |
| Count cards / verify total matches deck size | `deck-stats <deck.json> <hydrated.json>` |
| Know which skeleton cards I own and how many | `mark-owned <deck.json> <collection.json> [--output PATH] [--bulk-data <path>]` |
| Plan wildcard spend / get per-card Arena rarity | `price-check <deck.json> --format <fmt> --bulk-data <path>` |
| Check land count, curve, category totals, avg CMC | `deck-stats <deck.json> <hydrated.json>` |
| Check mana-base health | `mana-audit <deck.json> <hydrated.json>` |
| Check format legality | `legality-audit <deck.json> <hydrated.json>` |
| Find existing combos or near-misses in the skeleton | `combo-search <deck.json> --hydrated <hydrated.json>` |
| Find combos by outcome or card name | `combo-discover --result "..." \| --card "..." [filters]` |
| Filter cards by color/oracle/type/CMC/price | `card-search --bulk-data <path> --format <fmt> [--arena-only] [filters]` |
| Price check (paper USD) | `price-check <deck.json> --bulk-data <path>` |
| Price check (Arena wildcards) | `price-check <deck.json> --format <fmt> --bulk-data <path>` |
| Research metagame/strategy | WebSearch + WebFetch (or `web-fetch` script for bot-blocked sites) |
| Export for Moxfield/Arena import | `export-deck <deck.json>` |
| Find owned, legal, commander-eligible cards from a collection | `find-commanders <collection.json> --format <fmt> --bulk-data <path> --output <working-dir>/.cache/candidates.json` |
| Populate a deck's owned_cards from an Arena Player.log | `mtga-import --bulk-data <path> --output-dir <working-dir>` |

---

## Step 1: Interview

Start by determining the format. Ask: "What format do you want to build for?"

If the user says Commander, Brawl, or Historic Brawl, follow the **Commander/Brawl Interview** below. If they name a 60-card constructed format (Standard, Pioneer, Modern, etc.), follow the **60-Card Constructed Interview**.

If the user mentions Arena without specifying a format, clarify:
- Standard, Alchemy, Historic, Timeless are Arena formats (60-card constructed)
- Standard Brawl (called "Standard Brawl" on Arena) is Brawl
- "Brawl" on Arena actually refers to Historic Brawl
- Pioneer is also on Arena but shares a card pool with paper
- Modern, PreModern, Legacy, Vintage are paper/MTGO only

### 60-Card Constructed Interview

Each answer informs the next question's options, so ask sequentially via AskUserQuestion:

1. **Format** — Which format? (Standard, Pioneer, Modern, etc.)
2. **Platform** — Arena or paper? (determines pricing mode and card pool filtering; skip if format implies it, e.g., Alchemy is always Arena)
3. **Best-of-One or Best-of-Three?** — Arena only; skip for paper. Bo1 has no sideboarding — skip sideboard construction entirely (Step 3f) and build a mainboard optimized for Game 1 resilience (more versatile cards, fewer narrow answers). Bo3 proceeds normally with full sideboard.
4. **Playstyle** — Aggro, midrange, control, combo, tempo? (brief explanations if user is unsure)
5. **Color preference** — Any color preference, or open to anything?
6. **Budget** — USD budget for paper, or wildcard budget for Arena?
7. **Archetype preference** — "Do you want to follow a proven metagame archetype, or build something original/off-meta?"
8. **Pet cards** — Any cards you definitely want to include? (open-ended text, not AskUserQuestion)

Note: questions 2-3 can sometimes be merged or skipped (paper is always Bo3; Legacy/Vintage/Modern are always paper).

#### Combo-First Path

If the user says "build around a combo" or names a specific combo/build-around card, switch to the combo-first variant:

**Step 1b-alt: Combo/Build-Around Discovery**
- If user names a card: `scryfall-lookup` it, then `combo-discover --card "<Name>" --format <fmt>`
- If user names an outcome: `combo-discover --result "<outcome>" --format <fmt>`
- If user wants to explore: Ask about mechanics, outcomes, or colors, then search
- **Supplement with WebSearch:** `combo-discover` uses Commander Spellbook, which is crowdsourced primarily by Commander players. Combos that are powerful in 1v1 60-card formats but weak in multiplayer Commander may be underrepresented. Search for `"<format> combo decks"` and `"<card name> combo <format>"` to catch format-specific interactions the API might miss.
- Present 3-5 combos with: cards, oracle text, result, color identity, popularity
- Batch-lookup all combo pieces via `scryfall-lookup --batch`
- Let user pick a combo or build-around card

### Commander/Brawl/Historic Brawl Interview

#### Commander Selection

Ask: "Do you know what commander you want to build a deck for?"

**If yes:**
- Take the commander name.
- Look up via `scryfall-lookup` to validate it exists.
- Verify it's a legal commander using Scryfall's `is:commander` filter (the source of truth for commander legality — don't try to reimplement the rules).
- For Brawl and Historic Brawl, also check that the card is legal in the deck's format using the Scryfall `legalities` field (key `standardbrawl` for Brawl, `brawl` for Historic Brawl).
- Check the commander's oracle text for partner, friends forever, or choose a background. If present, ask: "This commander supports a pairing — do you have a partner/background in mind, or would you like a recommendation?" Look up and validate the second commander the same way.
- For partner/background pairs, the deck's color identity is the combined identity of both commanders. Use the combined identity for all subsequent steps.
- Ask: "Want a standard build or go outside the box with unusual combos?"
  - **Standard:** Proceed to shared questions.
  - **Outside the box:** Proceed to shared questions, then follow the "Outside the Box" workflow (Step 2-alt) after commander analysis.

**If no:** Ask: "Want to explore standard archetypes or go outside the box with unusual combos?"

- **Standard archetypes:** Continue with the guided interview below, then standard workflow.
- **Outside the box:** Skip to the "Outside the Box" workflow (Step 1b-alt) after format selection and shared questions.

#### Commander Selection from a Collection

**If the user provides a collection export (Untapped.gg CSV, Moxfield CSV, or any deck-list export) of cards they own** and wants to pick a commander from what they already have, follow this exact procedure. Do NOT write ad-hoc Python that loads the file and calls `.get()` on it. **Note:** collection exports often contain entries with quantity 0 (tracked/wishlisted cards the user doesn't own). `parse-deck` preserves these quantities and `mark-owned` / `find-commanders` filter by `--min-quantity 1` by default, so quantity-zero entries are excluded automatically.

This narrows the candidate *pool*; it does NOT replace the guided interview. Run the interview anyway — the answers drive ranking against the narrowed pool.

**Workflow:**

0. **Arena players — ask for a collection CSV first.** If the user mentions Arena, Brawl, Historic Brawl, or wildcards, ask: "Do you have a collection export from Untapped.gg, Moxfield, or a similar tracker? A CSV with card names and quantities is the most reliable way to know what you own." If they have one, proceed to step 1. If they don't have a collection CSV, fall back to `mtga-import` as a last resort — but **warn the user**: mtga-import reconstructs a collection from saved Arena decks, which is unreliable because Arena allows building decks with unowned cards. **Always run `mtga-import` for wildcard extraction regardless** — it reads `InventoryInfo` from `Player.log` which is reliable for wildcard counts: `mtga-import --bulk-data <bulk-data-path> --output-dir <working-dir>`. This writes `wildcards.json`. Linux users need to pass `--log-path` explicitly.

1. **Parse the collection** — `parse-deck <absolute-path-to-collection.csv>` produces a parsed deck JSON. `parse-deck` handles Untapped.gg CSV, Moxfield CSV, Moxfield deck export, Arena, MTGO, and plain text.

2. **Find commander candidates** — `find-commanders <parsed.json> --bulk-data <bulk-data-path> --format <format> --output <working-dir>/.cache/candidates.json [--color-identity <ci>] [--min-quantity 1]`. **Always pass `--output`** — the default path is under `$TMPDIR` which triggers outside-workspace permission prompts. Stdout is a compact text table with columns EDHREC rank, color identity, CMC, name, type_line, flags (PARTNER / BACKGROUND / GC). The last line is `Full JSON: <path>`.

3. **Run the guided interview** (colors, playstyle, mechanics, favorite cards, play group, bracket, budget) the same as the no-collection flow. The candidate pool is the constraint; the interview answers are what differentiates one commander from another.

4. **Build a mixed shortlist of ~5 candidates**, weighted by interview answers. Do NOT just pick the 5 lowest `edhrec_rank` values — that produces boring recommendations. Aim for roughly:
   - **2 staples** — well-supported commanders (low `edhrec_rank`) that obviously fit the user's stated preferences. These exist to give the user a safe pick.
   - **2 off-meta picks** — commanders with higher or null `edhrec_rank` whose oracle text mechanically matches the interview answers (especially the mechanics question). These are usually the most interesting options.
   - **1 wildcard** — something the user probably hasn't considered: an unusual color combo they own, a partner pairing where they own both halves, or a commander that enables a combo using cards already in their collection.
   - For bracket gating, use the `game_changer` flag and your judgment about combo density. Do NOT use any "EDHREC bracket" field — community bracket data is user-reported and unreliable.

5. **Enumerate partner pairings from within the owned pool.** Walk the candidate list once: for each card with `is_partner=true`, find compatible partners from the same list. For each card with `has_background_clause=true`, find Backgrounds in the candidate list. Surface promising pairings as wildcard or off-meta picks.

6. **Present the shortlist** following the "Commander Recommendation" rules below. Mention that candidates are filtered to cards they own.

#### Format Selection (Commander/Brawl)

Ask: "What format are you building for?"

- **Commander/EDH** (default) — 100 cards, 40 life
- **Brawl** — 60 cards, Standard card pool, 25/30 life, no commander damage
- **Historic Brawl** — 100 cards (or 60 in paper), Arena/paper card pool, 25/30 life, no commander damage

**Arena naming confusion:** On MTG Arena, "Brawl" (the queue name) actually refers to Historic Brawl, and "Standard Brawl" refers to what we call Brawl. If a user says "I play Brawl on Arena," they almost certainly mean Historic Brawl. Clarify which they mean.

If Brawl or Historic Brawl: ask "Are you playing on Arena or in paper?"
- **Arena** locks deck size automatically: Standard Brawl is always 60 cards, Historic Brawl (called "Brawl" on Arena) is always 100 cards. **Arena Brawl queues are always 1v1.** This fundamentally changes deck building: prioritize speed and tempo over politics, run more cheap targeted counterspells (only 1 opponent to interact with), fewer board wipes, and a faster curve.
- **Paper Historic Brawl** only: ask if they want 100 or 60 cards. Paper Brawl can be multiplayer — use the standard interaction scaling table.

If Brawl: any legendary planeswalker can be your commander (not just those with "can be your commander" text). Vehicles and Spacecraft with power/toughness are also eligible in all formats.

**Colorless commanders in Brawl:** If the chosen commander has no colors in its color identity, note that the deck may include any number of basic lands of one chosen basic land type.

**Partner mechanics** are available in all formats.

#### Guided Interview (Commander/Brawl, one question at a time)

1. **Colors** — "What colors do you enjoy playing? (Pick any combination, or 'no preference')"

2. **Playstyle** — "What's your preferred playstyle?" Present options with brief plain-language explanations so newer players can follow:
   - Aggro (attack fast and hard)
   - Combo (assemble card combinations that win the game)
   - Control (answer threats and win late)
   - Voltron (power up your commander for lethal damage)
   - Tokens (build a wide board of creature tokens)
   - Tribal (build around a creature type)
   - Midrange/Value (generate steady incremental advantage)
   - Group Hug/Politics (make allies, share resources, influence the table)

3. **Mechanics** — "Any specific mechanics you enjoy?" Offer examples with explanations: "+1/+1 counters (growing your creatures over time), theft (stealing opponents' cards), blink (flickering creatures to reuse their effects), spellslinger (casting lots of instants and sorceries), artifacts-matter, landfall (rewards for playing lands)." Open-ended. If the answer maps to multiple distinct sub-archetypes, ask one follow-up to disambiguate.

4. **Favorite cards/sets** — "Any favorite cards or recent sets that excited you? This helps me find commanders in a similar design space."

5. **Play group dynamics** — "How does your play group typically play? (casual/competitive, combo-heavy, creature-heavy, lots of interaction)"

6. **Bracket** — "What power bracket are you targeting? (1-4, or casual/mid/high/max)"

7. **Budget** — "What's your total budget for the deck? (dollar amount, or wildcard counts for Arena)"

#### Commander Recommendation

After the guided interview, recommend 3-5 commanders that fit. Partner pairs and commander + background pairings are valid recommendations — present each pair as a single option with their combined color identity. You may use training data to generate a shortlist — this is commander *discovery*, not card evaluation, so the Iron Rule does not apply at this stage. However, every recommended commander MUST be verified via `scryfall-lookup` before presenting.

Present each recommendation with:
- Card name and color identity
- Brief explanation of why it matches the user's preferences
- EDHREC deck count (if available) to indicate community support
- Any notable budget implications

Let the user pick.

#### Shared Questions (Commander/Brawl)

Ask all of these (skipping any already answered during the guided interview):

- **Bracket:** "What power bracket are you targeting? (1-4, or casual/mid/high/max)"
- **Budget:** "What's your total budget for the deck? (dollar amount, or wildcard counts for Arena)"
- **Experience level:** "What's your Commander experience level? (beginner/intermediate/advanced)"
- **Pet cards:** "Any cards you definitely want included?" (pet cards, combos they want to build around)

For pet cards: write all pet card names to a JSON list and batch-lookup in one call: `scryfall-lookup --batch <pet-cards.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`. Verify each exists and is within the commander's color identity. Slot pet cards into the appropriate template categories — they count against those category budgets. If pet cards exceed ~10, warn the user that it limits the ability to build a balanced skeleton.

### Companion Check (60-Card Only)

After the interview, check whether the deck's constraints naturally fit a Companion. Companions are powerful (a guaranteed extra card) and should be actively considered:

1. `card-search --format <fmt> --bulk-data <path> --oracle "Companion" --type "Creature"` to find format-legal Companions
2. For each Companion, check if the user's playstyle/colors/curve naturally meet the deck-building restriction (e.g., Lurrus requires no permanents with mana value > 2 — natural for low-curve aggro)
3. If a Companion fits, suggest it: "Your deck naturally meets Lurrus's restriction — would you like to use it as a Companion? It gives you a guaranteed extra card."
4. If the user accepts, note the Companion's restriction as a hard constraint for skeleton generation
5. The Companion occupies 1 of 15 sideboard slots
6. Yorion requires an 80-card deck — use `parse-deck --deck-size 80` if selected

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
3. For Commander/Brawl: verify within commander's color identity
4. Note their role (threat, removal, engine, etc.) for skeleton slotting

---

## Step 2: Research

### 60-Card: Metagame Research

#### Proven Archetype Path

1. **WebSearch** for `"<format> metagame 2026"` or `"<format> tier list"` to find current top archetypes
2. **WebFetch** (or `web-fetch` for bot-blocked sites) the top result to get archetype names and metagame share percentages
3. Present the top 5-8 archetypes with approximate metagame share
4. If user has color/playstyle preference, highlight matching archetypes
5. Let user pick an archetype
6. **WebSearch** for `"<archetype name> <format> decklist 2026"` to find a sample list
7. **WebFetch** the sample list — this becomes the skeleton foundation. Use `web-fetch` script as fallback if WebFetch is blocked (browser headers + curl fallback).
8. If the sample list is found, parse it: `parse-deck --format <fmt> <path> --output <working-dir>/deck.json`
9. Hydrate: `scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <working-dir>/.cache`

**Fallback if no sample list is obtainable:**
- Ask the user to paste a decklist directly — most players can copy one from MTGGoldfish, Moxfield, or similar sites
- If the user can't provide one, proceed to the Original/Off-Meta path below and build from scratch using the archetype name as a guide for `card-search` queries

#### Original/Off-Meta Path

1. Use the user's playstyle, colors, and pet cards as starting constraints
2. `card-search --format <fmt> --bulk-data <path> --oracle "<keyword>" --color-identity <colors>` to find build-around cards
3. `combo-discover` for combo shells in those colors
4. WebSearch for `"<format> <archetype/mechanic> deck"` for inspiration
5. Proceed to Step 3 without a sample list foundation

#### Combo-First Path (Step 2-alt)

1. From the combo chosen in Step 1b-alt, identify the minimum shell:
   - Combo pieces (must-haves)
   - Tutors that find combo pieces (format-legal tutors via `card-search`)
   - Protection for combo assembly (counterspells, discard, hexproof)
2. Identify the best colors (combo colors + support card availability)
3. Proceed to Step 3-alt

### Commander: Commander Analysis

1. **Scryfall lookup** — Run: `scryfall-lookup "<Commander Name>"`

   Read the full oracle text, color identity, CMC, and types. For partner/background pairs, look up both commanders and note how they interact with each other.

2. **EDHREC research** — Run: `edhrec-lookup "<Commander Name>"`

   For partner commanders: `edhrec-lookup "<Commander 1>" "<Commander 2>"`

   Review top cards, high synergy cards, and themes. **Brawl/Arena note:** EDHREC data is sourced from Commander/EDH decks. For Brawl/Historic Brawl, EDHREC recommendations must be legality-checked against the deck's format before including. For Arena decks, also verify cards exist on Arena.

3. **Web research** — Use `WebSearch` for the commander + "deck tech", "strategy", "guide". Use `WebFetch` or the helper script to read strategy articles:

   Run: `web-fetch "<url>" --max-length 10000`

4. **Strategy synthesis** — Summarize the commander's key mechanics, primary strategies, and synergy axes. For partner/background pairs, identify how both commanders contribute to the strategy and where their mechanics overlap or complement each other. Present to the user for validation. If the user defers or has no preference, default to the commander's most popular theme on EDHREC and move forward.

The goal is building enough understanding to make smart category fills — not deep analysis (the tuner handles that).

#### EDHREC Fallback

If EDHREC has no data for the commander (new or obscure cards), fall back to:

1. **Local bulk data search** — Use `card-search` to find cards that mechanically synergize with the commander's keywords/oracle text within the commander's color identity. For Arena decks, use `--arena-only`. For paper Brawl, use `--paper-only` to exclude Arena-only digital cards.
2. **EDHREC theme/archetype data** — Look up the commander's archetype rather than the specific commander. For Brawl/Historic Brawl, legality-check suggestions against the deck's format.
3. **Format staples** — Fill remaining slots with well-known staples for the color identity and bracket.

### Outside the Box Path (Commander Only)

#### Step 1b-alt: Mechanics/Outcome Interview (no commander known)

Ask (accepting either or both):
- "What mechanics excite you?" (open-ended — map to `card-search` oracle patterns and `combo-discover --card` queries)
- "What kind of outcome do you want?" (map to `combo-discover --result` query, e.g., "infinite tokens", "infinite mana", "mill entire library")
- "Color preferences?" (or "no preference")
- "How obscure do you want to go?" (somewhat unusual / very obscure / wildest thing you can find)
- "How many cards can your combo use?" (tight 2-3 card combos / allow bigger combos / full Rube Goldberg)

**Two discovery strategies based on user input:**
1. **Mechanics-first:** Use `card-search` with oracle text to find cards matching mechanics, then feed card names to `combo-discover --card "X" --card "Y"`
2. **Outcome-first:** Use `combo-discover --result "Infinite X"` directly
3. **Both:** Combine `--result` and `--card` filters

**Obscurity to popularity mapping:**
- Somewhat unusual: `--sort -popularity`, skip top results, popularity 1000-10000
- Very obscure: `--sort popularity`, skip 0s, popularity 100-1000
- Wildest thing: `--sort popularity`, popularity 0-100

**Jankiness to max combo size:**
- Tight: filter to combos with 3 or fewer cards
- Allow bigger: 4-5 cards
- Full Rube Goldberg: no limit

#### Step 2-alt: Combo Discovery (both paths)

For **commander known + outside the box:** use `combo-discover --color-identity <commander-CI>` to constrain to the commander's colors.

Before presenting, write all combo piece names across all combos to a JSON list and batch-lookup in one call: `scryfall-lookup --batch <combo-pieces.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`.

Present 3-5 interesting combos with:
- Cards involved and oracle text (from the batch-lookup results)
- What the combo produces
- Color identity
- Popularity score (lower = more obscure)
- Number of cards (jankiness indicator)
- For each combo piece: note standalone utility. Combo pieces that are dead outside the combo are a risk — flag them.

Ask: "Want to build around one of these, or combine multiple?" If combining, verify color identities are compatible.

#### Step 2b-alt: Commander Fitting (skip if commander already known)

Two-wave search for each selected combo:
1. **Mechanical fit:** `card-search --is-commander --color-identity <combo-CI> --oracle "<combo-keyword>"` — commanders whose oracle text mentions the combo's mechanics
2. **Strategic fit:** Use training data to shortlist commanders providing tutoring, draw, recursion, or protection in the combo's color identity. Write all shortlisted names to a JSON list and batch-lookup: `scryfall-lookup --batch <fit-candidates.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache` (Iron Rule applies).

Also check if any combo piece IS a legendary creature that could be the commander.

Present 2-3 commander options with:
- How the commander mechanically supports the combo
- Whether the commander adds a secondary strategy axis
- EDHREC data if available (may be sparse for obscure commanders)

User picks a combo + commander pairing.

---

## Step 3: Skeleton Generation

### 60-Card Constructed

#### Starting Point

- **Proven archetype with sample list:** Customize the sample list based on user preferences, budget, and pet cards. This is modification, not from-scratch building.
- **Original/off-meta or combo-first:** Build from scratch using the template below.

#### Category Template (60-card mainboard)

| Category | Typical Count | Notes |
|----------|--------------|-------|
| Threats/Creatures | 12-28 | Varies hugely by archetype (aggro: 28, control: 4-8) |
| Removal/Interaction | 4-12 | Format-dependent; more in slower formats |
| Card Advantage | 4-8 | Draw spells, planeswalkers, selection |
| Utility/Flex | 2-8 | Archetype-specific support |
| Lands | 20-27 | Constructed land formula (see below) |

**These counts are guidelines, not rules.** Aggressive decks skew toward threats; control decks skew toward interaction and card advantage. The archetype defines the balance.

#### Land Count Formula

Use the constructed land target formula:
- **Baseline:** 24 lands for a 60-card deck
- **Ramp adjustment:** -1 land per 2 ramp/mana-acceleration cards
- **Curve adjustment:** Low curve (avg CMC < 2.5) -> fewer lands; high curve (avg CMC > 3.5) -> more lands
- **Clamp:** Never below 20, never above 27

Run `mana-audit` after building to verify.

#### Land Base Composition

| Land Type | Budget | Mid-Range | High-End |
|-----------|--------|-----------|----------|
| Basics | 10-16 | 6-10 | 2-6 |
| Dual lands (shock, fast, check) | 4-8 | 8-12 | 8-12 |
| Fetch lands | 0 | 0-4 | 8-12 |
| Utility lands | 0-2 | 2-4 | 2-4 |

For Arena formats: Khans fetchlands are available (Pioneer and up), but Zendikar/Onslaught fetches are not. Use the Arena-available mana base (shock lands, fast lands, pathway lands, triomes, Khans fetches for Pioneer/Historic/Timeless).

#### Color Fixing Guidance (60-Card)

The land count formula gives a total, but the color *mix* matters just as much. Use `mana-audit` output (pip demand % vs. land production %) to verify, and follow these rules of thumb:

- **Mono-color:** All basics (plus 2-4 utility lands). Easiest mana base.
- **2-color:** Match land production to pip demand. If the deck is 60% red pips / 40% white pips, aim for roughly 60/40 red/white sources. A mix of ~8 dual lands + basics in the dominant color usually works.
- **3+ colors:** Basics alone can't support 3 colors reliably. Dual lands become near-mandatory. Budget permitting, prioritize lands that produce 2+ of your colors untapped (shock lands, fast lands, triomes). The common trap is running too many basics in a 3-color deck — if `mana-audit` flags a color deficit >5%, replace basics with duals that produce the deficient color.
- **Splash color (5-8 pips):** 4-6 sources of the splash color is usually enough. Pathway lands or dual lands that also produce a main color are ideal.
- **Untapped sources on key turns:** Aggro decks need nearly all lands untapped on turns 1-3. Control decks can tolerate more tapped lands since they operate at higher CMC.

#### Filling Process (60-Card)

For each category:
1. If starting from a sample list, evaluate what's already there
2. `card-search --format <fmt> --bulk-data <path> --oracle "<pattern>" --color-identity <colors>` for candidates
3. `scryfall-lookup --batch` to verify oracle text of all candidates
4. Filter by budget (paper: price; Arena: wildcard rarity)
5. Include pet cards in their appropriate categories
6. Prioritize format staples and proven performers

#### 4-of vs. Fewer Copies

- **4 copies:** Cards you want every game, core to the strategy
- **3 copies:** Strong cards you want most games but don't need multiples
- **2 copies:** Situational cards, legendary permanents, curve-toppers
- **1 copy:** Silver bullets, tutored targets, high-impact singletons

#### Step 3f: Build Sideboard (Bo3 Only)

The sideboard is 15 cards designed to improve matchups after Game 1.

**Process:**
1. Identify the top 3-5 archetypes in the metagame (from Step 2 research)
2. For each bad matchup, allocate 2-4 sideboard slots:
   - Anti-aggro: life gain, cheap removal, board wipes
   - Anti-control: cheap threats, counterspells, card advantage
   - Anti-combo: disruption, counterspells, graveyard hate
   - Anti-graveyard: `card-search --format <fmt> --bulk-data <path> --oracle "exile.*graveyard"`
   - Anti-artifact/enchantment: `card-search --format <fmt> --bulk-data <path> --oracle "destroy.*artifact"`
3. Prefer versatile cards that help in multiple matchups
4. Verify all sideboard cards are format-legal via `scryfall-lookup`

**Sideboard card counts:**
- 2-3 copies of narrow hate cards (graveyard hate, artifact removal)
- 3-4 copies of flexible answers (extra removal, counterspells)
- 1-2 copies of alternative win conditions or transformative cards

#### Combo-First Skeleton (Step 3-alt, 60-Card)

- Slot combo pieces first (must-haves)
- Use `card-search` to find: tutors that find combo pieces, protection for combo assembly, redundant effects
- Fill remaining categories (threats, removal, card advantage, lands) around the combo core
- Standard structural verification applies

### Commander/Brawl/Historic Brawl

#### Default Template

Card counts scale with deck size. The base counts below are for 100-card decks; for 60-card decks, multiply each count by 0.6 and round to the nearest integer.

| Category | 100-card | 60-card | Notes |
|----------|----------|---------|-------|
| Commander(s) | 1-2 | 1-2 | Already selected |
| Lands | 36-38 | 22-23 | Burgess formula scaled: `round((31 + colors + cmc) * deck_size / 100)` |
| Ramp | 10 | 6 | Mana rocks, dorks, land-fetch spells |
| Card draw | 10 | 6 | Prefer draw that aligns with strategy |
| Targeted removal/disruption | 5-12 | 3-7 | Scaled to bracket |
| Board wipes | 2-5 | 1-3 | Scaled to bracket |
| Win conditions | 3-5 | 2-3 | Cards that close out a game |
| Engine/synergy pieces | 15-20 | 9-12 | Cards that work with the commander |
| Protection/utility | 8-10 | 5-6 | Counterspells, hexproof, recursion |

#### Template Flexibility

The category counts above are defaults — adjust them after strategy validation to match the user's confirmed direction. Examples:

- **Voltron:** Increase protection/utility, shift engine slots toward equipment/auras
- **Combo:** Increase card draw and win conditions, add tutor slots
- **Aggro/tokens:** Reduce board wipes (they hurt you too), increase engine pieces
- **Control:** Increase interaction across the board, reduce engine pieces
- **Group hug/politics:** Reduce targeted removal, add political tools to utility

**Hard constraints that don't flex:** Lands and ramp stay at Burgess formula minimums regardless of strategy. Total card count must match the deck's expected size (100 for Commander/Historic Brawl, 60 for Brawl, or the user's specified size).

#### Land Base Composition (Commander/Brawl)

The land count comes from the Burgess formula, but composition matters. Guidelines:

- **Basics:** Enough to be fetched by ramp spells (Cultivate, Kodama's Reach, etc.) and not punished by Blood Moon/Back to Basics. Mono/two-color decks lean heavier on basics.
- **Color fixing:** Scale to budget and color count:
  - **Budget ($25-75):** Gain lands, temples (scry lands), tri-lands, check lands, pain lands
  - **Mid ($75-200):** Add filter lands, battle lands, pathway lands, talismans
  - **High ($200+):** Shocks, fetches, original duals if budget allows
- **Arena wildcard tiers:** For Arena decks, ignore dollar tiers and budget by wildcard rarity:
  - **Tight on wildcards:** Lean on uncommon lands (gain lands, check lands, surveil lands, tri-lands). Accept some tapped lands.
  - **Moderate wildcards:** Add rare untapped duals (shocks, fast lands, bond lands) for the most important color pairs.
  - **Plenty of wildcards / high bracket:** Full suite of rare untapped duals, Cavern of Souls if tribal, fetch lands if in format.
- **Utility lands (2-4):** Lands that synergize with the strategy. Don't overload — utility lands that enter tapped or produce colorless hurt consistency. **In mono-color and 2-color decks, avoid colorless-only utility lands** unless their utility directly supports the commander's strategy.
- **Command Tower:** Auto-include in 2+ color decks. **In mono-color, Command Tower is strictly worse than a basic** — it can't be fetched by ramp spells and doesn't have the basic land type. Use a basic instead.
- **Sol Ring:** Auto-include in Commander/EDH on paper. Not legal in Brawl or Historic Brawl.

Run `mana-audit` after filling to verify color balance.

#### Interaction Scaling by Bracket

Based on Command Zone #658 (2025), EDHREC, and MTGGoldfish guidelines:

| Category | Bracket 1-2 (Casual) | Bracket 3 (Upgraded) | Bracket 4 (Optimized) |
|----------|----------------------|----------------------|----------------------|
| Targeted removal/disruption | 5-7 | 8-10 | 10-12 |
| Board wipes | 2-3 | 3-4 | 4-5 |
| Total interaction | 8-10 | 12-14 | 15-18 |

"Disruption" includes counterspells, discard, and stax pieces — not just creature/artifact removal. Extra interaction slots come out of the engine/synergy budget.

#### Filling Process (Commander/Brawl)

**Wildcard-constrained path (Arena, under 10 combined rare + mythic wildcards):** When the user's rare + mythic wildcard budget totals less than 10, **invert the fill strategy**. Instead of drafting ideal cards and checking ownership after, search the user's collection for owned cards that fit each category first. Only spend wildcard slots on commons and uncommons that fill critical gaps.

**Category fill order matters.** Fill foundational categories first:

1. **Lands** (cheapest to fill, most important to get right)
2. **Ramp**
3. **Card draw**
4. **Targeted removal and board wipes**
5. **Protection/utility**
6. **Engine/synergy pieces**
7. **Win conditions**

**Per category:**

1. Pull candidates from EDHREC high-synergy and top cards for this commander. Supplement with `card-search` to find synergistic cards EDHREC may not surface. For Arena decks, use `--arena-only` and omit `--price-max`. For paper Brawl, use `--paper-only` to exclude Arena-only digital cards.
2. **Batch-lookup oracle text for all candidates** — write candidate names to a JSON list, then run: `scryfall-lookup --batch <candidates.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`. Run `card-summary <cache_path>` to see a compact table. Only `Read` the full cache file for the ~3-5 candidates you're actually deciding between, using `offset`/`limit`.
3. Filter by budget (cheapest printings, track running price total). For Arena, track wildcard rarity counts instead.
4. Filter by bracket (avoid Game Changers above target bracket).
5. Weight by interview preferences.
6. Weight by commander synergy (from the analysis step).
7. Include any pet cards the user requested.
8. Fill remaining slots with format staples appropriate to the color identity and budget.

#### Combo-First Skeleton (Step 3-alt, Commander)

- Slot combo pieces first (they're the deck's reason to exist)
- Use `card-search` to find supporting cards: tutors that find combo pieces, protection for combo pieces, redundant effects
- Note which combo pieces pull double duty vs. which are dead outside the combo
- Fill remaining categories (ramp, draw, removal, lands) weighted toward the combo's mechanics
- Standard structural verification applies

---

## Step 4: Structural Verification

Run all four checks in order. If any fail, fix and re-check from the top. Re-hydrate after any deck edit.

### 1. Legality Audit (must PASS)

```
legality-audit <deck.json> <hydrated.json>
```

Checks: format legality, copy limits (singleton for Commander/Brawl; 4-of rule + Vintage restricted for constructed), sideboard size (max 15 for constructed), deck minimum. Fix any violations before proceeding.

**Commander/Brawl note:** Historic Brawl bans many Commander staples (Sol Ring, Skullclamp, Hour of Reckoning, Triumph of the Hordes, etc.) that look like obvious includes if you're thinking in Commander terms — this check catches them. Color-identity violations typically mean a card slipped past the commander's identity gate.

### 2. Price Check (must be within budget)

```
# Paper
price-check <deck.json> --budget <budget> --bulk-data <path>

# Arena
price-check <deck.json> --format <fmt> --bulk-data <path>
```

If over budget, substitute expensive cards with budget alternatives. Re-run after changes. For Arena, "most expensive" means highest rarity — swap rare cards for uncommon alternatives. Watch the `illegal_or_missing` warning line for cards that escaped the legality audit.

### 3. Deck Stats (verify counts)

```
deck-stats <deck.json> <hydrated.json>
```

Verify: total card count matches expected size, land count matches formula target, category distribution looks reasonable, sideboard count (0-15 for constructed).

### 4. Mana Audit (must PASS or WARN)

```
mana-audit <deck.json> <hydrated.json>
```

Uses the Burgess/Karsten formula for Commander/Brawl, constructed land formula for 60-card formats. Checks land count and color balance. FAIL means the mana base needs fixing before proceeding.

**This is a gate — do not present a skeleton that fails any of these checks.** If any check fails and you edit the deck to fix it, re-parse, re-run `scryfall-lookup --batch` to refresh the hydrated cache, and re-run ALL checks from the top.

---

## Step 5: Present Skeleton

### 60-Card Constructed Presentation

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

**Sideboard (Bo3 only):**

```
## Sideboard (15)
3 Roiling Vortex — vs. free spells, lifegain decks
2 Rampaging Ferocidon — vs. token/lifegain strategies
3 Smash to Smithereens — vs. artifact-heavy decks
...
```

### Commander/Brawl Presentation

Present organized by the builder's categories (lands, ramp, card draw, removal, board wipes, win conditions, engine/synergy, protection/utility). Include brief notes on why key synergy cards were included.

### Summary Block

```
Mainboard: 60 cards | Lands: 20 | Avg CMC: 1.85
Sideboard: 15 cards
Budget: $45.20 / $50.00 (paper) or 2M/4R/8U/12C (Arena wildcards)
```

For Commander/Brawl, show:
- Total card count
- Land count and Burgess formula target
- Total estimated cost vs. budget (USD for paper, wildcard table for Arena)
- Category breakdown

For Arena decks, present a wildcard cost table:

> | Rarity | Skeleton Cost | Budget | Remaining |
> |--------|--------------|--------|-----------|
> | Mythic | X | Y | Z |
> | Rare | X | Y | Z |
> | Uncommon | X | Y | Z |
> | Common | X | Y | Z |

### Ask for Adjustments

Present the skeleton and ask: "Want to make any adjustments before I hand this off for tuning?"

If the user requests changes, apply them, re-run structural verification, and present again.

---

## Step 6: Hand Off to Deck-Tuner

### Write Output Files

1. Deck JSON: `<working-dir>/<deck-name>.json`
2. Moxfield export: `export-deck <deck.json>` -> `<working-dir>/<deck-name>-moxfield.txt`
3. Hydrated cache already at `<working-dir>/.cache/hydrated-<sha>.json`

### Invoke the Tuner

Invoke via the Skill tool (not by telling the user to type a slash command):

```
Skill(skill: "deck-tuner", args: "<carry-forward context>")
```

If the Skill tool reports that the tuner is not installed, fall back to telling the user:

> "I recommend installing the deck-tuner skill to refine this deck further. The skeleton is a playable starting point, but tuning will significantly improve it."

Only print this fallback when the Skill tool actually fails — never as the default path.

### Carry-Forward Context (60-Card Constructed)

Include in the args:
- **Format** and platform (Arena/paper)
- **Bo1 or Bo3** (Arena only; determines whether sideboard tuning applies)
- **Budget:** total budget, skeleton cost, remaining for upgrades
- **Owned cards** (if collection was provided; don't count toward budget)
- **Experience level**
- **Suggested max swaps:** 15-20 for a fresh skeleton (user can adjust)
- **Pain points:** "Freshly generated skeleton — general optimization" or specific concerns
- **Archetype:** name and brief description of the deck's game plan
- **Companion** (if one was selected, name it and its restriction)
- **File paths:** deck JSON, hydrated cache, Moxfield export

### Carry-Forward Context (Commander/Brawl)

Include in the args:
- Bracket target
- **Total budget** and **amount spent on skeleton**. For paper: "Total budget: $500, skeleton cost: $406, remaining for upgrades: $94". For Arena: "Total wildcard budget: 4M/10R/15U/40C, skeleton cost: 2M/8R/12U/30C, remaining: 2M/2R/3U/10C" (compact notation: M=mythic, R=rare, U=uncommon, C=common).
- Any cards the user already owns (these should not count toward either budget figure)
- Experience level
- Suggested max swaps: 20 (user can adjust during tuner intake)
- Format, deck size, and **Arena or paper** (e.g., "Format: historic_brawl, deck size: 100, Arena")
- Pain points: "This is a freshly generated skeleton — general optimization is the goal"
- **File paths:** deck JSON, hydrated cache, Moxfield export

---

## Red Flags

| Thought | Reality |
|---------|---------|
| "I know what this card does" | You don't. Look it up. Training data is not oracle text. |
| "This is a format staple, auto-include" | Verify format legality + oracle text + price. |
| "EDHREC recommends it so it must be good here" | EDHREC is aggregated data, not analysis. Evaluate for THIS build. |
| "This card is generally good in Commander" | Generic staples aren't always right. Check synergy with THIS commander. |
| "The sideboard can wait" | Sideboard is half the competitive advantage. Build it now. (60-card) |
| "The user said aggro, so 20 lands" | Run the formula. Verify with mana-audit. |
| "I'll just use the sample list as-is" | Customize for budget, pet cards, and user preferences. |
| "Skip structural verification, it looks right" | Tools catch errors humans miss. Run them. |
| "This card is cheap on paper so it's fine for Arena" | Paper price != Arena rarity. Use price-check. |
| "We're over budget but this card is too good to skip" | Budget is a hard constraint. Find a cheaper alternative. |
| "I'll just fill the rest with staples" | Every card should have a reason. Staples are a last resort, not a shortcut. |
| "The mana base is probably fine" | Run `mana-audit`. Don't eyeball mana bases. |
| "This step seems unnecessary for this deck" | Follow every step. The process exists because shortcuts cause mistakes. |
| "I can skip oracle text verification for well-known cards" | No. Look up every card. Even Sol Ring has oracle text worth reading. |

---

## Experience Level Adaptation

| Aspect | Beginner | Intermediate | Advanced |
|--------|----------|--------------|----------|
| Interview | Explain all terms, give examples | Use terms with brief context | Use shorthand |
| Recommendations | Explain why each card matters | Focus on synergy highlights | Category list with brief notes |
| Strategy | Explain what the strategy does and why | Explain key interactions | Name the archetype and key cards |
| Presentation | Narrative walkthrough of the deck | Grouped by category with notes | Concise tables |

---

## Script Reference

- `parse-deck --format <fmt> <path> [--output <path>] [--deck-size <N>]` — Parse deck list with sideboard
- `scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <dir>` — Hydrate all card data
- `scryfall-lookup "<Card Name>" --bulk-data <path>` — Single card lookup
- `card-search --format <fmt> --bulk-data <path> [--oracle <regex>] [--color-identity <CI>] [--type <type>] [--cmc-max <N>] [--price-max <N>] [--arena-only] [--paper-only] [--is-commander]` — Search for candidates
- `card-summary <hydrated.json> [--nonlands-only] [--lands-only] [--type <T>] [--deck <deck.json> --sideboard]` — Card table display
- `combo-discover [--card "<name>"] [--result "<outcome>"] [--format <fmt>] [--color-identity <CI>] [--sort <field>]` — Find combos
- `combo-search <deck.json> [--hydrated <hydrated.json>]` — Find existing combos and near-misses
- `edhrec-lookup "<Commander Name>" ["<Partner Name>"]` — EDHREC data for commander
- `legality-audit <deck.json> <hydrated.json>` — Check legality, copy limits, sideboard, deck minimum
- `mana-audit <deck.json> <hydrated.json>` — Land count and color balance
- `price-check <deck.json> [--format <fmt>] --bulk-data <path> [--budget <N>]` — Budget check
- `deck-stats <deck.json> <hydrated.json>` — Baseline stats
- `build-deck <deck.json> <hydrated.json> [--cuts <c.json>] [--adds <a.json>] [--sideboard-cuts <sc.json>] [--sideboard-adds <sa.json>] [--bulk-data <path>]` — Apply changes
- `deck-diff <old.json> <new.json> <old-hyd.json> <new-hyd.json>` — Compare deck versions
- `export-deck <deck.json>` — Moxfield/Arena import format with sideboard
- `mark-owned <deck.json> <collection.csv> [--bulk-data <path>] [--output <path>]` — Mark owned cards
- `find-commanders <collection.json> --format <fmt> --bulk-data <path> --output <path> [--color-identity <ci>] [--min-quantity <N>]` — Find commander candidates from collection
- `set-commander <deck.json> "<Card Name>"` — Move card to commanders zone
- `mtga-import --bulk-data <path> --output-dir <dir> [--log-path <path>]` — Import Arena collection/wildcards
- `download-bulk --output-dir <dir>` — Download Scryfall bulk data
- `web-fetch "<url>" [--max-length <N>]` — Fetch web page with browser headers
