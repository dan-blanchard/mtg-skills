---
name: deck-strat
description: Generate a Strategy Guide for a finished Commander, Brawl, or Historic Brawl deck — explains how to pilot it, with rules-cited stack/timing/interaction notes. Read-only on the deck; for tuning, run /deck-wizard first.
compatibility: Requires Python 3.12+ and uv. Shares mtg_utils package via symlink.
license: 0BSD
---

# Deck Strat

Produce a **Strategy Guide** for a finished MTG deck — a markdown
document that explains how to pilot the deck, organized into a fixed
core spine plus archetype-conditional sections, with every rules-adjacent
claim verified against the Comprehensive Rules. Each recommendation
MUST be grounded in actual oracle text and CR citations — never training
data.

deck-strat is **read-only** on the deck. It does not propose cuts, adds,
or tuning changes. If the user wants to tune the deck first, point them
at `/deck-wizard`, then run `/deck-strat` on the finished list. Both
skills share the working dir and the SHA-keyed hydrated cache, so chaining
is transparent.

## The Iron Rule

**NEVER assume what a card or rule does.** Before writing any clause
into the guide:

- For a card's behavior: look up its oracle text via `scryfall-lookup`
  or read it from the hydrated cache. Training data is not oracle text.
- For a rule's behavior: look it up via `rules-lookup` (`--rule`,
  `--term`, or `--grep`) and quote the verbatim text. Training data is
  not the CR.

A confidently wrong claim about commander-zone behavior, stack timing,
or a replacement-effect interaction makes the entire guide untrustworthy.
The Rules Audit subagent (Step 10) is the discipline gate that catches
slipped claims — but every authored sentence should be cite-defensible
before it gets there.

## Scope

deck-strat supports **Commander, Brawl, and Historic Brawl** (singleton
multiplayer formats with commanders). 60-card constructed formats are
out of scope in v1 — their strategy artifact is a sideboard plan + matchup
matrix, which is a different shape and is already produced by
`/deck-wizard` Step 12.

| Format | Deck Size | Pool | Multiplayer | Notes |
|---|---|---|---|---|
| commander | 100 | Full eternal | Yes (4P typical) | 40 life, commander damage rule |
| brawl | 60 | Standard | 1v1 on Arena, multiplayer in paper | 25/30 life, no commander damage |
| historic_brawl | 100 | Arena (broader than Standard) | 1v1 on Arena, multiplayer in paper | 25/30 life, no commander damage |

If the user invokes deck-strat on a 60-card constructed deck, decline
and redirect: "This skill produces multiplayer strategy guides for
singleton commander formats. For Standard/Modern/Pioneer/etc., run
`/deck-wizard` — its Step 12 finalize includes a sideboard guide."

## Progress Tracking

**Before starting, create a `TodoWrite` list** with these 10 items.
Mark each `in_progress` when you begin and `completed` the moment it
finishes — never batch.

1. Parse deck + set commander(s)
2. Hydrate via scryfall-lookup --batch
3. Baseline diagnostics
4. Commander Interaction Audit
5. Archetype detection
6. Combo + near-miss detection
7. EDHREC research
8. Rules verification pass
9. Draft Strategy Guide
10. Rules Audit subagent + revise

Step 4 is long enough that you should expand it inline when you start
it (sub-todos: keyword combos, trigger multiplication, feedback loops,
recurring cards, commander multiplication, combo detection). Step 10
is also long enough to expand (dispatch audit, process report, revise
draft).

Iteration after step 10 (user-requested edits) is not a fresh pipeline
run — handle each user request as an `Edit` to the existing guide.

## Setup (First Run)

```bash
uv sync --directory <skill-install-dir>
download-bulk --output-dir <skill-install-dir>
download-rules --output-dir <working-dir>
```

Subsequent runs skip if `.venv` exists, bulk data is fresh (24h), and
CR is fresh (24h). The CR file MUST live in the working dir, not the
skill install dir — `rules-lookup` and the Rules Audit subagent both
look there.

## Tooling Notes

### Working dir & paths

- **Absolute paths only.** `uv` rebases the working directory to the
  skill install; relative paths resolve against the wrong root.
- **Cache directory:** `<working-dir>/.cache` for hydrated card data.
- **CR file:** `<working-dir>/comprehensive-rules-YYYYMMDD.txt`.
- **Bulk data:** `<skill-install-dir>/default-cards.json`.
- **Output:** `<working-dir>/STRATEGY-GUIDE.md`.

