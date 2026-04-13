---
name: deck-tuner
description: Analyze and optimize MTG decks across all formats — Commander/EDH, Brawl, Historic Brawl, Standard, Alchemy, Historic, Pioneer, Timeless, Modern, PreModern, Legacy, and Vintage.
compatibility: Requires Python 3.12+ and uv. Shares mtg_utils package via symlink.
license: 0BSD
---

# Deck Tuner

Structured process for analyzing and tuning MTG decks across all formats. Covers 100-card singleton formats (Commander, Brawl, Historic Brawl) and 60-card constructed formats with sideboards (Standard, Alchemy, Historic, Pioneer, Timeless, Modern, PreModern, Legacy, Vintage). Every recommendation MUST be grounded in actual card oracle text from Scryfall — never from training data.

## The Iron Rule

**NEVER assume what a card does.** Before referencing any card's abilities, look up its oracle text via the helper scripts. Training data is not oracle text.

---

## Progress Tracking

**Before starting Step 1, create a `TodoWrite` list with one item per top-level Step in this skill, in order:**

1. Step 1: Parse Deck List
2. Step 2: Hydrate Card Data
3. Step 3: Baseline Metrics
4. Step 4: User Intake
5. Step 5: Research
6. Step 6: Strategy Alignment
7. Step 7: Commander Interaction Audit *(Commander/Brawl/Historic Brawl only — skip for 60-card constructed)*
8. Step 8: Analysis
9. Step 9: Pre-Grill Verification
10. Step 10: Self-Grill
11. Step 11: Propose Changes
12. Step 12: Impact Verification
13. Step 13: Close Calls
14. Step 14: Finalize

Mark each item `in_progress` the moment you begin it and `completed` the moment it finishes — **do not batch updates**. The user relies on this list as a live progress indicator; batching defeats the point.

**Step 8 and Step 10 are long enough that the top-level item alone leaves the user staring at an unchanging list.** When you reach them, expand each into sub-todos *at that moment* (not up front):

- **Step 8** sub-todos: 8a Mana Base & Curve Audit, 8b Interaction & Threat Audit, 8c Archetype Coherence, 8d Draft Cuts, 8e Draft Additions, 8f Sideboard Evaluation (60-card only), 8g Swap Balance Check.
- **Step 10** sub-todos: Dispatch Proposer + Challenger Subagents, Process Challenger Report, Revise Proposal.

Do NOT create per-card sub-todos for the Cut Checklist inside Step 8 — that's execution detail and would flood the list.

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

**Use the Write tool** for any JSON file containing card names. Apostrophes in names break shell quoting. Write tool permissions are cacheable; `python3 -c "..."` re-prompts every time.

Do NOT write JSON via Bash heredocs (`cat > /tmp/foo.json << 'JSONEOF' ... JSONEOF`). Heredocs are functionally fine but they produce un-cacheable Bash permission patterns: Claude Code's permission engine bakes the heredoc body into the allow pattern, so every invocation with different content re-prompts the user. The Write tool generates a single `Write(/tmp/**)` permission that can be granted once and reused.

**The same caching trap applies to `python3 -c "..."`, `awk '...'`, `jq '...'`, and any other Bash pattern where the code body varies between invocations.** Each unique body is a fresh permission pattern. If you need to extract one field from a JSON file, prefer: (a) passing the file directly to a script that already knows how to parse it, (b) `Read` with `offset`/`limit` on the JSON file, or (c) `Grep` on the file. Reach for `python3 -c` only when those options genuinely don't cover the case, and accept the re-prompt cost when you do.

### Scratch File Paths

Reuse these stable paths within a session: `/tmp/cuts.json`, `/tmp/adds.json`, `/tmp/sideboard-cuts.json`, `/tmp/sideboard-adds.json`, `/tmp/candidates.json`.

**Critical:** Files at `/tmp/` persist across sessions. Always `Read` a scratch file before the first `Write` in a new session.

**Warning — `/tmp` files persist across sessions.** The Write tool requires a prior `Read` for any existing file, so the first `Write` to a reused `/tmp/*.json` path in a new session fails with *"File has not been read yet"*. If you batched that `Write` in parallel with a Bash call that reads the same file, **the Bash silently consumes the stale prior-session content** — the parallel Write error doesn't block the Bash, so `cut-check` / `scryfall-lookup --batch` / `price-check` / `build-deck` will happily run against the wrong data. Symptom: tool results list cards you never proposed. **Rule:** (a) at session start, `Read` each scratch path you plan to reuse before the first `Write`, OR (b) run `Write` sequentially (not parallel) and verify success before the dependent Bash call. Never batch `Write(/tmp/foo.json)` + `Bash(tool reading /tmp/foo.json)` in a single message. If a tool result lists cards that don't match your intended input, suspect stale-file consumption before suspecting a tool bug.

### Alchemy Card Warning

Alchemy includes two categories of digital-only cards beyond the Standard pool: (1) **Rebalanced cards** prefixed with `A-` (e.g., `A-Teferi, Time Raveler`) that have different oracle text from their paper counterparts, and (2) **Digital-only originals** with mechanics that only work on Arena (conjure, seek, perpetually, etc.). When tuning Alchemy decks, search for both `"<Card Name>"` and `"A-<Card Name>"` via `scryfall-lookup` to verify which version is legal and what its current oracle text says.

### AskUserQuestion Cap

The AskUserQuestion tool supports at most 4 options. If you have more than 4 choices (common in Step 13 close calls), either present the most relevant 4 (mention others exist) or present the information as text and ask a follow-up question.

**AskUserQuestion caps at 4 options — never silently drop the rest.** The tool's schema rejects more than 4 options per question. When presenting a longer list (5+ close-call swaps, 5 alternative commanders, etc.), do NOT pick 4 and hide the rest. List **every** option in the preceding text message with enough detail to decide on, then use AskUserQuestion only as a lightweight picker — either (a) put the top 3 on buttons plus a 4th "Other (specify in notes)" so the user can name any option from the text list, or (b) skip AskUserQuestion entirely for that decision and let the user reply in plain text. The failure mode to avoid is 4 option chips that look like the complete set when the text above mentioned 5+.

### Path Requirements

- **Absolute paths only.** `uv` rebases the working directory to the skill install.
- **Cache directory:** Always `<working-dir>/.cache`, not the skill install directory.
- **Re-hydration:** After every deck edit, re-run `scryfall-lookup --batch`. The cache is SHA-keyed; old caches go stale silently.

### Arena Rarity Warning

The `rarity` field in hydrated card data is the Scryfall default printing's rarity, which drifts from Arena's actual wildcard cost. Always use `price-check --format <fmt> --bulk-data <path>` for Arena wildcard budgeting.

### Licensed IP Card Names

