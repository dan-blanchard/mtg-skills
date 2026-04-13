---
name: deck-tuner
description: Analyze and optimize 60-card constructed MTG decks with sideboards for Standard, Alchemy, Historic, Pioneer, Timeless, Modern, Legacy, and Vintage.
compatibility: Requires Python 3.12+ and uv. Shares commander_utils package via symlink.
license: 0BSD
---

# Deck Tuner

Analyze and optimize existing 60-card constructed decks with sideboards for competitive MTG formats. Covers mainboard card evaluation, mana base tuning, sideboard planning against the metagame, and budget-aware upgrade paths.

## The Iron Rule

**Never assume what a card does.** Always look up oracle text via `scryfall-lookup` before evaluating a card. Training data may be outdated, cards get errata, and memory conflates similar effects.

---

## Progress Tracking

Create these top-level todos at session start. Mark `in_progress` immediately when starting a step, `completed` immediately when finishing. Never batch updates.

1. Step 1: Parse Deck List
2. Step 2: Hydrate Card Data
3. Step 2.5: Baseline Metrics
4. Step 3: User Intake
5. Step 4: Research
6. Step 5: Strategy Alignment
7. Step 6: Analysis
8. Step 7: Self-Grill
9. Step 8: Propose Changes
10. Step 8.5: Impact Verification
11. Step 9: Close Calls
12. Step 10: Finalize

**Step 6 expansion:** When starting Step 6, expand into sub-todos:
- 6a: Mana Base & Curve Audit
- 6b: Interaction & Threat Audit
- 6c: Archetype Coherence Check
- 6d: Draft Cuts (mainboard)
- 6e: Draft Additions (mainboard)
- 6f: Sideboard Evaluation
- 6g: Swap Balance Check

**Step 7 expansion:** When starting Step 7, expand into sub-todos:
- 7a: Dispatch Proposer + Challenger Subagents
- 7b: Process Challenger Report
- 7c: Revise Proposal

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

### Scratch File Paths

Reuse these stable paths within a session: `/tmp/cuts.json`, `/tmp/adds.json`, `/tmp/sideboard-cuts.json`, `/tmp/sideboard-adds.json`.

**Critical:** Files at `/tmp/` persist across sessions. Always `Read` a scratch file before the first `Write` in a new session.

### Alchemy Rebalancing Warning

Alchemy uses digitally rebalanced card versions prefixed with `A-` (e.g., `A-Teferi, Time Raveler`). These have different oracle text from their paper counterparts. When tuning Alchemy decks, search for both `"<Card Name>"` and `"A-<Card Name>"` via `scryfall-lookup` to verify which version is legal and what its current oracle text says. The rebalanced version is the one that matters for Alchemy gameplay.

### AskUserQuestion Cap

The AskUserQuestion tool supports at most 4 options. If you have more than 4 choices (common in Step 9 close calls), either present the most relevant 4 (mention others exist) or present the information as text and ask a follow-up question.

### Path Requirements

- **Absolute paths only.** `uv` rebases the working directory to the skill install.
- **Cache directory:** Always `<working-dir>/.cache`, not the skill install directory.
- **Re-hydration:** After every deck edit, re-run `scryfall-lookup --batch`. The cache is SHA-keyed; old caches go stale silently.

### Arena Rarity Warning

The `rarity` field in hydrated card data is the Scryfall default printing's rarity, which drifts from Arena's actual wildcard cost. Always use `price-check --format <fmt> --bulk-data <path>` for Arena wildcard budgeting.

### Decision Table

| Task | Tool |
|------|------|
| Find format-legal cards by oracle text, type, CMC | `card-search --format <fmt>` |
| Look up a specific card's oracle text | `scryfall-lookup "<Card Name>"` |
| View card table (mainboard) | `card-summary <hydrated.json> [--nonlands-only] [--lands-only] [--type <T>]` |
| View card table (sideboard) | `card-summary <hydrated.json> --deck <deck.json> --sideboard` |
| Find combos in the deck | `combo-search <deck.json>` |
| Find combos by card or outcome | `combo-discover --card "<Name>" --format <fmt>` |
| Check deck legality | `legality-audit <deck.json> <hydrated.json>` |
| Check mana base health | `mana-audit <deck.json> <hydrated.json>` |
| Compare mana before/after | `mana-audit <old.json> <old-hyd.json> --compare <new.json> <new-hyd.json>` |
| Price check (paper) | `price-check <deck.json> --bulk-data <path>` |
| Price check (Arena wildcards) | `price-check <deck.json> --format <fmt> --bulk-data <path>` |
| Apply mainboard + sideboard changes | `build-deck <deck.json> <hyd.json> --cuts <c.json> --adds <a.json> --sideboard-cuts <sc.json> --sideboard-adds <sa.json>` |
| Compare deck versions | `deck-diff <old.json> <new.json> <old-hyd.json> <new-hyd.json>` |
| Export for import | `export-deck <deck.json>` |
| Research metagame/strategy | WebSearch + WebFetch (or `web-fetch` script) |

