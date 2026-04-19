---
name: cube-wizard
description: Build and tune MTG cubes — curated card pools designed for drafting. Supports Vintage, Unpowered, Legacy, Modern, Pauper, Peasant, Set, Commander, and PDH cubes.
compatibility: Requires Python 3.12+ and uv. Shares mtg_utils package via symlink.
license: 0BSD
---

# Cube Wizard

Build MTG cubes from scratch (by cloning a well-known reference cube and
customizing) or tune existing ones. A cube is a curated card pool designed
for drafting, typically 360–720 cards. Unlike a deck, balance lives at the
*collection* level — archetype draftability, per-color-pair signal density,
fixing density, curve shape across the whole pool. Every recommendation MUST
be grounded in actual card oracle text from Scryfall — never from training
data.

The skill has two phases. **Phase 1 (Cube Acquisition)** determines how the
user gets a cube: parse an existing list (Path A) or clone a reference cube
(Path B). Both paths produce a cube JSON + hydrated cache. **Phase 2
(Tuning)** runs the same 9-step pipeline on that cube regardless of origin.

## The Iron Rule

**NEVER assume what a card does.** Before referencing any card's abilities,
look up its oracle text via the helper scripts. Training data is not oracle
text.

**Exception (archetype brainstorming only):** During Phase 1 Path B's
customization-intent interview, when the user is brainstorming archetypes
and themes, you may use training data to suggest theme names (tokens,
sacrifice, +1/+1 counters, etc.). But every card you propose for the cube
MUST be verified against Scryfall oracle text before the user accepts it —
write all candidate names to a JSON list and batch-lookup in one call:

```bash
scryfall-lookup --batch <candidates.json> --bulk-data <bulk-path> --cache-dir <wd>/.cache
```

---

## Supported Cube Formats

| Format | Default Size | Card Pool | Rarity Filter | Commander Pool | Notes |
|--------|-------------:|-----------|---------------|----------------|-------|
| vintage | 540 | Full eternal | — | No | Powered (Power 9 allowed) |
| unpowered | 540 | Full eternal | — | No | Power 9 banned by default |
| legacy | 540 | Legacy-legal | — | No | Legacy ban list applies |
| modern | 540 | Modern-legal | — | No | Modern ban list applies |
| pauper | 540 | Full eternal | Commons only | No | — |
| peasant | 540 | Full eternal | Commons + uncommons | No | — |
| set | 360 | Single set | — | No | Auto-detected if all cards share a set |
| commander | 540 | Commander-legal | — | Yes | Dedicated commander pack drafted separately |
| pdh | 540 | Full eternal | Commons (main) | Yes | Commanders: uncommons |

**Format is optional metadata, not a hard gate.** A "cats-and-dogs tribal
cube" or a "budget-capped cube" works fine — layer constraints on top of
whichever format's rarity/legality filter fits. The `designer_intent` block
in the cube JSON captures the user's specific goals.

---

## Progress Tracking

**Before starting, create a `TaskCreate` list.** The first question
determines the path; create tasks accordingly.

### Phase 1: Path A (Parse Existing Cube)

- Fetch / Read Cube
- Parse to Canonical Cube JSON
- Hydrate Card Data

### Phase 1: Path B (Clone Reference Cube)

- Interview
- Reference Cube Selection
- Fetch + Parse + Hydrate
- Baseline Review

### Phase 2: Tuning (Both Paths)

1. Baseline Metrics
2. Designer Intent Confirmation
3. Balance Dashboard
4. Archetype Audit
5. Power-Level Review
6. Self-Grill
7. Propose Changes
8. Pack Simulation
9. Finalize / Export

Mark each item `in_progress` the moment you begin it and `completed` the
moment it finishes — do not batch updates.

---

## Setup (First Run)

```bash
uv sync --directory <skill-install-dir>
download-bulk --output-dir <skill-install-dir>
```

Subsequent runs skip `uv sync` if `.venv` exists and bulk data is fresh
(24h).

---

## Tooling Notes

### Human-Readable stdout + JSON Sidecar (load-bearing)

Every cube CLI emits a short human-readable summary to stdout and writes the
full structured output to a sidecar JSON file, with a `Full JSON: <path>`
footer. This pattern exists because cube JSON at 540+ cards would blow
context if streamed to stdout verbatim.

