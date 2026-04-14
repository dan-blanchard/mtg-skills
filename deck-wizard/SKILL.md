---
name: deck-wizard
description: Build and tune MTG decks across all formats — Commander/EDH, Brawl, Historic Brawl, Standard, Alchemy, Historic, Pioneer, Timeless, Modern, PreModern, Legacy, and Vintage.
compatibility: Requires Python 3.12+ and uv. Shares mtg_utils package via symlink.
license: 0BSD
---

# Deck Wizard

Build MTG decks from scratch or tune existing ones, across every supported format: Commander/EDH, Brawl, Historic Brawl (singleton formats with commanders) and Standard, Alchemy, Historic, Pioneer, Timeless, Modern, PreModern, Legacy, Vintage (60-card constructed formats with sideboards). Every recommendation MUST be grounded in actual card oracle text from Scryfall — never from training data.

The skill has two phases. **Phase 1 (Deck Acquisition)** determines how the user gets a deck: either by parsing an existing list (Path A) or building from scratch (Path B). Both paths produce a deck JSON + hydrated cache. **Phase 2 (Tuning)** runs the same 12-step pipeline on that deck regardless of origin.

## The Iron Rule

**NEVER assume what a card does.** Before referencing any card's abilities, look up its oracle text via the helper scripts. Training data is not oracle text.

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

**Before starting, create a `TodoWrite` list.** The first question determines the path; create todos accordingly.

### Phase 1: Path A (Tune Existing Deck)

- Parse Deck List
- Hydrate Card Data

### Phase 1: Path B (Build from Scratch)

#### 60-Card Constructed

- Interview
- Metagame Research
- Skeleton Generation
- Structural Verification

**Skeleton Generation expansion:** When starting, expand into sub-todos:
- Fill Creatures/Threats
- Fill Removal/Interaction
- Fill Card Advantage
- Fill Utility/Flex Slots
- Fill Mana Base
- Fill Sideboard (Bo3 only)

**Combo-first variant:** If the user wants to build around a combo, add/swap:
- Combo/Build-Around Discovery (replaces standard research intro)
- Shell Construction (replaces Metagame Research)
- Skeleton with Combo Core (replaces standard Skeleton Generation)

#### Commander/Brawl/Historic Brawl

- Interview
- Commander Analysis
- Skeleton Generation
- Structural Verification

**Skeleton Generation expansion:** When starting, expand into sub-todos:
1. Fill Lands
2. Fill Ramp
3. Fill Card Draw
4. Fill Targeted Removal & Board Wipes
5. Fill Protection/Utility
6. Fill Engine/Synergy Pieces
7. Fill Win Conditions
8. Structural Verification (deck-stats, mana-audit, price-check)

If you draft the whole skeleton in a single batch instead of walking the fill order category-by-category, you still must not batch the sub-todo completions. Either (a) skip creating the fill-order sub-todos entirely for that session (mark only the top-level Skeleton Generation as it starts and completes) or (b) close each sub-todo individually at draft time as you mentally finish that category.

**If the user takes the "Outside the Box" workflow**, add or swap todos as you reach each alt step, leaving any already-completed standard steps in place.

Do NOT create per-card sub-todos inside any fill step — that's execution detail and would flood the list.

### Phase 2: Tuning (Both Paths)

1. Step 1: Baseline Metrics
2. Step 2: User Intake
3. Step 3: Research
4. Step 4: Strategy Alignment
5. Step 5: Commander Interaction Audit *(Commander/Brawl/Historic Brawl only — skip for 60-card constructed)*
6. Step 6: Analysis
7. Step 7: Pre-Grill Verification
8. Step 8: Self-Grill
9. Step 9: Propose Changes
10. Step 10: Impact Verification
11. Step 11: Close Calls
12. Step 12: Finalize

Mark each item `in_progress` the moment you begin it and `completed` the moment it finishes — **do not batch updates**.

**Step 6 and Step 8 are long enough that the top-level item alone leaves the user staring at an unchanging list.** When you reach them, expand each into sub-todos *at that moment* (not up front):

- **Step 6** sub-todos: 6a Mana Base & Curve Audit, 6b Interaction & Threat Audit, 6c Archetype Coherence, 6d Draft Cuts, 6e Draft Additions, 6f Sideboard Evaluation (60-card only), 6g Swap Balance Check.
- **Step 8** sub-todos: Dispatch Proposer + Challenger Subagents, Process Challenger Report, Revise Proposal.

Do NOT create per-card sub-todos for the Cut Checklist inside Step 6 — that's execution detail and would flood the list.

**Path B adaptations:** Steps 9-11 may produce zero changes if the skeleton is sound. If no changes are needed, skip to Step 12.

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

**Warning — `/tmp` files persist across sessions.** The Write tool requires a prior `Read` for any existing file, so the first `Write` to a reused `/tmp/*.json` path in a new session fails with *"File has not been read yet"*. If you batched that `Write` in parallel with a Bash call that reads the same file, **the Bash silently consumes the stale prior-session content** — the parallel Write error doesn't block the Bash, so `cut-check` / `scryfall-lookup --batch` / `price-check` / `build-deck` will happily run against the wrong data. Symptom: tool results list cards you never proposed. **Rule:** (a) at session start, `Read` each scratch path you plan to reuse before the first `Write`, OR (b) run `Write` sequentially (not parallel) and verify success before the dependent Bash call. Never batch `Write(/tmp/foo.json)` + `Bash(tool reading /tmp/foo.json)` in a single message. If a tool result lists cards that don't match your intended input, suspect stale-file consumption before suspecting a tool bug.

### Alchemy Card Warning

Alchemy includes two categories of digital-only cards beyond the Standard pool: (1) **Rebalanced cards** prefixed with `A-` (e.g., `A-Teferi, Time Raveler`) that have different oracle text from their paper counterparts, and (2) **Digital-only originals** with mechanics that only work on Arena (conjure, seek, perpetually, etc.). When building or tuning Alchemy decks, search for both `"<Card Name>"` and `"A-<Card Name>"` via `scryfall-lookup` to verify which version is legal and what its current oracle text says.