---

## Step 1: Parse Deck List

```
parse-deck <path> --format <format> --output <working-dir>/deck.json
```

- Auto-detects input format (Moxfield, MTGO, Arena, plain text, CSV)
- Routes sideboard cards to the `sideboard` field (separate from `cards`)
- Strips Moxfield set code suffixes automatically
- Reports: `parse-deck: 60 cards, 15 sideboard -> /path/to/deck.json`

### Collection Ownership (Arena)

If the user has an Arena collection:
1. Ask for Untapped.gg CSV export first (most reliable source)
2. `mark-owned <deck.json> <collection.csv> --bulk-data <path>` to populate `owned_cards`
3. Use `mtga-import` only for extracting wildcard counts, not collection data

---

## Step 2: Hydrate Card Data

```
scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <working-dir>/.cache
```

Returns an envelope with `cache_path`, `card_count`, `missing`, `digest`. The cache file contains all mainboard + sideboard cards hydrated with oracle text, legalities, prices, etc.

**Do NOT Read the cache file directly** — it's large and floods context. Use `card-summary` or `scryfall-lookup "<Name>"` for targeted reads.

---

## Step 2.5: Baseline Metrics

Run in this order (cheapest-to-fail first):

### 1. Legality Audit

```
legality-audit <deck.json> <hydrated.json>
```

Checks: format legality, copy limits (4-of + Vintage restricted), sideboard size, deck minimum. **Must PASS** before continuing. If FAIL, surface violations and ask user how to fix.

### 2. Deck Stats

```
deck-stats <deck.json> <hydrated.json>
```

Review: total cards, land count, creature count, ramp count, avg CMC, curve distribution, sideboard total. Note any obvious red flags.

### 3. Card Summary

```
card-summary <hydrated.json> --nonlands-only
card-summary <hydrated.json> --lands-only
card-summary <hydrated.json> --deck <deck.json> --sideboard
```

Scan mainboard and sideboard oracle text. Flag cards with alternative costs (suspend, foretell, etc.) for adjusted CMC evaluation.

### 4. Mana Audit

```
mana-audit <deck.json> <hydrated.json>
```

Uses the constructed land formula. Notes land count status (PASS/WARN/FAIL) and color balance.

### 5. Companion Check

Check the sideboard for a Companion card (`card-summary <hydrated.json> --deck <deck.json> --sideboard` and look for the Companion keyword). If one exists, note its deck-building restriction — all proposed changes must continue to meet it.

If no Companion exists, check whether the deck naturally meets one's restriction. Companions are powerful enough that a deck accidentally qualifying for one (e.g., a low-curve aggro deck meeting Lurrus's "no permanents with mana value > 2") should actively consider adding it. Use `card-search --format <fmt> --oracle "Companion" --type "Creature"` to find candidates, then check restrictions against the current deck. If one fits, suggest it in Step 8 as an addition (it takes 1 sideboard slot).

---

## Step 3: User Intake

Ask one at a time via AskUserQuestion:

1. **Experience level** — Beginner / Intermediate / Advanced
2. **Best-of-One or Best-of-Three?** — Arena only; skip for paper. If Bo1, sideboard tuning is irrelevant — focus entirely on mainboard. Skip Steps 6f (Sideboard Evaluation) and the sideboard guide in Step 10.
3. **Budget for upgrades** — USD or wildcard budget for changes
4. **Max swaps** — How many cards (mainboard + sideboard) are you willing to change? (suggest 10-20; mainboard-only for Bo1)
5. **Pain points** — What matchups feel bad? What problems do you notice? Or just "general optimization"?
6. **Target** — Competitive ladder, FNM, tournament?

### If Handed Off from Deck-Builder

Confirm carry-forward context: format, platform, Bo1/Bo3, budget (total/spent/remaining), experience level, archetype, Companion (if any), max swaps. Don't re-ask questions already answered.

### Arena Wildcard Budgets

For Arena, use compact notation: `NM/NR/NU/NC` (e.g., `2M/4R/8U/12C` = 2 mythic, 4 rare, 8 uncommon, 12 common wildcards).

