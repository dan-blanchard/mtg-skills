# deck-forge Context

The bounded context for collaborative, visual MTG deckbuilding: a human and an expert assistant build a deck together in a browser, with the assistant surfacing synergies, directions, and ranked candidates while the human makes every decision.

## Language

### Deck values

**HydratedDeck**:
A single immutable value joining a deck's card names to their Scryfall records — built once from a deck plus a name→record index, so a desynced deck/records pair can't exist. Analysis functions (`deck_stats`, `mana_audit`, `legality_audit`, …) take a `HydratedDeck` rather than a separate `(deck, hydrated)` pair. An un-hydratable card name is simply absent from `.records` / `.expanded()` (DROP), never represented as `None` — callers never choose drop-vs-pad. `has_records` is `False` only in **degraded mode**: cards exist but no Scryfall records could be joined (no bulk data on disk), distinct from an empty deck.

### Collection & ownership

**Medium** (paper / digital):
Whether a build is played on paper or digitally (Arena). Per-build state on the `DeckSession`; commander is always paper, Brawl / Historic Brawl default to digital. The medium — not the format — decides the active Collection slot and the cost mode (digital → wildcards, paper → USD).

**Collection**:
The user's owned cards as a name→quantity pile — what you own, distinct from a deck (what you're building). Global to the hub, persisted in one `collection.json`. Held in two slots, `paper` and `arena`; the active slot is picked by **Medium**, not format. Reads are strictly single-slot.

**Owned**:
A deck card's derived ownership: intersects the active Collection slot, surfaced as a per-card flag plus a deck-level "N of M owned" readout. Derived fresh on every snapshot — never the stored `owned_cards` field `mark_owned` writes into a deck JSON, which would go stale the moment the deck mutates.

**Printing ownership**:
The optional per-(set, collector_number) layer under a Collection entry — nonfoil/foil quantities per printing. Surfaced as owned-first sorting in the printing picker and as a tri-state `owned_printing` on deck cards: `true` = you own the shown printing, `false` = you own the card in a different printing, absent = no printing detail for that name.

**Companion zone**:
The fourth deck zone (`companion`, alongside commanders / cards / sideboard) holding at most one card with the companion ability (CR 103.2b). Excluded from deck-size math, slot budgets, curve/mana math, and the tuner's totals — but its deckbuilding condition IS audited against the starting deck including the commander (CR 702.139b, via `mtg_utils.companion`), and the card must still be format-legal.

**Commander discovery**:
The browser panel that surfaces commander-eligible cards from your active Collection slot, ranked to a stated intent rather than to popularity — a theme filter and a color filter narrow the owned pool, sorted by **Support depth** or **Novelty**. Never orders by community popularity.

**Support depth**:
How much of a commander's strategy you already own — the breadth-down-weighted count of in-identity cards in your active Collection slot that serve the commander's signal-derived lanes. The default Commander-discovery sort. Deliberately NOT raw signal/lane count: lane breadth is not quality, so a near-universal lane ("creatures matter") is down-weighted and the generic Staples lane is excluded.

**Novelty**:
The Commander-discovery sort that ranks owned commanders by signal rarity — the inverse frequency of their signals across the whole legal commander pool — so an off-beat hook outranks tokens/counters/ramp. Hard-gated by Support depth: only the buildable weird ones surface.

### Engine concepts

**Signal**:
A precisely-scoped fact extracted from one card's oracle text — a trigger condition, a payoff, a type-matters hook, or a cost-reducer. Informally called a **lane** (e.g. "the deck's signal lanes"). Scope is part of a Signal's identity: *Tinybones, the Pickpocket* yields "cast/steal from an **opponent's** graveyard," not "graveyard matters." Membership is strict: a card emits a Signal only when it literally performs that exact mechanic. Lane names encode role — `<x>_makers` = cards that *do* the mechanic, `<x>_matters` = the payoff side, `wants_<x>` = a card whose own identity makes a deck want the mechanic done to it. Archetype adjacency lives in the serve layer as a **SubAvenue**, never as an emission. Lane-level own-subtype emission (a Knight emitting `type_matters`/Knight at LOW confidence) is intentional, for the 99 too (ratified 2026-07-25): LOW emissions can never read as payoffs (`tribal_payoff_subjects` requires a HIGH non-commander emission), so they add support weight without inventing phantom tribal themes. `Signal.text` is empty for structural emissions — the matched-clause quote retired with the regex engine.