### Reused CLIs

deck-strat ships no CLIs of its own. Every tool below is re-declared
from `mtg_utils` in `deck-strat/pyproject.toml`. Invoke via
`uv run <name>` from the skill install directory.

| Phase | Tool | Purpose |
|---|---|---|
| Acquisition | `parse-deck` | Parse list (Moxfield, MTGO, Arena, plain text) → deck.json |
| Acquisition | `set-commander` | Move commanders into the commanders list (idempotent) |
| Acquisition | `scryfall-lookup --batch` | Hydrate all cards into one SHA-keyed cache |
| Acquisition | `scryfall-lookup "<name>"` | Single-card lookup when verifying a specific card |
| Acquisition | `download-bulk` | Refresh Scryfall bulk data (24h freshness check) |
| Acquisition | `download-rules` | Refresh CR text (24h freshness check) |
| Diagnostics | `legality-audit` | Format legality, copy limits, color identity |
| Diagnostics | `deck-stats` | Land/ramp/creature counts, curve, color sources, GC count |
| Diagnostics | `mana-audit` | Burgess/Karsten land target + color balance |
| Diagnostics | `card-summary` | Compact oracle-text table (lands/nonlands/types) |
| Analysis | `archetype-audit` | Theme-density regex over the deck (token, sac, reanimate, etc.) |
| Analysis | `combo-search` | Existing + near-miss combos via Commander Spellbook |
| Analysis | `combo-discover` | Optional: explore combos by outcome/card/colors |
| Analysis | `edhrec-lookup` | Community top-cards + high-synergy for the commander(s) |
| Analysis | `card-search` | Fallback card discovery when EDHREC is empty |
| Analysis | `web-fetch` | Strategy articles when WebFetch is blocked |
| Verification | `rules-lookup` | CR lookups by `--rule`, `--term`, `--grep` |
| Verification | `rulings-lookup` | Scryfall per-card rulings |

### JSON file writing

Use the `Write` tool, not Bash heredocs, for any JSON file containing
card names. Apostrophes break shell quoting; Write-tool permissions
cache cleanly across the session.

### Scratch file paths

Reuse these stable paths within a session: `/tmp/audit-claims.json`
(used by the Rules Audit subagent), `/tmp/combo-search.json` (combo
detection output if `--output` not specified).

**Warning:** `/tmp` files persist across sessions. At session start,
`Read` each scratch path you plan to reuse before the first `Write`,
or run `Write` sequentially and verify success before the dependent
Bash call.

### Hybrid rules-lawyer integration

See [ADR-0008](../docs/adr/0008-hybrid-rules-lawyer-integration.md).
deck-strat uses two paths for rules verification:

1. **CLI (`rules-lookup`, `rulings-lookup`) — routine claims.** Default
   to this when a claim can be verified from one rule number, one
   glossary term, or one narrow regex. Examples: "does shroud block
   self-targeting?" → `rules-lookup --term shroud`; "is the free first
   mulligan a Commander rule?" → `rules-lookup --grep "first mulligan"`.
2. **Skill tool (`Skill(rules-lawyer, ...)`) — nuanced claims.** Escalate
   when (a) the claim spans two or more rules and their interaction is
   the load-bearing part, (b) the relevant rule's prose is thin and a
   section slice is needed, or (c) verification requires reasoning about
   layers, replacement-effect ordering, or stack timing across triggered
   and activated abilities. The rules-lawyer skill carries its own
   Phase 1/2/3 escalation discipline (including subagent dispatch) that
   you do not duplicate here.

Both the Phase 3 rules verification pass (Step 8) and the Rules Audit
subagent (Step 10) follow the same escalation rule.

### Re-hydration

If for any reason the deck JSON is edited mid-session (e.g., the user
notices a wrong card name during iteration and you re-parse), re-run
`scryfall-lookup --batch` — the hydrated cache is SHA-keyed against
the deck JSON's content, so a stale `cache_path` gives stale data.

---

## Phase 1: Acquisition

### Step 1: Parse + set commander(s)

Accept either a raw deck list (`.txt`, Moxfield export, MTGO format,
pasted) or an already-parsed deck JSON. If raw:

```bash
parse-deck <path> --format <commander|brawl|historic_brawl> \
    --output <working-dir>/deck.json
```

If the input is already a parsed deck JSON, accept it as-is and verify
its `format` field matches one of the three supported formats.

**Always pass `--format` explicitly** when parsing. Without it,
`parse-deck` defaults to `commander` and downstream tools see the wrong
format.

If the parsed deck's `commanders` list is empty (common with Moxfield
exports that lack `//Commander` headers), ask the user who the
commander is. Don't guess — the first card isn't always the commander.
Supports:

- **Single commander**: `set-commander <deck.json> "Name"`
- **Partner / Friends Forever**: `set-commander <deck.json> "Name1" "Name2"`
- **Commander + Background**: `set-commander <deck.json> "Commander" "Background"`

`set-commander` is idempotent — safe to chain after `parse-deck` even
when the deck file already had a commander header.

#### Pilot bracket question

After parsing, ask the user:

> "What power bracket are you piloting this at? (1-5 / casual / upgraded /
> optimized / cEDH, or `auto`.) This determines how the guide weights
> politics, combo prominence, and threat assessment."

Default to `auto`: count Game Changers (from `deck-stats`), count
game-winning combos (from `combo-search`, run later), assess curve.
The mapping:

- 0 GC, 0 infinite combos, curve ≥ 3.5 → Bracket 2 (casual)
- 1-2 GC, 0-1 combos, curve 3.0-3.5 → Bracket 3 (upgraded)
- 3+ GC, 2+ combos, curve ≤ 3.0 → Bracket 4 (optimized)
- All fast tutors + free interaction → cEDH (Bracket 5)

If the user gives an explicit bracket, prefer it. Auto-detect only when
they say `auto` or don't answer. Record the resolved bracket — every
downstream step uses it.

### Step 2: Hydrate

```bash
scryfall-lookup --batch <working-dir>/deck.json \
    --bulk-data <skill-install-dir>/default-cards.json \
    --cache-dir <working-dir>/.cache
```

Stdout is a JSON envelope with `cache_path`, `card_count`, `missing`,
and a `digest` containing counts + curve. **Do NOT `Read` the cache
file directly** — it's large and floods context. Use `card-summary`,
`Grep`, or targeted `scryfall-lookup "<Name>"` calls for inspection.

If `missing` is non-empty, the user's deck contains unrecognized card
names — ask them to verify. Common causes: typos, set-code suffixes
that didn't get stripped, Arena/paper crossover renames (Paradise
Chocobo = Birds of Paradise, Skittering Kitten = Masked Meower, etc.).

---

## Phase 2: Analysis

These five steps read the hydrated cache independently — you can run
their CLI calls in parallel where useful. Each populates context that
later steps depend on.

### Step 3: Baseline diagnostics

Run in this order (cheapest-to-fail first):

```bash
legality-audit <deck.json> <hydrated.json>
deck-stats <deck.json> <hydrated.json>
mana-audit <deck.json> <hydrated.json>
card-summary <hydrated.json> --nonlands-only
card-summary <hydrated.json> --lands-only
```

- `legality-audit` must PASS. If FAIL, surface the violation and ask the
  user how to resolve (the guide can't be authored against an illegal
  list). Don't propose fixes — that's deck-wizard's job.
- `deck-stats` gives the Game Changer count, curve, color sources, ramp
  count, and alternative-cost cards. Record alternative-cost cards
  (suspend, foretell, evoke, escape, flashback, adventure) — these
  evaluate at their alt cost in the strategy guide, not their printed
  CMC.
- `mana-audit` may return WARN or FAIL — note it but don't propose fixes.
  The guide can call out the mana base as a tuning consideration.
- `card-summary` is for your reading; do not paste it verbatim into the
  guide.

### Step 4: Commander Interaction Audit

This step is the highest-leverage analysis in the pipeline — it
surfaces the synergies that are invisible when reading cards in
isolation. **Inherited verbatim from deck-wizard Step 5; the
dimensions are the same.**

For each commander (and for partner/background pairs, both), and for
the deck as a whole, work through these six dimensions and write down
what you find. The Strategy Guide's "core loop", "synergies", and
"common lines" sections derive from these notes.

**Sub-todos (expand into TodoWrite when starting Step 4):**

#### 4a. Keyword combinations

List the commander's keywords and any keywords granted by cards in
the deck. Check every pair for emergent effects:

- **Evasion stacking:** menace + "can't be blocked by more than one
  creature" = unblockable. Any blocking restriction combined with a
  conflicting blocking requirement may create unblockable.
- **Damage multiplication:** double strike + combat damage triggers =
  double triggers. Double strike + lifelink = double life. Trample +
  deathtouch = 1 damage kills, rest tramples over.
- **Protection stacking:** ward + hexproof, indestructible + regenerate.
  Identify which are redundant vs. complementary.

#### 4b. Trigger multiplication

Identify the commander's core multiplier (extra upkeeps, extra combats,
extra turns, extra phases, trigger copying, token doubling, etc.). For
every triggered ability in the deck that fires during the multiplied
window, calculate output at 1×, 3×, and 5× the base rate. The Strategy
Guide presents the **multiplied** value as the realistic case, not the
1× base.

For commanders whose trigger scales with combat damage, identify pump
as a strategic pillar — each +1 power isn't just +1 damage, it's +1
trigger of every effect in the multiplied window.

#### 4c. Feedback loops

For each card, ask: "Does this card's output feed back into its own
input or the commander's trigger condition?" Examples:

- A +1/+1 counter source on a commander whose trigger scales with power.
- A token creator that increases a count used by another card's scaling.
- A theft effect where stolen permanents change type to match a tribal
  count.

Cards with feedback loops are almost always stronger than they appear
in isolation. The guide should flag them in the "synergies" section.

#### 4d. Recurring cards

Identify all cards that return themselves to a usable zone: re-suspend,
buyback, retrace, escape, flashback, "return to hand" clauses, "exile
with time counters" effects. The guide evaluates these on per-game
value (total free casts over a typical game), not per-cast value.

#### 4e. Commander multiplication

Identify cards that multiply the commander's impact:

- **Commander copies**: Helm of the Host, Spark Double, Clone effects,
  Mirror March, Followed Footsteps. Non-legendary copies bypass the
  legend rule and retain all triggered + activated abilities.
- **Ability copiers / trigger multipliers**: Strionic Resonator, Rings
  of Brighthearth, Panharmonicon (for ETB commanders), Teysa Karlov
  (death triggers), Isshin (attack triggers), Seedborn Muse (extra
  activations).

Scan oracle text directly — these are force-multipliers and earn
prominent placement in the guide's "synergies" section.

#### 4f. Combo detection

This sub-step bridges into Step 6. Run:

```bash
combo-search <deck.json> --hydrated <hydrated.json> \
    --output <working-dir>/combo-search.json
```

Distinguish:

- **Game-winning combos** (result contains "infinite" or "win the game"):
  flag prominently. These are central to the guide's "win conditions"
  and "combo execution" sections.
- **Value interactions** (non-infinite synergies): note as context.

Before recommending a near-miss combo as something the guide should
mention as a "1-card-away" finishing line, `Read` the full `description`
field for that near-miss from the JSON. The compact text report omits
required pieces that aren't in the card list.

### Step 5: Archetype detection

Run `archetype-audit` with a curated preset list to identify which
**conditional sections** the Strategy Guide will render. The result is
a set of theme densities — themes above the warn threshold trigger
their corresponding conditional section.

```bash
archetype-audit <deck.json> <hydrated.json> \
    --include-commanders \
    --preset tokens \
    --preset sacrifice-outlet \
    --preset reanimate \
    --theme 'goad=goad|attacks each combat if able' \
    --theme 'aristocrats-drain=whenever .* creature .* dies|sacrifice .* creature' \
    --theme 'token-doubler=create twice that many|tokens .* plus that many' \
    --theme 'opponents-create-tokens=that.*player.*creates|each.*opponent.*creates' \
    --theme 'extra-combats=additional combat phase|extra combat' \
    --theme 'extra-turns=take an extra turn|additional turn' \
    --theme 'big-mana=add (any|four|five|six|seven|eight)' \
    --min-density 4 --warn-density 6 --show-matches
```

**Always pass `--include-commanders`** — for commander formats the
commander is usually the biggest theme piece.

Map theme density (in card copies) to conditional sections:

| Theme detected (≥ warn threshold) | Conditional section to render |
|---|---|
| tokens + token-doubler | Token-doubling math section |
| aristocrats-drain + sacrifice-outlet | Aristocrats sequencing section |
| goad + opponents-create-tokens | Politics scripts section |
| extra-combats | Combat multiplier math section |
| extra-turns | Extra-turn sequencing section |
| reanimate | Reanimation lines section |
| big-mana | Mana-pump payoff section |
| **Game-winning combo present** | Combo execution section |
| **Commander is voltron-shaped** | Voltron commander damage math section |
| **Commander has ETB trigger + Panharmonicon-likes in deck** | ETB multiplication section |

Voltron-shaped commanders are identified manually: oracle text gives
the commander evasion + power-scaling, the deck has 6+ equipment / aura
slots, and the deck lacks wide-board engines.

### Step 6: Combo + near-miss detection

The combo-search call from Step 4f already populated this. Now do the
bracket check:

- **Bracket 1-2**: intentional two-card infinite combos are prohibited
  by the bracket policy. If the deck has an infinite combo, the guide
  flags it as a bracket compliance issue and asks the user whether to
  treat it as an unintended line or a real wincon.
- **Bracket 3**: infinite combos allowed but should not reliably fire
  before turn 6. Guide notes timing.
- **Bracket 4 / cEDH**: no restrictions. Combo lines are central in the
  guide.

Near-misses (1-card-away from a combo): the guide includes a "Known
near-miss completions worth knowing" callout listing the missing piece
+ what the closed combo would do. This is informational, not a
recommendation to change the deck.

### Step 7: EDHREC research

```bash
edhrec-lookup "<Commander Name>"
```

For partner pairs:

```bash
edhrec-lookup "<Commander 1>" "<Commander 2>"
```

EDHREC gives community top-cards, high-synergy cards, and deck count.
Use it to:

- Confirm the deck's archetype identification is reasonable.
- Spot cards in the deck that EDHREC flags as high-synergy (these get
  prominent placement in the guide).
- Spot cards EDHREC marks as commonly included that are NOT in this
  deck — note as "deliberate omissions" in deck notes.

**Brawl/Arena caveat:** EDHREC data is sourced from Commander/EDH
decks. For Brawl/Historic Brawl, EDHREC suggestions must be legality-
checked against the deck's format before referencing in the guide.

**Fallback if EDHREC has no data** (new or obscure commanders):

1. Use `card-search` with the commander's mechanics keywords to find
   synergistic cards in the color identity.
2. Look up the archetype rather than the specific commander.
3. The guide proceeds without the "community comparison" callouts.

Use WebSearch + WebFetch sparingly — only if you need strategic context
for an obscure commander. Use `web-fetch` script as a fallback if
WebFetch is blocked.

---

## Phase 3: Authoring

### Step 8: Rules verification pass

Before writing the guide, list every rules-adjacent claim you intend
to make. These come from Step 4 (commander interaction audit) and Step
6 (combo execution lines). For each, verify via the CLI or escalate to
the rules-lawyer skill per the hybrid integration rules above.

Common claim types and their verification:

| Claim type | Default verification |
|---|---|
| What a keyword does (shroud, deathtouch, menace, trample, etc.) | `rules-lookup --term <keyword>` |
| What a specific rule says (903.9, 603.8, 702.18, etc.) | `rules-lookup --rule <n>` |
| Whether a card's oracle text matches your description | `scryfall-lookup "<name>"` |
| Per-card rulings on edge cases | `rulings-lookup --card "<name>" --bulk-data <path>` |
| Stack ordering across triggered + activated abilities | `Skill(rules-lawyer, ...)` |
| Replacement effect interaction with another replacement | `Skill(rules-lawyer, ...)` |
| Layer reasoning (continuous effects) | `Skill(rules-lawyer, ...)` |
| Commander zone behavior (903.9a / 903.9b) | `rules-lookup --rule 903.9a` then `--rule 903.9b` |

Record each claim + its CR citation in your working notes — the draft
step quotes the verbatim CR text.

### Step 9: Draft Strategy Guide

Write the guide to `<working-dir>/STRATEGY-GUIDE.md`. The structure is
a fixed core spine + the conditional sections triggered in Step 5.

#### Core spine (always render, in this order)

1. **Title + identity block.**
   - Deck name (commander[s], color identity, format).
   - One-sentence archetype label (e.g., "Politics-driven aristocrats",
     "Voltron with reanimator subtheme", "Stax-control with combo finish").