Some crossover sets use different card names on Arena than in paper/Scryfall: Through the Omenpaths (OM1, the Arena version of Marvel's Spider-Man), Ikoria Godzilla variants, Crimson Vow Dracula variants, and Avatar: The Last Airbender cards all have name discrepancies. **Always pass `--bulk-data` to `mark-owned`** when working with Arena collections — this enables `printed_name` and `flavor_name` aliasing so cards like "Skittering Kitten" (Arena name) correctly match "Masked Meower" (Scryfall name). Without `--bulk-data`, these cards silently appear unowned.

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
  "owned_cards": [{"name": "Lightning Bolt", "quantity": 4}, ...]
}
```

Commander formats use `commanders` and have no `sideboard`:

```json
{
  "format": "commander",
  "deck_size": 100,
  "commanders": [{"name": "...", "quantity": 1}, ...],
  "cards": [{"name": "...", "quantity": 1}, ...],
  "total_cards": 100,
  "owned_cards": [{"name": "...", "quantity": 1}, ...]
}
```

All card lists (`commanders`, `cards`, `sideboard`, `owned_cards`) share the `[{name, quantity}]` shape. `owned_cards` starts empty from `parse-deck` and is populated by `mark-owned`. `price-check` reads it to subtract owned copies from the budget; entries with `quantity < 1` are treated as "not owned."

### Decision Table

| Task | Tool |
|------|------|
| Find format-legal cards by oracle text, type, CMC | `card-search --format <fmt> --bulk-data <path>` |
| Look up a specific card's oracle text | `scryfall-lookup "<Card Name>"` |
| View card table (mainboard) | `card-summary <hydrated.json> [--nonlands-only] [--lands-only] [--type <T>]` |
| View card table (sideboard) | `card-summary <hydrated.json> --deck <deck.json> --sideboard` |
| Scan the deck for cards matching an oracle pattern | `Grep '<regex>' <hydrated.json>` — full oracle text, no truncation |
| Count cards / verify total matches deck size | `deck-stats <deck.json> <hydrated.json>` |
| Find combos in the deck | `combo-search <deck.json> --hydrated <hydrated.json>` |
| Find combos by card or outcome | `combo-discover --card "<Name>" --format <fmt>` |
| Check whether a proposed cut breaks a near-miss | `Grep '<cut-name>' <combo-search.json>` to find near-miss lines where this card appears as a partner |
| Check deck legality | `legality-audit <deck.json> <hydrated.json>` |
| Check mana base health | `mana-audit <deck.json> <hydrated.json>` |
| Compare mana before/after | `mana-audit <old.json> <old-hyd.json> --compare <new.json> <new-hyd.json>` |
| Price check (paper) | `price-check <deck.json> --bulk-data <path>` |
| Price check (Arena wildcards) | `price-check <deck.json> --format <fmt> --bulk-data <path>` |
| Apply mainboard + sideboard changes | `build-deck <deck.json> <hyd.json> --cuts <c.json> --adds <a.json> --sideboard-cuts <sc.json> --sideboard-adds <sa.json>` |
| Compare deck versions | `deck-diff <old.json> <new.json> <old-hyd.json> <new-hyd.json>` |
| Export for import | `export-deck <deck.json>` |
| Mark owned cards from collection | `mark-owned <deck.json> <collection.csv> [--bulk-data <path>]` |
| Know which deck cards I own and how many | `mark-owned <deck.json> <collection.json> [--output PATH] [--bulk-data <path>]` |
| Plan wildcard spend / get per-card or aggregate Arena rarity | `price-check <deck.json> --format <fmt> --bulk-data <path>` |
| Get a card's Arena-lowest rarity | `price-check --format <fmt>` (never the hydrated cache `rarity` field) |
| Find owned, legal, commander-eligible cards from a collection | `find-commanders <collection.json> --format <fmt> --bulk-data <path> --output <working-dir>/.cache/candidates.json` |
| Research metagame/strategy | WebSearch + WebFetch (or `web-fetch` script) |
| Run the self-grill (Step 10 hard gate) | Two parallel `Agent` calls with `subagent_type: "general-purpose"` |

Only write `python3 -c` when none of these cover the need. When you do, batch every related question into a single body — each unique body is a fresh permission pattern, so one big script beats five small ones.

**Parsed deck JSON is the canonical pipeline intermediate.** Once you have a parsed deck JSON from `parse-deck`, pass it **directly** to `scryfall-lookup --batch` and `price-check` — both scripts accept a parsed deck JSON as `<path>`, not just a JSON list of name strings. Do NOT extract card names into a separate `/tmp/*.json` via `python3 -c` or similar. (The exception is scripts whose input is a *subset* of the deck — `cut-check --cuts <path>` and `build-deck --cuts <path> --adds <path>` expect JSON lists of name strings, not parsed deck JSON, because the caller is specifying which cards to act on. Writing a small `/tmp/cuts.json` via the Write tool is correct in those cases.)

---

## Step 1: Parse Deck List

```
parse-deck <path> --format <format> --output <working-dir>/deck.json
```

- Auto-detects input format (Moxfield, MTGO, Arena, plain text, CSV)
- Routes sideboard cards to the `sideboard` field (separate from `cards`)
- Strips Moxfield set code suffixes and merges duplicate card names automatically
- Reports: `parse-deck: N cards, M sideboard -> /path/to/deck.json`

**Always pass `--format <format>` explicitly.** Without it, `parse-deck` defaults to `commander` and every downstream tool (legality-audit, price-check) sees the wrong format.

Supported formats: `commander` (100 cards), `brawl` (60 cards, Standard card pool), `historic_brawl` (100 cards, Historic/Arena card pool), `standard`, `alchemy`, `historic`, `pioneer`, `timeless`, `modern`, `legacy`, `vintage` (all 60 cards with 15-card sideboard). Use `--deck-size` to override the default deck size.

If the format is not obvious from context, ask the user.

### Commander Formats

If `commanders` is empty (common with Moxfield exports that lack `//Commander` headers), ask the user who the commander is. Don't guess — the first card in the list is often the commander, but not always. Supports partner commanders, friends forever, and background pairings.

Run `set-commander <deck.json> 'Commander Name'` to move the card from the cards list to the commanders list. **`set-commander` is idempotent** — calling it on a card already in the `commanders` zone is a silent no-op, so it's safe to chain after `parse-deck` even when the deck file already had a Moxfield `Commander` header.

### Collection Ownership (Arena)

If the user has an Arena collection:
1. Ask for Untapped.gg CSV export first (most reliable source)
2. `mark-owned <deck.json> <collection.csv> --bulk-data <path>` to populate `owned_cards` (accepts both CSV and parsed-deck JSON)
3. Use `mtga-import` only for extracting wildcard counts, not collection data

**Always pass `--bulk-data` for Arena collections** — this enables `printed_name` and `flavor_name` aliasing so crossover cards match correctly between Arena names and Scryfall canonical names.

`mark-owned` also does front-face aliasing for DFC / split / adventure / modal cards: a deck that lists `"Fable of the Mirror-Breaker"` (front face only, common in Arena/Moxfield exports) matches a collection entry for `"Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"` (Scryfall's canonical combined form) and vice versa. You do not need to normalize these by hand before calling `mark-owned`.

**`price-check` honors deck quantity and owned quantity.** Paper (USD) mode charges `max(deck_qty - owned_qty, 0) * unit_price` per card. Arena wildcard mode applies the same shortfall math plus the Arena 4-cap substitution: owning >=4 of a standard playset-capped card grants effectively infinite supply, but this substitution is suppressed for cards with oracle exemptions (`A deck can have any number of cards named X`).

---

## Step 2: Hydrate Card Data

```
scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <working-dir>/.cache
```

Returns an envelope with `cache_path`, `card_count`, `missing`, `digest`. The cache file contains all mainboard + sideboard + commander cards hydrated with oracle text, legalities, prices, etc.

**Do NOT Read the cache file directly** — it's large and floods context. Use `card-summary` or `scryfall-lookup "<Name>"` for targeted reads.

**Re-hydrate after every deck edit.** The hydrated cache path is SHA-keyed against the deck JSON's content, so editing the deck and re-running `parse-deck` produces a new SHA. If you keep using the old `cache_path`, downstream tools will show stale data. Any time you modify the deck, immediately re-run `scryfall-lookup --batch` and switch all downstream script calls to the new `cache_path`.

---

## Step 3: Baseline Metrics

Run in this order (cheapest-to-fail first):

### 1. Legality Audit

```
legality-audit <deck.json> <hydrated.json>
```

Checks: format legality, copy limits (singleton for commander formats, 4-of + Vintage restricted for 60-card), sideboard size, deck minimum, color identity (commander formats). **Must PASS** before continuing. If FAIL, surface violations and ask user how to fix.

### 2. Deck Stats

```
deck-stats <deck.json> <hydrated.json>
```

Review: total cards, land count, creature count, ramp count, avg CMC, curve distribution, sideboard total (60-card). Note any obvious red flags. Flag immediately if the total card count does not match the deck's expected size.

Review the `alternative_cost_cards` section. For any card with alternative costs (suspend, adventure, foretell, etc.), note the cost most likely to be used in this deck. Do not evaluate these cards at their CMC alone.

### 3. Card Summary

```
card-summary <hydrated.json> --nonlands-only
card-summary <hydrated.json> --lands-only
card-summary <hydrated.json> --deck <deck.json> --sideboard   # 60-card only
```

Scan mainboard (and sideboard for 60-card) oracle text. Flag cards with alternative costs for adjusted CMC evaluation.

### 4. Mana Audit

```
mana-audit <deck.json> <hydrated.json>
```

Notes land count status (PASS/WARN/FAIL) and color balance. Uses the Burgess/Karsten formula for commander formats and the constructed formula for 60-card formats.

### 5. Companion Check (60-card only)

Check the sideboard for a Companion card (`card-summary <hydrated.json> --deck <deck.json> --sideboard` and look for the Companion keyword). If one exists, note its deck-building restriction — all proposed changes must continue to meet it.

If no Companion exists, check whether the deck naturally meets one's restriction. Companions are powerful enough that a deck accidentally qualifying for one (e.g., a low-curve aggro deck meeting Lurrus's "no permanents with mana value > 2") should actively consider adding it. Use `card-search --format <fmt> --bulk-data <path> --oracle "Companion" --type "Creature"` to find candidates, then check restrictions against the current deck. If one fits, suggest it in Step 8 as an addition (it takes 1 sideboard slot).

---

## Step 4: User Intake

Ask via AskUserQuestion:

### Shared Questions

1. **Experience level** — Beginner / Intermediate / Advanced
2. **Budget for upgrades** — USD or wildcard budget for changes
3. **Max swaps** — How many cards are you willing to change?
4. **Pain points** — What matchups feel bad? What problems do you notice? Or just "general optimization"?

### 60-Card Constructed

5. **Best-of-One or Best-of-Three?** — Arena only; skip for paper. If Bo1, sideboard tuning is irrelevant — focus entirely on mainboard. Skip Step 8f (Sideboard Evaluation) and the sideboard guide in Step 14.
6. **Target** — Competitive ladder, FNM, tournament?

### Commander/Brawl/Historic Brawl

5. **Power bracket** — 1-5, or casual/core/upgraded/optimized/cEDH
6. **Arena vs. paper?** — For Brawl/Historic Brawl, ask if playing on Arena or paper if unclear.

**Format-specific context to mention when relevant:**
- **Brawl/Historic Brawl:** No commander damage (Voltron strategies are weaker), starting life is 25 (2-player) or 30 (multiplayer) instead of 40, free first mulligan
- **Brawl:** Standard card pool — many Commander staples are not legal. Colorless commanders can include any number of basics of one chosen type.
- **Historic Brawl:** Arena Brawl card pool — broader than Standard but different ban list from Commander
- **Arena Brawl queues are always 1v1.** Prioritize speed and tempo over politics, evaluate cards for 1v1 combat (not multiplayer table dynamics), expect more counterspells and targeted removal, fewer board wipes. Paper Brawl can be multiplayer — use standard scaling.

### Arena Wildcard Budgets

For Arena, use compact notation: `NM/NR/NU/NC` (e.g., `2M/4R/8U/12C` = 2 mythic, 4 rare, 8 uncommon, 12 common wildcards).

If the user ran `mtga-import`, check for `wildcards.json` in the working directory before asking about budget.

### If Handed Off from Deck-Builder

Confirm carry-forward context: format, platform, Bo1/Bo3 (60-card) or bracket (commander), budget (total/spent/remaining), experience level, archetype, Companion (if any), max swaps. Don't re-ask questions already answered.

When receiving a builder handoff, note both the **total budget** and the **upgrade budget** (total minus skeleton cost). Use the upgrade budget for swap decisions during analysis. Track owned cards separately — they don't count toward either budget.

---

## Step 5: Research

### 60-Card Constructed

#### Metagame Context

1. **WebSearch** for `"<format> metagame 2026"` or `"<format> tier list"`
2. **WebFetch** top results to understand the current metagame landscape
3. Identify: What are the top 5 archetypes? Where does this deck fit? What are its expected good/bad matchups?

#### Archetype-Specific Research

1. **WebSearch** for `"<deck archetype> <format> sideboard guide"` and `"<deck archetype> <format> matchup guide"`
2. **WebFetch** strategy articles for sideboard plans and matchup analysis
3. Compare the user's list to stock/optimized versions of the archetype

### Commander/Brawl/Historic Brawl

#### EDHREC + Web Strategy

Run: `edhrec-lookup "<Commander Name>"`

For partner commanders: `edhrec-lookup "<Commander 1>" "<Commander 2>"`

Also use `WebSearch` for the commander + "deck tech", "strategy", "guide" to find Command Zone, MTGGoldfish, and other content creator analysis.

**Fetching strategy articles:** Use `WebFetch` first. If it returns an empty JS shell or navigation-only content, fall back to the helper script:

Run: `web-fetch "<url>" --max-length 10000`

**Key principle:** Research informs but doesn't dictate. EDHREC popularity doesn't automatically make a card right, and unpopularity doesn't make it wrong.

**Combo discovery (optional):** For deeper exploration beyond what `combo-search` surfaces, use `combo-discover` to find combo lines the deck could support. Search by cards already in the deck (`--card "Key Card"`) or by desired outcomes (`--result "Infinite X"`).

**Brawl format note:** EDHREC data is sourced from Commander/EDH decks. When tuning a Brawl deck, EDHREC recommendations must be legality-checked against the deck's format before recommending. Use `card-search --format <format> --bulk-data <path>` to verify candidates are legal. For Arena decks, also use `--arena-only`.

### Combo Awareness (All Formats)

```
combo-search <deck.json> --hydrated <hydrated.json>
```

Surface existing combos and near-misses. Note which near-misses could be completed with 1-card additions.

**Before recommending any near-miss as an add, `Read` the full `description` field for that near-miss from the combo-search JSON** (use `offset`/`limit`). The compact text report shows only the card list and the result; the JSON's `description` spells out the activation sequence and frequently names **additional required pieces** not in the card list. Recommending a near-miss without reading its description is an Iron Rule violation.

**Supplement with WebSearch (60-card):** `combo-search` uses Commander Spellbook, which is crowdsourced primarily by Commander players. Combos that are powerful in 1v1 60-card formats but weak in multiplayer Commander may be underrepresented or missing. Search for `"<archetype> combo <format>"` and `"<key card> combo <format>"` to catch format-specific interactions the API might miss.

**Bracket compliance (Commander):** Check combo results against the user's target bracket:
- **Bracket 1-2:** Intentional two-card infinite combos are prohibited. Flag existing infinite combos as bracket violations. Do NOT suggest near-miss infinite combos as additions.
- **Bracket 3:** Infinite combos are allowed but should not reliably fire before turn 6.
- **Bracket 4:** No restrictions on combos.

---

## Step 6: Strategy Alignment

Present your understanding of the deck's:
- **Game plan:** How does this deck win?
- **Key cards:** What are the most important cards in the strategy?

### 60-Card Constructed

- **Expected matchups:** Given the metagame, which matchups are favorable/unfavorable?
- **Role flexibility:** In each matchup, is this deck the aggressor or the defender?

### Commander/Brawl/Historic Brawl

- **Commander mechanics:** Key mechanical interactions the commander enables
- **Trigger multiplier range:** If relevant, present your estimated multiplier (e.g., "Based on Obeka's 3 base power with typical pump, I'm estimating 3-7 extra upkeeps per hit"). **Ask the user to validate this range.** It feeds into `cut-check` and determines how trigger values are evaluated.

Ask the user to validate or correct. This alignment prevents wasted analysis on swaps that fight the deck's identity.

---

## Step 7: Commander Interaction Audit (Commander/Brawl/Historic Brawl Only)

**Skip this step entirely for 60-card constructed formats.** Mark it `completed` immediately and proceed to Step 8.

Before evaluating individual cards, systematically check for mechanical interactions between the commander and every card in the deck. This step catches synergies that are invisible when reading cards in isolation.

### Keyword Combinations

List the commander's keywords and any keywords granted by cards in the deck. Check every pair for emergent effects:
- **Evasion stacking:** menace + "can't be blocked by more than one creature" = unblockable. Any blocking restriction combined with a conflicting blocking requirement may create unblockable.
- **Damage multiplication:** double strike + combat damage triggers = double triggers. Double strike + lifelink = double life. Trample + deathtouch = 1 damage kills, rest tramples over.
- **Protection stacking:** ward + hexproof, indestructible + regenerate — identify which are redundant vs. complementary.

This applies to all cards, not just the commander. Equipment and auras that grant keywords to the commander are especially important.

### Trigger Multiplication

Identify the commander's core multiplier (extra upkeeps, extra combats, extra turns, extra phases, trigger copying, token doubling, etc.). For EVERY triggered ability in the deck that fires during the multiplied window, calculate its output at 1x, 3x, and 5x the base rate. Present and evaluate the **multiplied** value, not the base value.

A "1 damage to each opponent" trigger looks marginal at 1x. At 5x with 3 opponents, it's 15 damage + 15 life — a legitimate win condition. Evaluate accordingly.

For commanders whose trigger scales with combat damage dealt, explicitly identify **pump as a strategic pillar**. Each +1 power is not just +1 damage — it's +1 trigger of every effect in the multiplied window.

### Feedback Loops

For each card, ask: "Does this card's output feed back into its own input or the commander's trigger condition?" Examples:
- A +1/+1 counter source on a commander whose trigger scales with power
- A token creator that increases a count used by another card's scaling ability
- A theft effect where stolen permanents change type to match a tribal count
- A card that draws cards in a hand-size-matters deck

Cards with feedback loops are almost always stronger than they appear in isolation. Flag them before the analysis phase.

### Recurring Cards

Identify all cards that return themselves to a usable zone: re-suspend, buyback, retrace, escape, flashback, "return to hand" clauses, "exile with time counters" effects. Evaluate these on their per-game value (total free casts over a typical game), not their per-cast value. A 6-mana spell that re-suspends and gets cast for free every 1-2 turns is a permanent with a triggered ability, not a one-shot.

### Commander Multiplication

Identify cards that multiply the commander's impact. Two categories:

**Commander copies** — cards that create token copies or become copies of the commander (Helm of the Host, Spark Double, Clone effects, Mirror March, Followed Footsteps). Non-legendary copies bypass the legend rule and retain all triggered and activated abilities.

**Ability copiers and trigger multipliers** — cards that copy or double the commander's triggered/activated abilities (Strionic Resonator, Rings of Brighthearth, Panharmonicon for ETB commanders, Teysa Karlov for death triggers, Isshin for attack triggers, Seedborn Muse for extra activations).

Scan oracle text for these patterns directly — `cut-check`'s `commander_multiplication` field catches obvious cases but misses oddly-worded effects. **These cards are force-multipliers.** Treat any card you flag as untouchable when drafting cuts — it should not appear on the cuts list without explicit justification.

### Combo Detection

Run: `combo-search <parsed-deck-json> --output /tmp/combo-search.json`

Review existing combos and near-misses. Distinguish:
- **Game-winning combos** (result contains "infinite" or "win the game"): flag prominently, critical to protect during analysis.
- **Value interactions** (non-infinite synergies): note as context, but these don't block cuts.

---

## Step 8: Analysis

### 8a: Mana Base & Curve Audit

- Land count and ramp pieces (mana rocks, dorks, land-fetching spells)
- Average CMC of nonland cards
- Curve distribution
- `mana-audit` for quantitative check
- Color balance: pip demand vs. land production
- Mana base quality: untapped sources on key turns, color fixing
- Flag: too few/many lands, color deficits, too many tapped lands

**Commander formats:** Land count is a hard constraint. Calculate the Burgess formula result (`31 + colors_in_identity + commander_cmc`) and treat it as the target. The `mana-audit` script enforces this — if it returns FAIL, you must add lands or cut fewer lands. Proposing a land count below the Burgess formula result requires `mana-audit` to return PASS or WARN (not FAIL). Proposing a land count below 36 is almost always a FAIL.

**60-card constructed:** Uses the constructed land formula. Compare against format-specific expectations.

### 8b: Interaction & Threat Audit

#### Commander/Brawl/Historic Brawl

Count the deck's removal and interaction pieces. Compare against bracket-appropriate targets:

| Category | Bracket 1-2 (Casual) | Bracket 3 (Upgraded) | Bracket 4 (Optimized) |
|----------|----------------------|----------------------|----------------------|
| Targeted removal/disruption | 5-7 | 8-10 | 10-12 |
| Board wipes | 2-3 | 3-4 | 4-5 |
| Total interaction | 8-10 | 12-14 | 15-18 |

"Disruption" includes counterspells, discard, and stax pieces. Flag decks that fall below the low end of their bracket's range.

#### 60-Card Constructed

- Count removal (targeted + sweepers)
- Count threats (creatures + planeswalkers + other win conditions)
- Compare to format expectations (aggro formats need fewer answers; control metas need more)
- Flag: insufficient interaction for the metagame, redundant removal, missing threat types

### 8c: Archetype Coherence

#### Commander/Brawl/Historic Brawl

Group cards by commander-aware roles — roles defined by how they work with THIS commander, not generic categories. Analyze each group as a unit.

**For every card, answer:** "How does this card specifically interact with this commander?" Cite the oracle text.

Analysis dimensions:
- Synergy with the commander and other cards
- Mana curve distribution
- Card type balance (creatures, interaction, ramp, draw)
- Win conditions
- Mana base quality
- Bracket compliance (count Game Changers vs. target bracket)
- Pain point focus (weight toward user-identified issues)
- Combo awareness (combo pieces evaluated in context, near-miss cards as candidate additions)

#### 60-Card Constructed

Unlike commander (which anchors on the commander), constructed decks must have a **consistent game plan** visible across the 60 cards.

**Step 1 — Identify the build-around cards.** Every competitive deck has 1-3 cards that define its archetype (e.g., Monastery Swiftspear for burn, Arclight Phoenix for Izzet Phoenix, Amulet of Vigor for Amulet Titan). These are the constructed equivalent of the commander — the cards the deck is built to maximize.

**Step 2 — Evaluate every other card against the build-around.** For each non-land card, it should do at least one of:
- **Enable** the build-around (tutors, setup, mana acceleration)
- **Protect** the build-around (counterspells, removal, redundancy)
- **Complement** the build-around (cards that benefit from the same game state)
- **Close** the game when the build-around has done its job (win conditions)

Cards that don't clearly fit one of these roles are candidates for cuts.

**Step 3 — Check for orphaned "Plan B" cards.** A common deck-building mistake is including 2-3 cards from a secondary strategy the deck doesn't have the infrastructure to support.

**Step 4 — Scan oracle text systematically.** Use `card-summary <hydrated.json> --nonlands-only` and look for oracle text that doesn't mention the deck's key mechanics.

**Step 5 — Verify structural consistency:**
- **Threat density:** Does the deck have enough pressure to close games?
- **Curve alignment:** Does the curve support the intended speed?
- **Dead cards:** Cards that don't contribute to the primary game plan?
- **Mismatch cards:** Cards that belong to a different archetype?

### 8d: Draft Cuts

#### Commander/Brawl/Historic Brawl: Cut Checklist

Before recommending ANY cut, work through this checklist for every candidate. Skipping items is how cards get misjudged.

0. **Full oracle text verification.** Re-read the card's complete oracle text from the hydrated data. The `card-summary` table truncates oracle text and is for scanning only.

0.5. **Alternative cost check.** If the card has suspend, foretell, adventure, evoke, flashback, escape, or other alternative casting costs, evaluate at the cost most likely to be used in this deck, not the printed CMC.

1. **Clause-by-clause oracle text analysis.** Read each sentence independently. Ask: "How does THIS specific clause interact with my commander and the deck's strategy?" Common missed clauses:
   - Attack/block restrictions
   - Type-changing effects
   - Self-recurring mechanics
   - Static effects on other permanents

2. **Defensive value check.** Does this card reduce incoming damage or attacks? Protect other permanents? Deter opponents politically?

3. **Feedback loop check.** Does removing this card break a self-reinforcing cycle? (See Step 7.) If so, the cut needs much stronger justification.

4. **Pain point regression check.** Does cutting this card make the user's stated problem worse?

5. **Multiplied value calculation.** Calculate the card's output at the commander's expected trigger multiplier (see Step 7). If a trigger looks weak at 1x but kills a player at 5x, it is a win condition, not a role player.

6. **Combo piece check.** Is this card part of an existing combo line (from Step 7 combo search)?
   - **Game-winning combos:** hard to justify cutting. Valid justifications include "too slow for the bracket" or "bracket violation."
   - **Value interactions:** a soft consideration, not a hard gate.

**Cuts — Be Careful.** Before recommending ANY cut, re-read the oracle text of BOTH the card and the commander. Articulate specifically why the card underperforms in THIS deck.

#### 60-Card Constructed: Draft Cuts

For each proposed cut, evaluate:

1. **Oracle text verification** — Read full oracle text from hydrated data
2. **Alternative cost check** — Suspend, foretell, etc. change the effective CMC
3. **Role in the deck** — What role does this card fill? Is there redundancy?
4. **Matchup impact** — Does cutting this hurt specific matchups?
5. **Combo line check** — Is this card part of an existing combo? (from Step 5)
6. **Metagame relevance** — Is this card specifically good/bad in the current metagame?

**Be careful with cuts.** Re-read oracle text of both the card and its synergy partners. Articulate the specific underperformance.

### 8e: Draft Additions

Source candidates from:
- **60-card:** Metagame research (stock list differences), `card-search`, near-miss combos, WebSearch for archetype-specific tech
- **Commander:** EDHREC high-synergy cards, web research, `card-search` to find synergistic cards EDHREC may not surface

Run: `card-search --bulk-data <path> --format <fmt> [--color-identity <ci>] [--oracle "<keyword>"] [--price-max <budget-per-card>]`

For each proposed addition:
1. Verify format legality and oracle text
2. Check price (within budget?)
3. Identify what role it fills
4. Compare to the card it's replacing

**Before adding any card to the proposed adds list, verify its color identity** (commander formats) or format legality (all formats). Never rely on card name or memory. Cards like Pest Infestation (B/G despite looking like a green card) will slip through without verification.

Recommend the cheapest available printing. Track running cost against budget.

### 8f: Sideboard Evaluation (60-Card Only)

**Skip for Commander/Brawl/Historic Brawl.** Also skip for Bo1 (per Step 4 intake).

Evaluate the current sideboard against the metagame:
- Does it address the top 3-5 archetypes?
- Are there dead sideboard slots (cards for matchups that don't exist)?
- Are there missing answers (common archetypes with no sideboard plan)?
- Is the sideboard plan clear? (Which cards come in/out for each matchup?)

Draft sideboard changes alongside mainboard changes.

### 8g: Swap Balance Check

After drafting all changes (mainboard + sideboard if applicable):
- Verify total mainboard stays at expected size (60 or 100)
- Verify sideboard stays at 15 or fewer (60-card only)
- Check land count hasn't drifted
- Check curve hasn't spiked
- Run `mana-audit --compare` to verify color balance maintained
- Verify budget: `price-check` on proposed additions
- **Ramp count must stay stable.** Don't cut ramp pieces unless the deck has too many or you're adding equivalent ramp.

If the swaps would damage the mana base, revise before presenting. It is better to make fewer swaps than to break the deck's ability to cast its spells.

---

## Step 9: Pre-Grill Verification

Before the self-grill, verify mechanically.

### Price Check on Additions

```
price-check /tmp/adds.json --bulk-data <path> [--format <fmt>] [--budget <budget>]
```

For Arena formats, use `--format <fmt>` to get wildcard costs. If any single card or the total exceeds budget, find cheaper alternatives before proceeding. Do not send cards to the self-grill that the user cannot afford.

### Commander/Brawl/Historic Brawl: Mechanical Cut Check

Run `cut-check` on every proposed cut:

```
cut-check <hydrated.json> "<Commander Name>" --cuts <cuts.json> --multiplier-low <low> --multiplier-high <high> --opponents <N>
```

Stdout is a compact text report with one line per cut card summarizing flags (`COMMANDER_MULTIPLICATION`, `triggers=N (type=value-range)`, `self-recurring=yes/no`, `keyword-interactions=N`) plus a `Flags:` tally line.

For each proposed cut, write out (internally, not presented to user):
1. **Multiplied value:** [from cut-check output, or "no matching triggers"]
2. **Pain point regression:** Does cutting this card make the user's stated problem worse?
3. **Defensive value:** What does this card prevent, deter, or protect?
4. **Replacement justification:** What specific card in the additions replaces this card's role?
5. **Combo line:** Is this card part of an *existing* combo from Step 7? If game-winning, justify why cutting is acceptable.
6. **Near-miss partner check:** Which Step 7 near-miss results does this card enable as a partner? If any, justify the closure or revise the cut.

If you cannot fill in all six fields, you have not evaluated the card. Do not proceed to the self-grill.

### 60-Card Constructed: Internal Evaluation

For each proposed cut, write out (internally, not presented to user):
- Role in deck
- Matchup impact
- Combo line affected?
- Replacement justification
- Metagame relevance

If you can't articulate why a specific card should be cut, you haven't evaluated it — don't proceed.

---

## Step 10: Self-Grill (Two-Agent Debate)

**HARD GATE.** Must use two parallel `Agent` tool calls (`subagent_type: "general-purpose"`): one proposer, one challenger, with at least one revision round. This is NOT substituted by mechanical checks (mana-audit, price-check) — those catch quantitative errors; the self-grill catches strategic errors (wrong archetype assessment, missed synergy, weak justification, metagame misread).

### Data Delivery

Give both agents file paths (they can `Read` selectively), plus a one-paragraph bottom-line summary:

**Required file paths:**
- Hydrated cache path
- mana-audit output
- price-check output
- combo-search output
- Proposed cuts JSON
- Proposed adds JSON
- Sideboard cuts/adds JSON (if any, 60-card only)
- cut-check output (commander formats only)

**Bottom-line summary example (60-card):**
"Proposed 8 mainboard swaps + 4 sideboard swaps for Pioneer Mono-Red. mana-audit PASS; price-check $12.50 of $20 budget; combo-search 0 combos (aggro deck). Key thesis: shift from burn-heavy to creature-heavy for better Sheoldred matchup."

**Bottom-line summary example (commander):**
"cut-check flagged N commander_multiplication + M triggers across the cuts; mana-audit returned PASS/WARN/FAIL; price-check total is $X of $Y budget with Z over-limit cards; combo-search found N game-winning combos in the deck, K of which are affected by the proposed cuts."

**Fallback if `Read` is unavailable.** If a dispatched subagent reports it cannot `Read` the provided path, the parent must paste the relevant file excerpt into a follow-up message to that subagent — never dump the entire file.

### Proposer Instructions

Defend the proposal. Push back on challenger objections unless they provide:
- Specific oracle text interaction you missed
- Quantitative argument (mana math, matchup percentage)
- Metagame data contradicting your read

### Challenger Checklist

The challenger must verify:
- [ ] Read oracle text for every cut independently (don't trust paraphrasing)
- [ ] Verify each cut's role — is the replacement actually better in this slot?
- [ ] Check that no critical matchup coverage is lost
- [ ] Verify mana-audit is PASS
- [ ] Verify price-check within budget
- [ ] Verify no combo lines broken without justification
- [ ] Verify swap balance (land count, curve, total counts)
- [ ] **Archetype coherence test:** "Does this deck still have a clear game plan after these swaps?"

#### Additional 60-Card Checks

- [ ] Verify sideboard plan still covers top metagame archetypes
- [ ] **Companion restriction:** If the deck has a Companion, verify every addition still meets its deck-building restriction
- [ ] **Sideboard coherence test:** "For each top-3 matchup, what comes in and what goes out? Does that plan make sense?"

#### Additional Commander Checks

- [ ] Check every clause of every cut card's oracle text — defensive restrictions, type-changing effects, self-recurring mechanics, static effects
- [ ] Verify keyword interactions between the commander and each cut card (emergent combinations)
- [ ] Calculate multiplied value of any triggers being cut
- [ ] `Read` the cut-check JSON and verify every flag was addressed by the proposer
- [ ] Check `color_balance_flags` and per-color metrics
- [ ] For Brawl formats, scrutinize Voltron strategies extra hard (no commander damage). Account for lower life totals and free mulligan.
- [ ] **Commander fitness check** — apply the *commander identity test:* "If this deck's commander were hidden, could you guess what it is from the cards?" If the commander may be underperforming, shortlist 1-2 alternatives and surface as a close call in Step 13.

**Expect 2-3 rounds minimum.** If both agree immediately, the challenger isn't pushing hard enough.

---

## Step 11: Propose Changes

**HARD GATE:** Write the full proposal as a complete turn BEFORE any `AskUserQuestion`. Do not bundle a tool call with proposal markdown — the tool executes before text finalizes, and the user approves blind.

### Before Presenting

Run `build-deck` to construct the new deck, then `mana-audit` on the result. If FAIL, revise until PASS.

**Preferred path: `build-deck` + `export-deck`.** These produce a correctly-sized deck JSON by construction, so manual card counting never enters the loop.

**The user has not seen the debate.** Present the post-debate proposal as a complete, self-contained recommendation with full reasoning for every swap. Do not reference the debate.

### Proposal Format

Present as paired swaps with reasoning. Adapt detail to experience level.

**Mainboard changes:**
```
## Mainboard Changes (8 swaps)

**OUT: Shock (4) -> IN: Play with Fire (4)**
Shock deals 2 to any target; Play with Fire deals 2 to any target OR scrys 1 when it
deals damage to a player. Strictly better in this deck since we point burn at face.
Cost: $0.50 per copy.

**OUT: Viashino Pyromancer (2) -> IN: Eidolon of the Great Revel (2)**
Viashino is a one-shot 2 damage on ETB. Eidolon punishes the opponent for every spell
they cast, often dealing 6-10 damage per game in faster matchups.
Cost: $3.00 per copy.
...
```

**Sideboard changes (60-card only):**
```
## Sideboard Changes (4 swaps)

**OUT: Magma Spray (2) -> IN: Roiling Vortex (2)**
Magma Spray is narrow graveyard removal. Roiling Vortex hits free spells (Fury, Force),
lifegain (Sheoldred), and deals 1/turn. Better coverage across more matchups.
Cost: $1.00 per copy.
...
```

**Commander format swaps:** Explain why the cut underperforms with THIS commander (cite oracle text) and why the addition is better for the strategy (cite oracle text).

**Budget summary:**
```
## Budget
Total additions: $14.50 / $20.00 budget
Remaining: $5.50
```

For Arena wildcard budgets, show per-rarity breakdown.

---

## Step 12: Impact Verification

**HARD GATE.** Run BOTH checks on the new deck before presenting close calls. This step catches emergent regressions — cross-swap interactions visible only after all changes are applied together.

### Check 1: Deck Diff

```
deck-diff <old-deck.json> <new-deck.json> <old-hydrated.json> <new-hydrated.json>
```

Verify:
- Total count unchanged (still 60/100 mainboard, 15 sideboard if applicable)
- Land count healthy
- Avg CMC didn't spike
- Ramp/acceleration count stable
- Sideboard changes match proposal (60-card)

### Check 2: Combo Search (Post-Build)

```
combo-search <new-deck.json>
```

Compare to Step 5/7 results:
- Any combos lost? If so, was the loss intentional (documented in Step 8d/9)?
- Any new combos gained?
- Near-miss changes?

**Non-substitutable with Step 9 combo checks.** Step 9 catches cuts that close *near-miss* lines (pre-build). This Step 12 check catches cuts that break *existing* combo lines (post-build). Neither subsumes the other.

If any unintended regression, revise the proposal.

---

## Step 13: Close Calls

Surface genuinely debatable swaps from the self-grill debate. These are cards where:
- Proposer and challenger disagreed
- The decision depends on local metagame or playstyle preference
- Both options are defensible

Present as user decisions:
```
## Close Call: Eidolon of the Great Revel vs. Harsh Mentor

**Case for Eidolon:** Hits every spell, higher floor, proven format staple.
**Case for Harsh Mentor:** Cheaper at 2 mana, punishes activated abilities (fetchlands,
planeswalker activations), but doesn't hit spells.

Which do you prefer, or would you like to test both?
```

Do NOT present obvious decisions as close calls. Only surface genuine disagreements.

### Commander Swap Consideration (Commander/Brawl/Historic Brawl Only)

If the challenger flagged the commander during the self-grill, present it as a close call — never as a firm recommendation:

> "One thing worth considering: [specific observation about why the commander underperforms with this deck's composition]. [Alternative Commander] in the same colors does [specific oracle text interaction] which fits better with what the deck is actually doing. This would be a significant change though — worth exploring, or do you want to keep [current commander]?"

**This is always a close call.** The user chose their commander for a reason.

---

## Step 14: Finalize

### Export

```
export-deck <new-deck.json>
```

Outputs Moxfield/Arena import format with sideboard section.

### Final Price Check

```
price-check <new-deck.json> --bulk-data <path>
```

For Arena:
```
price-check <new-deck.json> --format <fmt> --bulk-data <path>
```

### Final Budget Summary

**Paper:**
```
| | Cost |
|---|---|
| Skeleton (from builder) | $X |
| Upgrades (this session) | $Y |
| **Total deck cost** | **$Z** |
| Owned cards (not counted) | card1, card2, ... |
| Total budget | $B |
| **Remaining** | **$R** |
```

If the total budget was not provided (standalone tuner session without builder), show just the upgrade cost and total deck cost.

**Arena:**
```
| Rarity   | Used | Available | Remaining |
|----------|------|-----------|-----------|
| Mythic   | 1    | 2         | 1         |
| Rare     | 3    | 4         | 1         |
| Uncommon | 4    | 8         | 4         |
| Common   | 6    | 12        | 6         |
```

### Sideboard Guide (60-Card Only)

Construct a matchup-by-matchup sideboard map for the top 3-5 metagame archetypes identified in Step 5. This is a natural output of the analysis already performed — don't skip it.

```
## Sideboard Guide

### vs. Mono-Red Aggro (IN: 5, OUT: 5)
IN: 2 Surge of Salvation, 3 Temporary Lockdown
OUT: 2 Disdainful Stroke, 1 Negate, 2 Memory Deluge
Rationale: Trade slow counterspells for cheap answers that stabilize before turn 4.

### vs. Azorius Control (IN: 4, OUT: 4)
IN: 3 Mystical Dispute, 1 Negate
OUT: 3 Temporary Lockdown, 1 Surge of Salvation
Rationale: Sweepers are dead; load up on cheap countermagic for the permission war.

### vs. Graveyard Combo (IN: 3, OUT: 3)
IN: 3 Rest in Peace
OUT: 1 Memory Deluge, 2 Absorb
Rationale: Rest in Peace shuts down the entire strategy; trim expensive interaction.
```

Each entry must specify exact cards in, exact cards out, and a one-line rationale. The in/out counts must match (total mainboard stays at 60).

### Offer (don't force)

- Mana curve before/after comparison
- Category breakdown comparison
- "Next upgrades" list for future budget

---

## Red Flags

| Thought | Reality |
|---------|---------|
| "I know what this card does" | You don't. Look it up. Training data is not oracle text. |
| "EDHREC recommends it so it must be good here" | EDHREC is aggregated data, not analysis. Evaluate for THIS build. |
| "This is a format staple, it can't be a cut" | Evaluate in context. Staples can underperform in specific shells. |
| "This card is generally weak" | Weak in general != weak with this commander. Read both oracle texts. |
| "The sideboard is fine, focus on mainboard" | Sideboard wins tournaments. Evaluate it. (60-card) |
| "We're over budget but this card is too good to skip" | Budget is a hard constraint. Find a cheaper alternative. |
| "Skip the self-grill, the analysis was thorough" | The self-grill catches exactly this overconfidence. Run it every time. |
| "I ran cut-check + mana-audit + price-check, that covers Step 10" | No. Those are Step 9 *mechanical* gates. Step 10 is the *strategic* gate and requires two Agent tool calls. |
| "This deck just came from the builder, the self-grill is overkill" | The builder runs no adversarial review. A fresh skeleton is the highest-leverage moment for a challenger pass. |
| "I'll dispatch the agents next turn / after the user confirms" | No. Step 10 must complete before Step 11. |
| "I'll bundle the Step 11 proposal and the Step 13 AskUserQuestion in one message" | No. `AskUserQuestion` renders option chips before the surrounding markdown commits, so bundling means the user approves blind. Write Step 11's proposal FIRST as its own turn. |
| "I'll trust the `rarity` field from the hydrated cache for Arena budgeting" | No. That field is the Scryfall "default" printing's rarity. Use `price-check --format <fmt>` for Arena rarity. |
| "I'll check combos in the deck but skip the near-miss partner scan when proposing cuts" | No. A near-miss combo is `<missing> + <partner1> + <partner2> = <result>`. Your cut list may silently target a `partner`. Check every proposed cut against Step 7 near-miss partner slots. |
| "I'll just Write over `/tmp/cuts.json` and run cut-check in the same message" | No. The first `Write` to an existing `/tmp` path from a prior session fails, but the parallel Bash call runs against stale content. |
| "I'll write a quick `python3 -c` to count / filter / extract" | Check the decision table first. Almost every common task is covered by an existing script. |
| "Skip impact verification, the swaps look clean" | Emergent cross-swap effects only visible post-build. Run the checks. |
| "This card is too expensive to cut" | Sunk cost. Evaluate on merit, not price. |
| "Propose changes and ask for approval in one message" | Step 11 is its own turn. AskUserQuestion comes in Step 13. |
| "The mana base is close enough" | Run mana-audit. "Close enough" is how you lose to color screw. |
| "This step seems unnecessary for this deck" | Follow every step. The process exists because shortcuts cause mistakes. |
| "Cutting this land for a nonland is fine, the deck has enough" | Count the lands. Count the ramp. Do the math. Don't eyeball mana bases. |
| "I can cut one more land, the ramp covers it" | Run `mana-audit`. If it says FAIL, you cannot. Ramp does not replace lands. |
| "I understand what this commander wants" | Present your strategic read and ask the user. They play the deck — you don't. |
| "This card only works with N other cards in the deck" | Check whether the card creates its own enablers. |
| "This trigger is too small to matter" | Multiply by expected extra triggers AND by number of opponents. Do the math. |
| "This is redundant evasion/protection" | Before cutting, check for unique mechanical interactions no other card replicates. |

---

## Experience Level Adaptation

| Aspect | Beginner | Intermediate | Advanced |
|--------|----------|-------------|----------|
| Terminology | Define terms (card advantage, tempo, etc.) | Use terms freely | Use shorthand |
| Metagame explanation | Define archetypes, explain matchups | Name archetypes, note key cards | Assume knowledge, focus on novel angles |
| Swap reasoning | Full sentences, explain why old card is worse | Note specific interaction | Concise: "Bolt > Shock (scry 1 upside)" |
| Sideboard guide | Explain what sideboarding means | Provide in/out plan per matchup | Shorthand sideboard map |
| Mana base | Explain land types, what good curve looks like | Note mana base tradeoffs | Focus on marginal improvements |
| Presentation | Narrative with examples | Grouped analysis | Concise tables |

---

## Script Reference

### Core Scripts

- `parse-deck <path> [--format FORMAT] [--deck-size N] [--output PATH]` — Parse deck list. Writes JSON to stdout or `--output` PATH. Supports Moxfield, Arena, MTGO, plain text, CSV. `<path>` must be absolute.
- `set-commander <deck.json> "Name" ["Name2"]` — Move card to commanders list. Idempotent.
- `scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <dir>` — Hydrate card data. Stdout is JSON envelope `{cache_path, card_count, missing, digest}`.
- `scryfall-lookup "<Card Name>" --bulk-data <path>` — Single card lookup
- `card-summary <hydrated.json> [--nonlands-only] [--lands-only] [--type <T>] [--deck <deck.json> --sideboard]` — Card table display
- `card-search --bulk-data <path> [--format FORMAT] [--color-identity CI] [--oracle REGEX] [--type TYPE] [--cmc-min N] [--cmc-max N] [--price-min N] [--price-max N] [--sort price-desc] [--limit 25] [--json] [--fields F1,F2,...] [--arena-only] [--paper-only] [--is-commander]` — Search local bulk data
- `combo-search <deck.json> [--hydrated <hydrated.json>] [--max-near-misses N] [--output PATH]` — Find existing combos and near-misses
- `combo-discover [--card "<name>"] [--result "<outcome>"] [--color-identity CI] [--format FORMAT] [--arena-only] [--paper-only] [--bulk-data PATH] [--output PATH]` — Discover combos by outcome or card
- `legality-audit <deck.json> <hydrated.json> [--output PATH]` — Check legality, copy limits, sideboard size, deck minimum, color identity
- `mana-audit <deck.json> <hydrated.json> [--compare <new-deck.json> <new-hydrated.json>] [--output PATH]` — Mana base audit (Burgess/Karsten for commander, constructed formula for 60-card)
- `price-check <deck.json> [--format <fmt>] --bulk-data <path> [--budget <N>] [--output PATH]` — Budget check. For Arena formats, reports wildcard costs by rarity.
- `deck-stats <deck.json> <hydrated.json> [--output PATH]` — Deck statistics
- `build-deck <deck.json> <hydrated.json> --cuts <c.json> --adds <a.json> [--sideboard-cuts <sc.json>] [--sideboard-adds <sa.json>] [--bulk-data <path>] [--output-dir <dir>]` — Apply changes. Cuts/adds accept `[{name, quantity}]` dicts or plain name strings.
- `deck-diff <old.json> <new.json> <old-hyd.json> <new-hyd.json>` — Compare deck versions
- `export-deck <deck.json>` — Export Moxfield/Arena format with sideboard
- `mark-owned <deck.json> <collection.csv> [--bulk-data <path>] [--output PATH]` — Mark owned cards. Always pass `--bulk-data` for Arena.
- `download-bulk --output-dir <dir>` — Download Scryfall bulk data
- `cut-check <hydrated.json> "<Commander Name>" --cuts <path> --multiplier-low N --multiplier-high N [--trigger-type TYPE ...] [--opponents N] [--output PATH]` — Mechanical pre-grill analysis (commander formats only)
- `edhrec-lookup "<Commander Name>" ["<Partner>"]` — EDHREC recommendations (commander formats only)
- `web-fetch "<url>" --max-length 10000` — Fetch web page with browser headers and curl fallback
- `find-commanders <parsed.json> --bulk-data <path> [--format FORMAT] [--color-identity CI] [--min-quantity N] [--output PATH]` — Find commander-eligible cards from collection
- `mtga-import --bulk-data <path> [--log-path PATH] [--output-dir DIR]` — Extract Arena collection and wildcards from Player.log