**Synergy package**:
The primary output unit the UI is built around — a set of real cards that amplify a shared Signal, carrying code-found enablers/payoffs and a written rationale for how each card connects. Not a **Combo** (a closed interaction that produces unbounded value or wins the game — Commander Spellbook's domain, shown as a separate "go infinite?" option).

**Exploration avenue**:
A direction the assistant offers to pursue — "lean Voltron vs. tokens," "look at ramp now?" A branch in the build, never a specific card. A **SubAvenue** is a separately searchable angle on the same Signal (one Signal can want several distinct buckets, each with its own search + classifier). A **Focused avenue** is one the human has pinned to declare it a lane they're actually building toward; when ≥1 avenue is focused, a Candidate's `synergy_fit` counts only focused avenues. A fused `_matters` signal splits into a **payoff avenue** (cards that reward the thing) and a **source avenue** (cards that are/produce the thing) so a deck can see it has ten payoffs and no sources (ADR-0026).

**Candidate**:
A specific real card surfaced to fill a need, carrying a "why it fits" note and an honest cost. Every Candidate is a real Scryfall card the deterministic core found — never named from the assistant's memory.

**Color widening** (the partner sort):
The primary ranking axis for the Partner/Background avenue: the count of NEW colors a candidate second commander adds to the deck's current identity. Strict-tiered — widening first, then Candidate synergy fit, then price/cmc — so the broadest color-openers surface first.

**Find surface**:
The single card-finding surface that replaces separate Search and Synergies tabs. Focusing one or more Avenues OR-combines their `serve` specs into the search filters and returns one flat ✦-ranked list.

**Slot** / **slot budget**:
A role the deck needs filled (ramp, draw, removal, wipe, win condition, interaction, or a mana-curve bucket) and its remaining count measured against the active **Template** — the role-count guideline for a format (e.g. the Command Zone Commander template), a *soft* target, distinct from the *hard* curve/land-count gate.

**Grant-covered role**:
A Slot role (draw, removal, …) whose effect the deck receives from a mass ability grant rather than dedicated cards (e.g. a commander giving every tribe creature "draw a card" on ETB). The Slot budget stays a literal card count; coverage is surfaced alongside it and downgrades the shortfall from actionable to advisory, never suppresses it.

**Granter**:
A card whose text gives an ability to a whole class of your creatures ("Sliver creatures you control have outlast {2}"). Cutting a Granter removes that ability from every recipient, so its keep/cut value is the granted ability's quality relative to the Granter's cost — never the strength of its own body.

### Card IR & signals

**Signal key**:
The canonical id of a Signal (e.g. `coin_flip`, `token_maker`) — the contract between the detector (`signals.py`) and the exploitation map (`signal_specs.py`, which maps it to an avenue). Cross-file keys live as constants in `signal_keys.py`.

**Key-agreement gate**:
The import-time assertion in `signal_specs.py` that every producible static key resolves to a spec. Its input is the served-key manifest (a hand-maintained literal — keeping it honest against the lane code is a test discipline, not a derivation; see ADR-0014).

**Folded object**:
A commander's effective Signal set extends to objects its plan deterministically brings into play — a ventured dungeon, an emblem, a meld result (Acererak + Tomb of Annihilation → lifegain synergy invisible from Acererak's own text). Commander-only; the 99 never fold.

**Detriment-directed targeting**:
The scoping convention that a bare "target player" on a detrimental effect reads as opponent-directed for signal purposes (`detriment_directed_scope`).

