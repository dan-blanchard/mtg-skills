# deck-forge Context

The bounded context for collaborative, visual MTG deckbuilding: a human and an
expert assistant build a deck together in a browser, with the assistant surfacing
synergies, directions, and ranked candidates while the human makes every decision.

## Language

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

**Candidate**:
A specific real card surfaced to fill a need, carrying a "why it fits" note and an
honest cost. Every Candidate is a real Scryfall card the deterministic core found —
never named from the assistant's memory.
_Avoid_: "recommendation" (implies the tool decides; the human chooses),
"pick" (that's the human's act of selecting a Candidate).

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

### Gates & accuracy

**Curve gate**:
The hard land-count check (Burgess/Karsten for commander, constructed formula for
60-card). Below the floor the deck holds a persistent FAIL that blocks marking the
deck *finished* until an explicit override — distinct from soft Template nudges.
_Avoid_: "land warning" (understates that it gates finalize).

**No-listing card**:
A card for which neither bulk data nor the live price API returns a price. Treated
as *likely scarce/expensive*, never as free ($0). A deliberate domain term to stop
the "missing price = $0" mistake.
_Avoid_: "free card", "$0 card", "priceless".
