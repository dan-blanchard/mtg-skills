---
name: rules-lawyer
description: Answer MTG rules questions by citing the Comprehensive Rules and Scryfall per-card rulings. Resolves keyword interactions, trigger timing, replacement-effect layer issues, and other card-rules questions with authoritative citations.
compatibility: Requires Python 3.12+ and uv. Shares mtg_utils package via symlink.
license: 0BSD
---

# Rules Lawyer

Answer Magic: The Gathering rules questions by citing the actual
Comprehensive Rules (CR) and Scryfall per-card rulings. Usable
standalone ("does prowess trigger off my own spells?") or invoked by
deck-wizard / cube-wizard via the Skill tool whenever they hit a
trigger-interaction or timing question during deck tuning.

Think of this as the project's legal research department: the CR is
statute, the Scryfall rulings are case law. Always quote chapter and
verse — never paraphrase from memory.

## The Iron Rule

**NEVER answer a rules question from training data.** Every answer
MUST cite at least one specific CR rule number (e.g., "702.19a") with
the rule text the CLI returned. If the agent is uncertain or the CLI
returns no match, say so and escalate (Phase 3) rather than making
something up. A confident hallucinated rule number is worse than an
honest "I couldn't find a matching rule — here's the closest neighbor."

## Setup (First Run)

```bash
uv sync --directory <skill-install-dir>
download-rules --output-dir <working-dir>
download-bulk --output-dir <working-dir>       # only if rulings-lookup needed
```

`download-rules` fetches the current MTG Comprehensive Rules TXT with
a 24-hour freshness check (matches the `download-bulk` convention).
The CR landing page is scraped for the newest `MagicCompRules*.txt`
download link and saved as
`<working-dir>/comprehensive-rules-YYYYMMDD.txt`.

## Workflow

### Phase 1: Classify the Question

Before running any CLI, decide what kind of rules question this is.
The query mode maps 1:1 to a `rules-lookup` flag.

| Question shape | CLI |
|---|---|
| "What does rule 702.19a say?" | `rules-lookup --rule 702.19a` |
| "What's the rule for trample?" / "Define 'library'." | `rules-lookup --term trample` |
| "Which rules mention 'combat damage step'?" | `rules-lookup --grep "combat damage step"` |
| "How does *Card Name* interact with X?" | `rulings-lookup --card "Card Name"` + follow up with CR lookups |
| "Given this deck, are there any stack/layer issues with Y?" | Use deck-wizard's `cut-check --cite-rules`, then cross-check with `rules-lookup` |

**Keyword → term mapping.** Most CR keywords (trample, deathtouch,
double strike, menace, flash, haste, hexproof, indestructible, etc.)
map to a glossary entry whose `see_rules` field points to the
authoritative rule. Prefer `--term` for these: you get both the
glossary definition AND the rule number in one round-trip.

### Phase 2: Look Up

Run exactly one `rules-lookup` invocation for the classified question.
The CLI writes a JSON sidecar and prints a human-readable summary. If
the summary answers the question, stop — don't escalate for its own
sake.

```bash
# Exact rule number
rules-lookup --rule 702.19a --rules-file <wd>/comprehensive-rules-*.txt

# Glossary term (preferred for keyword questions)
rules-lookup --term "deathtouch" --rules-file <wd>/comprehensive-rules-*.txt

# Regex search — use a narrow pattern or you'll get noise
rules-lookup --grep "can't be blocked by more than" --rules-file <wd>/comprehensive-rules-*.txt --limit 5
```

For per-card questions, prefer rulings first, then resolve the cited
rules:

```bash
rulings-lookup --card "Sensei's Divining Top" --bulk-data <wd>/default-cards.json
# Then for any CR rule referenced in a ruling:
rules-lookup --rule 116.1  --rules-file <wd>/comprehensive-rules-*.txt
```

### Phase 3: Escalate (only when needed)

If `rules-lookup` returns no match or the match is clearly wrong for
the question, do ONE of:

1. **Widen the search.** Try a `--term` lookup with a synonym, or a
   broader `--grep` pattern. The CR glossary is large (~670 terms in
   the 2024 CR) — a missed term usually means a bad query.