**Script-to-script chaining uses file paths, not piped JSON.** Read the
sidecar selectively with `Read` + `offset`/`limit` when you need specific
fields. Pass `--json` only when a downstream script needs the full payload
on stdout (rare).

### JSON File Writing

**Use the Write tool** for any JSON file containing card names. Apostrophes
(e.g., "Ashnod's Altar") break shell quoting in heredocs and inline Python.
Write tool permissions are cacheable across the session; `python3 -c "..."`
re-prompts every time.

### Scratch File Paths

Reuse these stable paths within a session: `/tmp/cube-cuts.json`,
`/tmp/cube-adds.json`, `/tmp/cube-candidates.json`, `/tmp/cube-themes.json`.

`/tmp` files persist across sessions. At session start, `Read` each scratch
path you plan to reuse before the first `Write`, OR run `Write` sequentially
and verify success before the dependent Bash call. Never batch
`Write(/tmp/foo.json)` + `Bash(tool reading /tmp/foo.json)` in a single
message.

### Path Requirements

- **Absolute paths only.** `uv` rebases the working directory to the skill
  install; relative paths resolve against the wrong root.
- **Cache directory:** Always `<working-dir>/.cache`, not the skill install.
- **Re-hydration:** After every cube edit, re-run
  `scryfall-lookup --batch` on the new cube JSON. The hydrated cache is
  SHA-keyed; old caches go stale silently.

### CubeCobra Fetch Caveats

CubeCobra returns 403 to plain Python UAs for some endpoints. `cubecobra-fetch`
handles this transparently by falling back to curl via `web_fetch`. Fetch
priority: `cubeJSON` (richest — mainboard/maybeboard split, designer tags,
per-card overrides) → CSV → plain cubelist. If all three fail, the user can
export manually from the CubeCobra UI and pass the file to `parse-cube`.

### Balance Checks are Informational, Not Pass/Fail

`cube-balance` reports observed metrics against conventional reference
ranges (e.g., "22–28% removal density"). It does NOT mark a cube as broken
if it falls outside the range. A mono-blue cube, a combo cube, or a
cats-and-dogs tribal cube may legitimately differ from conventional
expectations. Read the reference ranges as "typical" — not "required."

Reference ranges come from Riptide Lab and Star City Games consensus plus
Lucky Paper's "How Many Lands Should You Include in Your Cube" numerics.

### Regex Scope Warning for `cube-balance` and `archetype-audit`

Removal detection uses an oracle-text regex bank (destroy/exile/counter/
damage/bounce/fight/−X). It's tuned to be generous — false positives are
acceptable for an informational metric. When the density feels off, spot-
check by running:

```bash
card-search --bulk-data <path> --oracle "<your regex>" --color-identity <ci>
```

For `archetype-audit`, the user supplies the regex per theme
(`--theme name=regex`), so theme detection is exactly as precise as the
regex the user writes.

### Canonical Cube JSON Schema

```json
{
  "cube_format": "vintage|unpowered|legacy|modern|pauper|peasant|set|commander|pdh",
  "target_size": 540,
  "name": "Regular Cube",
  "drafters": 12,
  "pack_size": 15,
  "packs_per_drafter": 3,
  "source": "cubecobra:<id>",
  "cloned_at": "2026-04-18T12:34:56Z",
  "designer_intent": {
    "description": "<from CubeCobra overview>",
    "tags": ["unpowered", "vintage"],
    "stated_archetypes": [
      {"name": "Boros Equipment", "regex": "equip|attach"},
      {"name": "Simic Ramp", "regex": "search your library for.*land"}
    ]
  },
  "pack_templates": {},
  "balance_targets_override": {},
  "commander_pool": [
    {"name": "Atraxa, Praetors' Voice", "quantity": 1, "scryfall_id": "..."}
  ],
  "cards": [
    {"name": "Lightning Bolt", "quantity": 1,
     "cube_color": "R", "cube_cmc": 1.0,
     "tags": ["burn"], "scryfall_id": "..."}
  ],
  "total_cards": 540
}
```

