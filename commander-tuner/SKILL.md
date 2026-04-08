---
name: commander-tuner
description: Use when analyzing, evaluating, or tuning an MTG Commander deck list (Commander/EDH, Brawl, Historic Brawl) — covers card lookup, synergy analysis, budget-aware recommendations, and deck optimization
compatibility: Requires Python 3.12+ and uv
license: 0BSD
---

# Commander Deck Tuner

## Overview

Structured process for analyzing and tuning MTG Commander decks. Every recommendation MUST be grounded in actual card oracle text from Scryfall — never from training data.

## The Iron Rule

**NEVER assume what a card does.** Before referencing any card's abilities, look up its oracle text via the helper scripts. Training data is not oracle text.

## Progress Tracking

**Before starting Step 1, create a `TodoWrite` list with one item per top-level Step in this skill, in order:**

1. Step 1: Parse Deck List
2. Step 2: Hydrate Card Data
3. Step 2.5: Baseline Metrics
4. Step 3: User Intake
5. Step 4: Research
6. Step 5: Strategy Alignment Check
7. Step 5.5: Commander Interaction Audit
8. Step 6: Analysis
9. Step 6.5: Mechanical Cut Check
10. Step 7: Self-Grill (Two-Agent Debate)
11. Step 8: Propose Changes
12. Step 8.5: Impact Verification
13. Step 9: Close Calls
14. Step 10: Finalize

Mark each item `in_progress` the moment you begin it and `completed` the moment it finishes — **do not batch updates**. The user relies on this list as a live progress indicator; batching defeats the point.

**Step 6 and Step 7 are long enough that the top-level item alone leaves the user staring at an unchanging list.** When you reach them, expand each into sub-todos *at that moment* (not up front):

- **Step 6** sub-todos: Mana Base & Curve Audit, Interaction Audit, Draft Cuts, Draft Additions, Swap Balance Check.
- **Step 7** sub-todos: Dispatch Proposer + Challenger Subagents, Process Challenger Report, Revise Proposal.

Do NOT create per-card sub-todos for the Cut Checklist inside Step 6 — that's execution detail and would flood the list.

## Setup (First Run)

Before first use, set up the Python environment from the skill's install directory:

```bash
uv sync --directory <skill-install-dir>
```

Then download Scryfall bulk data (~500MB):

```bash
download-bulk --output-dir <skill-install-dir>
```

Subsequent runs skip these steps if the `.venv` exists and bulk data is fresh (<24 hours old).

## Tooling Notes

**Script invocation shorthand:** All script examples below elide the `uv run --directory <skill-install-dir> ` prefix for readability. Every actual invocation must include it (e.g., `parse-deck deck.txt` shown here is run as `uv run --directory <skill-install-dir> parse-deck deck.txt`).

**Writing JSON files with card names:** Card names often contain apostrophes (Azor's Elocutors, Krark's Thumb) which break shell quoting. **Use the `Write` tool** for any `/tmp/*.json` file you create — the Write tool only requires a prior `Read` for *existing* files; new files in `/tmp` work fine on the first call. Example:

> `Write(file_path="/tmp/cuts.json", content='["Azor\'s Elocutors", "Krark\'s Thumb"]')`

Do NOT write JSON via Bash heredocs (`cat > /tmp/foo.json << 'JSONEOF' ... JSONEOF`). Heredocs are functionally fine but they produce un-cacheable Bash permission patterns: Claude Code's permission engine bakes the heredoc body into the allow pattern, so every invocation with different content re-prompts the user. The Write tool generates a single `Write(/tmp/**)` permission that can be granted once and reused.

**The same caching trap applies to `python3 -c "..."`, `awk '...'`, `jq '...'`, and any other Bash pattern where the code body varies between invocations.** Each unique body is a fresh permission pattern. If you need to extract one field from a JSON file, prefer: (a) passing the file directly to a script that already knows how to parse it (see "Parsed deck JSON is the canonical pipeline intermediate" below), (b) `Read` with `offset`/`limit` on the JSON file, or (c) `Grep` on the file. Reach for `python3 -c` only when those options genuinely don't cover the case, and accept the re-prompt cost when you do.

**Scratch-file reuse.** Reuse a small set of stable `/tmp/*.json` paths (e.g., `/tmp/cuts.json`, `/tmp/adds.json`, `/tmp/candidates.json`) across a session rather than minting a new file name each time. Write-tool permissions are granted per path; six distinct scratch paths is six permission prompts, while reusing three paths collapses to three.

Do NOT use `echo` or unquoted shell strings for JSON containing card names — apostrophes in card names break shell quoting.

**Parsed deck JSON is the canonical pipeline intermediate.** Once you have a parsed deck JSON from `parse-deck`, pass it **directly** to `scryfall-lookup --batch` and `price-check` — both scripts accept a parsed deck JSON as `<path>`, not just a JSON list of name strings. Do NOT extract card names into a separate `/tmp/*.json` via `python3 -c` or similar. Every unnecessary extraction costs a Bash permission prompt (content-varying `python3 -c` is un-cacheable), a Write permission prompt for the temp file, and wall-clock time. If you catch yourself writing `json.load(...)` to pull out `c['name']`, stop — the script already handles that. (The exception is scripts whose input is a *subset* of the deck — `cut-check --cuts <path>` and `build-deck --cuts <path> --adds <path>` expect JSON lists of name strings, not parsed deck JSON, because the caller is specifying which cards to act on. Writing a small `/tmp/cuts.json` via the Write tool is correct in those cases.)

**Always use absolute paths for every positional argument and file-path flag.** Not just `--cache-dir`. `uv run --directory <skill-install-dir>` rebinds the subprocess CWD to the skill install, so a relative path like `jinnie-fay.txt` passed to `parse-deck` resolves against the skill install dir and fails with a misleading "Path does not exist" error. This applies to `parse-deck <path>`, `card-search --bulk-data <path>`, `cut-check <hydrated> --cuts <path>`, `build-deck <deck> <hydrated> --output-dir <path>` — every path the caller supplies. Resolve paths against the user's working directory first.

**Place `--cache-dir` inside the user's working directory, NOT the skill install.** Pass an absolute path inside the user's repo, e.g. `--cache-dir <working-dir>/.cache` where `<working-dir>` is the absolute path to the user's current repo (the directory they ran Claude Code from). Putting the cache under the skill install (whether explicitly or implicitly via `./`) causes every downstream `Read`, `cp`, or script call against the hydrated path to trigger an outside-workspace permission prompt. Keeping the cache in the working directory eliminates that friction and lets the hydrated file serve directly as the "write output files to the working directory" artifact when handing off between skills.