2. **Core loop.** 3-5 sentences describing how the deck wins. Derives
   from Step 4 (commander interaction audit) — name the multiplier,
   the engine pieces, and the terminal effect.

3. **Win conditions.** Ordered by likelihood:
   - Primary plan (the core loop's terminal event).
   - Secondary plan (engine grind / commander damage / pump alpha-strike).
   - Tertiary plan (combo, if present and bracket-allowed).
   Each plan gets 2-4 sentences naming the cards involved.

4. **Mulligan guide.** What a keepable hand looks like. Reference the
   free first mulligan rule (CR 800.6) once. Common shapes to mulligan
   into. Common shapes to mulligan away from.

5. **Turn-by-turn pacing.** T1-T8+ sketch. What to deploy each turn
   range. Where the deck shifts from setup to harvest. Bracket-aware:
   faster brackets need a shorter setup window.

6. **Threat assessment.** Cards / decks to fear (sorted), cards / decks
   to eat for breakfast. Bracket-aware: Bracket 4 fears specific cards
   (Drannith, Null Rod, Cursed Totem) where Bracket 2 fears mass
   removal.

7. **Common lines + stack tricks.** Stack ordering on key sequences.
   The pre-wipe sequencing question (sac iteration vs. one wipe).
   Commander damage math. Equipment timing. **Every claim in this
   section gets a CR citation.**

8. **Deck quirks.** Borderline mana base, single Game Changer, weird
   reprint names (e.g., Paradise Chocobo = Birds of Paradise), suspended
   self-sac clauses (Endrek Sahr). Things that surprise a first-time
   pilot.

9. **Cheat sheet.** A bulleted per-turn checklist: "Did a token die →
   Joel triggered. Did opponents fight → Karazikar drew. Did a token
   enter → Mirkwood Bats / Impact Tremors fired." Strip names to the
   triggers a pilot needs to remember.

10. **Appendix: Verified card interaction notes.** A list of the rules-
    adjacent claims with their CR citations. This is the audit trail —
    the Rules Audit subagent (Step 10) verifies against this list.

#### Conditional sections (render when triggered in Step 5)

Each conditional section names its trigger at the top so a future
re-run reproduces the same shape if signals fire again.

- **Politics scripts** (triggered by goad + opponents-create-tokens):
  scripted lines for steering opponent attention, who to curse first,
  when to deploy goad effects.
- **Aristocrats sequencing** (aristocrats-drain + sacrifice-outlet):
  the pre-wipe-iterate-sacs question with sac-trigger vs. death-trigger
  asymmetry called out. Per-payoff trigger count.
- **Combo execution** (game-winning combo present): step-by-step stack
  ordering of the combo, required board state, protection options,
  near-miss completions.
- **Voltron commander damage math** (voltron-shaped commander): base
  power → equipment stack → growth-per-turn → turns to lethal. Hexproof
  / shroud / protection tooling.
- **Token doubling math** (tokens + token-doubler): with N doublers
  out, M token producers fire X tokens. Includes Chatterfang/Parallel
  Lives stacking semantics.
- **Extra-combats / extra-turns** sections: mana flow + threat density
  needed to make these worthwhile.
- **Reanimation lines** (reanimate density): which graveyard fillers
  feed which reanimators, exile-vs-graveyard differentiation.
- **Mana-pump payoffs** (big-mana): the X-spell finisher line, the
  Kessig Wolf Run line, the Helix Pinnacle line.
- **ETB multiplication** (Panharmonicon-likes): which ETB triggers in
  the deck benefit most, ordering on the stack.

#### Writing style

- **Cite CR rules verbatim**, not paraphrased. Quote the rule number
  + the trimmed sentence: "Per CR 903.9a: 'If a commander is in a
  graveyard or in exile and that object was put into that zone since
  the last time state-based actions were checked, its owner may put it
  into the command zone.'"
- **Reference cards by full oracle text** when the behavior is
  load-bearing. Paraphrase only for obvious cases (Sol Ring).
- **Adapt tone to experience level** (see table below). If not stated,
  ask the user during Step 1 acquisition or default to intermediate.
- **No emojis.** No marketing fluff. The guide is a reference document.

### Step 10: Rules Audit subagent + revise

**HARD GATE.** Before presenting the guide, dispatch one general-
purpose Agent with this exact charter:

> You are a Rules Audit agent for an MTG Strategy Guide. The guide is at
> `<absolute-path-to-STRATEGY-GUIDE.md>`. The deck's hydrated card data
> is at `<cache_path>`. The CR is at `<working-dir>/comprehensive-rules-
> YYYYMMDD.txt`.
>
> Your task: for every rules-adjacent claim in the guide (stack timing,
> replacement effects, commander-zone behavior, keyword interactions,
> intervening-if clauses, layers, trigger ordering, oracle text
> quotations), verify the claim against:
>
> 1. The card's actual oracle text via `scryfall-lookup "<name>"` or by
>    reading the hydrated cache.
> 2. The relevant CR rule via `rules-lookup --rule <n>` / `--term
>    <keyword>` / `--grep "<regex>"`.
> 3. For multi-rule reasoning, escalate to the rules-lawyer skill via
>    the Skill tool — the rules-lawyer skill's own escalation rules
>    apply.
>
> Return a JSON report at `/tmp/audit-claims.json` with this shape:
>
> ```
> {
>   "errors": [
>     {"section": "...", "claim": "...", "cr_says": "...", "fix": "..."}
>   ],
>   "unsupported": [
>     {"section": "...", "claim": "...", "needed_citation": "..."}
>   ],
>   "verified": [
>     {"section": "...", "claim": "...", "cr_rule": "...", "match": "exact|paraphrased"}
>   ]
> }
> ```
>
> Be specific. If the guide says "the trigger goes on top of the spell,"
> cite CR 603.3. If the guide says "shroud means can't be targeted,"
> cite CR 702.18a. Errors are claims that are factually wrong. Unsupported
> claims are factually fine but need a citation added. Verified claims
> are correct and cite-defensible.
>
> Do NOT propose strategic / deck-tuning changes. Your scope is rules
> verification only.

While the subagent runs, do nothing else — wait for the report.

Process the report:

- **Errors**: edit the guide in place to correct each one. Quote the
  CR text in the edit.
- **Unsupported**: edit the guide to add the missing CR citation.
- **Verified**: no action.

If the subagent reports zero errors and zero unsupported claims, present
the guide. If it reports any issues, fix them and **dispatch a
verification round 2** with the same charter — confirm no regressions
before presenting.

### Step 11: Present + iterate

Show the user the path to the guide and a brief summary of what's in
it (which conditional sections rendered, which combos detected, which
bracket-flag warnings if any).

Iteration is user-driven and in-place:

- User asks to add / remove / rewrite a section → `Edit` the existing
  `STRATEGY-GUIDE.md` file. Don't regenerate from scratch.
- User reports a rules error you missed → `rules-lookup` the relevant
  rule, fix in place, note that the Rules Audit missed it (this is a
  signal that the audit charter may need sharpening over time).
- User reports the deck changed (different cards) → restart the
  pipeline. The SHA-keyed hydrated cache will rebuild automatically;
  the guide gets rewritten.

---

## Failure Modes

| Symptom | Cause | Recovery |
|---|---|---|
| `scryfall-lookup --batch` reports `missing` cards | Typo, set-code suffix, crossover rename | Ask the user; for crossovers, suggest the canonical name (Paradise Chocobo → Birds of Paradise) |
| `legality-audit` returns FAIL | Banned card or color identity violation | Surface to user; deck-strat is read-only, can't fix it. Recommend `/deck-wizard` |
| `mana-audit` returns FAIL but user wants to proceed | Borderline land count or color balance | Proceed with the guide; flag the mana base as a tuning consideration in deck quirks |
| `combo-search` 404s or times out | Commander Spellbook API issue | Continue without combo section; log a warning in deck quirks; near-miss section omitted |
| `edhrec-lookup` 404s | Obscure commander not on EDHREC | Fall back to `card-search` by mechanic keywords; omit community-comparison callouts |
| `rules-lookup --term <X>` returns no match | Bad query | Try a synonym; widen to `--grep`; if still nothing, escalate to `Skill(rules-lawyer, ...)` |
| Rules Audit subagent reports >10 errors | First-draft was sloppy on rules | Revise; the second audit must come back clean. If round 2 also reports errors, treat as a SKILL.md bug and surface to user |
| User asks for a 60-card constructed deck | Out of scope | Decline + redirect to `/deck-wizard` |

---

## Experience-level Adaptation

Inherit deck-wizard's table for prose tone. Default to intermediate if
the user doesn't say.

| Aspect | Beginner | Intermediate | Advanced |
|---|---|---|---|
| Terminology | Define terms (tempo, card advantage, etc.) | Use freely | Use shorthand |
| Card references | Full oracle text quoted in-line | Quote only when load-bearing | Cite by name; assume the reader knows the card |
| CR citations | Brief explanation alongside | Rule number + trimmed sentence | Just rule number + sentence |
| Politics scripts | Narrative scenarios | Bullet scripts | Bullet scripts, terse |
| Combo execution | Step-by-step with explanation | Step list | Just the stack-order list |
| Mulligan | Sentence-form rules | Bulleted | Compact rubric |

---

## Red Flags

These thoughts mean STOP — you're rationalizing:

| Thought | Reality |
|---|---|
| "I know what this card does" | You don't. Look it up. Training data is not oracle text. |
| "I know what this rule says" | You don't. Look it up. Training data is not the CR. |
| "This rule is obvious, skip the citation" | Obvious-looking rules are where you'll get caught. The Rules Audit will flag it as unsupported. Cite it now. |
| "The user knows this format, skip mulligan/cheat sheet" | The core spine is mandatory. If a section truly doesn't apply, write a one-line note saying so — but it stays. |
| "Skip the Rules Audit subagent, the draft is clean" | The audit is the discipline gate that catches the claim you didn't realize was wrong. It runs every time. |
| "This 60-card deck just needs a quick guide" | Out of scope. Redirect to `/deck-wizard`. |
| "I'll fold combo execution into win conditions" | Combo execution is its own conditional section with stack ordering. Don't compress it. |
| "EDHREC says include X, so the guide should recommend swapping" | Read-only. No swaps. The guide can note a deliberate omission, not propose a change. |
| "I'll re-run parse-deck without --format" | Always pass `--format`. Defaulting to commander silently breaks Brawl decks. |
| "I'll use the rarity field from hydrated cache to score budget" | deck-strat doesn't do budget. That's `price-check` in deck-wizard. |
| "The bracket question is annoying, default to auto" | Default IS auto. Ask anyway — the answer changes the guide's center of gravity. |

---

## Decision Table

| Task | Tool |
|---|---|
| Parse list → deck.json | `parse-deck <path> --format <fmt> --output <out>` |
| Set commander(s) | `set-commander <deck.json> "Name" ["Name2"]` |
| Hydrate all cards | `scryfall-lookup --batch <deck.json> --bulk-data <path> --cache-dir <wd>/.cache` |
| Single card lookup | `scryfall-lookup "<Name>" --bulk-data <path>` |
| Card table (nonlands) | `card-summary <hydrated.json> --nonlands-only` |
| Card table (lands) | `card-summary <hydrated.json> --lands-only` |
| Format legality + color identity | `legality-audit <deck.json> <hydrated.json>` |
| Curve, ramp, Game Changers | `deck-stats <deck.json> <hydrated.json>` |
| Mana base audit | `mana-audit <deck.json> <hydrated.json>` |
| Theme density / archetype detection | `archetype-audit <deck.json> <hydrated.json> --include-commanders --preset ...` |
| In-deck combos + near-misses | `combo-search <deck.json> --hydrated <hydrated.json> --output <wd>/combo-search.json` |
| Explore combos by outcome | `combo-discover --result "<outcome>" --color-identity <ci>` |
| EDHREC top cards | `edhrec-lookup "<Name>" ["<Partner>"]` |
| CR rule by number | `rules-lookup --rule <n> --rules-file <wd>/comprehensive-rules-*.txt` |
| CR keyword / glossary term | `rules-lookup --term <keyword> --rules-file <wd>/comprehensive-rules-*.txt` |
| CR regex search | `rules-lookup --grep "<pattern>" --rules-file <wd>/comprehensive-rules-*.txt --limit 5` |
| Per-card Scryfall rulings | `rulings-lookup --card "<Name>" --bulk-data <path>` |
| Multi-rule timing / layer / stack | `Skill(rules-lawyer, ...)` |
| Strategy article fallback | `web-fetch "<url>" --max-length 10000` |
| Write/edit the guide | `Write` (first draft), `Edit` (iteration) |
| Run the Rules Audit | `Agent(subagent_type=general-purpose, ...)` with the charter in Step 10 |
