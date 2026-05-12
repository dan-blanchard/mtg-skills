# deck-strat Context

The bounded context for producing **Strategy Guides** — markdown
documents that explain how to pilot a finished MTG deck. Read-only
on the deck: deck-strat does not propose cuts, adds, or tuning
changes. For tuning, run `/deck-wizard` first; `/deck-strat` consumes
the finished list.

Scope: Commander, Brawl, and Historic Brawl. 60-card constructed
formats are out of scope in v1 — sideboard plans and matchup tables
are a different artifact shape and `/deck-wizard` already produces a
sideboard guide in its Step 12 finalize.

## Language

### Output artifact

**Strategy Guide**:
A markdown document at `<working-dir>/STRATEGY-GUIDE.md` that
explains how to pilot a specific deck. Has a fixed structure (the
core spine) plus archetype-conditional sections. One file per
working dir, edited in place when the user requests revisions.
_Avoid_: "deck guide" (ambiguous with build guides), "playbook"
(sounds prescriptive — a strategy guide describes lines and trade-
offs, it doesn't dictate plays).

**Core spine**:
The always-present sections of a Strategy Guide: identity, core
loop, win conditions, mulligan guide, turn-by-turn pacing, threat
assessment, common lines + stack tricks, deck quirks, cheat sheet,
appendix. Every deck-strat output has these. The order is fixed
so guides are scannable across the user's decks.
_Avoid_: "default sections" (sounds optional; the spine is
mandatory).

**Conditional section**:
A Strategy Guide section that's rendered only when a specific
signal is detected during Phase 2 analysis. Examples: a "politics
scripts" section only renders if the deck has goad/incite cards
(Karazikar, Disrupt Decorum, etc.); a "voltron commander damage"
section only renders if the commander is a voltron-style finisher;
a "combo execution" section only renders if `combo-search` returned
a game-winning combo. Each conditional section names its trigger
signal — when re-running the skill on a tuned deck, the same
signal must fire for the section to re-appear.
_Avoid_: "optional section" (sounds user-toggled — the trigger is
mechanical, not preference-driven).

### Analysis concepts

**Core loop**:
The 3-5 sentence summary of how the deck wins. Every Strategy
Guide leads with this. Derived from the commander interaction
audit + archetype detection. Distinct from "win condition" (which
is the terminal event) — the core loop is the *path* to the
terminal event.
_Avoid_: "game plan" (too generic), "strategy" (overloaded — the
guide *is* the strategy).

**Role grouping**:
The act of clustering each card in the deck by its commander-
relative role: engine piece / ramp / drain payoff / sac outlet /
token producer / removal / political tool / wincon / protection.
A card's role is defined by how it interacts with THIS commander,
not by its generic category. A vanilla 1/1 is "creature" generically
but might be "drain enabler" with Blood Artist out.
_Avoid_: "category" (the generic word; role grouping is
commander-aware).

**Commander Interaction Audit**:
Phase 2 Step 4. Systematically checks for keyword combinations,
trigger multiplication (extra combats / extra triggers / token
doubling), feedback loops (where a card's output feeds its own
input), self-recurring cards, and commander multiplication
(Helm of the Host, Spark Double, Strionic Resonator, etc.).
Inherited verbatim from deck-wizard's Step 5 — same dimensions,
same discipline, but applied to authoring a guide rather than
gating cuts.
_Avoid_: "synergy check" (generic; the audit has six specific
named dimensions).

**Rules verification pass**:
Phase 3 Step 8. For every rules-adjacent claim that will go into
the guide (stack timing, replacement effects, commander-zone
behavior, keyword interactions, intervening-if clauses), look up
the relevant CR rule via `rules-lookup` and quote it. Routine
lookups use the CLI; multi-rule nuance escalates to the
`rules-lawyer` skill via Skill-tool invocation. See ADR-0008 for
the integration model.
_Avoid_: "fact check" (sounds journalistic; this is rule citation
discipline).

**Rules Audit**:
Phase 3 Step 10. A general-purpose subagent dispatched in parallel
with the draft. Charter: read the draft Strategy Guide, verify
every rules-adjacent claim against the CR and against the actual
card oracle text, return a list of errors / unsupported claims /
under-citations. Parent revises before presenting. Distinct from
deck-wizard's Step 8 self-grill (two-agent debate) — deck-strat
only needs the single rules-focused audit because it makes no
tuning decisions.
_Avoid_: "review pass" (could mean either rules or strategic
review; "Rules Audit" pins it to rules).

### Bracket adaptation

**Pilot bracket**:
The power bracket the user intends to pilot the deck at, asked up
front during Phase 1 acquisition (or auto-detected from Game
Changer count + infinite combo presence + curve). Distinct from
"deck bracket" — a deck built to Bracket 3 specs may be piloted at
a Bracket 2 table; the guide adapts to what the user will actually
encounter. Influences threat assessment, turn-by-turn pacing,
combo-section prominence, and politics weight.
_Avoid_: "power level" (ambiguous; bracket is the WotC-formal
1-5 scale).

## Cross-context relationships

- **deck-strat → deck-wizard**: Composes sequentially. User runs
  `/deck-wizard` to build/tune, then `/deck-strat` on the finished
  deck. No nested skill invocation; both share the working dir
  and the SHA-keyed hydrated cache, so deck-strat reuses
  deck-wizard's parse + hydrate output transparently.
- **deck-strat → rules-lawyer**: Hybrid (see ADR-0008). deck-strat
  re-declares `rules-lookup` / `rulings-lookup` / `download-rules`
  in its `pyproject.toml` for routine claim verification (Phase 3
  Step 8). For multi-rule timing / layer / stack questions during
  drafting, deck-strat invokes the `rules-lawyer` skill via the
  Skill tool. Same hybrid pattern cube-wizard uses.
- **deck-strat ↔ mtg-utils**: Symlinked `src/`, re-declared CLIs.
  Same shared-package model as every other skill.

## Tuning pipeline shape

Three phases, 10-11 steps:

1. **Phase 1 Acquisition** — parse, set commander, hydrate.
2. **Phase 2 Analysis** — baseline diagnostics, commander
   interaction audit, archetype detection, combo detection,
   EDHREC research.
3. **Phase 3 Authoring** — rules verification, draft, Rules Audit
   subagent, present + iterate.

See SKILL.md for the full step list, tool invocations, and
templates.
