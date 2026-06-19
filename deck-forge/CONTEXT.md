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

### Collection & ownership

**Medium** (paper / digital):
Whether a build is played on paper or digitally (Arena). Per-build state on the
`DeckSession`; commander is always paper, Brawl / Historic Brawl default to digital. The
**medium** — not the format — decides the active Collection slot (digital → arena, paper →
paper) and the cost mode (digital → wildcards, paper → USD). This is the amendment to
ADR-0018, whose first cut keyed the slot off format via `paper_only`.
_Avoid_: "format" as a synonym (a paper and a digital Historic Brawl share one format but
differ in medium), "Arena" as the only digital sense (it's the digital medium here).

**Collection**:
The user's owned cards as a name→quantity pile (the `parse_deck` pile shape, same as a
deck) — *what you own*, distinct from a deck (*what you're building*). Global to the hub,
not per-build: it lives on `ForgeState`, persisted in one `collection.json`, auto-loaded
on launch. Held in **two slots**, `paper` and `arena`, because the two real libraries are
distinct; the active slot is auto-picked by the build's **Medium** (digital → arena,
paper → paper), not by format. Reads are strictly single-slot — a paper deck
never consults the Arena slot — and an empty active slot surfaces an import prompt, never
a silent "owns nothing."
_Avoid_: "deck" (a Collection is owned cards, not a build), "owned_cards" (that's the
CLI's stored field — see Owned), "library" alone (collides with the MTG in-game zone).

**Owned**:
A deck card's derived ownership: it intersects the active Collection slot (matched with
`mark_owned`'s DFC / Arena-alias logic), surfaced as a per-card flag in `deck_view` plus
a deck-level "N of M owned" readout. DERIVED fresh on every snapshot from the live deck ×
the global Collection — never the stored `owned_cards` field `mark_owned` writes into a
deck JSON, which would go stale the moment the deck mutates.
_Avoid_: "owned_cards" (the stored CLI field this deliberately replaces with a live
derivation), "have / missing" (reserve those for a future buy-list framing).

**Commander discovery**:
The browser panel that surfaces commander-eligible cards from your active Collection slot,
ranked to a *stated intent* rather than to popularity — a theme filter (a `theme_presets`
lane) and a color filter narrow the owned pool, and the sort is **Support depth** or
**Novelty**. Deterministic and EDHREC-free (ADR-0009): it never orders by community
popularity. The browser-native realization of deck-wizard's "Commander Selection from a
Collection" — intent controls in place of a chat interview.
_Avoid_: "best commanders" (there is no context-free best — ranking is always to a stated
intent), "recommendation" (the human picks; see [[Candidate]]).

**Support depth**:
How much of a commander's strategy you already own — the breadth-down-weighted count of
in-identity cards in your active Collection slot that serve the commander's signal-derived
lanes. The default Commander-discovery sort. Deliberately NOT raw signal/lane count:
*lane breadth is not quality* — owning the pieces is — so a near-universal lane
("creatures matter") is down-weighted and the generic Staples lane is excluded (owning
good-stuff isn't commander-specific support).
_Avoid_: "signal richness" / "lane count" (the rejected breadth-as-quality proxy),
"owned count" alone (it's lane-weighted, not a flat tally).

**Novelty** (unusual-ability sort):
The Commander-discovery sort that ranks owned commanders by **signal rarity** — the inverse
frequency of their signals across the whole legal commander pool — so an off-beat hook
outranks tokens / counters / ramp. Hard-gated by Support depth: only the *buildable* weird
ones surface. Blind by construction to commanders whose ability is so singular no detector
fires (they emit no signals, so score zero) — the accepted limit of any signal-based
novelty.
_Avoid_: "best" / "strongest" (novelty is strangeness, not power), "random".

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

**Color widening** (the partner sort):
The *primary* ranking axis for the Partner / Background avenue: the count of NEW colors a
candidate second commander adds to the deck's current identity (`partner.color_identity −
deck identity`). A second commander is the only card that can change color identity, so
widening exists only here. The partner sort is strict-tiered — widening first, then
[[Candidate]] synergy fit, then price/cmc — so the broadest color-openers surface first
and synergy merely orders them *within* a widening tier (a high-widen / low-synergy
partner outranks a low-widen / high-synergy one, deliberately). It counts *colors*, is
unbounded (a five-color opener tops a two-color one), and never measures "synergy
unlocked."
_Avoid_: "synergy widening" (it counts colors, not unlocked cards — that alternative was
weighed and dropped), "color fixing" (a manabase concern, unrelated).

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

**Folded object**:
A persistent game-object a commander's *own* abilities deterministically bring into its
core strategy — the dungeon it ventures into (a *Ventured dungeon*), the emblem from its
ultimate, the Ring it bears, the creature it melds into (a meld *result*) — whose
rules-text effects are part of the commander's Signals even though they aren't (always)
printed on the commander itself. The unifying idea: a
commander's effective oracle extends to the objects it reliably creates or enters. Where
the object's text is *quoted in the commander's oracle* (an emblem) it is already read;
where it lives on a *separate object* (a dungeon, the Ring) it must be joined in. The
card-backed separate objects are discovered through Scryfall's `all_parts` (the same link
that finds a card's tokens), so the join is structured rather than prose-scraped. Gated to
objects the commander's text brings in as its plan (not one-off references) that carry
their own rules text.
_Avoid_: treating these as flavor or as out-of-scope "deck context" — they are mechanically
the commander's plan (Acererak's *Tomb of Annihilation* bleed is why its decks run lifegain).

**Ventured dungeon** (a *Folded object*):
The specific dungeon a commander deterministically enters, whose room oracle is read as
an additional source of that commander's Signals — because the dungeon's effects are
mechanically part of the commander's strategy even though they print on a separate card.
*Tomb of Annihilation*'s rooms ("Each player loses 1 life", "…loses 2 life unless they
sacrifice…") make *Acererak the Archlich* a self-bleed + sacrifice commander, which is
why its decks run lifegain sustain (Demon's Horn) — a synergy invisible from Acererak's
own text. The candidate dungeons are found in `all_parts` (which lists *all three* D&D
dungeons for any venture card, so it can't disambiguate alone); the *specific* dungeon to
fold is the one the commander's oracle names (Acererak → Tomb of Annihilation, whose ETB
only stops bouncing him once ToA is completed) or that a rule fixes (the Initiative →
Undercity). A generic "venture into the dungeon" names nothing — the player chooses — so no
specific dungeon is folded; broad venture support covers it (picking one would need
popularity, which the gate forbids).
_Avoid_: "dungeon matters" (the contentless, generic version this replaces — the point is
the *specific* dungeon's rooms, not dungeons in the abstract).

**Payoff avenue** vs **Source avenue** (the two halves of a mechanic):
A `<mechanic>_matters` signal is a *payoff/enabler* fact ("this deck wants to suit up" —
the commander, the equip-cost reducer, the extra-combat). A **Source avenue** is the
separate lane of cards that *are or produce* the thing the payoff wants (the Auras &
Equipment to suit up). Both are real, focusable [[Exploration avenue]]s; the Source
avenue is a [[SubAvenue]] of the payoff signal's spec, so one signal fans out into a
payoff lane + a source lane the human can focus and count independently. The split
exists for *balance visibility* — "I have 6 sources but only 1 payoff" is unreadable
from one fused list. The canonical *fully-realized* instance is the subject-keyed tribal split: a
`type_matters:Goblin` signal already fans into "Goblin tribal" (the bodies = source),
"Goblin payoffs" (lords/anthems), and "Goblin enablers" (type-changers) as three
[[SubAvenue]]s. The 46 fused *non-subject* specs (voltron, artifacts_matter,
spellcast_matters, …) are the ones NOT yet brought into line — each fuses an oracle
payoff pattern with a `serve_types`/`serve_keywords` source into one avenue. The
generalization: derive the payoff avenue from `serve.oracle` and the Source avenue from
`serve.types`/`keywords` (+ the `serve_not` veto), the static-membership analogue of
what `_subject_spec` does for tribes. A small DENYLIST of *modifier* keywords (haste,
indestructible, trample, the evasion set) keeps a property keyword from spawning a
junk "pool" lane. Two source FLAVORS exist and stay distinct: a *membership* source
(you ARE the thing — type/keyword serve, e.g. auras) vs an *effect* source (you MAKE
the thing — a detector signal, e.g. `token_maker`, which is subject-keyed and correctly
its own lane).
_Avoid_: "piece" as a lane name (a Source avenue may *produce* the thing, not just *be*
it — token_maker makes tokens), "the voltron lane" (there are two: payoff + source).

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

**Card IR**:
The per-face structured parse of a card — `Filter` / `Quantity` / `Effect` / `Trigger` /
`Ability` / `Face` / `Card` (`card_ir.py`) — that deck-forge's detection reasons over
instead of re-grepping oracle text. Projected once from phase-rs's parser output by a
deterministic *forge projection* (`_card_ir/project.py`) plus a combinator-parser
*supplement* (`_card_ir/supplement.py`) that fills phase's gaps, then cached to an
`oracle_id`-keyed sidecar. Unlike a regex it binds the *operand* a card scales with
(Craterhoof's "for each creature you control") and the *scope* of an effect (Tinybones
reanimates only from opponents' graveyards), so a [[Signal key]] becomes a derived query
over structure rather than a substring match. The substrate of the regex→IR cutover
(ADR-0027).
_Avoid_: "phase IR" (phase provides the structural substrate; the Card IR is *our*
payoff/scope-shaped projection of it), "the parser" (the projection consumes phase's
parse, it is not itself a card parser).

**parse_confidence**:
The per-card completeness of its [[Card IR]] — `full` when no clause fell through to a
generic "other" category, `partial` otherwise — derived from phase warnings + supplement
coverage. The detection-substrate health metric (~100% `full` over commander-legal cards),
and the value the signal `coverage_gate` reads after the cutover's A4 step (replacing the
regex blind-spot heuristics). Not a per-firing accuracy score: a fully-parsed card can
still feed an over-broad lane, which is a downstream gating concern, not a parse gap.
_Avoid_: "accuracy" (it measures parse completeness, not whether a lane fires correctly),
"coverage" alone (collides with `coverage_gate`'s blind-spot sense).

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

**Import** (bring-in, the mirror of Handoff):
Bringing an external list INTO the hub — a decklist or a Collection — parsed and
populated in-process by the Deterministic core (`parse_deck` / `mark_owned` /
`find_commanders`), no LLM and no API key. The *inbound* mirror of a **Handoff** (which
routes a *finished deck out*); like a run-here handoff it is pure compute the hub runs
itself, never the Session-agent. A **deck import** always mints a NEW build rather than
overwriting the live one — build data is never clobbered — and never guesses a commander
(an unmarked list lands as a pile the user promotes from).
_Avoid_: "handoff" for an import (opposite direction), "load" (reserve that for
reopening a saved build via `BuildStore`), "parse" alone (parsing is one step of
importing).

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

### Deterministic tuning

The vocabulary of the agent-less deck-evaluation pass that scores a deck and proposes
budgeted swaps (the "Tune" surface). Distinct from the [[Session-agent]] reasoning loop:
this is pure [[Deterministic core]] compute, runnable with no session attached. Its unit
of *direction* is the existing [[Exploration avenue]]; this feature coins no new
"theme"/"lane" concept.

**Tune** (the deterministic tuner):
The agent-less, hub-side evaluation-and-swap pass, surfaced as its own left tab. Three layers:
**diagnose** (the [[Shape]] chip + [[Efficiency]] / [[Template deviation]] / [[Focus]] panels +
[[Commander fit]] + a severity-ranked Top-issues list), **cut candidates**, and budgeted
**swaps** (a cut+add pair per top issue; [[Spine]] swaps efficiency-first, [[Engine card]] swaps
synergy-first). Pure [[Deterministic core]] — runs with no [[Session-agent]] attached, so it
works in deterministic-only mode and lives in the always-visible left column, not the
attach-gated rail. Proposes only; the human confirms each swap or "applies all."
_Avoid_: "auto-tune" / "auto-fix" (it never mutates the deck itself — propose-only), "tuner
mode" (that is deck-wizard's *agent-driven* pipeline; Tune is the deterministic subset).

**Spine**:
The mandatory scaffolding every deck needs regardless of [[Shape]]. Two tiers: a
**hard-counted** tier measured against the [[Template]] (lands, ramp, card draw,
interaction, board wipes — counterspells fold into *interaction*, never a separate
role), and a **conditional** tier surfaced as [[Shape]]-scaled advisory flags rather
than fixed counts (win conditions; protection, only when the [[Shape]] calls for it).
Deliberately **exempt from the focus judgment** — a deck is never "spread too thin" for
running its interaction; the Spine's health is template deviation, not focus.
_Avoid_: "core" (overloaded), "staples" (a Spine card need not be a generically-good
staple — see the always-on staples avenue, a different thing), "protection" as a
*counted* role (it is a conditional flag, and counterspells fold into interaction).

**Engine card**:
A nonland deck card whose primary job is to serve one of the deck's signal-derived
[[Exploration avenue]]s — payoffs, enablers, synergy pieces. The ONLY pool the **focus**
metric measures for concentration (the always-on Staples avenue is excluded — good-stuff
is not a theme, the same exclusion [[Support depth]] makes). A [[Spine]] card may *also*
serve an avenue (a dual-purpose "win-win" card); that synergy only ever *adds* to focus,
never subtracts.
_Avoid_: "Engine module" (that is `engine.py`, a code term — unrelated), "Synergy
package" (a surfaced set of suggestions, not a deck card's role), "theme"/"lane" for the
avenue it serves (an [[Exploration avenue]] is the canonical unit; a *theme* is a
`theme_presets` matcher — the plumbing *under* an avenue).

**Filler**:
A nonland deck card that is neither [[Spine]] nor serves any [[Exploration avenue]] — the
"good stuff that does nothing *here*" pile. A high filler share is itself a
spread/efficiency signal, and the first place cut-selection looks.
_Avoid_: "bad card" (filler may be individually strong; it is just unsupported *here*),
"cut" (filler is a *candidate* to cut, not a cut).

**Shape** (the speed/role axis):
The aggro / midrange / control / combo classification of a deck, inferred deterministically
from its composition (curve, creature density, interaction density, combo presence). Scales
the conditional Spine floors (win-cons, protection) and the curve expectations; orthogonal
to the **synergy axis** (its [[Exploration avenue]]s), which drives focus. One deck has
exactly one Shape but many avenues. The same aggro/midrange/control/combo axis cube-wizard
defines as **Shape** — reused here with identical meaning, now *inferred* from a finished
deck rather than declared on a cube.
_Avoid_: "archetype" unqualified (cube-wizard reserves it for stated / gauntlet
archetypes; here the speed axis is Shape, the synergy axis is an [[Exploration avenue]]),
"bracket" (power level, a different axis).

**Efficiency** (curve / tempo health):
A [[Shape]]-aware panel of curve and tempo readouts — avg mana value within the Shape's
band, ramp adequacy for that curve, early-play front-load, and *closing power* (enough
top-end to not durdle, not so much it clogs). A transparent multi-readout (matching
`mana_audit`'s gate style), NOT one opaque score, and deliberately **not a per-card
power/rate judgment** — deck-forge has no card-quality model and won't fake one (ADR-0009).
Distinct from the [[Curve gate]] / `mana_audit`, which own *land* count and color;
Efficiency owns the *nonland* curve.
_Avoid_: "power level" ([[Shape]]/bracket-adjacent, not curve health), "card quality" (the
explicitly-absent per-card rate judgment), "speed" alone.

**Focus** (the anti-"spread too thin" metric):
The concentration of [[Engine card]]s across the deck's signal-derived [[Exploration
avenue]]s (Staples excluded). Lead readout: the deck's *themes* and their depths, scored on
a **tiered floor** — a **main** theme at/above ~20-per-100, a **sub**-theme at/above
~10-per-100 (a sub is genuinely shallower than the main, so it is NOT held to the main's
bar), and an **emerging** theme at/above ~5-per-100 (a real-but-under-supported direction
the deck started but didn't commit to — surfaced as a "commit more or cut" nudge, not
dropped as noise). Plus a top-2 concentration ratio and the filler rate. The research ideal is one main +
one sub; 3+ themes reads `SPREAD-THIN`. Two exclusions keep the count honest: **lands** never
count as theme support (mana base, not a lane), and **Spine-role avenues** (ramp / draw /
removal — they mirror the [[Template]]) are dropped, so scaffolding can't masquerade as the
main lane. Near-duplicate avenues collapse (≥80% shared members) so one theme isn't two.
[[Shape]]-aware: a small-engine-pool control deck reads `SPINE-LED`, never spread-thin — the
[[Spine]] is its plan. Dual-purpose [[Spine]] cards *deepen* a theme (bonus), never penalize.
_Avoid_: "synergy score" (it is concentration, not a quality score), "archetype focus" (the
avenue is the unit, not a cube archetype).

**Template deviation** (the Spine-health metric):
How far the deck's [[Spine]] role counts sit *outside* the [[Template]] bands — 0 within the
band, otherwise the distance to the nearest edge. Computed by the one shared `slot_budgets`,
which takes an optional [[Shape]]: the always-on Budgets panel passes none (flat Command Zone
bands), the Tune surface passes the inferred Shape (scaled — e.g. control wants more
interaction). The hard-counted roles (lands / ramp / draw / interaction / wipes) drive
deviation; the conditional roles (win-cons, protection) surface as [[Shape]]-scaled advisory
flags, not deviation.
_Avoid_: "off-template" as failure (deviation is a nudge, never a gate — the [[Curve gate]]
is the only hard land check), "budget" alone (a slot budget is the *remaining count*; this is
the distance over it).

**Commander fit** (built-deck alignment):
How well the *current* commander's signal-derived avenues align with the deck's dominant
viable [[Exploration avenue]]s — surfaced as a cheap default-diagnostic flag ("serves 1 of
your 3 viable avenues → maybe built for a different commander"). Its opt-in companion ranks
*alternative* commanders to the deck you already built ([[Commander discovery]] scored against
the deck instead of a stated intent), each shown with its **identity cost**: the in-deck cards
that fall out of color identity on the switch. The one tuning fix card swaps structurally
cannot make.
_Avoid_: "best commander" (it is fit-to-*this*-deck, not context-free best — same caveat as
[[Commander discovery]]), "recommendation" (the human switches; the tool ranks).
