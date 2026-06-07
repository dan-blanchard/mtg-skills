# deck-forge Context

The bounded context for collaborative, visual MTG deckbuilding: a human and an
expert assistant build a deck together in a browser, with the assistant surfacing
synergies, directions, and ranked candidates while the human makes every decision.

## Language

### Deck values

**HydratedDeck**:
A single immutable value that owns the join of a deck's card names to their Scryfall
records — the deck dict and its resolved records behind one interface, built once from
a deck plus a name→record index. A desynced deck/records pair is unconstructable, so
the analysis functions (`deck_stats`, `mana_audit`, `legality_audit`, …) take a
`HydratedDeck` rather than a separate `(deck, hydrated)` pair. Deck-domain only; a cube
is a different shape (see ADR-0012).
_Avoid_: "hydrated list" (the bare records list it replaces), "(deck, hydrated) pair"
(the shallow shape it supersedes).

**DROP convention**:
The single rule for an un-hydratable card name: it is simply absent from a
HydratedDeck's `.records` / `.expanded()`, never represented as `None`. Callers never
choose drop-vs-pad — the value enforces DROP, and the one place a miss surfaces is
`.by_name.get(name)` returning `None`.
_Avoid_: "None-pad" (the retired outlier convention), "skip" (ambiguous).

**Degraded mode**:
The state where a deck has cards but no Scryfall records could be joined (no bulk data
on disk). Exposed as the typed `HydratedDeck.has_records` flag (False only here) —
distinct from an empty deck, and the queryable successor to the old `check_hydration`
warning.
_Avoid_: "empty deck" (an empty deck is not degraded), "no-bulk" alone (the cause, not
the state).

### Engine concepts

**Signal**:
A precisely-scoped fact extracted from one card's oracle text — a trigger
condition ("a creature you control enters"), a payoff, a type-matters hook, or a
cost-reducer. Scope is part of the Signal's identity: *Tinybones, the Pickpocket*
yields the Signal "cast/steal from an **opponent's** graveyard," NOT "graveyard
matters." Signals are the atoms the discovery engine reasons over.
_Avoid_: "theme" (a Signal is narrower and clause-scoped), "trigger" alone
(ignores payoffs / static hooks), "keyword".

**Synergy package**:
The primary output unit the UI is built around — a set of real cards that amplify
a shared Signal, carrying code-found enablers/payoffs and a written rationale for
how each card connects. A package is a *direction made concrete in cards*.
_Avoid_: "combo" (reserve that for closed game-winning loops — see below), "pile",
"list".