**Card IR**:
The structured parse deck-forge reasons over instead of re-grepping oracle text: a typed mirror of phase-rs's own parse, plus a derived **concept overlay** that maps its nodes into the ~80-concept synergy vocabulary a Signal key queries. The overlay's output per card face is a **concept tree** — what `_ir_lookup.trees_for` returns and the lane package (`_deck_forge/lanes/`) queries over. Unlike a regex it binds the *operand* a card scales with and the *scope* of an effect, so a Signal key becomes a query over structure rather than a substring match.

**Bridge** (ledgered, self-retiring):
A sanctioned text-regex read living inside a signal lane for a mechanic phase-rs doesn't yet parse structurally, tracked in one central ledger with a gap rationale — gap-gated (it only fires where the structural read is absent) and scheduled to retire once phase's parse catches up. Not a "fallback": every bridge is enumerated and adjudicated, never leftover tech-debt.

### Roles & surfaces

**Session-agent**:
The interactive Claude Code session that supplies the judgment the deterministic core cannot — scoping Signals, proposing novel Synergy patterns, writing "why it fits," judging rules interactions, curating the next avenue. Runs on interactive subscription billing.

**Deterministic core**:
The agent-less Python layer (wraps `mtg-utils`) that does card search, curve/mana audit, combo lookup, and pricing. Always available; the source of every real card the Session-agent grounds its patterns against.

**Backend hub**:
The local process that owns canonical session state, hosts the Deterministic core, serves the browser surface, and is the message bus between the browser and the Session-agent.

**Handoff** / **Import**:
A **Handoff** is a one-click route from a finished deck OUT into another repo tool. A *run-here handoff* (goldfish, proxies) is pure local compute the hub runs in-process, no LLM needed. A *session handoff* (strategy guide, store-sourcing) needs reasoning or a headed browser, so it routes to the attached Session-agent and greys out when detached. An **Import** is the inbound mirror — bringing an external decklist or Collection IN, parsed by the Deterministic core, no LLM. An import always mints a NEW build rather than overwriting the live one, and never guesses a commander.

**Engine module** (`engine.py`):
The deck-analysis surface inside the hub — snapshot, ranked Signals, Avenues, finalize report, partner search — as free functions over a `ForgeState`, so they read state at call time and can't desync from the mutable session.

**Views module** (`views.py`):
The serialization seam owning the card shapes the browser SPA consumes — one atomic `project` plus the deck/search/candidate/combo variants.

**Transport adapter**:
The FastAPI route closures in `app.py`: parse payload → call Engine/Views → apply side effects (mutation, autosave, SSE publish) → return. Holds no deck logic.

### Gates & accuracy

**Curve gate**:
The hard land-count check (Burgess/Karsten for commander, constructed formula for 60-card). Below the floor the deck holds a persistent FAIL that blocks marking the deck finished until an explicit override.

**Flood line**:
The upper land-count band (`recommended_land_count + 2`). Above it the deck is over-landed and gets a soft FLOOD nudge plus a "Trim lands" action — never blocks finalize, since an all-lands combo deck is a legitimate build.

**No-listing card**:
A card for which neither bulk data nor the live price API returns a price. Treated as likely scarce/expensive, never as free ($0).

### Deterministic tuning

The vocabulary of the agent-less deck-evaluation pass that scores a deck and proposes budgeted swaps (the "Tune" surface) — pure Deterministic core compute, runnable with no session attached.

**Tune**:
The agent-less, hub-side evaluation-and-swap pass. Three layers: diagnose (Shape + Efficiency/Template deviation/Focus panels + Commander fit + a severity-ranked issues list), cut candidates, and budgeted swaps (a cut+add pair per top issue). Proposes only; the human confirms each swap or "applies all."

**Spine**:
The mandatory scaffolding every deck needs regardless of Shape. A hard-counted tier (lands, ramp, card draw, interaction, board wipes — counterspells fold into interaction) measured against the Template, and a conditional tier (win conditions, protection) surfaced as Shape-scaled advisory flags. Exempt from the focus judgment — running your interaction never reads as "spread too thin."