All cube CLIs accept this shape. Hydrated cache lives at
`<working-dir>/.cache/<sha>.json`, SHA-keyed so re-hydration is idempotent.

---

## Decision Table

| Task | Tool |
|------|------|
| Pull a CubeCobra cube | `cubecobra-fetch <id-or-url> --output-dir <wd>` |
| Parse a cube list / CSV / JSON | `parse-cube <path> --cube-format <fmt> --output <wd>/cube.json` |
| Hydrate card data | `scryfall-lookup --batch <cube.json> --bulk-data <path> --cache-dir <wd>/.cache` |
| Top-line cube metrics | `cube-stats <cube.json> <hyd.json>` |
| Balance dashboard | `cube-balance <cube.json> <hyd.json> [--check <name>]` |
| **Format legality + rarity audit** | **`cube-legality-audit <cube.json> <hyd.json>`** |
| Archetype validation | `archetype-audit <cube.json> <hyd.json> --theme name=regex` |
| Bridge cards | Included in `archetype-audit` output when ≥2 themes supplied |
| Compare cube revisions | `cube-diff <old.json> <new.json> [--old-hydrated <h> --new-hydrated <h> --metrics]` |
| Sample an opening pack | `pack-simulate <cube.json> <hyd.json> --seed N --pack-size 15` |
| Stress-test draftability | `pack-simulate ... --simulate-drafts 100` |
| Find candidate cards | `card-search --bulk-data <path> --oracle "<regex>" --color-identity <ci>` |
| Cube budget check | `price-check <cube.json> --bulk-data <path>` |
| Find accidental infinites | `combo-search <cube.json>` |
| Export to CubeCobra CSV | `export-cube <cube.json> --format csv --output <wd>/cube.csv` |
| Cite MTG Comprehensive Rules | `rules-lookup --rule <n>` / `--term <keyword>` / `--grep "<regex>"` |
| Fetch Scryfall per-card rulings | `rulings-lookup --card "<name>" --bulk-data <path>` |
| Deeper rules question (archetype legality, keyword interaction) | Invoke the `rules-lawyer` skill via the Skill tool |

### Rules Lawyer

Cube design occasionally runs into rules questions — "does this combo actually work in the format?", "is this trigger mandatory?", "how does the layer system handle this static?". Run `rules-lookup --term <keyword>` for straightforward keyword/glossary questions. For anything nuanced (layers, replacement effects, multi-rule interactions), invoke the `rules-lawyer` skill via the Skill tool, which handles escalation to subagents loaded with the relevant CR section.

Run `download-rules --output-dir <working-dir>` once per session before the first `rules-lookup` call (24-hour freshness check, same pattern as `download-bulk`).

---

## Phase 1: Cube Acquisition

**Opening question:** "Do you have an existing cube list you want to tune,
or do you want to build a new cube starting from a well-known reference?"

### Path A: Parse Existing Cube

1. **Acquire the cube list.** One of:
   - CubeCobra ID or URL → `cubecobra-fetch <id> --output-dir <wd>`
   - Local file (CubeCobra CSV, plain text, etc.) — use as-is
2. **Parse to canonical cube JSON.**
   ```bash
   parse-cube <wd>/<cube>.json --cube-format <fmt> --output <wd>/cube.json
   ```
   If the user didn't specify a format, `parse-cube` auto-detects
   `set` cubes (all cards share a set code) and defaults to `vintage`
   otherwise.
3. **Hydrate card data.**
   ```bash
   scryfall-lookup --batch <wd>/cube.json --bulk-data <wd>/default-cards.json --cache-dir <wd>/.cache
   ```
4. **Confirm scope.** Read `cube.json.designer_intent.description` and
   `tags` — these provide the context the Phase 2 pipeline needs. If the
   cube has stated archetypes but no regexes, ask the user to supply regex
   queries for each during Step 4.

### Path B: Clone Reference Cube