2. **Read a section slice.** For complex multi-rule reasoning (layer
   interactions, replacement effects applying simultaneously, stack
   ordering across triggered and activated abilities), `Read` the
   relevant section directly from the downloaded TXT:
   - `500-series`: turn structure
   - `600-series`: spells, abilities, effects (including stack)
   - `700-series`: additional rules, keyword abilities/actions
   - `800-series`: multiplayer
   Use `Read <comprehensive-rules-*.txt> offset=<line> limit=<n>` to
   pull only the relevant band.
3. **Spawn a subagent.** For a question that needs reasoning across
   multiple sections (e.g., "how do layers interact with a static
   ability that's turned off by a replacement effect"), `Agent` a
   specialist with the relevant section text preloaded. Prompt the
   subagent to return a rule-cited answer, not a paraphrase.

### Phase 4: Write the Answer

Every answer has three required parts:

1. **The verdict.** One sentence: what happens / what the ruling is.
2. **The citations.** Each cited rule number MUST come from the CLI
   output, not from memory. Include the verbatim rule text the CLI
   returned (trim to the directly-relevant sentence).
3. **The edge cases.** If the ruling hinges on a condition ("only if
   the source has deathtouch", "only during your upkeep"), name that
   condition explicitly. If there's a well-known trap the question
   sounds like but ISN'T asking about, note it briefly.

**Example answer shape:**

> **Verdict.** Yes — a creature with both trample and deathtouch
> only needs to assign 1 damage per blocker to consider it "lethal,"
> then trample over the rest.
>
> **CR 702.19b:** "…the attacking creature's controller need not
> assign lethal damage to all those blocking creatures but in any
> case may not assign combat damage to a player or planeswalker or
> battle unless every blocking creature is assigned at least lethal
> damage."
>
> **CR 702.2b:** "A creature with toughness greater than 0 that's
> been dealt damage by a source with deathtouch since the last time
> state-based actions were checked is destroyed as a state-based
> action."
>
> **Edge case.** This requires the source to have deathtouch at the
> moment damage is assigned; removing deathtouch mid-combat
> (e.g., via protection or static abilities in the
> continuous-effects layer 6) kills the interaction. See CR 613 for
> layers.

## Decision Table

| Task | Tool |
|------|------|
| Look up a rule by number | `rules-lookup --rule <n>` |
| Look up a keyword / defined term | `rules-lookup --term <name>` |
| Search for rules mentioning a phrase | `rules-lookup --grep "<regex>"` |
| Per-card rulings (Scryfall "case law") | `rulings-lookup --card "<name>" --bulk-data <path>` |
| Batch rulings for a deck | `rulings-lookup --batch <deck.json> --bulk-data <path>` |
| Download/refresh CR locally | `download-rules --output-dir <wd>` |
| Download Scryfall bulk data | `download-bulk --output-dir <wd>` |
| Resolve card name → oracle text | `scryfall-lookup "<name>" --bulk-data <path>` |

All CLIs emit a human-readable summary to stdout plus a full JSON
sidecar at an absolute path (prefix `rules-lookup-`, `rulings-lookup-`,
etc.). Read the sidecar with `Read` when you need fields the summary
elided.

## Delegation: When Other Skills Should Invoke This

deck-wizard's `cut-check` and `legality-audit` accept a `--cite-rules`
flag. When that's set, they call `rules-lookup --term <keyword>` for
any flagged keyword interaction and attach CR citations to the JSON
output. That flag covers the common case; for anything more nuanced
(the agent is unsure why a cut was flagged, or a user asks "why did
the auditor complain?"), invoke this skill.

## Scratch File Paths

Reuse these stable paths within a session:
`/tmp/rules-scratch.json`, `/tmp/rulings-scratch.json`.

`/tmp` files persist across sessions. At session start, `Read` each
scratch path you plan to reuse before the first `Write`, OR run
`Write` sequentially and verify success before the dependent `Bash`
call.

## Path Requirements

- **Absolute paths only.** `uv` rebases the working directory to the
  skill install; relative paths resolve against the wrong root.
- **Rules file:** Store under the calling skill's working directory
  (e.g., `<wd>/comprehensive-rules-20260227.txt`), NOT the skill
  install directory.
- **Cache directory for rulings:** `$TMPDIR/scryfall-rulings/` is
  used automatically; callers don't need to manage it.