**Engine card**:
A nonland deck card whose primary job is to serve one of the deck's signal-derived avenues. The only pool the **Focus** metric measures for concentration (the always-on Staples avenue is excluded). A Spine card may also serve an avenue; that synergy only adds to focus, never subtracts.

**Filler**:
A nonland deck card that is neither Spine nor serves any avenue — good stuff that does nothing *here*. A high filler share is itself a spread/efficiency signal and the first place cut-selection looks.

**Shape**:
The aggro/midrange/control/combo classification of a deck, inferred deterministically from its composition (curve, creature density, interaction density, combo presence). Scales the conditional Spine floors and curve expectations; orthogonal to the synergy axis (its avenues), which drives focus.

**Efficiency**:
A Shape-aware panel of curve and tempo readouts — avg mana value within the Shape's band, ramp adequacy, early-play front-load, closing power. A transparent multi-readout, not one opaque score. Owns the *nonland* curve (distinct from the Curve gate, which owns lands).

**Rate**:
How good a card is at its job for its mana cost: a percentile of effect-per-mana within the card's peer group. Crowd-independent by construction — a structural formula where the IR gives clean numbers, a curated ability-quality table where it doesn't, and neutral (0.5) where neither applies. Multiplies the synergy sort (`score × (0.5 + rate)`), so an off-plan card can never leapfrog on Rate alone.

**Pair read**:
A registered two-card mechanic interaction the ranker scores deterministically: a candidate ident-pattern × a deck anchor (commander-anchor or density-anchor), with a flat curated weight and a CR-grounded rationale. Lands in a separate additive `pair_score` readout — never inside the synergy clusters, never multiplied by Rate. Exists because per-lane additive synergy can't price multiplicative interactions (a mana doubler under an X commander is one lane of credit but the whole reason the crowd plays it).

**Hook**:
The written mechanical reason a candidate belongs in THIS deck: cites the candidate's machine-readable evidence (idents, matched Pair read, or cluster readout) AND the deck-context reason. A top pick whose Hook doesn't survive adversarial refutation counts as a miss. Popularity is never a Hook.

**Adjudicated precision**:
The share of the ranker's top-20 out-of-deck picks, per commander on a fixed 10-commander panel, whose Hooks survive a refuter-majority adversarial check — the primary discovery-quality metric. Crowd recall (EDHREC targets) stays computable as a secondary drift indicator but is never a bar. Acceptance is a paired-delta test: an iteration is judged only on its changed picks, non-inferior within 5 points and drift improving.

**Focus**:
The concentration of Engine cards across the deck's signal-derived avenues (Staples excluded). Scored on a tiered floor — main (~20-per-100), sub (~10-per-100), emerging (~5-per-100) — plus a top-2 concentration ratio and the filler rate. One main + one sub is the research ideal; 3+ themes reads SPREAD-THIN. Lands never count as theme support, and Spine-role avenues (ramp/draw/removal) are dropped so scaffolding can't masquerade as the main lane. Shape-aware: a small-engine-pool control deck reads SPINE-LED, never spread-thin.

**Template deviation**:
How far the deck's Spine role counts sit outside the Template bands — 0 within the band, otherwise the distance to the nearest edge. The hard-counted roles drive deviation; the conditional roles surface as Shape-scaled advisory flags, not deviation.

**Commander fit**:
How well the current commander's signal-derived avenues align with the deck's dominant viable avenues — a cheap default-diagnostic flag ("serves 1 of your 3 viable avenues"). Its opt-in companion ranks alternative commanders to the deck you already built, each shown with its identity cost (in-deck cards that fall out of color identity on the switch).

**Bracket-constraint gate**:
A check, parameterized by a target Commander bracket (1-5), that flags deck elements exceeding that bracket's official WotC allowances — Game Changers count, mass land denial, extra-turn cards, two-card infinite combos. Orthogonal to Template deviation (permission, not density). The **target** bracket is what the builder aims for; the **detected** bracket is `detect_bracket`'s descriptive inference of the deck's natural bracket from the same signals — a deck can detect as Bracket 3 while the builder targets Bracket 2.