1. **Interview.** In order:
   - Cube format (see Supported Cube Formats table)
   - Target size (360 / 450 / 540 / 630 / 720, default from format)
   - Drafters / pack size (defaults from `cube_config.SIZE_TO_DRAFTERS`)
   - Reference cube selection: present the hardcoded options for the chosen
     format from `cube_config.REFERENCE_CUBES`, plus "Paste a CubeCobra URL"
     for any cube the user knows. Use `AskUserQuestion` (respect the 4-option
     cap — list all options in the text message, let the user pick any).
   - Customization intent (open-ended): "What do you want to change from
     this reference? Add an archetype? Cut specific cards? Tribal theme?
     Budget cap? Or just tune the baseline?"
   - Budget (optional): paper USD cap
   - Restrictions (optional): no fast mana, no infinite combos, tribal
     constraints, single-set, single-color, etc.
2. **Fetch + parse + hydrate.** Same commands as Path A applied to the
   reference cube's CubeCobra ID.
3. **Baseline review.** Run `cube-stats` and `cube-balance` on the
   unmodified reference cube. Present the baseline to the user so they
   confirm the starting point matches their intent before customization
   begins.

---

## Phase 2: Tuning Pipeline

The same 9 steps apply whether the cube came from Path A (existing) or Path
B (cloned reference). Use `TaskCreate` to track progress through them.

### Step 1: Baseline Metrics

```bash
cube-stats <cube.json> <hyd.json>
cube-balance <cube.json> <hyd.json>
```

Capture the observed color distribution, curve, removal density, fixing
density, and commander-pool composition (if any). These are the before-
picture for Step 7's impact verification.

### Step 2: Designer Intent Confirmation