### AskUserQuestion Cap

**AskUserQuestion caps at 4 options — never silently drop the rest.** The tool's schema rejects more than 4 options per question. When presenting a longer list (5+ close-call swaps, 5 alternative commanders, etc.), do NOT pick 4 and hide the rest. List **every** option in the preceding text message with enough detail to decide on, then use AskUserQuestion only as a lightweight picker — either (a) put the top 3 on buttons plus a 4th "Other (specify in notes)" so the user can name any option from the text list, or (b) skip AskUserQuestion entirely for that decision and let the user reply in plain text. The failure mode to avoid is 4 option chips that look like the complete set when the text above mentioned 5+.

### Path Requirements

- **Absolute paths only.** `uv` rebases the working directory to the skill install; relative paths resolve against the wrong root.
- **Cache directory:** Always `<working-dir>/.cache`, not the skill install directory. Keeping the cache in the working directory avoids outside-workspace permission prompts.
- **Re-hydration:** After every deck edit, re-run `scryfall-lookup --batch` on the new deck JSON. The hydrated cache is SHA-keyed; old caches go stale silently.

**Always pass `--format <format>` to `parse-deck` once the format is established.** Without this, `parse-deck` defaults to `commander` and every downstream tool sees the wrong format.

### Arena Rarity Warning

The `rarity` field in hydrated card data is the **default Scryfall printing's rarity**, which drifts from Arena's actual wildcard cost. Always use `price-check --format <fmt> --bulk-data <path>` for Arena wildcard budgeting — it reports the lowest Arena-legal rarity per card by walking every Arena printing.

### Licensed IP Card Warning

