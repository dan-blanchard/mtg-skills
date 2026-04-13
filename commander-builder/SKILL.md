---
name: commander-builder
description: Use when building a new MTG Commander deck from scratch (Commander/EDH, Brawl, Historic Brawl) — covers commander selection, deck skeleton generation, and handoff to commander-tuner for refinement
compatibility: Requires Python 3.12+ and uv. Recommend installing commander-tuner skill alongside for deck refinement.
license: 0BSD
---

# Commander Deck Builder

## Overview

Structured process for building an MTG Commander deck from scratch. Guides the user through commander selection, preference gathering, and skeleton generation, then hands off to commander-tuner for refinement.

Every card recommendation MUST be grounded in actual card oracle text from Scryfall — never from training data.

## The Iron Rule

**NEVER assume what a card does.** Before including any card in the skeleton, look up its oracle text via the helper scripts. Training data is not oracle text.

**Exception:** During commander *discovery* (recommending commanders to a user who doesn't know what to build), you may use training data to generate a shortlist of candidates. But every recommended commander MUST be verified before presenting — write all candidate names to a JSON list and batch-lookup in one call: `scryfall-lookup --batch <candidates.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`.

## Progress Tracking

**Before starting Step 1, create a `TodoWrite` list with one item per top-level Step in this skill, in order:**

1. Step 1: Interview
2. Step 2: Commander Analysis
3. Step 3: Skeleton Generation
4. Step 4: Present Skeleton
5. Step 5: Hand Off to Commander-Tuner

Mark each item `in_progress` the moment you begin it and `completed` the moment it finishes — **do not batch updates**. The user relies on this list as a live progress indicator; batching defeats the point.

**If you draft the whole skeleton in a single batch instead of walking the fill order category-by-category, you still must not batch the sub-todo completions.** Either (a) skip creating the fill-order sub-todos entirely for that session (mark only the top-level Step 3 as it starts and completes) or (b) close each sub-todo individually at draft time as you mentally finish that category. Leaving eight "Fill Lands / Fill Ramp / ..." sub-todos open the whole session and then collapsing them into a batch "all done" when Step 3's parent closes is the failure mode — it silently hides the stale progress indicator from the user until they notice.

**Step 3 (Skeleton Generation) is long enough that the top-level item alone leaves the user staring at an unchanging list.** When you reach it, expand it into sub-todos *at that moment* (not up front), one per category in the fill order plus the verification gate:

1. Fill Lands
2. Fill Ramp
3. Fill Card Draw
4. Fill Targeted Removal & Board Wipes
5. Fill Protection/Utility
6. Fill Engine/Synergy Pieces
7. Fill Win Conditions
8. Structural Verification (deck-stats, mana-audit, price-check)

**If the user takes the "Outside the Box" workflow**, add or swap todos as you reach each alt step, leaving any already-completed standard steps in place. The alt steps are Step 1b-alt (Mechanics/Outcome Interview), Step 2-alt (Combo Discovery), Step 2b-alt (Commander Fitting — skip if commander already known), and Step 3-alt (Skeleton with Combo Core); Steps 4 and 5 are shared with the standard flow. Step 3-alt expands into the same fill-order sub-todos as Step 3.

Do NOT create per-card sub-todos inside any fill step — that's execution detail and would flood the list.

## Setup and Tooling

This skill shares its install with commander-tuner via symlink. For one-time setup commands (`uv sync`, `download-bulk`) and the full script reference, see `commander-tuner/SKILL.md` — those run once per install and aren't hot-path during a builder session.

**Script invocation shorthand:** All script examples below elide the `uv run --directory <skill-install-dir> ` prefix for readability — every actual invocation must include it.

**Writing JSON files with card names:** Card names often contain apostrophes (Azor's Elocutors, Krark's Thumb) which break shell quoting. **Use the `Write` tool** for any `/tmp/*.json` file you create — the Write tool only requires a prior `Read` for *existing* files; new files in `/tmp` work fine on the first call. Example:

> `Write(file_path="/tmp/candidates.json", content='["Azor\'s Elocutors", "Krark\'s Thumb", "Fire // Ice"]')`

Do NOT write JSON via Bash heredocs (`cat > /tmp/foo.json << 'JSONEOF' ... JSONEOF`). Heredocs are functionally fine but they produce un-cacheable Bash permission patterns: Claude Code's permission engine bakes the heredoc body into the allow pattern, so every invocation with different content re-prompts the user. The Write tool generates a single `Write(/tmp/**)` permission that can be granted once and reused.

**The same caching trap applies to `python3 -c "..."`, `awk '...'`, `jq '...'`, and any other Bash pattern where the code body varies between invocations.** Each unique body is a fresh permission pattern. If you need to extract one field from a JSON file, prefer: (a) passing the file directly to a script that already knows how to parse it (see "Parsed deck JSON is the canonical pipeline intermediate" below), (b) `Read` with `offset`/`limit` on the JSON file, or (c) `Grep` on the file. Reach for `python3 -c` only when those options genuinely don't cover the case, and accept the re-prompt cost when you do.

**Decision table — use the script, not `python3 -c`.** Before writing any inline Python/awk/jq body, check this table:

| I want to... | Use this |
|---|---|
| See every card's oracle text / type / CMC | `card-summary <hydrated.json> [--nonlands-only\|--lands-only\|--type X]` |
| Scan the skeleton for cards matching an oracle pattern | `Grep '<regex>' <hydrated.json>` — full oracle text, no truncation. For human-readable context on matches, pair with `card-summary [--type X]` |
| Count cards / verify total matches deck size | `deck-stats <deck.json> <hydrated.json>` (reports `total_cards`) or re-run `parse-deck` (reports count in stdout) |
| Know which skeleton cards I own and how many | `mark-owned <deck.json> <collection.json> [--output PATH] [--bulk-data <path>]` (populates `owned_cards` in place by default; pass `--bulk-data` for Arena name aliasing) |
| Plan wildcard spend / get per-card or aggregate Arena rarity | `price-check <deck.json> --format <fmt> --bulk-data <path>` — reports per-card rarity AND aggregate per-rarity totals vs. budget |
| Check land count, curve, category totals, avg CMC | `deck-stats <deck.json> <hydrated.json>` |
| Check mana-base health (Burgess/Karsten, color balance) | `mana-audit <deck.json> <hydrated.json>` |
| Check format legality / color identity / singleton | `legality-audit <deck.json> <hydrated.json>` |
| Find existing combos or near-misses in the skeleton | `combo-search <deck.json> --hydrated <hydrated.json>` |
| Discover combos by outcome or card name | `combo-discover --result "..." \| --card "..." [filters]` |
| Filter Arena-legal cards by color/oracle/type/CMC/price | `card-search --bulk-data <path> --format <fmt> --arena-only [filters]` |
| Extract one field or a few entries from a JSON file | `Read` with `offset`/`limit`, or `Grep` |
| Get a card's Arena-lowest rarity | `price-check --format <fmt>` (never the hydrated cache `rarity` field — that's the default printing's rarity, not Arena's) |
| Find owned, legal, commander-eligible cards from a collection | `find-commanders <collection.json> --format <fmt> --bulk-data <path> --output <working-dir>/.cache/candidates.json` |
| Populate a deck's owned_cards from an Arena Player.log | `mtga-import --bulk-data <path> --output-dir <working-dir>` |
| Export the skeleton to a Moxfield-importable text file | `export-deck <deck.json> > <path>` |