**Combo**:
A closed interaction between cards that produces unbounded value or wins the game
(Commander Spellbook's domain). Combos are a *secondary* layer in deck-forge, shown
as a "go infinite?" option, distinct from the headline Synergy packages.
_Avoid_: using "combo" for ordinary synergies (the most common drift; a Synergy
package is not a Combo).

**Exploration avenue**:
A *direction* the assistant offers to pursue — "lean Voltron vs. tokens," "look at
ramp now?" An avenue is a branch in the build, never a specific card.
_Avoid_: "suggestion" (overloaded — covers cards too), "option".

**Focused avenue**:
An Avenue the human has *pinned* to declare it a lane they're actually building
toward (vs. one that merely happens to occur in a card already in the deck). The
focused set is the basis for a Candidate's synergy fit: when ≥1 avenue is focused,
`synergy_fit` counts only focused avenues, so the ✦ number reads "serves N of your M
focused lanes." The empty focus set is the default and means *everything counts* —
today's behavior — so focusing is purely opt-in narrowing.
_Avoid_: "selected avenue" (reserve "select" for the multi-pick of packages), "active
avenue" (active = present/derived, not curated), "tracked".

**Candidate**:
A specific real card surfaced to fill a need, carrying a "why it fits" note and an
honest cost. Every Candidate is a real Scryfall card the deterministic core found —
never named from the assistant's memory.
_Avoid_: "recommendation" (implies the tool decides; the human chooses),
"pick" (that's the human's act of selecting a Candidate).

**Find surface** (the unified Search ⊕ Synergies tab):
The single card-finding surface that replaces the separate Search and Synergies tabs.
Focusing one or more Avenues OR-combines their `serve` specs into the search filters
(oracle/type unioned, color identity unioned), runs one search, and returns a single
flat ✦-ranked list — there is no per-package grouped presentation. "Discover all"
serendipity is recovered by the Avenues panel itself (focus-all → sort by ✦). See
ADR-0015.
_Avoid_: "Synergies tab"/"Packages tab" (both dissolved into this), "search results"
alone (undersells that focused avenues drive it).

**Slot** / **slot budget**:
A *role* the deck needs filled (ramp, draw, removal, win condition, interaction, or
a mana-curve bucket) and its remaining count measured against the active Template.
A "choose up to N" prompt is sized to a Slot's remaining budget.
_Avoid_: "category" (used for color/type classification elsewhere), "quota".

**Template**:
The role-count guideline for a format (e.g. the Command Zone Commander template)
used as a *soft* target for Slot budgets — a starting point, not a rule. Distinct
from the mana-curve / land-count **gate**, which is hard.
_Avoid_: "rule", "requirement" (Templates never block).

### Signal plumbing

**Signal key**:
The canonical id of a Signal (e.g. `coin_flip`, `token_maker`) — the contract between
the detector (`signals.py`, which emits it) and the exploitation map (`signal_specs.py`,
which maps it to an avenue). Cross-file keys live as constants in `signal_keys.py`.
_Avoid_: "signal name", "signal type".

**Silent orphan** (silent no-avenue):
A Signal key a detector produces but no spec resolves — historically a *silent* failure
(extraction worked, `spec_for` returned `None`, the avenue was just dropped). The
key-agreement gate turns it into a loud import-time error.
_Avoid_: "missing spec" alone (understates that it failed silently).

**Key-agreement gate**:
The import-time assertion in `signal_specs.py` that every producible static key resolves
to a spec, derived from `signals.producible_static_keys()` (a union of the producer
tables, so it can't lag). The successor to a hand-typed coverage list.
_Avoid_: "validation", "check" (too generic).

### Roles & surfaces

**Session-agent** (a.k.a. the reasoning layer):
The interactive Claude Code session that supplies the judgment the deterministic
core cannot — scoping Signals, proposing novel Synergy patterns, writing "why it
fits," judging rules interactions, curating the next avenue. The human-in-the-loop
brain; runs on interactive subscription billing.
_Avoid_: "the AI"/"the bot" (vague), "BYO-key provider" (a deferred
non-subscription fallback, not the primary path).

**Deterministic core**:
The agent-less Python layer (wraps `mtg-utils`) that does card search, curve/mana
audit, combo lookup, and pricing. Always available; it is the source of every real
card the Session-agent grounds its patterns against.
_Avoid_: "the backend logic" (the core is one part of the backend).

**Backend hub**:
The local process that owns canonical session state, hosts the Deterministic core,
serves the browser surface, and is the message bus between the browser and the
Session-agent.
_Avoid_: "the server" alone (ambiguous about the hub role).

**Handoff** (run-here vs session):
A one-click route from a finished deck into another repo tool, split by the billing
boundary. A **run-here handoff** (goldfish, proxies) is *pure local compute* — a
`mtg_utils` function the hub already imports, run in-process with no LLM/API key — so
its result renders in the browser even with no session attached. A **session handoff**
(strategy guide via `deck-strat`, store-sourcing via `lgs-search`) needs reasoning or a
headed browser, so it can only be routed to the attached Session-agent over the agent
bridge and greys out when detached. The boundary is load-bearing: the hub may execute
pure-compute tools but must never run a reasoning/browser skill itself (ADR-0010, ADR-0016).
_Avoid_: "handoff" as if all four behave alike (the two tiers are not interchangeable),
"the hub runs the skill" (it runs pure-compute tools; skills go to the session).

**Engine module** (`engine.py`):
The deck-analysis surface inside the hub — snapshot, ranked Signals, Avenues, finalize
report, partner search — as free functions over a `ForgeState`. Free functions, not a
class, so they read state at call time and can't desync from the mutable session; the
interface is the direct test surface (no HTTP round-trip).
_Avoid_: "the backend logic" (the engine is the analysis part only).

**Views module** (`views.py`) / **wire card shape**:
The serialization seam owning the card shapes the browser SPA consumes — one atomic
`project` plus the deck / search / candidate / combo variants. Centralized so the
frontend contract has one module to diff against.
_Avoid_: "serializer" alone, "DTO".

**Transport adapter**:
The FastAPI route closures in `app.py`: parse payload → call Engine/Views → apply side
effects (mutation, autosave, SSE publish) → return. Holds no deck logic.
_Avoid_: "the API", "the route layer" (those undersell that it's deliberately thin).

### Gates & accuracy

**Curve gate**:
The hard land-count check (Burgess/Karsten for commander, constructed formula for
60-card). Below the floor the deck holds a persistent FAIL that blocks marking the
deck *finished* until an explicit override — distinct from soft Template nudges.
_Avoid_: "land warning" (understates that it gates finalize).

**Flood line**:
The *upper* land-count band: `recommended_land_count + 2` (i.e. `max(burgess, karsten)
+ 2`). Above it the deck is over-landed and the Mana Gate surfaces a **soft** FLOOD
nudge plus a "Trim lands (−N)" action that removes basics (most over-produced color
first) down to `recommended`. Deliberately **soft — it never blocks finalize** —
because an all-lands two/three-card combo deck (mostly lands plus a few pieces) is a
legitimate build, the mirror-image asymmetry of the hard floor (too few lands can
brick a deck; too many is only a quality nudge).
_Avoid_: "land ceiling" as a *hard* cap (it never gates), "Karsten ceiling" (the raw
Karsten number can dip below the Burgess floor, so the band hangs off `recommended`,
not Karsten alone).

**No-listing card**:
A card for which neither bulk data nor the live price API returns a price. Treated
as *likely scarce/expensive*, never as free ($0). A deliberate domain term to stop
the "missing price = $0" mistake.
_Avoid_: "free card", "$0 card", "priceless".