If the user ran `mtga-import`, check for `wildcards.json` in the working directory before asking about budget.

---

## Step 4: Research

### Metagame Context

1. **WebSearch** for `"<format> metagame 2026"` or `"<format> tier list"`
2. **WebFetch** top results to understand the current metagame landscape
3. Identify: What are the top 5 archetypes? Where does this deck fit? What are its expected good/bad matchups?

### Archetype-Specific Research

1. **WebSearch** for `"<deck archetype> <format> sideboard guide"` and `"<deck archetype> <format> matchup guide"`
2. **WebFetch** strategy articles for sideboard plans and matchup analysis
3. Compare the user's list to stock/optimized versions of the archetype

### Combo Awareness

```
combo-search <deck.json>
```

Surface existing combos and near-misses. Note which near-misses could be completed with 1-card additions.

**Supplement with WebSearch:** `combo-search` uses Commander Spellbook, which is crowdsourced primarily by Commander players. Combos that are powerful in 1v1 60-card formats but weak in multiplayer Commander may be underrepresented or missing. Search for `"<archetype> combo <format>"` and `"<key card> combo <format>"` to catch format-specific interactions the API might miss.

---

## Step 5: Strategy Alignment

Present your understanding of the deck's:
- **Game plan:** How does this deck win?
- **Key cards:** What are the most important cards in the strategy?
- **Expected matchups:** Given the metagame, which matchups are favorable/unfavorable?
- **Role flexibility:** In each matchup, is this deck the aggressor or the defender?

Ask the user to validate or correct. This alignment prevents wasted analysis on swaps that fight the deck's identity.

---

## Step 6: Analysis

### 6a: Mana Base & Curve Audit

- Land count vs. constructed formula target
- Color balance: pip demand vs. land production
- Mana base quality: untapped sources on key turns, color fixing
- `mana-audit` for quantitative check
- Flag: too few/many lands, color deficits, too many tapped lands

### 6b: Interaction & Threat Audit

- Count removal (targeted + sweepers)
- Count threats (creatures + planeswalkers + other win conditions)
- Compare to format expectations (aggro formats need fewer answers; control metas need more)
- Flag: insufficient interaction for the metagame, redundant removal, missing threat types

### 6c: Archetype Coherence Check

Unlike commander (which anchors on the commander), constructed decks must have a **consistent game plan** visible across the 60 cards.

**Step 1 — Identify the build-around cards.** Every competitive deck has 1-3 cards that define its archetype (e.g., Monastery Swiftspear for burn, Arclight Phoenix for Izzet Phoenix, Amulet of Vigor for Amulet Titan). These are the constructed equivalent of the commander — the cards the deck is built to maximize.

**Step 2 — Evaluate every other card against the build-around.** For each non-land card, it should do at least one of:
- **Enable** the build-around (tutors, setup, mana acceleration)
- **Protect** the build-around (counterspells, removal, redundancy)
- **Complement** the build-around (cards that benefit from the same game state)
- **Close** the game when the build-around has done its job (win conditions)

Cards that don't clearly fit one of these roles are candidates for cuts.

**Step 3 — Check for orphaned "Plan B" cards.** A common deck-building mistake is including 2-3 cards from a secondary strategy the deck doesn't have the infrastructure to support (e.g., a single planeswalker in an aggro deck with no way to protect it, or a graveyard payoff in a deck with no self-mill).

**Step 4 — Scan oracle text systematically.** Use `card-summary <hydrated.json> --nonlands-only` and look for oracle text that doesn't mention the deck's key mechanics. Cards whose text has no mechanical relationship to the build-around are red flags.

**Step 5 — Verify structural consistency:**
- **Threat density:** Does the deck have enough pressure to close games?
- **Curve alignment:** Does the curve support the intended speed?
- **Dead cards:** Cards that don't contribute to the primary game plan?
- **Mismatch cards:** Cards that belong to a different archetype?

### 6d: Draft Cuts (Mainboard)

For each proposed cut, evaluate:

1. **Oracle text verification** — Read full oracle text from hydrated data
2. **Alternative cost check** — Suspend, foretell, etc. change the effective CMC
3. **Role in the deck** — What role does this card fill? Is there redundancy?
4. **Matchup impact** — Does cutting this hurt specific matchups?
5. **Combo line check** — Is this card part of an existing combo? (from Step 4)
6. **Metagame relevance** — Is this card specifically good/bad in the current metagame?

**Be careful with cuts.** Re-read oracle text of both the card and its synergy partners. Articulate the specific underperformance.

### 6e: Draft Additions (Mainboard)