Only write `python3 -c` when none of these cover the need. When you do, batch every related question you can into a single body — each unique body is a fresh permission pattern, so one big script beats five small ones.

**Scratch-file reuse.** Reuse a small set of stable `/tmp/*.json` paths (e.g., `/tmp/candidates.json`, `/tmp/pet-cards.json`, `/tmp/cuts.json`) across a session rather than minting a new file name each time. Write-tool permissions are granted per path; six distinct scratch paths is six permission prompts, while reusing three paths collapses to three.

**Warning — `/tmp` files persist across sessions.** The Write tool requires a prior `Read` for any existing file, so the first `Write` to a reused `/tmp/*.json` path in a new session fails with *"File has not been read yet"*. If you batched that `Write` in parallel with a Bash call that reads the same file, **the Bash silently consumes the stale prior-session content** — the parallel Write error doesn't block the Bash, so `scryfall-lookup --batch` / `price-check` / other readers will happily run against the wrong data. Symptom: tool results list cards you never put in the candidate list. **Rule:** (a) at session start, `Read` each scratch path you plan to reuse before the first `Write`, OR (b) run `Write` sequentially (not parallel) and verify success before the dependent Bash call. Never batch `Write(/tmp/foo.json)` + `Bash(tool reading /tmp/foo.json)` in a single message. If a tool result lists cards that don't match your intended input, suspect stale-file consumption before suspecting a tool bug.

Do NOT use `echo` or unquoted shell strings for JSON containing card names — apostrophes in card names break shell quoting.