Some crossover sets use different card names on Arena than in paper/Scryfall: Through the Omenpaths (OM1, the Arena version of Marvel's Spider-Man), Ikoria Godzilla variants, Crimson Vow Dracula variants, and Avatar: The Last Airbender cards all have name discrepancies. **Always pass `--bulk-data` to `mark-owned`** when working with Arena collections — this enables `printed_name` and `flavor_name` aliasing so cards like "Skittering Kitten" (Arena name) correctly match "Masked Meower" (Scryfall name). Without `--bulk-data`, these cards silently appear unowned.

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
  "owned_cards": [{"name": "Lightning Bolt", "quantity": 4}, ...]
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

All card lists (`commanders`, `cards`, `sideboard`, `owned_cards`) share the `[{name, quantity}]` shape. `owned_cards` starts empty from `parse-deck` and is populated by `mark-owned`. `price-check` reads it to subtract owned copies from the budget; entries with `quantity < 1` are treated as "not owned."

**Parsed deck JSON is the canonical pipeline intermediate.** Once you have a parsed deck JSON from `parse-deck`, pass it **directly** to `scryfall-lookup --batch` and `price-check` — both scripts accept a parsed deck JSON as `<path>`, not just a JSON list of name strings. Do NOT extract card names into a separate `/tmp/*.json` via `python3 -c` or similar. (The exception is scripts whose input is a *subset* of the deck — `cut-check --cuts <path>` and `build-deck --cuts <path> --adds <path>` expect JSON lists of name strings, not parsed deck JSON, because the caller is specifying which cards to act on. Writing a small `/tmp/cuts.json` via the Write tool is correct in those cases.)

### Script Invocation

All scripts are invoked via `uv run <script-name>` from the skill install directory. Examples in this document elide the `uv run` prefix for brevity.

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

`mark-owned` also does front-face aliasing for DFC / split / adventure / modal cards: a deck that lists `"Fable of the Mirror-Breaker"` (front face only, common in Arena/Moxfield exports) matches a collection entry for `"Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"` (Scryfall's canonical combined form) and vice versa. You do not need to normalize these by hand before calling `mark-owned`.

**`price-check` honors deck quantity and owned quantity.** Paper (USD) mode charges `max(deck_qty - owned_qty, 0) * unit_price` per card. Arena wildcard mode applies the same shortfall math plus the Arena 4-cap substitution: owning >=4 of a standard playset-capped card grants effectively infinite supply, but this substitution is suppressed for cards with oracle exemptions (`A deck can have any number of cards named X`).

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
| Run the self-grill (Step 8 hard gate) | Two parallel `Agent` calls with `subagent_type: "general-purpose"` |

Only write `python3 -c` when none of these cover the need. When you do, batch every related question into a single body — each unique body is a fresh permission pattern, so one big script beats five small ones.

---

## Phase 1: Deck Acquisition

Start by asking: **"Do you have an existing deck to tune, or do you want to build from scratch?"**

If the user provides a deck list (pasted, file path, or URL), follow **Path A**. If they want to build from scratch, follow **Path B**.

---

## Phase 1, Path A: Parse + Hydrate Existing Deck

### Parse Deck List

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

#### Commander Formats

If `commanders` is empty (common with Moxfield exports that lack `//Commander` headers), ask the user who the commander is. Don't guess — the first card in the list is often the commander, but not always. Supports partner commanders, friends forever, and background pairings.

Run `set-commander <deck.json> 'Commander Name'` to move the card from the cards list to the commanders list. **`set-commander` is idempotent** — calling it on a card already in the `commanders` zone is a silent no-op, so it's safe to chain after `parse-deck` even when the deck file already had a Moxfield `Commander` header.

#### Collection Ownership (Arena)

If the user has an Arena collection:
1. Ask for Untapped.gg CSV export first (most reliable source)
2. `mark-owned <deck.json> <collection.csv> --bulk-data <path>` to populate `owned_cards` (accepts both CSV and parsed-deck JSON)
3. Use `mtga-import` only for extracting wildcard counts, not collection data

Always pass `--bulk-data` for Arena collections (see Tooling Notes > Populating `owned_cards` for details on aliasing).

### Hydrate Card Data

```
scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <working-dir>/.cache
```

Returns an envelope with `cache_path`, `card_count`, `missing`, `digest`. The cache file contains all mainboard + sideboard + commander cards hydrated with oracle text, legalities, prices, etc.

**Do NOT Read the cache file directly** — it's large and floods context. Use `card-summary` or `scryfall-lookup "<Name>"` for targeted reads.

**Re-hydrate after every deck edit.** The hydrated cache path is SHA-keyed against the deck JSON's content, so editing the deck and re-running `parse-deck` produces a new SHA. If you keep using the old `cache_path`, downstream tools will show stale data. Any time you modify the deck, immediately re-run `scryfall-lookup --batch` and switch all downstream script calls to the new `cache_path`.

After hydration, proceed to **Phase 2: Tuning**.

---

## Phase 1, Path B: Build from Scratch

### Interview

Start by determining the format. Ask: "What format do you want to build for?"

If the user says Commander, Brawl, or Historic Brawl, follow the **Commander/Brawl Interview** below. If they name a 60-card constructed format (Standard, Pioneer, Modern, etc.), follow the **60-Card Constructed Interview**.

If the user mentions Arena without specifying a format, clarify:
- Standard, Alchemy, Historic, Timeless are Arena formats (60-card constructed)
- Standard Brawl (called "Standard Brawl" on Arena) is Brawl
- "Brawl" on Arena actually refers to Historic Brawl
- Pioneer is also on Arena but shares a card pool with paper
- Modern, PreModern, Legacy, Vintage are paper/MTGO only

#### 60-Card Constructed Interview

Each answer informs the next question's options, so ask sequentially via AskUserQuestion:

1. **Format** — Which format? (Standard, Pioneer, Modern, etc.)
2. **Platform** — Arena or paper? (determines pricing mode and card pool filtering; skip if format implies it, e.g., Alchemy is always Arena)
3. **Best-of-One or Best-of-Three?** — Arena only; skip for paper. Bo1 has no sideboarding — skip sideboard construction entirely and build a mainboard optimized for Game 1 resilience (more versatile cards, fewer narrow answers). Bo3 proceeds normally with full sideboard.
4. **Playstyle** — Aggro, midrange, control, combo, tempo? (brief explanations if user is unsure)
5. **Color preference** — Any color preference, or open to anything?
6. **Budget** — USD budget for paper, or wildcard budget for Arena?
7. **Archetype preference** — "Do you want to follow a proven metagame archetype, or build something original/off-meta?"
8. **Pet cards** — Any cards you definitely want to include? (open-ended text, not AskUserQuestion)

Note: questions 2-3 can sometimes be merged or skipped (paper is always Bo3; Legacy/Vintage/Modern are always paper).

##### Combo-First Path

If the user says "build around a combo" or names a specific combo/build-around card, switch to the combo-first variant:

**Combo/Build-Around Discovery:**
- If user names a card: `scryfall-lookup` it, then `combo-discover --card "<Name>" --format <fmt>`
- If user names an outcome: `combo-discover --result "<outcome>" --format <fmt>`
- If user wants to explore: Ask about mechanics, outcomes, or colors, then search
- **Supplement with WebSearch:** `combo-discover` uses Commander Spellbook, which is crowdsourced primarily by Commander players. Combos that are powerful in 1v1 60-card formats but weak in multiplayer Commander may be underrepresented. Search for `"<format> combo decks"` and `"<card name> combo <format>"` to catch format-specific interactions the API might miss.
- Present 3-5 combos with: cards, oracle text, result, color identity, popularity
- Batch-lookup all combo pieces via `scryfall-lookup --batch`
- Let user pick a combo or build-around card

#### Commander/Brawl/Historic Brawl Interview

##### Commander Selection

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
  - **Outside the box:** Proceed to shared questions, then follow the "Outside the Box" workflow after commander analysis.

**If no:** Ask: "Want to explore standard archetypes or go outside the box with unusual combos?"

- **Standard archetypes:** Continue with the guided interview below, then standard workflow.
- **Outside the box:** Skip to the "Outside the Box" workflow after format selection and shared questions.

##### Commander Selection from a Collection

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

##### Format Selection (Commander/Brawl)

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

##### Guided Interview (Commander/Brawl, one question at a time)

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

##### Commander Recommendation

After the guided interview, recommend 3-5 commanders that fit. Partner pairs and commander + background pairings are valid recommendations — present each pair as a single option with their combined color identity. You may use training data to generate a shortlist — this is commander *discovery*, not card evaluation, so the Iron Rule does not apply at this stage. However, every recommended commander MUST be verified via `scryfall-lookup` before presenting.

Present each recommendation with:
- Card name and color identity
- Brief explanation of why it matches the user's preferences
- EDHREC deck count (if available) to indicate community support
- Any notable budget implications

Let the user pick.

##### Shared Questions (Commander/Brawl)

Ask all of these (skipping any already answered during the guided interview):

- **Bracket:** "What power bracket are you targeting? (1-4, or casual/mid/high/max)"
- **Budget:** "What's your total budget for the deck? (dollar amount, or wildcard counts for Arena)"
- **Experience level:** "What's your Commander experience level? (beginner/intermediate/advanced)"
- **Pet cards:** "Any cards you definitely want included?" (pet cards, combos they want to build around)

For pet cards: write all pet card names to a JSON list and batch-lookup in one call: `scryfall-lookup --batch <pet-cards.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`. Verify each exists and is within the commander's color identity. Slot pet cards into the appropriate template categories — they count against those category budgets. If pet cards exceed ~10, warn the user that it limits the ability to build a balanced skeleton.

#### Companion Check (60-Card Only)

After the interview, check whether the deck's constraints naturally fit a Companion. Companions are powerful (a guaranteed extra card) and should be actively considered:

1. `card-search --format <fmt> --bulk-data <path> --oracle "Companion" --type "Creature"` to find format-legal Companions
2. For each Companion, check if the user's playstyle/colors/curve naturally meet the deck-building restriction (e.g., Lurrus requires no permanents with mana value > 2 — natural for low-curve aggro)
3. If a Companion fits, suggest it: "Your deck naturally meets Lurrus's restriction — would you like to use it as a Companion? It gives you a guaranteed extra card."
4. If the user accepts, note the Companion's restriction as a hard constraint for skeleton generation
5. The Companion occupies 1 of 15 sideboard slots
6. Yorion requires an 80-card deck — use `parse-deck --deck-size 80` if selected

#### Experience Level Detection

Infer from answers. If unclear, ask directly: beginner, intermediate, or advanced?

| Level | Interview Depth | Explanation Style |
|-------|----------------|-------------------|
| Beginner | Explain format basics, define archetypes | Full sentences, analogies |
| Intermediate | Assume format knowledge | Concise, note key interactions |
| Advanced | Assume deep knowledge | Tables, shorthand, focus on novel angles |

#### Pet Card Validation

If the user provides pet cards:
1. `scryfall-lookup --batch` to verify existence and oracle text
2. Check format legality (`legalities.<format>` field)
3. For Commander/Brawl: verify within commander's color identity
4. Note their role (threat, removal, engine, etc.) for skeleton slotting

---

### Research (Path B)

#### 60-Card: Metagame Research

##### Proven Archetype Path

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

##### Original/Off-Meta Path

1. Use the user's playstyle, colors, and pet cards as starting constraints
2. `card-search --format <fmt> --bulk-data <path> --oracle "<keyword>" --color-identity <colors>` to find build-around cards
3. `combo-discover` for combo shells in those colors
4. WebSearch for `"<format> <archetype/mechanic> deck"` for inspiration
5. Proceed to Skeleton Generation without a sample list foundation

##### Combo-First Path

1. From the combo chosen in the Combo/Build-Around Discovery, identify the minimum shell:
   - Combo pieces (must-haves)
   - Tutors that find combo pieces (format-legal tutors via `card-search`)
   - Protection for combo assembly (counterspells, discard, hexproof)
2. Identify the best colors (combo colors + support card availability)
3. Proceed to Combo-First Skeleton Generation

#### Commander: Commander Analysis

1. **Scryfall lookup** — Run: `scryfall-lookup "<Commander Name>"`

   Read the full oracle text, color identity, CMC, and types. For partner/background pairs, look up both commanders and note how they interact with each other.

2. **EDHREC research** — Run: `edhrec-lookup "<Commander Name>"`

   For partner commanders: `edhrec-lookup "<Commander 1>" "<Commander 2>"`

   Review top cards, high synergy cards, and themes. **Brawl/Arena note:** EDHREC data is sourced from Commander/EDH decks. For Brawl/Historic Brawl, EDHREC recommendations must be legality-checked against the deck's format before including. For Arena decks, also verify cards exist on Arena.

3. **Web research** — Use `WebSearch` for the commander + "deck tech", "strategy", "guide". Use `WebFetch` or the helper script to read strategy articles:

   Run: `web-fetch "<url>" --max-length 10000`

4. **Strategy synthesis** — Summarize the commander's key mechanics, primary strategies, and synergy axes. For partner/background pairs, identify how both commanders contribute to the strategy and where their mechanics overlap or complement each other. Present to the user for validation. If the user defers or has no preference, default to the commander's most popular theme on EDHREC and move forward.

The goal is building enough understanding to make smart category fills — not deep analysis (Phase 2 handles that).

##### EDHREC Fallback

If EDHREC has no data for the commander (new or obscure cards), fall back to:

1. **Local bulk data search** — Use `card-search` to find cards that mechanically synergize with the commander's keywords/oracle text within the commander's color identity. For Arena decks, use `--arena-only`. For paper Brawl, use `--paper-only` to exclude Arena-only digital cards.
2. **EDHREC theme/archetype data** — Look up the commander's archetype rather than the specific commander. For Brawl/Historic Brawl, legality-check suggestions against the deck's format.
3. **Format staples** — Fill remaining slots with well-known staples for the color identity and bracket.

#### Outside the Box Path (Commander Only)

##### Mechanics/Outcome Interview (no commander known)

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

##### Combo Discovery (both paths)

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

##### Commander Fitting (skip if commander already known)

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

### Skeleton Generation (Path B)

#### 60-Card Constructed

##### Starting Point

- **Proven archetype with sample list:** Customize the sample list based on user preferences, budget, and pet cards. This is modification, not from-scratch building.
- **Original/off-meta or combo-first:** Build from scratch using the template below.

##### Category Template (60-card mainboard)

| Category | Typical Count | Notes |
|----------|--------------|-------|
| Threats/Creatures | 12-28 | Varies hugely by archetype (aggro: 28, control: 4-8) |
| Removal/Interaction | 4-12 | Format-dependent; more in slower formats |
| Card Advantage | 4-8 | Draw spells, planeswalkers, selection |
| Utility/Flex | 2-8 | Archetype-specific support |
| Lands | 20-27 | Constructed land formula (see below) |

**These counts are guidelines, not rules.** Aggressive decks skew toward threats; control decks skew toward interaction and card advantage. The archetype defines the balance.

##### Land Count Formula

Use the constructed land target formula:
- **Baseline:** 24 lands for a 60-card deck
- **Ramp adjustment:** -1 land per 2 ramp/mana-acceleration cards
- **Curve adjustment:** Low curve (avg CMC < 2.5) -> fewer lands; high curve (avg CMC > 3.5) -> more lands
- **Clamp:** Never below 20, never above 27

Run `mana-audit` after building to verify.

##### Land Base Composition

| Land Type | Budget | Mid-Range | High-End |
|-----------|--------|-----------|----------|
| Basics | 10-16 | 6-10 | 2-6 |
| Dual lands (shock, fast, check) | 4-8 | 8-12 | 8-12 |
| Fetch lands | 0 | 0-4 | 8-12 |
| Utility lands | 0-2 | 2-4 | 2-4 |

For Arena formats: Khans fetchlands are available (Pioneer and up), but Zendikar/Onslaught fetches are not. Use the Arena-available mana base (shock lands, fast lands, pathway lands, triomes, Khans fetches for Pioneer/Historic/Timeless).

##### Color Fixing Guidance (60-Card)

The land count formula gives a total, but the color *mix* matters just as much. Use `mana-audit` output (pip demand % vs. land production %) to verify, and follow these rules of thumb:

- **Mono-color:** All basics (plus 2-4 utility lands). Easiest mana base.
- **2-color:** Match land production to pip demand. If the deck is 60% red pips / 40% white pips, aim for roughly 60/40 red/white sources. A mix of ~8 dual lands + basics in the dominant color usually works.
- **3+ colors:** Basics alone can't support 3 colors reliably. Dual lands become near-mandatory. Budget permitting, prioritize lands that produce 2+ of your colors untapped (shock lands, fast lands, triomes). The common trap is running too many basics in a 3-color deck — if `mana-audit` flags a color deficit >5%, replace basics with duals that produce the deficient color.
- **Splash color (5-8 pips):** 4-6 sources of the splash color is usually enough. Pathway lands or dual lands that also produce a main color are ideal.
- **Untapped sources on key turns:** Aggro decks need nearly all lands untapped on turns 1-3. Control decks can tolerate more tapped lands since they operate at higher CMC.

##### Filling Process (60-Card)

For each category:
1. If starting from a sample list, evaluate what's already there
2. `card-search --format <fmt> --bulk-data <path> --oracle "<pattern>" --color-identity <colors>` for candidates
3. `scryfall-lookup --batch` to verify oracle text of all candidates
4. Filter by budget (paper: price; Arena: wildcard rarity)
5. Include pet cards in their appropriate categories
6. Prioritize format staples and proven performers

##### 4-of vs. Fewer Copies

- **4 copies:** Cards you want every game, core to the strategy
- **3 copies:** Strong cards you want most games but don't need multiples
- **2 copies:** Situational cards, legendary permanents, curve-toppers
- **1 copy:** Silver bullets, tutored targets, high-impact singletons

##### Build Sideboard (Bo3 Only)

The sideboard is 15 cards designed to improve matchups after Game 1.

**Process:**
1. Identify the top 3-5 archetypes in the metagame (from research)
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

##### Combo-First Skeleton (60-Card)

- Slot combo pieces first (must-haves)
- Use `card-search` to find: tutors that find combo pieces, protection for combo assembly, redundant effects
- Fill remaining categories (threats, removal, card advantage, lands) around the combo core
- Standard structural verification applies

#### Commander/Brawl/Historic Brawl

##### Default Template

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

##### Template Flexibility

The category counts above are defaults — adjust them after strategy validation to match the user's confirmed direction. Examples:

- **Voltron:** Increase protection/utility, shift engine slots toward equipment/auras
- **Combo:** Increase card draw and win conditions, add tutor slots
- **Aggro/tokens:** Reduce board wipes (they hurt you too), increase engine pieces
- **Control:** Increase interaction across the board, reduce engine pieces
- **Group hug/politics:** Reduce targeted removal, add political tools to utility

**Hard constraints that don't flex:** Lands and ramp stay at Burgess formula minimums regardless of strategy. Total card count must match the deck's expected size (100 for Commander/Historic Brawl, 60 for Brawl, or the user's specified size).

##### Land Base Composition (Commander/Brawl)

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

##### Interaction Scaling by Bracket

Based on Command Zone #658 (2025), EDHREC, and MTGGoldfish guidelines:

| Category | Bracket 1-2 (Casual) | Bracket 3 (Upgraded) | Bracket 4 (Optimized) |
|----------|----------------------|----------------------|----------------------|
| Targeted removal/disruption | 5-7 | 8-10 | 10-12 |
| Board wipes | 2-3 | 3-4 | 4-5 |
| Total interaction | 8-10 | 12-14 | 15-18 |

"Disruption" includes counterspells, discard, and stax pieces — not just creature/artifact removal. Extra interaction slots come out of the engine/synergy budget.

##### Filling Process (Commander/Brawl)

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

##### Combo-First Skeleton (Commander)

- Slot combo pieces first (they're the deck's reason to exist)
- Use `card-search` to find supporting cards: tutors that find combo pieces, protection for combo pieces, redundant effects
- Note which combo pieces pull double duty vs. which are dead outside the combo
- Fill remaining categories (ramp, draw, removal, lands) weighted toward the combo's mechanics
- Standard structural verification applies

---

### Structural Verification (Path B)

Run all four checks in order. If any fail, fix and re-check from the top. Re-hydrate after any deck edit.

#### 1. Legality Audit (must PASS)

```
legality-audit <deck.json> <hydrated.json>
```

Checks: format legality, copy limits (singleton for Commander/Brawl; 4-of rule + Vintage restricted for constructed), sideboard size (max 15 for constructed), deck minimum. Fix any violations before proceeding.

**Commander/Brawl note:** Historic Brawl bans many Commander staples (Sol Ring, Skullclamp, Hour of Reckoning, Triumph of the Hordes, etc.) that look like obvious includes if you're thinking in Commander terms — this check catches them. Color-identity violations typically mean a card slipped past the commander's identity gate.

#### 2. Price Check (must be within budget)

```
# Paper
price-check <deck.json> --budget <budget> --bulk-data <path>

# Arena
price-check <deck.json> --format <fmt> --bulk-data <path>
```

If over budget, substitute expensive cards with budget alternatives. Re-run after changes. For Arena, "most expensive" means highest rarity — swap rare cards for uncommon alternatives. Watch the `illegal_or_missing` warning line for cards that escaped the legality audit.

#### 3. Deck Stats (verify counts)

```
deck-stats <deck.json> <hydrated.json>
```

Verify: total card count matches expected size, land count matches formula target, category distribution looks reasonable, sideboard count (0-15 for constructed).

#### 4. Mana Audit (must PASS or WARN)

```
mana-audit <deck.json> <hydrated.json>
```

Uses the Burgess/Karsten formula for Commander/Brawl, constructed land formula for 60-card formats. Checks land count and color balance. FAIL means the mana base needs fixing before proceeding.

**This is a gate — do not present a skeleton that fails any of these checks.** If any check fails and you edit the deck to fix it, re-parse, re-run `scryfall-lookup --batch` to refresh the hydrated cache, and re-run ALL checks from the top.

---

### Present Skeleton (Path B)

#### 60-Card Constructed Presentation

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

#### Commander/Brawl Presentation

Present organized by the builder's categories (lands, ramp, card draw, removal, board wipes, win conditions, engine/synergy, protection/utility). Include brief notes on why key synergy cards were included.

#### Summary Block

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

#### Ask for Adjustments

Present the skeleton and ask: "Want to make any adjustments before we move on to tuning?"

If the user requests changes, apply them, re-run structural verification, and present again.

---

### Write Output Files (Path B)

1. Deck JSON: `<working-dir>/<deck-name>.json`
2. Moxfield export: `export-deck <deck.json>` -> `<working-dir>/<deck-name>-moxfield.txt`
3. Hydrated cache already at `<working-dir>/.cache/hydrated-<sha>.json`

After presenting and getting user approval, proceed to **Phase 2: Tuning**.

---

## Phase 2: Tuning

Both paths converge here. The deck JSON and hydrated cache are ready.

---

## Step 1: Baseline Metrics

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

If no Companion exists, check whether the deck naturally meets one's restriction. Companions are powerful enough that a deck accidentally qualifying for one (e.g., a low-curve aggro deck meeting Lurrus's "no permanents with mana value > 2") should actively consider adding it. Use `card-search --format <fmt> --bulk-data <path> --oracle "Companion" --type "Creature"` to find candidates, then check restrictions against the current deck. If one fits, suggest it in Step 6 as an addition (it takes 1 sideboard slot).

---

## Step 2: User Intake

### Path A (Tune Existing)

Ask via AskUserQuestion:

#### Shared Questions

1. **Experience level** — Beginner / Intermediate / Advanced
2. **Budget for upgrades** — USD or wildcard budget for changes
3. **Max swaps** — How many cards are you willing to change?
4. **Pain points** — What matchups feel bad? What problems do you notice? Or just "general optimization"?

#### 60-Card Constructed

5. **Best-of-One or Best-of-Three?** — Arena only; skip for paper. If Bo1, sideboard tuning is irrelevant — focus entirely on mainboard. Skip Step 6f (Sideboard Evaluation) and the sideboard guide in Step 12.
6. **Target** — Competitive ladder, FNM, tournament?

#### Commander/Brawl/Historic Brawl

5. **Power bracket** — 1-5, or casual/core/upgraded/optimized/cEDH
6. **Arena vs. paper?** — For Brawl/Historic Brawl, ask if playing on Arena or paper if unclear.

**Format-specific context to mention when relevant:**
- **Brawl/Historic Brawl:** No commander damage (Voltron strategies are weaker), starting life is 25 (2-player) or 30 (multiplayer) instead of 40, free first mulligan
- **Brawl:** Standard card pool — many Commander staples are not legal. Colorless commanders can include any number of basics of one chosen type.
- **Historic Brawl:** Arena Brawl card pool — broader than Standard but different ban list from Commander
- **Arena Brawl queues are always 1v1.** Prioritize speed and tempo over politics, evaluate cards for 1v1 combat (not multiplayer table dynamics), expect more counterspells and targeted removal, fewer board wipes. Paper Brawl can be multiplayer — use standard scaling.

#### Arena Wildcard Budgets

For Arena, use compact notation: `NM/NR/NU/NC` (e.g., `2M/4R/8U/12C` = 2 mythic, 4 rare, 8 uncommon, 12 common wildcards).

If the user ran `mtga-import`, check for `wildcards.json` in the working directory before asking about budget.

### Path B (Build from Scratch)

Confirm carry-forward context from Phase 1: format, platform, Bo1/Bo3 (60-card) or bracket (commander), budget (total/spent/remaining), experience level, archetype, Companion (if any), max swaps. Don't re-ask questions already answered.

When arriving from Path B, note both the **total budget** and the **upgrade budget** (total minus skeleton cost). Use the upgrade budget for swap decisions during analysis. Track owned cards separately — they don't count toward either budget.

**Path B default:** Suggest max swaps of 15-20 for a fresh skeleton (user can adjust). Pain points default to "general optimization" unless the user raised specific concerns during Phase 1.

---

## Step 3: Research

### 60-Card Constructed

#### Path A: Full Research

##### Metagame Context

1. **WebSearch** for `"<format> metagame 2026"` or `"<format> tier list"`
2. **WebFetch** top results to understand the current metagame landscape
3. Identify: What are the top 5 archetypes? Where does this deck fit? What are its expected good/bad matchups?

##### Archetype-Specific Research

1. **WebSearch** for `"<deck archetype> <format> sideboard guide"` and `"<deck archetype> <format> matchup guide"`
2. **WebFetch** strategy articles for sideboard plans and matchup analysis
3. Compare the user's list to stock/optimized versions of the archetype

#### Path B: Verification Pass

Research was already done in Phase 1. Verify metagame alignment rather than repeating:
1. Confirm the metagame context from Phase 1 is still the basis for analysis
2. Note any archetype-specific research findings that inform tuning priorities
3. Skip redundant WebSearch/WebFetch unless the user raised new concerns

### Commander/Brawl/Historic Brawl

#### Path A: Full Research

##### EDHREC + Web Strategy

Run: `edhrec-lookup "<Commander Name>"`

For partner commanders: `edhrec-lookup "<Commander 1>" "<Commander 2>"`

Also use `WebSearch` for the commander + "deck tech", "strategy", "guide" to find Command Zone, MTGGoldfish, and other content creator analysis.

**Fetching strategy articles:** Use `WebFetch` first. If it returns an empty JS shell or navigation-only content, fall back to the helper script:

Run: `web-fetch "<url>" --max-length 10000`

**Key principle:** Research informs but doesn't dictate. EDHREC popularity doesn't automatically make a card right, and unpopularity doesn't make it wrong.

**Combo discovery (optional):** For deeper exploration beyond what `combo-search` surfaces, use `combo-discover` to find combo lines the deck could support. Search by cards already in the deck (`--card "Key Card"`) or by desired outcomes (`--result "Infinite X"`).

**Brawl format note:** EDHREC data is sourced from Commander/EDH decks. When tuning a Brawl deck, EDHREC recommendations must be legality-checked against the deck's format before recommending. Use `card-search --format <format> --bulk-data <path>` to verify candidates are legal. For Arena decks, also use `--arena-only`.

#### Path B: Verification Pass

Commander analysis was already done in Phase 1. Verify alignment rather than repeating:
1. Confirm EDHREC findings and strategy synthesis from Phase 1
2. Note key synergy axes that inform tuning priorities
3. Skip redundant EDHREC/WebSearch unless the user raised new concerns

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

## Step 4: Strategy Alignment

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

## Step 5: Commander Interaction Audit (Commander/Brawl/Historic Brawl Only)

**Skip this step entirely for 60-card constructed formats.** Mark it `completed` immediately and proceed to Step 6.

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

## Step 6: Analysis

### 6a: Mana Base & Curve Audit

- Land count and ramp pieces (mana rocks, dorks, land-fetching spells)
- Average CMC of nonland cards
- Curve distribution
- `mana-audit` for quantitative check
- Color balance: pip demand vs. land production
- Mana base quality: untapped sources on key turns, color fixing
- Flag: too few/many lands, color deficits, too many tapped lands

**Commander formats:** Land count is a hard constraint. Calculate the Burgess formula result (`31 + colors_in_identity + commander_cmc`) and treat it as the target. The `mana-audit` script enforces this — if it returns FAIL, you must add lands or cut fewer lands. Proposing a land count below the Burgess formula result requires `mana-audit` to return PASS or WARN (not FAIL). Proposing a land count below 36 is almost always a FAIL.

**60-card constructed:** Uses the constructed land formula. Compare against format-specific expectations.

### 6b: Interaction & Threat Audit

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

### 6c: Archetype Coherence

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

### 6d: Draft Cuts

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

3. **Feedback loop check.** Does removing this card break a self-reinforcing cycle? (See Step 5.) If so, the cut needs much stronger justification.

4. **Pain point regression check.** Does cutting this card make the user's stated problem worse?

5. **Multiplied value calculation.** Calculate the card's output at the commander's expected trigger multiplier (see Step 5). If a trigger looks weak at 1x but kills a player at 5x, it is a win condition, not a role player.

6. **Combo piece check.** Is this card part of an existing combo line (from Step 5 combo search)?
   - **Game-winning combos:** hard to justify cutting. Valid justifications include "too slow for the bracket" or "bracket violation."
   - **Value interactions:** a soft consideration, not a hard gate.

**Cuts — Be Careful.** Before recommending ANY cut, re-read the oracle text of BOTH the card and the commander. Articulate specifically why the card underperforms in THIS deck.

#### 60-Card Constructed: Draft Cuts

For each proposed cut, evaluate:

1. **Oracle text verification** — Read full oracle text from hydrated data
2. **Alternative cost check** — Suspend, foretell, etc. change the effective CMC
3. **Role in the deck** — What role does this card fill? Is there redundancy?
4. **Matchup impact** — Does cutting this hurt specific matchups?
5. **Combo line check** — Is this card part of an existing combo? (from Step 3)
6. **Metagame relevance** — Is this card specifically good/bad in the current metagame?

**Be careful with cuts.** Re-read oracle text of both the card and its synergy partners. Articulate the specific underperformance.

#### Path B Adaptation: Draft Cuts

For Path B (freshly built skeleton), cuts are cards from the skeleton that the self-grill identifies as suboptimal. The checklist above still applies. There may be zero cuts if the skeleton is sound.

### 6e: Draft Additions

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

### 6f: Sideboard Evaluation (60-Card Only)

**Skip for Commander/Brawl/Historic Brawl.** Also skip for Bo1 (per Step 2 intake).

Evaluate the current sideboard against the metagame:
- Does it address the top 3-5 archetypes?
- Are there dead sideboard slots (cards for matchups that don't exist)?
- Are there missing answers (common archetypes with no sideboard plan)?
- Is the sideboard plan clear? (Which cards come in/out for each matchup?)

Draft sideboard changes alongside mainboard changes.

### 6g: Swap Balance Check

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

## Step 7: Pre-Grill Verification

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
5. **Combo line:** Is this card part of an *existing* combo from Step 5? If game-winning, justify why cutting is acceptable.
6. **Near-miss partner check:** Which Step 5 near-miss results does this card enable as a partner? If any, justify the closure or revise the cut.

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

## Step 8: Self-Grill (Two-Agent Debate)

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
- [ ] **Commander fitness check** — apply the *commander identity test:* "If this deck's commander were hidden, could you guess what it is from the cards?" If the commander may be underperforming, shortlist 1-2 alternatives and surface as a close call in Step 11.

#### Path B Adaptation: Skeleton Review

For Path B (freshly built skeleton), the self-grill debates the skeleton AS A WHOLE, not just proposed changes. The challenger's checklist adds:
- [ ] **Archetype coherence:** Does the skeleton have a clear, consistent game plan?
- [ ] **Missing synergies:** Are there obvious synergy cards for this commander/archetype that were overlooked?
- [ ] **Budget waste:** Are any expensive cards underperforming relative to cheaper alternatives?
- [ ] **Dead cards:** Cards that don't contribute to the primary strategy?
- [ ] **Mana base fitness:** Does the mana base support the curve and color demands?

The debate may conclude with zero changes needed. That is a valid outcome for a well-built skeleton.

**Expect 2-3 rounds minimum.** If both agree immediately, the challenger isn't pushing hard enough.

---

## Step 9: Propose Changes

**HARD GATE:** Write the full proposal as a complete turn BEFORE any `AskUserQuestion`. Do not bundle a tool call with proposal markdown — the tool executes before text finalizes, and the user approves blind.

### Before Presenting

Run `build-deck` to construct the new deck, then `mana-audit` on the result. If FAIL, revise until PASS.

**Preferred path: `build-deck` + `export-deck`.** These produce a correctly-sized deck JSON by construction, so manual card counting never enters the loop.

**The user has not seen the debate.** Present the post-debate proposal as a complete, self-contained recommendation with full reasoning for every swap. Do not reference the debate.

### Path B: No Changes Needed

If the self-grill concluded that the skeleton is sound and no changes are needed, skip Steps 9-11 and proceed directly to Step 12.

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

## Step 10: Impact Verification

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

Compare to Step 3/5 results:
- Any combos lost? If so, was the loss intentional (documented in Step 6d/7)?
- Any new combos gained?
- Near-miss changes?

**Non-substitutable with Step 7 combo checks.** Step 7 catches cuts that close *near-miss* lines (pre-build). This Step 10 check catches cuts that break *existing* combo lines (post-build). Neither subsumes the other.

If any unintended regression, revise the proposal.

---

## Step 11: Close Calls

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

## Step 12: Finalize

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

If Path A (standalone tuner session without a builder phase), show just the upgrade cost and total deck cost.

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

Construct a matchup-by-matchup sideboard map for the top 3-5 metagame archetypes identified in Step 3. This is a natural output of the analysis already performed — don't skip it.

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
| "This is a format staple, auto-include" | Verify format legality + oracle text + price. |
| "EDHREC recommends it so it must be good here" | EDHREC is aggregated data, not analysis. Evaluate for THIS build. |
| "This is a format staple, it can't be a cut" | Evaluate in context. Staples can underperform in specific shells. |
| "This card is generally good in Commander" | Generic staples aren't always right. Check synergy with THIS commander. |
| "This card is generally weak" | Weak in general != weak with this commander. Read both oracle texts. |
| "The sideboard can wait" | Sideboard is half the competitive advantage. Build it now. (60-card) |
| "The sideboard is fine, focus on mainboard" | Sideboard wins tournaments. Evaluate it. (60-card) |
| "The user said aggro, so 20 lands" | Run the formula. Verify with mana-audit. |
| "I'll just use the sample list as-is" | Customize for budget, pet cards, and user preferences. |
| "Skip structural verification, it looks right" | Tools catch errors humans miss. Run them. |
| "This card is cheap on paper so it's fine for Arena" | Paper price != Arena rarity. Use price-check. |
| "We're over budget but this card is too good to skip" | Budget is a hard constraint. Find a cheaper alternative. |
| "I'll just fill the rest with staples" | Every card should have a reason. Staples are a last resort, not a shortcut. |
| "The mana base is probably fine" | Run `mana-audit`. Don't eyeball mana bases. |
| "This step seems unnecessary for this deck" | Follow every step. The process exists because shortcuts cause mistakes. |
| "I can skip oracle text verification for well-known cards" | No. Look up every card. Even Sol Ring has oracle text worth reading. |
| "Skip the self-grill, the analysis was thorough" | The self-grill catches exactly this overconfidence. Run it every time. |
| "I ran cut-check + mana-audit + price-check, that covers Step 8" | No. Those are Step 7 *mechanical* gates. Step 8 is the *strategic* gate and requires two Agent tool calls. |
| "This deck just came from the builder, the self-grill is overkill" | The builder runs no adversarial review. A fresh skeleton is the highest-leverage moment for a challenger pass. |
| "I'll dispatch the agents next turn / after the user confirms" | No. Step 8 must complete before Step 9. |
| "I'll bundle the Step 9 proposal and the Step 11 AskUserQuestion in one message" | No. `AskUserQuestion` renders option chips before the surrounding markdown commits, so bundling means the user approves blind. Write Step 9's proposal FIRST as its own turn. |
| "I'll trust the `rarity` field from the hydrated cache for Arena budgeting" | No. That field is the Scryfall "default" printing's rarity. Use `price-check --format <fmt>` for Arena rarity. |
| "I'll check combos in the deck but skip the near-miss partner scan when proposing cuts" | No. A near-miss combo is `<missing> + <partner1> + <partner2> = <result>`. Your cut list may silently target a `partner`. Check every proposed cut against Step 5 near-miss partner slots. |
| "I'll just Write over `/tmp/cuts.json` and run cut-check in the same message" | No. The first `Write` to an existing `/tmp` path from a prior session fails, but the parallel Bash call runs against stale content. |
| "I'll write a quick `python3 -c` to count / filter / extract" | Check the decision table first. Almost every common task is covered by an existing script. |
| "Skip impact verification, the swaps look clean" | Emergent cross-swap effects only visible post-build. Run the checks. |
| "This card is too expensive to cut" | Sunk cost. Evaluate on merit, not price. |
| "Propose changes and ask for approval in one message" | Step 9 is its own turn. AskUserQuestion comes in Step 11. |
| "The mana base is close enough" | Run mana-audit. "Close enough" is how you lose to color screw. |
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
| Interview | Explain all terms, give examples | Use terms with brief context | Use shorthand |
| Terminology | Define terms (card advantage, tempo, etc.) | Use terms freely | Use shorthand |
| Metagame explanation | Define archetypes, explain matchups | Name archetypes, note key cards | Assume knowledge, focus on novel angles |
| Recommendations | Explain why each card matters | Focus on synergy highlights | Category list with brief notes |
| Swap reasoning | Full sentences, explain why old card is worse | Note specific interaction | Concise: "Bolt > Shock (scry 1 upside)" |
| Strategy | Explain what the strategy does and why | Explain key interactions | Name the archetype and key cards |
| Sideboard guide | Explain what sideboarding means | Provide in/out plan per matchup | Shorthand sideboard map |
| Mana base | Explain land types, what good curve looks like | Note mana base tradeoffs | Focus on marginal improvements |
| Presentation | Narrative walkthrough with examples | Grouped analysis with notes | Concise tables |

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