## Step 1: Parse Deck List

Run: `parse-deck <path-to-deck-file> [--format <format>] [--deck-size <N>]`

Supported formats: `commander` (default, 100 cards), `brawl` (60 cards, Standard card pool), `historic_brawl` (100 cards, Historic/Arena card pool). Use `--deck-size` to override the default deck size (e.g., `--format historic_brawl --deck-size 60` for 60-card Historic Brawl).

If the format is not obvious from context, ask the user: "What format is this deck for? (Commander, Brawl, Historic Brawl)"

This auto-detects format (Moxfield, MTGO, plain text, CSV) and outputs JSON with `commanders` and `cards`. Automatically strips Moxfield set code suffixes like `(OTJ) 222` from card names.

If `commanders` is empty (common with Moxfield exports that lack `//Commander` headers), ask the user who the commander is. Don't guess — the first card in the list is often the commander, but not always. Supports partner commanders, friends forever, and background pairings.

Run `set-commander <deck.json> 'Commander Name'` to move the card from the cards list to the commanders list. This outputs updated JSON to stdout. Supports partner commanders, friends forever, and background pairings. **`set-commander` is idempotent** — calling it on a card already in the `commanders` zone is a silent no-op, so it's safe to chain after `parse-deck` even when the deck file already had a Moxfield `Commander` header.

**AskUserQuestion caps at 4 options — never silently drop the rest.** The tool's schema rejects more than 4 options per question. When presenting a longer list (5+ close-call swaps, 5 alternative commanders, etc.), do NOT pick 4 and hide the rest. List **every** option in the preceding text message with enough detail to decide on, then use AskUserQuestion only as a lightweight picker — either (a) put the top 3 on buttons plus a 4th "Other (specify in notes)" so the user can name any option from the text list, or (b) skip AskUserQuestion entirely for that decision and let the user reply in plain text. The failure mode to avoid is 4 option chips that look like the complete set when the text above mentioned 5+.

**Parsed deck JSON schema.** The deck JSON you'll pass around for the rest of this workflow looks like:

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

All three card lists (`commanders`, `cards`, `owned_cards`) are the same shape — `[{name, quantity}]` dicts. `owned_cards` starts empty from `parse-deck` and is populated by `mark-owned` (or by hand). `price-check` reads it to subtract owned copies from the budget; entries with `quantity < 1` are treated as "not owned," so a Moxfield wishlist row exported at quantity 0 does not silently zero out the budget.

**Populating `owned_cards` from a user's collection:** use the dedicated helper, not inline `python3 -c`:

```
mark-owned <deck.json> <collection.json>
```

This writes the intersection (by normalized, diacritic-folded card name) back into `deck.json`'s `owned_cards` field in place. The recorded quantity is the authoritative count from the collection side, so the field answers "how many copies do I own?" rather than "how many did the deck ask for?" — relevant for Arena wildcard planning and playset-limited formats. `mark-owned` sums duplicate collection rows (Moxfield exports split the same card across printings, so 51 distinct Island rows correctly add up to the user's true 205 Island count). Pass `--output <path>` to write elsewhere instead. Every unique `python3 -c` body is a fresh un-cacheable Bash permission pattern, so one `mark-owned` call beats three inline Python variations.

**`price-check` honors deck quantity and owned quantity.** Paper (USD) mode charges `max(deck_qty - owned_qty, 0) * unit_price` per card, so a deck running 17 Hare Apparent with 4 owned is correctly charged for 13 copies rather than 1. Arena wildcard mode applies the same shortfall math plus the Arena 4-cap substitution: owning ≥4 of a standard playset-capped card grants effectively infinite supply (no legal non-singleton deck can need a 5th), but this substitution is suppressed for cards with oracle exemptions (`A deck can have any number of cards named X` or `A deck can have up to N cards named X`), where owning 4 of Hare Apparent gives you exactly 4. This means the budget math handles any-quantity cards correctly in both paper and Arena contexts without the caller having to care.

## Step 2: Hydrate Card Data

Run: `scryfall-lookup --batch <parsed-deck-json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`

Looks up every card (including the commander) in Scryfall bulk data, falling back to the Scryfall API for cards not found locally. If bulk data is missing or stale, run `download-bulk --output-dir <skill-install-dir>` first.

**Stdout is a small JSON envelope**, not the hydrated card list:

```json
{
  "cache_path": "/absolute/path/to/hydrated-<sha>.json",
  "card_count": 100,
  "missing": [],
  "digest": {
    "categories": {"lands": 36, "creatures": 32, "instants": 6, ...},
    "avg_cmc_nonland": 3.2,
    "curve": {"1": 5, "2": 12, "3": 18, ...}
  }
}
```

Read the envelope to extract `cache_path` — **that file path is what you pass as `<hydrated-cards-json>` to every downstream script** (`card-summary`, `deck-stats`, `mana-audit`, `cut-check`, `build-deck`). Sanity-check the digest against the parsed deck (does land count look right for the format?) and verify `missing` is empty; anything missing is either a typo or a card absent from bulk data.

**Do NOT `Read` the cache file directly.** It holds full hydrated data for every card and will flood context. The human-readable oracle text view comes from `card-summary` in Step 2.5; the full hydrated JSON should only flow through other scripts.

**Re-hydrate after every deck edit.** The hydrated cache path is SHA-keyed against the deck JSON's content, so editing the deck text file (or re-running `parse-deck`) produces a new SHA. If you keep using the old `cache_path`, downstream tools like `card-summary` will happily show you cards that no longer exist in the deck (and miss ones you just added). Any time you modify the deck and re-run `parse-deck`, immediately re-run `scryfall-lookup --batch` on the new deck JSON and switch all downstream script calls to the new `cache_path`.

## Step 2.5: Baseline Metrics

**Legality audit first.** Before anything else in this step, verify the deck is actually legal in its declared format:

Run: `legality-audit <parsed-deck-json> <hydrated-cards-json>`

Stdout is a compact text report: `legality-audit: PASS/FAIL — ...` followed by three violation categories (`format_legality`, `color_identity`, `singleton`) with the specific offending cards. If `FAIL`, stop and surface the violations to the user — the rest of Step 2.5 and everything downstream is wasted effort on a deck that won't load in its format. Banned-card failures are forced cuts; color-identity failures usually mean a card slipped past the commander's identity gate during building; singleton failures are rare but catch off-by-one quantity errors.

Then run the remaining stats and card summary scripts to establish a quantitative baseline and get readable oracle text:

Run: `card-summary <hydrated-cards-json> --nonlands-only`
Run: `card-summary <hydrated-cards-json> --lands-only`
Run: `deck-stats <parsed-deck-json> <hydrated-cards-json>`

Review the card summary output to build your understanding of every card's oracle text. Use the deck stats to note the starting land count, ramp count, creature count, average CMC, curve distribution, and total card count. Flag immediately if the total card count does not match the deck's expected size (100 for Commander/Historic Brawl, 60 for Brawl, or the user's specified deck size).

Review the `alternative_cost_cards` section in deck-stats output. For any card with alternative costs (suspend, adventure, foretell, etc.), note the cost most likely to be used in this deck. Do not evaluate these cards at their CMC alone.

## Step 3: User Intake

Ask all of these in a single message:

> Before I start analyzing, a few quick questions:
> 1. What's your Commander experience level? (beginner / intermediate / advanced)
> 2. What power bracket are you targeting? (1-5, or casual/core/upgraded/optimized/cEDH)
> 3. Budget for upgrades? (dollar amount, or wildcard counts for Arena)
> 4. Max number of card swaps?
> 5. Any specific pain points (e.g., "I run out of gas," "mana base is inconsistent"), or just general optimization?

Handle partial or natural language answers. Fill sensible defaults for anything not specified. Only follow up if something is truly ambiguous.

**Format-specific context to mention when relevant:**
- **Brawl/Historic Brawl:** No commander damage (Voltron strategies are weaker), starting life is 25 (2-player) or 30 (multiplayer) instead of 40, free first mulligan
- **Brawl:** Standard card pool — many Commander staples are not legal. Colorless commanders can include any number of basics of one chosen type.
- **Historic Brawl:** Arena Brawl card pool — broader than Standard but different ban list from Commander

**Arena vs. paper:** Brawl and Historic Brawl can be played on Arena or in paper. When searching for cards, use `--arena-only` for Arena players (excludes paper-only cards) and `--paper-only` for paper players (excludes Arena-only digital cards like conjure/perpetual cards). If unclear, ask: "Are you playing on Arena or in paper?"

**Arena wildcard budgets:** For Arena Brawl players, budget is typically in wildcards (e.g., "1 mythic, 2 rare, 11 uncommon, 38 common") rather than dollars. If the user provides wildcard counts, track them per-rarity throughout the analysis. Use `price-check --format <format>` with `--bulk-data` to get wildcard costs — it reports the lowest rarity available across all Arena printings legal in the format.

If any of these values were already provided earlier in the conversation (e.g., from a commander-builder handoff), confirm them with the user rather than re-asking. Example: "I see you're targeting bracket 3 with $94 remaining for upgrades (from a $500 total budget) — still correct?" For Arena handoffs, the builder uses compact wildcard notation: `NM/NR/NU/NC` (e.g., "remaining: 2M/2R/3U/10C" means 2 mythic, 2 rare, 3 uncommon, 10 common wildcards).

When receiving a builder handoff, note both the **total budget** and the **upgrade budget** (total minus skeleton cost). Use the upgrade budget for swap decisions during analysis. Track owned cards separately — they don't count toward either budget. The total budget will be used in Step 10 for the final summary.

## Step 4: Research

Run: `edhrec-lookup "<Commander Name>"`

For partner commanders: `edhrec-lookup "<Commander 1>" "<Commander 2>"`

Also use `WebSearch` for the commander + "deck tech", "strategy", "guide" to find Command Zone, MTGGoldfish, and other content creator analysis.

**Fetching strategy articles:** Use `WebFetch` first. If it returns an empty JS shell or navigation-only content, fall back to the helper script:

Run: `web-fetch "<url>" --max-length 10000`

This uses browser-like headers and falls back to `curl` for sites that block Python requests via TLS fingerprinting (e.g., Commander's Herald). Use `--max-length` to avoid overwhelming context with full page content.

**Key principle:** Research informs but doesn't dictate. EDHREC popularity doesn't automatically make a card right, and unpopularity doesn't make it wrong.

**Combo discovery (optional):** For deeper exploration beyond what `combo-search` surfaces from the current deck list, use `combo-discover` to find combo lines the deck could support. Search by cards already in the deck (`--card "Key Card"`) or by desired outcomes (`--result "Infinite X"`). This is especially useful for finding unusual synergies that EDHREC and Commander Spellbook's `find-my-combos` don't surface.

**Brawl format note:** EDHREC data is sourced from Commander/EDH decks. When tuning a Brawl deck, EDHREC recommendations must be legality-checked against the deck's format before recommending. Use `card-search --format <format>` to verify candidates are legal. For Arena decks, also use `--arena-only` to ensure cards are actually available on MTG Arena — some cards are legal in Brawl/Historic but have no Arena printing.

## Step 5: Strategy Alignment Check

Before analyzing individual cards, present your understanding of the commander's key mechanics and the strategic directions they suggest. **Ask the user to validate or expand this.**

For example: "Based on Alibou's oracle text, the deck wants: (1) high artifact density for bigger X triggers, (2) go-wide with artifact creature tokens, and (3) extra combats to re-trigger. Does that match how you think about the deck, or are there angles I'm missing?"

This catches blind spots — the user may see synergies you missed (like trigger-copying effects, combo lines, or political angles). Don't start evaluating cards until you and the user agree on what "good" looks like for this specific commander.

Present your estimated trigger multiplier range for `cut-check` analysis (e.g., "Based on Obeka's 3 base power with typical pump, I'm estimating 3-7 extra upkeeps per hit"). **Ask the user to validate this range.** The multiplier range feeds into `cut-check` and determines how trigger values are evaluated.

## Step 5.5: Commander Interaction Audit

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
- A +1/+1 counter source on a commander whose trigger scales with power (more counters → more damage → more triggers → more counters)
- A token creator that increases a count used by another card's scaling ability
- A theft effect where stolen permanents change type to match a tribal count, increasing future theft
- A card that draws cards in a hand-size-matters deck

Cards with feedback loops are almost always stronger than they appear in isolation. Flag them before the analysis phase.

### Recurring Cards

Identify all cards that return themselves to a usable zone: re-suspend, buyback, retrace, escape, flashback, "return to hand" clauses, "exile with time counters" effects. Evaluate these on their per-game value (total free casts over a typical game), not their per-cast value. A 6-mana spell that re-suspends and gets cast for free every 1-2 turns is a permanent with a triggered ability, not a one-shot.

### Commander Multiplication

Identify cards that multiply the commander's impact. Two categories:

**Commander copies** — cards that create token copies or become copies of the commander (Helm of the Host, Spark Double, Clone effects, Mirror March, Followed Footsteps). Non-legendary copies bypass the legend rule and retain all triggered and activated abilities, so each copy functions independently — a commander with three triggered abilities effectively becomes two commanders when copied.

**Ability copiers and trigger multipliers** — cards that copy or double the commander's triggered/activated abilities (Strionic Resonator, Rings of Brighthearth, Panharmonicon for ETB commanders, Teysa Karlov for death triggers, Isshin for attack triggers, Sundial of the Infinite for "until end of turn" effects, Seedborn Muse for extra activations).

Scan oracle text for these patterns directly — `cut-check`'s `commander_multiplication` field (which the §6.5 mechanical pass surfaces against the proposed cuts list) catches the obvious cases via keyword detection but misses oddly-worded effects. **These cards are force-multipliers.** Treat any card you flag as untouchable when drafting cuts — it should not appear on the cuts list at all without explicit justification that the replacement provides comparable strategic value.

### Combo Detection

Run the combo search on the deck:

Run: `combo-search <parsed-deck-json> --output /tmp/combo-search.json`

Stdout is a compact text report listing existing combos (labeled `GAME_WINNING` or `VALUE`) with their card lists and results, then near-misses with the missing card identified. The first line names counts (e.g., `combo-search: 2 existing combos (1 game-winning, 1 value), 3 near-misses`). The last line is `Full JSON: <path>` naming the full structured data for Step 7 subagents. Review the text report directly:

**Existing combos:** List each combo with its cards, result, and bracket tag. Flag all cards involved as combo pieces — these cards must not be evaluated in isolation during analysis. Distinguish between:
- **Game-winning combos** (result contains "infinite" or "win the game"): flag prominently, these are critical to protect during analysis.
- **Value interactions** (non-infinite synergies): note as context, but these don't block cuts.

**Near-misses:** List combos the deck is one card away from completing, with the missing card identified. These are potential additions to evaluate in Step 6.

**Before recommending any near-miss as an add, `Read` the full `description` field for that near-miss from the combo-search JSON** (use `offset`/`limit` — don't read the whole file). The compact text report shows only the card list and the result; the JSON's `description` spells out the activation sequence and frequently names **additional required pieces** that aren't in the card list. Example: a "Monk Gyatso + Lightning Greaves = infinite ETBs" near-miss whose description says "Cast the creature from exile by paying {0} due to its affinity ability" actually needs a third card — an affinity creature that goes to 0 mana — without which the two listed pieces do nothing. Recommending a near-miss without reading its description is an Iron Rule violation.

**Bracket compliance:** Check combo results against the user's target bracket:
- **Bracket 1-2:** Intentional two-card infinite combos are prohibited. Flag existing infinite combos as bracket violations — they must be cut or the user must acknowledge they're playing above bracket. Do NOT suggest near-miss infinite combos as additions.
- **Bracket 3:** Infinite combos are allowed but should not reliably fire before turn 6. Flag low-CMC/easily-tutored infinite combos as potential bracket concerns.
- **Bracket 4:** No restrictions on combos.

If `combo-search` returns empty results (API unavailable), proceed without combo data — the analysis works fine without it.

## Step 6: Analysis

Group cards by commander-aware roles — roles defined by how they work with THIS commander, not generic categories. Analyze each group as a unit.

**For every card, answer:** "How does this card specifically interact with this commander?" Cite the oracle text.

### Mana Base & Curve Audit

Before evaluating individual cards, count the deck's mana infrastructure:
- **Land count** and **ramp pieces** (mana rocks, dorks, land-fetching spells)
- **Average CMC** of nonland cards
- **Curve distribution** (how many cards at each mana value)

**Land count is a hard constraint, not a suggestion.** Calculate the Burgess formula result (`31 + colors_in_identity + commander_cmc`) and treat it as the target. The `mana-audit` script enforces this — if it returns FAIL, you must add lands or cut fewer lands.

Proposing a land count below the Burgess formula result requires the `mana-audit` script to return PASS or WARN (not FAIL). Proposing a land count below 36 is almost always a FAIL. Do not rationalize — fix it.

Flag any existing problems: too few lands, curve too high, not enough ramp for the curve, color fixing gaps.

Sources: [EDHREC Superior Numbers](https://edhrec.com/articles/superior-numbers-land-counts), [Draftsim Land Count Guide](https://draftsim.com/mtg-edh-deck-number-of-lands/), Frank Karsten's Commander mana base simulations.

### Interaction Audit

Count the deck's removal and interaction pieces. Compare against bracket-appropriate targets:

| Category | Bracket 1-2 (Casual) | Bracket 3 (Upgraded) | Bracket 4 (Optimized) |
|----------|----------------------|----------------------|----------------------|
| Targeted removal/disruption | 5-7 | 8-10 | 10-12 |
| Board wipes | 2-3 | 3-4 | 4-5 |
| Total interaction | 8-10 | 12-14 | 15-18 |

"Disruption" includes counterspells, discard, and stax pieces — not just creature/artifact removal. Flag decks that fall below the low end of their bracket's range.

Sources: [Command Zone #658](https://edhrec.com/articles/the-command-zone-commander-deckbuilding-template-for-the-new-era-the-command-zone-658-mtg-edh-magic-gathering), [EDHREC Solve the Equation](https://edhrec.com/articles/solve-the-equation-choosing-and-using-your-interaction), [MTGGoldfish Deckbuilding Checklist](https://www.mtggoldfish.com/articles/the-power-of-a-deckbuilding-checklist-commander-quickie)

### Analysis Dimensions

- Synergy with the commander and other cards
- Mana curve distribution
- Card type balance (creatures, interaction, ramp, draw)
- Removal/interaction suite
- Win conditions
- Mana base quality
- Bracket compliance (count Game Changers vs. target bracket)
- Pain point focus (weight toward user-identified issues)
- Combo awareness (reference combo data from Step 5.5 — combo pieces should be evaluated in context of the combo, not in isolation; near-miss cards are candidates for additions)

### Cut Checklist

Before recommending ANY cut, work through this checklist for every candidate. Skipping items is how cards get misjudged.

0. **Full oracle text verification.** Before evaluating any card for a cut, re-read the card's complete oracle text from the hydrated data (Step 2). The `card-summary` table truncates oracle text and is for scanning only, not for evaluating individual cards. Never base a cut decision on truncated oracle text.

0.5. **Alternative cost check.** If the card has suspend, foretell, adventure, evoke, flashback, escape, or other alternative casting costs, evaluate at the cost most likely to be used in this deck, not the printed CMC. A suspend card in an extra-upkeep deck is not an 8-drop.

1. **Clause-by-clause oracle text analysis.** Read each sentence of the card's oracle text independently. Ask: "How does THIS specific clause interact with my commander and the deck's strategy?" Cards often have 3-4 separate abilities. If you only evaluated one, you haven't read the card. Common missed clauses:
   - Attack/block restrictions ("can't attack its owner," "can't be blocked by more than one creature")
   - Type-changing effects ("is a Mercenary in addition to its other types")
   - Self-recurring mechanics (re-suspend, return to hand, exile with counters)
   - Static effects on other permanents ("creatures you control but don't own are...")

2. **Defensive value check.** Does this card reduce incoming damage or attacks? Protect other permanents? Deter opponents politically? Force opponents to attack each other? If the user's pain point involves survivability, weight defensive value higher than offensive value.

3. **Feedback loop check.** Does removing this card break a self-reinforcing cycle? (See Step 5.5.) If so, the cut needs much stronger justification.

4. **Pain point regression check.** Does cutting this card make the user's stated problem worse? A card that gains life in a deck whose pilot gets ganged up on may be load-bearing even if it looks underpowered.

5. **Multiplied value calculation.** Calculate the card's output at the commander's expected trigger multiplier (see Step 5.5). If a trigger looks weak at 1x but kills a player at 5x, it is a win condition, not a role player. Do not cut win conditions for utility unless replacing with a better win condition.

6. **Combo piece check.** Is this card part of an existing combo line (from the §5.5 combo search)?
   - **Game-winning combos** (result contains "infinite" or "win the game"): hard to justify cutting. Valid justifications include "too slow for the bracket" or "bracket violation per §5.5" — "I didn't notice it was a combo piece" is not. If cutting, note which combo it breaks and verify the replacement strategy still has a viable win condition.
   - **Value interactions** (non-infinite synergies): a soft consideration, not a hard gate.

### Cuts — Be Careful

Before recommending ANY cut, re-read the oracle text of BOTH the card and the commander. Articulate specifically why the card underperforms in THIS deck. Cards that look mediocre in general can be incredible with specific commanders.

### Additions

Source from EDHREC high-synergy cards and web research. Supplement with `card-search` to find synergistic cards EDHREC may not surface — search the local bulk data by color identity, oracle text, type, CMC, and price:

Run: `card-search --bulk-data <bulk-data-path> --color-identity <ci> --oracle "<relevant-keyword>" --price-max <budget-per-card>`

Recommend the cheapest available printing. Track running cost against budget.

### Swap Balance Check

After drafting all cuts and additions, verify the swaps don't break the mana base:
- **Land count must stay in a healthy range.** If you cut a land, you must add a land (or add ramp to compensate). If the deck is already land-light, don't cut lands at all.
- **Mana curve must not get worse.** If you're cutting a 2-drop for a 5-drop, note the curve impact. Swaps that raise the average CMC need justification.
- **Color balance matters.** Don't cut the deck's only source of a color. Check that color-producing land count supports the color requirements of the additions.
- **Ramp count must stay stable.** Don't cut ramp pieces unless the deck has too many or you're adding equivalent ramp.
- **Color balance must be verified quantitatively.** After drafting all swaps, run `mana-audit --compare` with the old and new deck. If any color's land percentage drops below its pip demand percentage, adjust the mana base (swap a basic land for a different basic, replace a dual land, etc.). Do not present swaps that create a color deficit.

If the swaps would damage the mana base, revise before presenting. It is better to make fewer swaps than to break the deck's ability to cast its spells.

## Step 6.5: Mechanical Cut Check

Run `price-check` on all proposed additions with the user's budget (`price-check <adds-names-json> --budget <budget> --bulk-data <bulk-data-path> [--format <format>] --output /tmp/price-check.json`). For Arena formats, use `--format brawl` or `--format historic_brawl` to get wildcard costs (lowest rarity per card) instead of USD prices. Stdout is a compact text report with per-card price, running total, and PASS/OVER BUDGET status. If any single card or the total exceeds budget, find cheaper alternatives before proceeding. Do not send cards to the self-grill that the user cannot afford.

Before launching the self-grill, run `cut-check` on every proposed cut (`cut-check <hydrated-cards-json> "<Commander Name>" --cuts <cuts-names-json> --multiplier-low <low> --multiplier-high <high> --opponents <N> --output <cut-check.json>`). Stdout is a compact text report with one line per cut card summarizing flags (`COMMANDER_MULTIPLICATION`, `triggers=N (type=value-range)`, `self-recurring=yes/no`, `keyword-interactions=N`) plus a `Flags:` tally line. Read the report directly — it is sufficient for the §6.5 evaluation below. For any flagged card where you want to see the full trigger text, keyword interaction details, or commander_copy match strings, `Read` the JSON file at the `Full JSON:` footer path (use offset/limit to pull only the entries you care about).

For each proposed cut, write out (internally, not presented to user):
1. **Multiplied value:** [from cut-check output, or "no matching triggers"]
2. **Pain point regression:** Does cutting this card make the user's stated problem worse? [yes/no + one sentence why]
3. **Defensive value:** What does this card prevent, deter, or protect? [one sentence, or "none"]
4. **Replacement justification:** What specific card in the additions replaces this card's role? [name + one sentence]
5. **Combo line:** Is this card part of a combo from Step 5.5? [combo name + result, or "not a combo piece"]. If game-winning, justify why cutting is acceptable.

If you cannot fill in all five fields, you have not evaluated the card. Do not proceed to the self-grill.

Review the multiplied trigger values from `cut-check` output. Any cut where the multiplied output is significant for the user's stated goals requires explicit justification for why the replacement is better *for the user's pain point*. If you cannot articulate this, do not cut it.

## Step 7: Self-Grill (Two-Agent Debate)

> **HARD GATE.** Step 7 is satisfied only by **two `Agent` tool invocations** (proposer + challenger) and at least one round of revision based on the challenger's report. Running the §6.5 mechanical gates (`cut-check`, `mana-audit`, `price-check`, `combo-search`) is NOT a substitute — those gates catch *mechanical* errors; the self-grill catches *strategic* errors (missed synergy angles, wrong commander fit, weak swap justification, paraphrased oracle text). If you proceed to Step 8 without the two Agent calls in this turn's tool history, you have skipped the gate. Do not rationalize this as "the gates already passed" or "the deck is freshly built and low-stakes" — the discipline failure mode for this step is *exactly* that rationalization.

Before presenting to the user, launch **two subagents** that debate the proposed changes. Use `subagent_type: "general-purpose"` for both, dispatched in parallel via two `Agent` tool calls in a single message.

**Data delivery: file paths, not pasted content.** All upstream script outputs already exist as files on disk (every script in §5.5, §6.5, and §8 writes to `$TMPDIR/...-<sha>.json` or `<cache-dir>/hydrated-<sha>.json` by default; pass `--output PATH` if you want a specific location). Build each subagent prompt with **file paths and a one-paragraph bottom-line summary**, never with pasted JSON. Both subagents have the `Read` tool and can load specific entries selectively (use `offset`/`limit` or `Grep` on the files to pull only what they need). Pasting JSON into subagent prompts wastes tokens twice — once for each subagent.

**Fallback if `Read` is unavailable.** If a dispatched subagent reports it cannot `Read` the provided path (unexpected tool-set restriction, sandbox difference, etc.), the parent must paste the relevant file excerpt into a follow-up message to that subagent — never dump the entire file. Extract the specific entries the subagent asked about. This converts a silent breakage into a recoverable fallback at the cost of one extra round-trip.

Required file paths to hand to both subagents:
- The hydrated cards `cache_path` from the §2 scryfall-lookup envelope (full card data for the whole deck)
- `cut-check` output from §6.5
- `mana-audit` output from §6.5 and §8
- `price-check` output from §6.5
- `combo-search` output from §5.5
- The proposed cuts JSON file and the proposed adds JSON file

Required bottom-line summary (one paragraph) derived from the compact text reports you already read: "cut-check flagged N commander_multiplication + M triggers across the cuts; mana-audit returned PASS/WARN/FAIL; price-check total is $X of $Y budget with Z over-limit cards; combo-search found N game-winning combos in the deck, K of which are affected by the proposed cuts."

**Proposer** defends the proposal. Framing to paste into the proposer prompt:

> "These are the mechanical flags from analysis. You addressed them in your proposal. Defend your reasoning against the challenger's points. Do not concede a point unless the challenger provides a specific oracle text interaction or quantitative argument you missed. Use `Read` on the hydrated cache file (`<cache_path>`) to re-verify oracle text claims when needed. Pushing back is your job."

**Challenger** attacks the proposal. Paste the file paths, the bottom-line summary, and this checklist verbatim (the challenger cannot follow back-references to this SKILL.md — the instructions must be self-contained):

- `Read` the hydrated cache file for every proposed cut independently. Do NOT rely on the proposer's paraphrasing — any discrepancy between the proposer's description and the actual oracle text is an automatic flag. Use `offset`/`limit` to read only the cards you want to verify; the cache is large.
- Check every clause of every cut card's oracle text, not just the primary ability. Defensive restrictions, type-changing effects, self-recurring mechanics, and static effects on other permanents are commonly missed.
- Verify keyword interactions between the commander and each cut card. Flag emergent combinations (e.g., menace + "can't be blocked by more than one creature" = unblockable; double strike + lifelink = double life).
- Calculate the multiplied value of any upkeep/combat/phase/etb triggers being cut. A trigger that looks weak at 1x may be a win condition at 5x with 3 opponents. `Read` the cut-check JSON file to pull the exact trigger text and base values for any card you want to challenge.
- `Read` the cut-check JSON and verify every flag (commander_multiplication, parseable triggers, keyword_interactions, self_recurring) was addressed by the proposer. Any unaddressed flag is an automatic challenge.
- `Read` the mana-audit JSON and verify `overall_status` is PASS. Any WARN or FAIL is an automatic challenge. Check `color_balance_flags` and the per-color `land_color_pct` vs. `pip_demand_pct` for any color deficits.
- Verify the swap balance: land count, curve, ramp count, color balance.
- `Read` the price-check JSON and verify total cost ≤ budget. Flag any single card that consumes a disproportionate share of the budget.
- `Read` the combo-search JSON and verify no proposed cut breaks a game-winning combo without explicit justification from the proposer. Any unaddressed combo break is an automatic challenge.
- Look for missing synergy angles the proposer didn't consider; challenge whether the most expensive add is really the highest priority.
- For Brawl formats, scrutinize Voltron strategies extra hard (no commander damage). Account for lower life totals and free mulligan.
- **Commander fitness check** — apply the *commander identity test:* "If this deck's commander were hidden, could you guess what it is from the cards?" If not, the commander may not be driving the strategy. Count mechanical interactions with the commander's oracle text (not thematic overlap), compare its CMC against the mana base, and trace the user's pain points back to it. If underperforming, shortlist 1-2 alternative commanders whose identity covers the existing card pool, verify each via `scryfall-lookup`, and surface them as a close call in §9 — never as a firm recommendation.

The challenger reports issues. The proposer responds or revises. Repeat until the challenger has no remaining objections.

**This is not a formality.** If both agents agree immediately, something is wrong — the challenger isn't pushing hard enough. Expect at least 2-3 rounds of challenges.

## Step 8: Propose Changes

**Before presenting any proposal to the user, run `mana-audit` on the proposed new deck (using `build-deck` output). If `mana-audit` returns FAIL, revise cuts/adds until it passes. Do not present a failing proposal.**

This is not a guideline. It is a gate. A proposal with FAIL status does not leave this step.

**The user has not seen the debate.** Present the post-debate proposal as a complete, self-contained recommendation with full reasoning for every swap. Do not reference the debate, do not say "after reviewing" or "the revised list" — present it as your recommendation with the reasoning baked in.

For each swap, explain:
- Why the cut underperforms with THIS commander (cite oracle text)
- Why the addition is better for the strategy (cite oracle text)
- Any mana base or curve impact

Present changes adapted to the user's experience level:
- **Beginner:** Full explanations, define terms like "card advantage"
- **Intermediate:** Explain specific interactions, skip basics
- **Advanced:** Concise tables, minimal explanation

Format: paired swaps where possible (cut X → add Y). Show running price total and swap count vs. budget.

## Step 8.5: Impact Verification

Before presenting close calls, verify the proposal's impact on deck metrics:

Run: `deck-diff <old-deck.json> <new-deck.json> <old-hydrated.json> <new-hydrated.json>`

Confirm:
- Total card count matches the deck's expected size
- Land count stays in a healthy range
- Average CMC didn't increase unexpectedly
- Ramp count didn't decrease

If any metric is off, revise the proposal before continuing.

## Step 9: Close Calls

After presenting the proposal, surface any **close calls from the debate** — swaps where the proposer and challenger genuinely disagreed, or where a card was borderline keep/cut. Present these as decisions for the user:

> "A few things that were close calls — I'd like your input:"
> - "Card X could go either way. It does A (good with your commander) but also B (bad). Keep or cut?"
> - "I considered Card Y as an addition but it costs $Z. Worth it, or would you rather save the budget?"

This gives the user final say on the genuinely debatable choices without making them re-evaluate every swap. Adjust the proposal based on their answers.

### Commander Swap Consideration

If the challenger flagged the commander during the self-grill, present it as a close call — never as a firm recommendation:

> "One thing worth considering: [specific observation about why the commander underperforms with this deck's composition]. [Alternative Commander] in the same colors does [specific oracle text interaction] which fits better with what the deck is actually doing. This would be a significant change though — worth exploring, or do you want to keep [current commander]?"

**This is always a close call.** The user chose their commander for a reason. The skill surfaces the information; the user decides.

## Step 10: Finalize

Output the updated deck list in the same format as the input. Export a Moxfield-importable text file:

Run: `export-deck <new-deck.json>`

### Final Budget Summary

Run `price-check` on the complete final deck to get the total cost:

Run: `price-check <new-deck.json> --bulk-data <bulk-data-path> [--format <format>]`

For Arena formats, use `--format brawl` or `--format historic_brawl` to get wildcard costs.

Present a budget summary that shows the full picture. For paper/Commander:

> **Budget Summary**
> | | Cost |
> |---|---|
> | Skeleton (from builder) | $X |
> | Upgrades (this session) | $Y |
> | **Total deck cost** | **$Z** |
> | Owned cards (not counted) | card1, card2, ... |
> | Total budget | $B |
> | **Remaining** | **$R** |

For Arena (Brawl/Historic Brawl with wildcard budget):

> **Wildcard Summary**
> | Rarity | Used | Available | Remaining |
> |--------|------|-----------|-----------|
> | Mythic | X | Y | Z |
> | Rare | X | Y | Z |
> | Uncommon | X | Y | Z |
> | Common | X | Y | Z |

If the total budget was not provided (standalone tuner session without builder), show just the upgrade cost and total deck cost.

Include: summary of changes, swap count.

Offer (don't force): mana curve before/after, category breakdown comparison, "next upgrades" list for future budget.

## Red Flags — STOP If You Catch Yourself Thinking These

| Thought | Reality |
|---------|---------|
| "I know what this card does" | You don't. Look it up. Training data is not oracle text. |
| "EDHREC recommends it so it must be good here" | EDHREC is aggregated data, not analysis. Evaluate for THIS build. |
| "This card is generally weak" | Weak in general ≠ weak with this commander. Read both oracle texts. |
| "We're over budget but this card is too good to skip" | Budget is a hard constraint. Find a cheaper alternative. |
| "My analysis is thorough enough, no need to self-grill" | The self-grill catches exactly this overconfidence. Run it every time. |
| "I ran cut-check + mana-audit + price-check, that covers Step 7" | No. Those are §6.5 *mechanical* gates. Step 7 is the *strategic* gate and requires two Agent tool calls in this turn. Mechanical gates catch zero of: missed synergy angles, paraphrased oracle text, wrong commander fit, weak swap justification. |
| "This deck just came from the builder, the self-grill is overkill" | The builder runs no adversarial review. A fresh skeleton is the highest-leverage moment for a challenger pass — that's when bad assumptions are cheapest to fix. Run it. |
| "I'll dispatch the agents next turn / after the user confirms" | No. Step 7 must complete in the same turn as Step 8. Splitting it across turns means the user sees the proposal before the challenger has reviewed it, which defeats the purpose. |
| "This step seems unnecessary for this deck" | Follow every step. The process exists because shortcuts cause mistakes. |
| "Cutting this land for a nonland is fine, the deck has enough" | Count the lands. Count the ramp. Do the math. Don't eyeball mana bases. |
| "I understand what this commander wants" | You might be missing angles. Present your strategic read and ask the user before analyzing. They play the deck — you don't. |
| "This card only works with N other cards in the deck" | Check whether the card creates its own enablers — theft effects that change types, token creators that increase counts, self-recurring cards that sustain themselves. |
| "This trigger is too small to matter" | Multiply by expected extra triggers AND by number of opponents. 1 damage × 5 upkeeps × 3 opponents = 15. Do the math. |
| "This is redundant evasion/protection" | Redundancy in the deck's most important effects is intentional. Before cutting, check whether the card creates a unique mechanical interaction (e.g., blocking restriction + menace = unblockable) that no other card replicates. |
| "I can cut one more land, the ramp covers it" | Run `mana-audit`. If it says FAIL, you cannot. Ramp does not replace lands — it supplements them. |

## Experience Level Adaptation

| Aspect | Beginner | Intermediate | Advanced |
|--------|----------|--------------|----------|
| Terminology | Define terms (card advantage, tempo, etc.) | Use terms freely | Use shorthand |
| Explanations | Why each card matters | Focus on non-obvious interactions | Just the synergy line |
| Mana curve | Explain what good curve looks like | Note problems | Numbers only |
| Presentation | Narrative with examples | Grouped analysis | Concise tables |

## Script Input Formats

- `parse-deck <path> [--format FORMAT] [--deck-size N]` — outputs `{"format": str, "deck_size": int, "commanders": [{"name": str, "quantity": int}], "cards": [...], "total_cards": int, "owned_cards": [{"name": str, "quantity": int}]}`. All three card lists share the `[{name, quantity}]` shape; `owned_cards` is initialized empty and populated by `mark-owned`. Supports Moxfield (`//Commander` headers), Arena (bare `Commander`/`Deck` headers), MTGO, plain text, and CSV. **Note:** `<path>` must be an absolute path when using `uv run --directory`.
- `set-commander <deck.json> "Name" ["Name2"]` — outputs updated deck JSON to stdout. Idempotent: names already in the commander zone are silently skipped, so `parse-deck | set-commander` is safe even when the source file had a Moxfield `Commander` header.
- `mark-owned <deck.json> <collection.json> [--output PATH]` — populates the deck's `owned_cards` field with the intersection of `deck ∩ collection` (by normalized, diacritic-folded card name). Writes in place by default; `--output` writes elsewhere. Use this instead of inline `python3 -c` for the owned-cards intersection — content-varying Python bodies produce un-cacheable Bash permission patterns.
- `scryfall-lookup "Card Name"` — outputs single card JSON to stdout
- `scryfall-lookup --batch <path> [--cache-dir DIR]` — accepts either a JSON list of name strings or a parsed deck JSON. Stdout is a JSON envelope `{cache_path, card_count, missing, digest}`. Full hydrated card list is written to the sha-keyed `<cache_dir>/hydrated-<sha>.json` (default `<cache_dir>` is `$TMPDIR/scryfall-cache/`). Downstream scripts accept `cache_path` as `<hydrated-cards-json>`. The envelope is bounded (~400 bytes regardless of deck size) — never Read the cache file directly.
- `price-check <path> [--budget N] [--bulk-data <path>] [--format FORMAT] [--output PATH]` — accepts either a JSON list of name strings or a parsed deck JSON. Stdout is a compact text report with per-card price (or wildcard rarity for Arena formats), running total, and budget status. Full JSON is always written to `$TMPDIR/price-check-<sha>.json` by default. For Arena formats (`brawl`, `historic_brawl`), the text report shows wildcard counts by rarity instead of USD. Auto-detects format from deck JSON if not specified.
- `build-deck <deck-json> <hydrated-json> [--cuts <path>] [--adds <path>] [--bulk-data <path>] [--output-dir <dir>]` — applies cuts/adds, writes `new-deck.json` and `new-hydrated.json`. Cuts/adds accept list of `{"name": str, "quantity": int}` dicts or plain name strings (quantity defaults to 1). Output defaults to the same directory as `<deck-json>`.
- `cut-check <hydrated-json> "<Commander Name>" --cuts <path> --multiplier-low N --multiplier-high N [--trigger-type TYPE ...] [--opponents N] [--output PATH]` — mechanical pre-grill analysis. `--cuts` expects JSON list of name strings; `--multiplier-low`/`--multiplier-high` are required; `--opponents` defaults to 3. Stdout is a compact text report (one line per cut card plus a `Flags:` tally) with a `Full JSON: <path>` footer. Full structured JSON is always written to the path (default: `$TMPDIR/cut-check-<sha>.json`); `--output` overrides the default. Pass the file path to Step 7 subagents; they `Read` it selectively.
- `deck-stats <deck.json> <hydrated.json> [--output PATH]` — stdout is a compact text report (total cards, types, avg CMC, curve, color sources, alternative-cost cards). Full JSON is written to `$TMPDIR/deck-stats-<sha>.json` by default (includes `alternative_cost_cards` with full structure: `{"name": str, "cmc": float, "alt_costs": [...]}`).
- `mana-audit <deck.json> <hydrated.json> [--compare <new-deck.json> <new-hydrated.json>] [--output PATH]` — stdout is a compact text report (PASS/WARN/FAIL, land count, Burgess/Karsten targets, per-color pip demand vs. land and rock production percentages, color balance status, any flags). With `--compare`, shows primary/comparison side-by-side plus a delta line. Full JSON is written to `$TMPDIR/mana-audit-<sha>.json` by default.
- `legality-audit <deck.json> <hydrated.json> [--output PATH]` — audits format legality, color identity, and singleton rule against the declared format. Stdout is a compact text report (`legality-audit: PASS/FAIL — ...`) with per-category violation lists. Full JSON at `$TMPDIR/legality-audit-<sha>.json` contains `overall_status`, `counts`, and a `violations` dict keyed by `format_legality`, `color_identity`, `singleton`. Checks commanders and non-commanders uniformly against `legalities[<format>]`; honors the Brawl/Historic Brawl colorless-commander exemption allowing one basic land type; honors "A deck can have any number of cards named X" and "A deck can have up to N cards named X" oracle text for the singleton check.
- `export-deck <deck.json>` — outputs Moxfield import format (`N CardName` lines) to stdout
- `card-search --bulk-data <path> [--color-identity CI] [--oracle REGEX] [--type TYPE] [--cmc-min N] [--cmc-max N] [--price-min N] [--price-max N] [--sort price-desc] [--limit 25] [--json] [--fields name,type_line,cmc,...] [--format FORMAT] [--arena-only] [--paper-only] [--is-commander]` — searches local bulk data for cards matching filters; `--format` filters by format legality (commander, brawl, historic_brawl); `--arena-only` restricts to cards on MTG Arena; `--paper-only` excludes Arena-only digital cards; `--is-commander` filters to cards eligible as commanders (format-aware: includes planeswalkers for brawl); output includes rarity column (C/U/R/M); default output is a compact table sorted by price descending. Use `--fields` with `--json` to project only the card fields you need (e.g. `--fields name,type_line,cmc,color_identity`); omitting it returns the full 12-field set. The default text-table output is already compact — `--json` is for callers that need structured output to feed into other tools.
- `combo-search <parsed-deck-json> [--max-near-misses N] [--output PATH]` — find existing combos and near-misses in the deck via Commander Spellbook. Stdout is a compact text report listing combos (labeled `GAME_WINNING` or `VALUE`) and near-misses (with the missing card identified). Full JSON is written to `$TMPDIR/combo-search-<sha>.json` by default.
- `combo-discover [--result "Infinite X"] [--card "Card Name"] [--color-identity CI] [--sort popularity] [--limit 10] [--format FORMAT] [--arena-only] [--paper-only] [--bulk-data PATH] [--output PATH]` — discover combos from Commander Spellbook by outcome (`--result`), card name (`--card`, repeatable), or color identity. Stdout is a compact text report with one entry per combo showing popularity, bracket, color identity, card count, card list, and result. Full JSON is written to `$TMPDIR/combo-discover-<sha>.json` by default (overridable with `--output`). `--sort popularity` returns obscure combos first, `--sort -popularity` returns popular ones; `--arena-only`/`--paper-only` filter combo pieces by platform availability.
- `find-commanders <parsed.json> --bulk-data <path> [--format FORMAT] [--color-identity CI] [--min-quantity N] [--output PATH]` — from a parsed deck/collection JSON (output of `parse-deck`), returns owned, format-legal, commander-eligible cards as a JSON array. Each entry includes `name`, `color_identity`, `type_line`, `mana_cost`, `cmc`, `oracle_text`, `edhrec_rank`, `game_changer`, `is_partner`, `partner_with`, `has_background_clause`, `owned_quantity`. Defaults: `--format commander`, `--min-quantity 1`. The script does no ranking — agents do that, weighted by user preferences. Used primarily by commander-builder for collection-aware commander selection. **Always pass `--output <working-dir>/.cache/candidates.json`** — the default output path is under `$TMPDIR`, which is outside the workspace and triggers an outside-workspace permission prompt on every subsequent `Read`.