**Parsed deck JSON is the canonical pipeline intermediate.** Once you have a parsed deck JSON from `parse-deck`, pass it **directly** to `scryfall-lookup --batch` and `price-check` — both scripts accept a parsed deck JSON as `<path>`, not just a JSON list of name strings. Do NOT extract card names into a separate `/tmp/*.json` via `python3 -c` or similar. Every unnecessary extraction costs a Bash permission prompt (content-varying `python3 -c` is un-cacheable), a Write permission prompt for the temp file, and wall-clock time. If you catch yourself writing `json.load(...)` to pull out `c['name']`, stop — the script already handles that. (The exception is candidate lists that don't correspond to a parsed deck — e.g., commander discovery shortlists and combo piece lists from external research — where `/tmp/*.json` via the Write tool is still correct.)

**Always pass `--format <format>` to `parse-deck` once the format is established in Step 1.** Without this, `parse-deck` defaults to `commander` and every downstream tool sees the wrong format. This is especially important for Historic Brawl, where the ban list and legality checks differ from Commander. Example: `parse-deck <path> --format historic_brawl`.

**Always use absolute paths for every positional argument and file-path flag.** Not just `--cache-dir`. `uv run --directory <skill-install-dir>` rebinds the subprocess CWD to the skill install, so a relative path like `my-deck.txt` passed to `parse-deck` resolves against the skill install dir and fails with a misleading "Path does not exist" error. This applies to `parse-deck <path>`, `card-search --bulk-data <path>`, `scryfall-lookup --batch <path>`, `price-check <path>` — every path the caller supplies. Resolve paths against the user's working directory first.

**Place `--cache-dir` inside the user's working directory, NOT the skill install.** Pass an absolute path inside the user's repo, e.g. `--cache-dir <working-dir>/.cache` where `<working-dir>` is the absolute path to the user's current repo (the directory they ran Claude Code from). Putting the cache under the skill install (whether explicitly or implicitly via `./`) causes every downstream `Read`, `cp`, or script call against the hydrated path to trigger an outside-workspace permission prompt. Keeping the cache in the working directory also lets the hydrated file serve directly as the "write output files to the working directory" artifact in Step 5, with no `cp` needed.

**Re-hydrate after every deck edit.** The hydrated cache path is SHA-keyed against the deck JSON's content, so editing the deck text file (or re-running `parse-deck`) produces a new SHA. If you keep using the old `cache_path`, downstream tools like `card-summary` will happily show you cards that no longer exist in the deck (and miss ones you just added). Any time you modify the skeleton and re-run `parse-deck`, immediately re-run `scryfall-lookup --batch` on the new deck JSON and switch all downstream script calls to the new `cache_path`.

**Parsed deck JSON schema.** `parse-deck` emits:

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

All three card lists (`commanders`, `cards`, `owned_cards`) are the same shape — `[{name, quantity}]` dicts. `owned_cards` starts empty and is populated by `mark-owned` (see below) or by hand. `price-check` reads it to subtract owned copies from the budget; entries with `quantity < 1` are treated as "not owned" (so a Moxfield wishlist row exported at quantity 0 does not zero out the budget).

**Populating `owned_cards`:** when building from a user's collection, use the dedicated helper rather than inline `python3 -c`:

```
mark-owned <deck.json> <collection.json> [--bulk-data <bulk-data-path>]
```

**Always pass `--bulk-data` for Arena collections** — this enables `printed_name` and `flavor_name` aliasing so crossover cards (Through the Omenpaths, Godzilla, Dracula, Avatar) match correctly between Arena names and Scryfall canonical names.

This overwrites the deck JSON in place with the intersection of deck and collection (by normalized, diacritic-folded card name). The recorded quantity is the authoritative count from the collection side (summed across split-printing rows), so the field answers "how many copies do I own?" not "how many does the deck ask for?" `price-check` then uses this to compute `max(deck_qty - owned_qty, 0)` shortfalls per slot — so a deck running 17 Hare Apparent with 4 owned is correctly billed for 13, not 1. Use `--output <path>` to write elsewhere. The script is idempotent and safe to chain after every `parse-deck` / `set-commander` call. Avoid inline Python — every unique `python3 -c` body is a fresh un-cacheable Bash permission pattern.

**`set-commander` is idempotent.** Calling it on a card that is already in the `commanders` zone is a silent no-op, not an error. This means `parse-deck | set-commander` is safe to chain even when the deck file already had a Moxfield `Commander` header (which `parse-deck` honors automatically). You do not need to pre-check `deck.commanders` before calling `set-commander`.

**`find-commanders` writes its full JSON to `$TMPDIR` by default**, which is outside the working directory and triggers an outside-workspace permission prompt when you try to `Read` it. **Always pass `--output <working-dir>/.cache/candidates.json`** so the JSON lives in the workspace from the start. Do NOT `cp` the `$TMPDIR` file into the workspace after the fact — that's one avoidable permission prompt for the read and another for the copy.

**AskUserQuestion caps at 4 options — never silently drop the rest.** The tool's schema rejects more than 4 options per question. When you have more candidates than that (a 5-commander shortlist, 5 archetype choices, a long swap list), do NOT pick 4 and hide the rest. Instead, list **every** option in the preceding text message with enough detail to decide on, then use AskUserQuestion only as a lightweight picker — either (a) present the top 3 as buttons plus a 4th "Other (specify in notes)" option so the user can type any name from the text list, or (b) skip AskUserQuestion entirely for that decision and let the user reply in plain text. The failure mode to avoid is showing 4 option chips that look like the complete set when the text above mentioned 5+.

**Card count verification:** After writing or editing a deck text file by hand, always parse it immediately and verify the total card count matches the format's expected size (100 for Commander/Historic Brawl, 60 for Brawl). Off-by-one errors from manual edits are common and silent. **Preventive:** before writing the deck file, tally your categories visibly in the narrative — format-appropriate:
> - **100-card** (Commander / Historic Brawl): e.g., "Lands 36 + Ramp 10 + Draw 10 + Removal 10 + Wipes 3 + Utility 8 + Engine 18 + Wincons 4 = 99 + 1 commander = 100"
> - **60-card** (Brawl / 60-card Historic Brawl): scale each category by 0.6 and round. E.g., "Lands 22 + Ramp 6 + Draw 6 + Removal 6 + Wipes 2 + Utility 5 + Engine 11 + Wincons 1 = 59 + 1 commander = 60"

Verify by eye before `parse-deck` catches it a step later — pre-write tallies prevent rebuild cycles.

**Arena rarity ≠ hydrated cache `rarity` field.** `scryfall-lookup --batch` writes each card's `rarity` from whichever printing Scryfall treats as the "default" — typically the most-referenced paper printing, *not* the Arena printing. Rarity drifts across printings: Ashnod's Altar is uncommon in most paper sets but rare on Arena (BRR is its only Arena printing). If you read `rarity` from the hydrated cache to plan wildcard spend, you will get the wrong number for cards with printing drift, and your wildcard budget in Step 3 (Structural Verification → price-check) will disagree with your expectation, forcing a rebuild. **For any Arena rarity question, always use `price-check --format brawl` or `--format historic_brawl` with `--bulk-data`** — it reports the lowest Arena-legal rarity per card by walking every Arena printing, which is what MTG Arena actually charges as a wildcard. Never trust the hydrated cache's `rarity` field when you're budgeting wildcards against a fixed per-rarity wildcard count.

**Licensed IP cards have different names on Arena.** Some crossover sets use different card names on Arena than in paper/Scryfall: Through the Omenpaths (OM1, the Arena version of Marvel's Spider-Man) uses names like "Skittering Kitten" where Scryfall uses "Masked Meower"; Ikoria Godzilla variants, Crimson Vow Dracula variants, and Avatar: The Last Airbender cards have similar discrepancies. **Always pass `--bulk-data` to `mark-owned`** when working with Arena collections — this enables `printed_name` and `flavor_name` aliasing from Scryfall data, so a collection containing "Skittering Kitten" correctly matches a deck containing "Masked Meower". Without `--bulk-data`, these cards silently appear unowned. When recommending cards from crossover sets for Arena, note that the Arena display name may differ from the Scryfall name shown in `card-search` results.

## Step 1: Interview

### Commander Selection

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

### Commander Selection from a Collection

**If the user provides a collection export (Untapped.gg CSV, Moxfield CSV, or any deck-list export) of cards they own** and wants to pick a commander from what they already have, follow this exact procedure. Do NOT write ad-hoc Python that loads the file and calls `.get()` on it — the helper scripts already handle every step correctly. **Note:** collection exports often contain entries with quantity 0 (tracked/wishlisted cards the user doesn't own). `parse-deck` preserves these quantities and `mark-owned` / `find-commanders` filter by `--min-quantity 1` by default, so quantity-zero entries are excluded automatically.

This narrows the candidate *pool*; it does NOT replace the guided interview. Run the interview anyway — the answers drive ranking against the narrowed pool.

**Workflow:**

0. **Arena players — ask for a collection CSV first.** If the user mentions Arena, Brawl, Historic Brawl, or wildcards, ask: "Do you have a collection export from Untapped.gg, Moxfield, or a similar tracker? A CSV with card names and quantities is the most reliable way to know what you own." If they have one, proceed to step 1. If they don't have a collection CSV, fall back to `mtga-import` as a last resort — but **warn the user**: mtga-import reconstructs a collection from saved Arena decks, which is unreliable because Arena allows building decks with unowned cards. The resulting collection will contain false positives (cards in speculative decks that aren't owned) as well as false negatives (owned cards never put into a deck). **Always run `mtga-import` for wildcard extraction regardless** — it reads `InventoryInfo` from `Player.log` which is reliable for wildcard counts: `mtga-import --bulk-data <bulk-data-path> --output-dir <working-dir>` (prefixed with `uv run --directory <skill-install-dir>`). This writes `wildcards.json` (read by commander-tuner during Step 3 intake). Linux users need to pass `--log-path` explicitly. If the user provided a CSV, ignore the `collection.json` output from mtga-import — only use the `wildcards.json`.

1. **Parse the collection** — `parse-deck <absolute-path-to-collection.csv>` produces a parsed deck JSON. `parse-deck` handles Untapped.gg CSV, Moxfield CSV, Moxfield deck export, Arena, MTGO, and plain text — use it for any collection format the user gives you.

2. **Find commander candidates** — `find-commanders <parsed.json> --bulk-data <bulk-data-path> --format <format> --output <working-dir>/.cache/candidates.json [--color-identity <ci>] [--min-quantity 1]`. **Always pass `--output`** — the default path is under `$TMPDIR` which triggers outside-workspace permission prompts for every subsequent `Read`. Pass `--color-identity` only if the user has already stated a color preference; otherwise omit and narrow in step 4. Pass `--min-quantity 0` only if the user explicitly wants their wishlist/binder rows considered. **Stdout is a compact text table** with columns EDHREC rank, color identity, CMC, name, type_line, flags (PARTNER / BACKGROUND / GC). Read the table directly to do shortlisting — do not parse it as structured data. The last line is `Full JSON: <path>` naming the file you passed to `--output`, which contains the full per-candidate dict including `oracle_text`, `partner_with`, and the usual identification fields. Only `Read` that JSON file for the ~5 candidates you're actually shortlisting (to grab oracle text for the Iron Rule verification step) — not the whole candidate list, which would defeat the point of the compact table.

3. **Run the guided interview** (colors, playstyle, mechanics, favorite cards, play group, bracket, budget) the same as the no-collection flow. The candidate pool is the constraint; the interview answers are what differentiates one commander from another.

4. **Build a mixed shortlist of ~5 candidates**, weighted by interview answers. Do NOT just pick the 5 lowest `edhrec_rank` values — that produces boring recommendations. Aim for roughly:
   - **2 staples** — well-supported commanders (low `edhrec_rank`) that obviously fit the user's stated preferences. These exist to give the user a safe pick.
   - **2 off-meta picks** — commanders with higher or null `edhrec_rank` whose oracle text mechanically matches the interview answers (especially the mechanics question). These are usually the most interesting options.
   - **1 wildcard** — something the user probably hasn't considered: an unusual color combo they own, a partner pairing where they own both halves, or a commander that enables a combo using cards already in their collection.
   - For bracket gating, use the `game_changer` flag and your judgment about combo density. Do NOT use any "EDHREC bracket" field — community bracket data is user-reported and unreliable.

5. **Enumerate partner pairings from within the owned pool.** Walk the candidate list once: for each card with `is_partner=true`, find compatible partners from the same list (any other `is_partner=true` card; for `partner_with` cards, look for the named target). For each card with `has_background_clause=true`, find Backgrounds (`type_line` contains both "Legendary Enchantment" and "Background") in the candidate list. Surface promising pairings as wildcard or off-meta picks — "you already own both halves" is exactly the kind of non-obvious recommendation that makes a collection-aware flow feel useful. Skip pairings where the combined color identity doesn't match the user's stated colors.

6. **Present the shortlist** following the existing "Commander Recommendation" rules (verified oracle text from the script output, color identity, EDHREC count as one signal not the ranking, why-it's-on-the-list label of "staple" / "off-meta fit" / "wildcard"). Mention to the user that candidates are filtered to cards they own and that the default `--min-quantity 1` excludes any wishlist/binder rows — in case they expected to see something tracked at quantity 0. Let the user pick, then proceed to the standard shared questions and Step 2 (Commander Analysis).

   **If the shortlist has 5+ commanders, list all of them in the prose description above.** `AskUserQuestion` is capped at 4 options per question — do NOT pick 4 and hide the rest in an AskUserQuestion call. Either (a) use AskUserQuestion with your top 3 picks as buttons plus a 4th "Other (specify in notes)" so the user can type any name from the prose list, or (b) skip AskUserQuestion entirely and let the user reply in plain text. See "AskUserQuestion caps at 4 options" in the Tooling Notes.

### Format Selection

Ask: "What format are you building for?"

- **Commander/EDH** (default) — 100 cards, 40 life
- **Brawl** — 60 cards, Standard card pool, 25/30 life, no commander damage
- **Historic Brawl** — 100 cards (or 60 in paper), Arena/paper card pool, 25/30 life, no commander damage

**Arena naming confusion:** On MTG Arena, "Brawl" (the queue name) actually refers to Historic Brawl, and "Standard Brawl" refers to what we call Brawl. If a user says "I play Brawl on Arena," they almost certainly mean Historic Brawl. Clarify which they mean.

If Brawl or Historic Brawl: ask "Are you playing on Arena or in paper?"
- **Arena** locks deck size automatically: Standard Brawl is always 60 cards, Historic Brawl (called "Brawl" on Arena) is always 100 cards. **Arena Brawl queues are always 1v1.** This fundamentally changes deck building: prioritize speed and tempo over politics, run more cheap targeted counterspells (only 1 opponent to interact with), fewer board wipes (wiping your own board and only one opponent's is a worse trade than in multiplayer), and a faster curve. The interaction scaling table targets are for multiplayer — in 1v1, shift toward cheaper, more targeted interaction.
- **Paper Historic Brawl** only: ask if they want 100 or 60 cards. Paper Brawl can be multiplayer — use the standard interaction scaling table.

If Brawl: any legendary planeswalker can be your commander (not just those with "can be your commander" text). Vehicles and Spacecraft with power/toughness are also eligible in all formats.

**Colorless commanders in Brawl:** If the chosen commander has no colors in its color identity, note that the deck may include any number of basic lands of one chosen basic land type. This is a Brawl-specific exception.

**Partner mechanics** are available in all formats.

**If no:** Ask: "Want to explore standard archetypes or go outside the box with unusual combos?"

- **Standard archetypes:** Continue with the guided interview below, then standard workflow.
- **Outside the box:** Skip to the "Outside the Box" workflow (Step 1b-alt) after format selection and shared questions.

**Guided Interview (one question at a time, for standard archetypes):**

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

3. **Mechanics** — "Any specific mechanics you enjoy?" Offer examples with explanations: "+1/+1 counters (growing your creatures over time), theft (stealing opponents' cards), blink (flickering creatures to reuse their effects), spellslinger (casting lots of instants and sorceries), artifacts-matter, landfall (rewards for playing lands)." Open-ended. If the answer maps to multiple distinct sub-archetypes, ask one follow-up to disambiguate with explanations (e.g., "When you say graveyard, are you thinking more reanimator (bringing big creatures back from the dead), aristocrats (sacrificing creatures for value), or self-mill (filling your graveyard as a resource)?").

4. **Favorite cards/sets** — "Any favorite cards or recent sets that excited you? This helps me find commanders in a similar design space."

5. **Play group dynamics** — "How does your play group typically play? (casual/competitive, combo-heavy, creature-heavy, lots of interaction)"

6. **Bracket** — "What power bracket are you targeting? (1-4, or casual/mid/high/max)"

7. **Budget** — "What's your total budget for the deck? (dollar amount, or wildcard counts for Arena)"

### Commander Recommendation

After the guided interview, recommend 3-5 commanders that fit. Partner pairs and commander + background pairings are valid recommendations — present each pair as a single option with their combined color identity. You may use training data to generate a shortlist — this is commander *discovery*, not card evaluation, so the Iron Rule does not apply at this stage. However, every recommended commander MUST be verified via `scryfall-lookup` before presenting (to confirm it exists, is a legal commander, and its oracle text matches the claimed strategy). Check EDHREC deck counts where possible to gauge how well-supported each commander is.

Present each recommendation with:
- Card name and color identity
- Brief explanation of why it matches the user's preferences
- EDHREC deck count (if available) to indicate community support
- Any notable budget implications

Let the user pick.

### Shared Questions

Ask all of these (skipping any already answered during the guided interview):

- **Bracket:** "What power bracket are you targeting? (1-4, or casual/mid/high/max)"
- **Budget:** "What's your total budget for the deck? (dollar amount, or wildcard counts for Arena)"
- **Experience level:** "What's your Commander experience level? (beginner/intermediate/advanced)"
- **Pet cards:** "Any cards you definitely want included?" (pet cards, combos they want to build around)

For pet cards: write all pet card names to a JSON list and batch-lookup in one call: `scryfall-lookup --batch <pet-cards.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`. Verify each exists and is within the commander's color identity. Slot pet cards into the appropriate template categories — they count against those category budgets. If pet cards exceed ~10, warn the user that it limits the ability to build a balanced skeleton and ask if they want to trim. If a category overflows due to pet cards, shrink it and redistribute remaining slots.

## Step 2: Commander Analysis

1. **Scryfall lookup** — Run: `scryfall-lookup "<Commander Name>"`

   Read the full oracle text, color identity, CMC, and types. For partner/background pairs, look up both commanders and note how they interact with each other.

2. **EDHREC research** — Run: `edhrec-lookup "<Commander Name>"`

   For partner commanders: `edhrec-lookup "<Commander 1>" "<Commander 2>"`

   Review top cards, high synergy cards, and themes. **Brawl/Arena note:** EDHREC data is sourced from Commander/EDH decks. For Brawl/Historic Brawl, EDHREC recommendations must be legality-checked against the deck's format before including. For Arena decks, also verify cards exist on Arena — some cards are legal in a format but have no Arena printing.

3. **Web research** — Use `WebSearch` for the commander + "deck tech", "strategy", "guide". Use `WebFetch` or the helper script to read strategy articles:

   Run: `web-fetch "<url>" --max-length 10000`

4. **Strategy synthesis** — Summarize the commander's key mechanics, primary strategies, and synergy axes. For partner/background pairs, identify how both commanders contribute to the strategy and where their mechanics overlap or complement each other. Present to the user for validation. If the user defers or has no preference, default to the commander's most popular theme on EDHREC and move forward.

The goal is building enough understanding to make smart category fills — not deep analysis (commander-tuner handles that).

## Step 3: Skeleton Generation

### Default Template

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

### Template Flexibility

The category counts above are defaults — adjust them after strategy validation to match the user's confirmed direction. Examples:

- **Voltron:** Increase protection/utility, shift engine slots toward equipment/auras
- **Combo:** Increase card draw and win conditions, add tutor slots
- **Aggro/tokens:** Reduce board wipes (they hurt you too), increase engine pieces
- **Control:** Increase interaction across the board, reduce engine pieces
- **Group hug/politics:** Reduce targeted removal, add political tools to utility

**Hard constraints that don't flex:** Lands and ramp stay at Burgess formula minimums regardless of strategy. Total card count must match the deck's expected size (100 for Commander/Historic Brawl, 60 for Brawl, or the user's specified size).

### Land Base Composition

The land count comes from the Burgess formula, but composition matters. Guidelines:

- **Basics:** Enough to be fetched by ramp spells (Cultivate, Kodama's Reach, etc.) and not punished by Blood Moon/Back to Basics. Mono/two-color decks lean heavier on basics.
- **Color fixing:** Scale to budget and color count:
  - **Budget ($25-75):** Gain lands, temples (scry lands), tri-lands, check lands, pain lands
  - **Mid ($75-200):** Add filter lands, battle lands, pathway lands, talismans
  - **High ($200+):** Shocks, fetches, original duals if budget allows
- **Arena wildcard tiers:** For Arena decks, ignore dollar tiers and budget by wildcard rarity:
  - **Tight on wildcards:** Lean on uncommon lands (gain lands, check lands, surveil lands, tri-lands). Accept some tapped lands.
  - **Moderate wildcards:** Add rare untapped duals (shocks, fast lands, bond lands) for the most important color pairs.
  - **Plenty of wildcards / high bracket:** Full suite of rare untapped duals, Cavern of Souls if tribal, fetch lands if in format. Untapped duals greatly accelerate a deck and are worth the rare wildcards at higher brackets.
- **Utility lands (2-4):** Lands that synergize with the strategy (e.g., creature lands for aggro, Reliquary Tower for draw-heavy, Rogue's Passage for voltron). Don't overload — utility lands that enter tapped or produce colorless hurt consistency. **In mono-color and 2-color decks, avoid colorless-only utility lands** (Darksteel Citadel, Reliquary Tower, etc.) unless their utility directly supports the commander's strategy. A Mountain is almost always better than a colorless land in mono-red — every colorless land is a potential dead draw that can't cast your spells.
- **Command Tower:** Auto-include in 2+ color decks. **In mono-color, Command Tower is strictly worse than a basic** — it can't be fetched by ramp spells and doesn't have the basic land type (which matters for cards like Castle Garenbrig, Boseiju's discount, etc.). Use a basic instead. More broadly, any land that only taps for one mana of any color with no other upside (Mana Confluence, City of Brass, Tarnished Citadel) is strictly worse than a basic in mono-color because it costs life for the same output.
- **Sol Ring:** Auto-include in Commander/EDH on paper. Not legal in Brawl or Historic Brawl (never entered those card pools).

Run `mana-audit` after filling to verify color balance. If any color's land production falls below its pip demand, swap basics or upgrade fixing.

### Interaction Scaling by Bracket

Based on Command Zone #658 (2025), EDHREC, and MTGGoldfish guidelines:

| Category | Bracket 1-2 (Casual) | Bracket 3 (Upgraded) | Bracket 4 (Optimized) |
|----------|----------------------|----------------------|----------------------|
| Targeted removal/disruption | 5-7 | 8-10 | 10-12 |
| Board wipes | 2-3 | 3-4 | 4-5 |
| Total interaction | 8-10 | 12-14 | 15-18 |

"Disruption" includes counterspells, discard, and stax pieces — not just creature/artifact removal. Extra interaction slots come out of the engine/synergy budget.

Sources: [Command Zone #658](https://edhrec.com/articles/the-command-zone-commander-deckbuilding-template-for-the-new-era-the-command-zone-658-mtg-edh-magic-gathering), [EDHREC Solve the Equation](https://edhrec.com/articles/solve-the-equation-choosing-and-using-your-interaction), [MTGGoldfish Deckbuilding Checklist](https://www.mtggoldfish.com/articles/the-power-of-a-deckbuilding-checklist-commander-quickie)

### EDHREC Fallback

If EDHREC has no data for the commander (new or obscure cards), fall back to:

1. **Local bulk data search** — Use `card-search` to find cards that mechanically synergize with the commander's keywords/oracle text within the commander's color identity. For example, if the commander cares about +1/+1 counters: `card-search --bulk-data <bulk-data-path> --color-identity <ci> --oracle "\+1/\+1 counter" --type Creature --price-max <budget-per-card> [--arena-only | --paper-only]`. For Arena decks, use `--arena-only` and omit `--price-max` (manage budget by wildcard rarity instead). For paper Brawl, use `--paper-only` to exclude Arena-only digital cards. This searches the full Scryfall database locally — no API calls needed.
2. **EDHREC theme/archetype data** — Look up the commander's archetype (e.g., "tokens," "voltron," "+1/+1 counters") rather than the specific commander. For Brawl/Historic Brawl, legality-check EDHREC suggestions against the deck's format. For Arena, verify cards exist on Arena.
3. **Format staples** — Fill remaining slots with well-known staples for the color identity and bracket.

This fallback path produces a more generic skeleton, but commander-tuner's refinement step will tighten it.

### Filling Process

**Wildcard-constrained path (Arena, under 10 combined rare + mythic wildcards):** A typical 100-card skeleton uses 15-25 rare/mythic slots, so under 10 wildcards means most rares must come from the collection. When the user's rare + mythic wildcard budget totals less than 10, **invert the fill strategy**. Instead of drafting ideal cards from EDHREC/card-search and checking ownership after, search the user's collection for owned cards that fit each category first. For each category below, grep or search the collection JSON for cards matching the category's role, batch-lookup their oracle text, and select from what's owned. Only spend wildcard slots on commons and uncommons that fill critical gaps no owned card covers. This avoids the costly rebuild cycle of drafting unaffordable cards, discovering most aren't owned, and starting over.

**Category fill order matters.** Fill foundational categories first to ensure the mana base and core infrastructure are solid before spending budget on synergy:

1. **Lands** (cheapest to fill, most important to get right)
2. **Ramp**
3. **Card draw**
4. **Targeted removal and board wipes**
5. **Protection/utility**
6. **Engine/synergy pieces**
7. **Win conditions**

**Per category:**

1. Pull candidates from EDHREC high-synergy and top cards for this commander. Supplement with `card-search` to find synergistic cards EDHREC may not surface: `card-search --bulk-data <bulk-data-path> --color-identity <ci> --oracle "<relevant-keyword>" --type <category-type> --price-max <budget-per-card> [--arena-only | --paper-only]`. For Arena decks, use `--arena-only` and omit `--price-max` (manage budget by wildcard rarity instead). For paper Brawl, use `--paper-only` to exclude Arena-only digital cards.
2. **Batch-lookup oracle text for all candidates** — write candidate names to a JSON list, then run: `scryfall-lookup --batch <candidates.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`. Stdout is a small envelope; extract `cache_path`. Run `card-summary <cache_path>` to see a compact table of every candidate with full oracle text (truncated only at 1000 chars, which virtually no card reaches) — that's enough for category-fit scanning. Only `Read` the full cache file for the ~3-5 candidates you're actually deciding between for this slot, and use `offset`/`limit` to pull just those entries.
3. Filter by budget (cheapest printings, track running price total against remaining budget). For Arena, track wildcard rarity counts against remaining wildcards instead of prices.
4. Filter by bracket (avoid Game Changers above target bracket).
5. Weight by interview preferences (e.g., if user said "I enjoy graveyard strategies," prefer self-mill draw engines over generic draw).
6. Weight by commander synergy (from the analysis step).
7. Include any pet cards the user requested, slotting them into the appropriate category.
8. Fill remaining slots with format staples appropriate to the color identity and budget.

### Structural Verification

After filling, run these checks **in this order**. The order matters: legality is cheapest to fail and least recoverable (banned cards force specific cuts), price is next because first-draft failures are overwhelmingly price-related, and mana/stats come last.

1. **Legality audit** — Run: `legality-audit <deck.json> <hydrated.json>`

   Stdout is a compact text report: `legality-audit: PASS/FAIL — ...` with per-category violation lists (`format_legality`, `color_identity`, `singleton`). **This is the cheapest check to fail and the most important to run first.** A skeleton with banned cards, off-identity cards, or singleton violations is structurally broken and no amount of price/mana tuning will make it playable. In particular, Historic Brawl bans many Commander staples (Sol Ring, Skullclamp, Hour of Reckoning, Triumph of the Hordes, etc.) that look like obvious includes if you're thinking in Commander terms — this check catches them before the user sees the skeleton. Color-identity violations typically mean a card slipped past the commander's identity gate during building and must be replaced. Singleton violations usually indicate an off-by-one quantity error from manual deck edits.

2. **Price check** — Run: `price-check <deck.json> --budget <budget> --bulk-data <bulk-data-path> [--format <format>]`

   Stdout is a compact text report with per-card price and running total. For Arena formats, use `--format brawl` or `--format historic_brawl` to get wildcard costs by rarity instead of USD prices. Verify total cost (or wildcard counts) is within the user's budget. If over budget, swap the most expensive non-essential cards (starting from synergy/engine, not lands/ramp) for cheaper alternatives. For Arena, "most expensive" means highest rarity — swap rare cards for uncommon alternatives. Re-run until the total is within budget. Per-category price tracking during the fill is a guide, not a substitute — real Scryfall prices drift from mental estimates, and a whole-deck draft frequently lands meaningfully over on the first pass. For Arena, also watch the `illegal_or_missing` warning line — cards that surface there escaped the legality audit because they weren't in the deck when that check ran, or the cache went stale.

3. **Deck stats** — Run: `deck-stats <deck.json> <hydrated.json>`

   Stdout is a compact text report — read it directly to verify total card count matches the deck's expected size and review curve and category counts.

4. **Mana audit** — Run: `mana-audit <deck.json> <hydrated.json>`

   Stdout is a compact text report with PASS/WARN/FAIL and per-color breakdown. Fix any FAIL results before proceeding.

**This is a gate — do not present a skeleton that fails any of these checks.** If any check fails and you edit the deck text file to fix it, re-parse, **re-run `scryfall-lookup --batch` to refresh the hydrated cache**, and re-run ALL checks from the top. Manual edits frequently introduce card count errors, and a stale hydrated cache makes the subsequent checks lie about what's in the deck.

## Step 4: Present Skeleton

Present the skeleton to the user as a markdown list organized by the builder's categories (lands, ramp, card draw, removal, board wipes, win conditions, engine/synergy, protection/utility). Include brief notes on why key synergy cards were included.

Show a summary:
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

Ask: "Want to make any adjustments before I hand this off for tuning?"

If the user requests changes, apply them, re-run structural verification, and present again.

## Step 5: Hand Off to Commander-Tuner

1. **Write output files** — Save the parsed deck JSON to the working directory (e.g., `<working-dir>/aesi-deck.json`). The hydrated card JSON already lives at `<working-dir>/.cache/hydrated-<sha>.json` from the Step 3 batch-lookup — that counts as "in the working directory" for handoff purposes; no `cp` is needed, just pass its absolute path to commander-tuner. Also export a Moxfield-importable text file:

   Run: `export-deck <deck.json> > <deck-moxfield.txt>`

   The deck JSON format: `{"format": str, "deck_size": int, "commanders": [{"name": str, "quantity": int}], "cards": [{"name": str, "quantity": int}, ...], "total_cards": int}`

2. **Invoke commander-tuner via the Skill tool** — Do NOT tell the user to type `/commander-tuner` themselves, and do NOT print a "handoff" block and stop. Slash commands are user-typed and cannot be triggered by Claude; the Skill tool is the only way to chain into the next skill in the same turn.

   Call the Skill tool with `skill: "commander-tuner"` and pass the carry-forward context (Step 5.3 below) inside the `args` field as a single prompt block. The commander-tuner skill will load and execute in this conversation, picking up the deck files you just wrote.

   If the Skill tool reports that `commander-tuner` is not installed, fall back to telling the user:

   > "I recommend installing the commander-tuner skill to refine this deck further. You can install it with `npx skills install <source>`. The skeleton is a playable starting point, but tuning will significantly improve it."

   Only print this fallback when the Skill tool actually fails — never as the default path.

3. **Carry forward context** — When invoking commander-tuner, provide the following so it can skip re-asking:
   - Bracket target
   - **Total budget** and **amount spent on skeleton**. For paper: "Total budget: $500, skeleton cost: $406, remaining for upgrades: $94". For Arena: "Total wildcard budget: 4M/10R/15U/40C, skeleton cost: 2M/8R/12U/30C, remaining: 2M/2R/3U/10C" (compact notation: M=mythic, R=rare, U=uncommon, C=common). Pass both numbers so the tuner can show a complete budget picture at the end.
   - Any cards the user already owns (these should not count toward either budget figure)
   - Experience level
   - Suggested max swaps: 20 (user can adjust during commander-tuner's intake)
   - Format, deck size, and **Arena or paper** (e.g., "Format: historic_brawl, deck size: 100, Arena")
   - Pain points: "This is a freshly generated skeleton — general optimization is the goal"

## "Outside the Box" Workflow (Combo-First Deck Building)

This alternative workflow builds decks from combos and mechanics first, then finds a commander to house them. It produces decks that don't fit standard EDHREC archetypes.

### Step 1b-alt: Mechanics/Outcome Interview (no commander known)

Ask (accepting either or both):
- "What mechanics excite you?" (open-ended — map to `card-search` oracle patterns and `combo-discover --card` queries)
- "What kind of outcome do you want?" (map to `combo-discover --result` query, e.g., "infinite tokens", "infinite mana", "mill entire library")
- "Color preferences?" (or "no preference")
- "How obscure do you want to go?" (somewhat unusual / very obscure / wildest thing you can find)
- "How many cards can your combo use?" (tight 2-3 card combos / allow bigger combos / full Rube Goldberg)

**Two discovery strategies based on user input:**
1. **Mechanics-first:** Use `card-search` with oracle text to find cards matching mechanics → feed card names to `combo-discover --card "X" --card "Y"` to find combos involving those cards
2. **Outcome-first:** Use `combo-discover --result "Infinite X"` directly
3. **Both:** Combine `--result` and `--card` filters

**Obscurity → popularity mapping:**
- Somewhat unusual: `--sort -popularity`, skip top results, popularity 1000-10000
- Very obscure: `--sort popularity`, skip 0s, popularity 100-1000
- Wildest thing: `--sort popularity`, popularity 0-100

**Jankiness → max combo size:**
- Tight: filter to combos with ≤3 cards
- Allow bigger: ≤4-5 cards
- Full Rube Goldberg: no limit

### Step 2-alt: Combo Discovery (both paths)

For **commander known + outside the box:** use `combo-discover --color-identity <commander-CI>` to constrain to the commander's colors.

Before presenting, write all combo piece names across all combos to a JSON list and batch-lookup in one call: `scryfall-lookup --batch <combo-pieces.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache`.

Present 3-5 interesting combos with:
- Cards involved and oracle text (from the batch-lookup results)
- What the combo produces
- Color identity
- Popularity score (lower = more obscure)
- Number of cards (jankiness indicator)
- For each combo piece: note standalone utility (e.g., "Viscera Seer is also a sac outlet for value even without the combo"). Combo pieces that are dead outside the combo are a risk — flag them.

Ask: "Want to build around one of these, or combine multiple?" If combining, verify color identities are compatible (can be covered by a single commander's identity) and check total combo piece count isn't excessive for one deck.

### Step 2b-alt: Commander Fitting (skip if commander already known)

Two-wave search for each selected combo:
1. **Mechanical fit:** `card-search --is-commander --color-identity <combo-CI> --oracle "<combo-keyword>"` — commanders whose oracle text mentions the combo's mechanics
2. **Strategic fit:** Use training data to shortlist commanders providing tutoring, draw, recursion, or protection in the combo's color identity. Write all shortlisted names to a JSON list and batch-lookup: `scryfall-lookup --batch <fit-candidates.json> --bulk-data <bulk-data-path> --cache-dir <working-dir>/.cache` (Iron Rule applies).

Also check if any combo piece IS a legendary creature that could be the commander.

Present 2-3 commander options with:
- How the commander mechanically supports the combo
- Whether the commander adds a secondary strategy axis
- EDHREC data if available (may be sparse for obscure commanders)

User picks a combo + commander pairing.

### Step 3-alt: Skeleton with Combo Core

- Slot combo pieces first (they're the deck's reason to exist)
- Use `card-search` to find supporting cards: tutors that find combo pieces, protection for combo pieces, redundant effects
- Note which combo pieces pull double duty vs. which are dead outside the combo
- Fill remaining categories (ramp, draw, removal, lands) weighted toward the combo's mechanics
- Standard structural verification applies (Step 3: Structural Verification)

### Steps 4-5-alt: Standard presentation and handoff

Same as the normal flow. When handing off to commander-tuner, note in the pain points: "Deck built around [combo description] — protect combo pieces and ensure the combo can be assembled reliably."

## Red Flags — STOP If You Catch Yourself Thinking These

| Thought | Reality |
|---------|---------|
| "I know what this card does" | You don't. Look it up. Training data is not oracle text. |
| "EDHREC recommends it so it must be good here" | EDHREC is aggregated data, not analysis. Evaluate for THIS build. |
| "This card is generally good in Commander" | Generic staples aren't always right. Check synergy with THIS commander. |
| "We're over budget but this card is too good to skip" | Budget is a hard constraint. Find a cheaper alternative. |
| "I'll just fill the rest with staples" | Every card should have a reason. Staples are a last resort, not a shortcut. |
| "The mana base is probably fine" | Run `mana-audit`. Don't eyeball mana bases. |
| "This step seems unnecessary for this deck" | Follow every step. The process exists because shortcuts cause mistakes. |
| "I can skip oracle text verification for well-known cards" | No. Look up every card. Even Sol Ring has oracle text worth reading. |

## Experience Level Adaptation

| Aspect | Beginner | Intermediate | Advanced |
|--------|----------|--------------|----------|
| Interview | Explain all terms, give examples | Use terms with brief context | Use shorthand |
| Recommendations | Explain why each card matters | Focus on synergy highlights | Category list with brief notes |
| Strategy | Explain what the strategy does and why | Explain key interactions | Name the archetype and key cards |
| Presentation | Narrative walkthrough of the deck | Grouped by category with notes | Concise tables |

## Script Reference

All scripts come from commander-tuner via symlink. See `commander-tuner/SKILL.md` for the full reference, or run any script with `--help`.