Summarize the cube's stated intent back to the user:
- Format, size, drafters
- Designer description from CubeCobra overview (or the customization
  intent from Path B's interview)
- Stated archetypes (if any)
- Explicit restrictions

Ask the user to confirm or adjust. Persist any clarifications back to
`cube.json.designer_intent.stated_archetypes` as `{name, regex}` entries
for Step 4.

### Step 3: Balance Dashboard & Legality Audit

Already computed in Step 1; walk through each section with the user and
note any "outside typical range" items that are intentional (e.g., "yes,
the removal density is low because I want this cube to be creature-heavy").

Also run the mechanical legality audit:

```bash
cube-legality-audit <cube.json> <hyd.json>
```

Unlike `cube-balance`, this is a **hard-constraint check**: errors indicate
format rule violations that should be fixed before shipping. Checks:

- **Rarity filter** — e.g., a Pauper cube with a rare card (uses Scryfall's
  `legalities.pauper` when available, falls back to default-printing rarity
  as a warn for Peasant).
- **Legality key** — e.g., a Modern cube with a Modern-illegal card.
- **Ban list** — e.g., Power 9 cards in an `unpowered` cube.
- **Commander pool rarity** — e.g., PDH commanders must be uncommons.

Any `error`-severity violation requires a fix (swap the card or change the
cube format). `warn`-severity items require manual verification (default-
printing rarity drift, missing legality data).

### Step 4: Archetype Audit

For each stated archetype, build a regex that matches the oracle text of
cards that enable it. Example:
- `tokens=create .* creature token`
- `sacrifice=sacrifice (a|another) (creature|permanent)`
- `counters=\+1/\+1 counter`
- `spells=(instant|sorcery) you (control|cast)`
- `blink=exile .* return .* (battlefield|owner's control)`

```bash
archetype-audit <cube.json> <hyd.json> \
    --theme "tokens=create .* creature token" \
    --theme "sacrifice=sacrifice (a|another) (creature|permanent)" \
    --theme "counters=\\+1/\\+1 counter"
```

Output reports per-theme density, per-guild density, orphan signals
(payoffs only in one color), and bridge cards (cards supporting multiple
themes — design-priority connective tissue).

**Close any theme that has fewer than 3–4 cards with the user** — Lucky
Paper's FAQ says an archetype "needs as little as 3–4 cards" to be
draftable; below that threshold it's a non-archetype.

### Step 5: Power-Level Review

Two checks:

1. **Price outliers** (proxy for power): flag cards $50+ and $100+ tier
   outliers via `price-check <cube.json> --bulk-data <path>`.
2. **Accidental infinite combos** — a cube's main worry is that unrelated
   cards form a two-card infinite that warps drafts:
   ```bash
   combo-search <cube.json>
   ```
   `combo-search` is deck-scoped but works fine on cube JSON (both share the
   `cards[]` shape). Review flagged combos with the user.

### Step 6: Self-Grill (HARD GATE)

Run parallel Agent calls — one proposer, one challenger — following the
deck-wizard Step 8 pattern. Challenger prompt focuses on cube-specific
failure modes: archetype starvation (cutting enablers without replacing
payoffs), color imbalance introduced, signal dilution (new cards support 0
themes), power outliers, fixing disruption.

Brief both agents with:
- The cube's stated archetypes and designer intent
- Current `cube-stats` + `cube-balance` baseline
- Current `archetype-audit` per-theme density
- Proposed cuts/adds (from the tuning session)

### Step 7: Propose Changes

Write cuts/adds to `/tmp/cube-cuts.json` and `/tmp/cube-adds.json` via
`Write` tool. Regenerate the cube JSON (by applying cuts/adds), re-hydrate,
and re-run the Phase 2 metrics:

```bash
cube-diff <old-cube.json> <new-cube.json> \
    --old-hydrated <old-hyd.json> --new-hydrated <new-hyd.json> --metrics
```

Review the deltas with the user before proceeding.

### Step 8: Pack Simulation

```bash
pack-simulate <new-cube.json> <new-hyd.json> --seed 1 --pack-size 15
pack-simulate <new-cube.json> <new-hyd.json> --seed 1 --pack-size 15 --simulate-drafts 100
```

Spot-check a few opening packs visually, then look at the aggregate
distribution across 100 packs. If a category is severely under-represented
or the color distribution feels off, return to Step 7.

### Step 9: Finalize / Export

```bash
export-cube <new-cube.json> --format csv --output <wd>/<cube-id>-updated.csv
```

Hand the CSV to the user with instructions to use CubeCobra's **"Replace
with CSV Import"** function to push the changes back upstream.

---

## Cube vs Deck Differences

Some deck-wizard tools apply to cubes and some don't:

**Apply as-is** (share the same `cards[]` shape):
- `card-search`, `scryfall-lookup`, `download-bulk`, `price-check`
- `combo-search` — genuinely useful for finding accidental infinites
- `card-summary`, `mark-owned`, `web-fetch`

**Don't apply** (deck-specific assumptions):
- `mana-audit` — expects a 60-card or 100-card deck
- `legality-audit` — expects format deck-construction rules
- `parse-deck` — use `parse-cube` instead
- `cut-check` — designed for commander combo/synergy detection in a deck
- `build-deck`, `deck-stats`, `deck-diff` — cube versions exist
- `export-deck` — use `export-cube`
- `set-commander`, `find-commanders`, `edhrec-lookup`, `mtga-import` —
  not relevant for cubes

---

## References

Philosophy articles worth WebFetching during Step 2 (designer intent) or
Step 6 (self-grill). Lucky Paper has no API; the agent should fetch on
demand when the conversation touches a design question the article
addresses.

- [Lucky Paper: The First Four Questions Cube Designers Should Ask](https://luckypaper.co/articles/the-first-four-questions-cube-designers-should-ask/)
- [Lucky Paper: Cube Synergy — A User's Guide](https://luckypaper.co/articles/cube-synergy-a-users-guide/)
- [Lucky Paper: Removal vs. Synergies in Cube](https://luckypaper.co/articles/removal-vs-synergies-in-cube/)
- [Lucky Paper: Cube Power Level](https://luckypaper.co/articles/cube-power-level-a-users-guide/)
- [Lucky Paper: An Ode to Scaleable Threats](https://luckypaper.co/articles/an-ode-to-scaleable-threats/)
- [Lucky Paper: How Many Lands Should You Include in Your Cube](https://luckypaper.co/articles/how-many-lands-should-you-include-in-your-cube/)
- [Lucky Paper: Cube FAQ](https://luckypaper.co/articles/frequently-asked-questions-about-cube/)
- [Caleb Gannon: Everything I Have Learned About Cube Design](https://calebgannon.com/2022/04/25/everything-i-have-learned-about-cube-design/)
- [CubeCobra](https://cubecobra.com/)

---

## Attribution

Cube-specific logic (draft category classifier, pack templates for sizes
9/11/15) is ported from
[dan-blanchard/cube-utils](https://github.com/dan-blanchard/cube-utils)
(MIT-licensed, used with attribution).