Source candidates from:
- Metagame research (stock list differences)
- `card-search --format <fmt>` for format-legal options
- Near-miss combos (from Step 4)
- WebSearch for archetype-specific tech

For each proposed addition:
1. Verify format legality and oracle text
2. Check price (within budget?)
3. Identify what role it fills
4. Compare to the card it's replacing

### 6f: Sideboard Evaluation

Evaluate the current sideboard against the metagame:
- Does it address the top 3-5 archetypes?
- Are there dead sideboard slots (cards for matchups that don't exist)?
- Are there missing answers (common archetypes with no sideboard plan)?
- Is the sideboard plan clear? (Which cards come in/out for each matchup?)

Draft sideboard changes alongside mainboard changes.

### 6g: Swap Balance Check

After drafting all changes (mainboard + sideboard):
- Verify total mainboard stays at 60+
- Verify sideboard stays at 15 or fewer
- Check land count hasn't drifted
- Check curve hasn't spiked
- Run `mana-audit --compare` to verify color balance maintained
- Verify budget: `price-check` on proposed additions

---

## Step 6.5: Pre-Grill Verification

Before the self-grill, verify mechanically:

1. **Price check on additions:**
   ```
   price-check /tmp/adds.json --bulk-data <path>
   ```
   Verify total additions cost is within upgrade budget.

2. **Internal evaluation for each cut** (not shown to user):
   - Role in deck
   - Matchup impact
   - Combo line affected?
   - Replacement justification
   - Metagame relevance

If you can't articulate why a specific card should be cut, you haven't evaluated it — don't proceed.

---

## Step 7: Self-Grill (Two-Agent Debate)

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
- Sideboard cuts/adds JSON (if any)

**Bottom-line summary example:**
"Proposed 8 mainboard swaps + 4 sideboard swaps for Pioneer Mono-Red. mana-audit PASS; price-check $12.50 of $20 budget; combo-search 0 combos (aggro deck). Key thesis: shift from burn-heavy to creature-heavy for better Sheoldred matchup."

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
- [ ] Verify sideboard plan still covers top metagame archetypes
- [ ] Verify no combo lines broken without justification
- [ ] Verify swap balance (land count, curve, total counts)
- [ ] **Companion restriction:** If the deck has a Companion, verify every addition still meets its deck-building restriction
- [ ] **Archetype coherence test:** "Does this deck still have a clear game plan after these swaps?"
- [ ] **Sideboard coherence test:** "For each top-3 matchup, what comes in and what goes out? Does that plan make sense?"

**Expect 2-3 rounds minimum.** If both agree immediately, the challenger isn't pushing hard enough.

---

## Step 8: Propose Changes

**HARD GATE:** Write the full proposal as a complete turn BEFORE any `AskUserQuestion`. Do not bundle a tool call with proposal markdown — the tool executes before text finalizes, and the user approves blind.

### Before Presenting

Run `build-deck` to construct the new deck, then `mana-audit` on the result. If FAIL, revise until PASS.

### Proposal Format

Present as paired swaps with reasoning. Adapt detail to experience level.

**Mainboard changes:**
```
## Mainboard Changes (8 swaps)

**OUT: Shock (4) → IN: Play with Fire (4)**
Shock deals 2 to any target; Play with Fire deals 2 to any target OR scrys 1 when it
deals damage to a player. Strictly better in this deck since we point burn at face.
Cost: $0.50 per copy.

**OUT: Viashino Pyromancer (2) → IN: Eidolon of the Great Revel (2)**
Viashino is a one-shot 2 damage on ETB. Eidolon punishes the opponent for every spell
they cast, often dealing 6-10 damage per game in faster matchups. Key against combo
and low-curve decks.
Cost: $3.00 per copy.
...
```

**Sideboard changes:**
```
## Sideboard Changes (4 swaps)

**OUT: Magma Spray (2) → IN: Roiling Vortex (2)**
Magma Spray is narrow graveyard removal. Roiling Vortex hits free spells (Fury, Force),
lifegain (Sheoldred), and deals 1/turn. Better coverage across more matchups.
Cost: $1.00 per copy.
...
```

**Budget summary:**
```
## Budget
Total additions: $14.50 / $20.00 budget
Remaining: $5.50
```

---

## Step 8.5: Impact Verification

**HARD GATE.** Run BOTH checks on the new deck before presenting close calls. This step catches emergent regressions — cross-swap interactions visible only after all changes are applied together.

### Check 1: Deck Diff

```
deck-diff <old-deck.json> <new-deck.json> <old-hydrated.json> <new-hydrated.json>
```

Verify:
- Total count unchanged (still 60 mainboard, 15 sideboard)
- Land count healthy
- Avg CMC didn't spike
- Ramp/acceleration count stable
- Sideboard changes match proposal

### Check 2: Combo Search (Post-Build)

```
combo-search <new-deck.json>
```

Compare to Step 4 results:
- Any combos lost? If so, was the loss intentional (documented in Step 6d)?
- Any new combos gained?
- Near-miss changes?

If any unintended regression, revise the proposal.

---

## Step 9: Close Calls

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

---

## Step 10: Finalize

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
Mainboard upgrades: $14.50
Sideboard upgrades: $3.00
Total spent: $17.50 / $20.00 budget
Remaining: $2.50
Owned cards used: 12 (not counted toward budget)
```

**Arena:**
```
| Rarity   | Used | Available | Remaining |
|----------|------|-----------|-----------|
| Mythic   | 1    | 2         | 1         |
| Rare     | 3    | 4         | 1         |
| Uncommon | 4    | 8         | 4         |
| Common   | 6    | 12        | 6         |
```

### Sideboard Guide

Construct a matchup-by-matchup sideboard map for the top 3-5 metagame archetypes identified in Step 4. This is a natural output of the analysis already performed — don't skip it.

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
| "I know what this card does" | Look it up. Training data drifts. |
| "This is a format staple, it can't be a cut" | Evaluate in context. Staples can underperform in specific shells. |
| "The sideboard is fine, focus on mainboard" | Sideboard wins tournaments. Evaluate it. |
| "Skip the self-grill, the analysis was thorough" | Mechanical checks find numbers. Self-grill finds strategy. Both required. |
| "Skip impact verification, the swaps look clean" | Emergent cross-swap effects only visible post-build. Run the checks. |
| "This card is too expensive to cut" | Sunk cost. Evaluate on merit, not price. |
| "I'll just cut the worst cards" | Worst for what? Evaluate against archetype, matchups, and metagame. |
| "The mana base is close enough" | Run mana-audit. "Close enough" is how you lose to color screw. |
| "Propose changes and ask for approval in one message" | Step 8 is its own turn. AskUserQuestion comes in Step 9. |

---

## Experience Level Adaptation

| Aspect | Beginner | Intermediate | Advanced |
|--------|----------|-------------|----------|
| Metagame explanation | Define archetypes, explain matchups | Name archetypes, note key cards | Assume knowledge, focus on novel angles |
| Swap reasoning | Full sentences, explain why old card is worse | Note specific interaction | Concise: "Bolt > Shock (scry 1 upside)" |
| Sideboard guide | Explain what sideboarding means | Provide in/out plan per matchup | Shorthand sideboard map |
| Mana base | Explain land types | Note mana base tradeoffs | Focus on marginal improvements |

---

## Script Reference

### Core Scripts

- `parse-deck --format <fmt> <path>` — Parse deck list with sideboard
- `scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <dir>` — Hydrate card data
- `scryfall-lookup "<Card Name>" --bulk-data <path>` — Single card lookup
- `card-summary <hydrated.json> [--nonlands-only] [--lands-only] [--type <T>] [--deck <deck.json> --sideboard]` — Card table display
- `card-search --format <fmt> [--oracle <regex>] [--color-identity <CI>] [--type <type>] [--cmc-max <N>] [--price-max <N>]` — Search for candidates
- `combo-search <deck.json>` — Find existing combos and near-misses
- `combo-discover [--card "<name>"] [--result "<outcome>"] [--format <fmt>]` — Discover combos
- `legality-audit <deck.json> <hydrated.json>` — Check legality, 4-of, sideboard size, deck minimum
- `mana-audit <deck.json> <hydrated.json> [--compare <new-deck.json> <new-hydrated.json>]` — Mana base audit
- `price-check <deck.json> [--format <fmt>] --bulk-data <path> [--budget <N>]` — Budget check
- `deck-stats <deck.json> <hydrated.json>` — Deck statistics
- `build-deck <deck.json> <hydrated.json> --cuts <c.json> --adds <a.json> [--sideboard-cuts <sc.json>] [--sideboard-adds <sa.json>] [--bulk-data <path>]` — Apply changes
- `deck-diff <old.json> <new.json> <old-hyd.json> <new-hyd.json>` — Compare deck versions
- `export-deck <deck.json>` — Export Moxfield/Arena format with sideboard
- `mark-owned <deck.json> <collection.csv> [--bulk-data <path>]` — Mark owned cards
- `download-bulk --output-dir <dir>` — Download Scryfall bulk data

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
