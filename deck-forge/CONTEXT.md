# deck-forge Context

The bounded context for collaborative, visual MTG deckbuilding: a human and an expert assistant build a deck together in a browser, with the assistant surfacing synergies, directions, and ranked candidates while the human makes every decision.

## Language

### Deck values

**Family**:
The Format's family (mtg-utils CONTEXT: Family — `commander` / `constructed` /
`limited`), as the hub and the SPA read it: served in the format table with the
facts it implies, and every family decision keys off one of those facts, never off
the format's name (ADR-0054). The Commander-only surfaces — discovery, partner,
staples, the bracket pill, commander fit — read `has_commander` and are absent
(null, a 400) elsewhere, never an empty no-op; the limited surfaces — the Pool
panel, the pool zone, the seed — read `pool_bounded`.
_Avoid_: "the Commander family" as an allowlist, an `id === "commander"` compare.

**Pool**:
A sealed / draft build's opened cards — the fifth zone (`pool`), the cards the deck
and sideboard are drawn from plus basic lands (CR 100.2b). Imported from an Arena
/ Moxfield export (Deck + Sideboard pooled; a bare list is all pool), hydrated like
any zone, counted by no analysis. The Pool panel enumerates every colour pair it
supports on equal footing (**Colour-pair enumeration**: playables, creatures,
removal, evasion, power-4-plus bodies, rares — `set_scan.pool_color_pairs`) before
any opinion is formed, and seeds a first 40 in a pair from the pool's own cards
(replacing the main deck, with one undo held until the next seed or build switch).

**Pool containment**:
A pool-bounded build's legality: every copy in the deck is in the pool at that
quantity (basics excepted). In the hub the pool IS the copy limit (`copy_limit`
reads the pool's count), so the one add rule enforces it and Find strips by it; the
audit's `check_pool_containment` is the CLI-layer statement of the same rule.

**Derived sideboard**:
A pool-bounded build's sideboard: the pool less the main deck
(`DeckSession.derived_sideboard`), emitted by every snapshot and export, never
stored, never written to. A cut is just leaving the deck; playing a pool card is an
add the pool bounds; a move never changes the pool. Uncapped (the "unused" pill).

**Set scan**:
What a SET holds — removal by rarity, sweepers, evasion, the biggest bodies, the
curve — over the pool's set index (`CardPool.set_records`), read-only and
agent-free (`set-scan`, `GET /api/set-scan`): the threats and answers a pool's
opponents draw from, which the pool alone never shows.

**Copy limit**:
How many copies of one card the build may run: the audit's own
`legality_audit.card_copy_limit` — the Format's `max_copies` (1 singleton, 4
constructed), a restricted card's one, and the exemptions (a basic land or an "any
number of cards named" card is unlimited; a named cap is its own). ONE ladder, read
by the audit and by the hub's add rule (`check_copy_add`, a 400 past the limit —
the hub never over-adds) and by Find (`at_copy_limit`: a 2-of stays findable, a
basic never disappears). Spans every zone: the deck and sideboard (CR 100.4a), the
command zone, the companion.

**Zone move**:
Moving copies between two zones in one call (`move_card`, `POST /api/deck/move`):
main deck ⇄ sideboard, promote to commander, reveal as companion. Every rule runs
before the session changes, so a refused move leaves the build untouched — the
old remove-then-add-then-restore dance is gone. A pinned printing rides along.

**Deck colours**:
What a lane search is scoped to, by Family: the commanders' colour identity under a
command zone (the rule, CR 903.4), else the castable colours of the nonland cards
the deck runs — a description, so the Find pips stay unlocked and a splash is the
builder's call. Served in the snapshot; the SPA shows it as a caption.
_Avoid_: "colour identity" for a 60-card deck (it has none as a rule).

**Sideboard**:
The third zone a constructed Family has (`sideboard_size` 15, CR 100.4a; zero for
the Commander family, whose builds never render one; uncapped and derived for a
pool-bounded build — see **Derived sideboard**). Never counts toward the deck
size, a template row, the mana base or the avenues; the copy limit spans it. Over
the cap is a warning (a build in progress may park cards while swapping), reported at
finalize, never a hard rule.

**HydratedDeck**:
A single immutable value joining a deck's card names to their Scryfall records — built once from a deck plus a name→record index, so a desynced deck/records pair can't exist. Analysis functions (`deck_stats`, `mana_audit`, `legality_audit`, …) take a `HydratedDeck` rather than a separate `(deck, hydrated)` pair. An un-hydratable card name is simply absent from `.records` / `.expanded()` (DROP), never represented as `None` — callers never choose drop-vs-pad. `has_records` is `False` only in **degraded mode**: cards exist but no Scryfall records could be joined (no bulk data on disk), distinct from an empty deck.

### Collection & ownership

**Medium** (paper / digital):
Whether a build is played on paper or digitally (Arena). Per-build state on the `DeckSession`, which stores only the raw override; the `Format` (ADR-0045) resolves the effective medium from its allowed media (commander is always paper, Competitive Brawl always digital, Brawl / Historic Brawl default to digital). The medium — not the format — decides the active Collection slot and the cost mode (digital → wildcards, paper → USD). The SPA's format, medium and size pickers read the served `format_options` table, never a hand-list.

**Collection**:
The user's owned cards as a name→quantity pile — what you own, distinct from a deck (what you're building). Global to the hub, persisted in one `collection.json`. Held in two slots, `paper` and `arena`; the active slot is picked by **Medium**, not format. Reads are strictly single-slot.

**Owned**:
A deck card's derived ownership: intersects the active Collection slot, surfaced as a per-card flag plus a deck-level "N of M owned" readout. Derived fresh on every snapshot — never the stored `owned_cards` field `mark_owned` writes into a deck JSON, which would go stale the moment the deck mutates.

**Printing ownership**:
The optional per-(set, collector_number) layer under a Collection entry — nonfoil/foil quantities per printing. Surfaced as owned-first sorting in the printing picker and as a tri-state `owned_printing` on deck cards: `true` = you own the shown printing, `false` = you own the card in a different printing, absent = no printing detail for that name.

**Companion zone**:
The fourth deck zone (`companion`, alongside commanders / cards / sideboard) holding at most one card with the companion ability (CR 103.2b). Excluded from deck-size math, slot budgets, curve/mana math, and the tuner's totals — but its deckbuilding condition IS audited against the starting deck including the commander (CR 702.139b, via `mtg_utils.companion`), and the card must still be format-legal.

**Busy meter**:
The hub's one long job in flight, reported as it runs. Two jobs show it: the first-launch card-signal index build (`_analysis/signals_index`, a one-time ~2-4 min `extract_signals` pass over the whole bulk, cached as a sidecar) and a cold commander-discovery sweep (the per-lane pool density and served-name scans, cached as sidecars keyed by the bulk AND the serve-definition fingerprint — so a bulk refresh or a change to the signal sources recomputes them, one commander at a time). The hub warms both in a background thread at launch (the index, then discovery for the active Collection slot); `state.busy` carries `{job, label, done, total, eta_s}` through the transport's `report_busy`, every snapshot includes it, and each step is pushed over SSE so every open tab shows the meter. A discovery pass reports only once it has run half a second, so a warm pass never flickers the bar. A Find with a theme preset or a discovery run that needs the index meanwhile waits on the same build (one seed lock), never a second one. Null when idle.

**Commander discovery**:
The browser panel that surfaces commander-eligible cards from your active Collection slot, ranked to a stated intent rather than to popularity — the theme picker (Find's preset picker, with Find's meaning: a commander must match every selected preset) and a color filter narrow the owned pool, sorted by **Support depth** or **Novelty**. Never orders by community popularity.

**Discovery module** (`discovery.py`, ADR-0053):
Commander discovery's implementation: the ranking (`discover_commanders`), the background `warm` a Collection import schedules, and the `DiscoveryCache` the `ForgeState` holds — the pool-density sweep and each Collection's served-name sets, locked, persisted to sidecars, and keyed by the Collection's own content so a changed Collection needs no invalidation.

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

**Pre-release card** (the "include unreleased" toggle):
A card from a spoiled-but-unreleased set. MTGJSON publishes these as soon as they're fully spoiled but leaves their legalities empty until release day, which the adapter fills as `not_legal` in every format — so the default legality gate hides them. The Find surface's *include unreleased* checkbox (`SearchPayload.include_unreleased`) widens the gate for exactly those, and results carry an `unreleased` flag the SPA renders as a **PRE** badge. Membership comes from `ForgeState.unreleased_ids`, an ORACLE-level set (`card_search.unreleased_oracle_ids`) — never the record's own `released_at`, because search dedups to the cheapest printing, which for a reprint can itself be future-dated. It is a *widening* control, so it is deliberately excluded from `has_user_filters`: ticking it alone leaves Find idle rather than dumping the vault.

**Slot** / **slot budget**:
A role the deck needs filled (ramp, draw, removal, wipe, win condition, interaction, or a mana-curve bucket) and its remaining count measured against the active **Template** — the role-count guideline for the build's Family (`_analysis/budgets.py`: the Command Zone bands for the Commander family; interaction with sweepers folded in, card draw and an advisory creature count for constructed; creatures, removal and the curve buckets for limited), stated at the family's base size and scaled to the deck's. A *soft* target, distinct from the *hard* curve/land-count gate. Each row carries its label; an **advisory row** is a fact about the deck (a type-line or mana-value count — never a role, ADR-0051) shown beside the verdict, never sourced by the tuner, never a cut pool, never a deviation.

**Grant-covered role**:
A Slot role (draw, removal, …) whose effect the deck receives from a mass ability grant rather than dedicated cards (e.g. a commander giving every tribe creature "draw a card" on ETB). The Slot budget stays a literal card count; coverage is surfaced alongside it and downgrades the shortfall from actionable to advisory, never suppresses it.

**Granter**:
A card whose text gives an ability to a whole class of your creatures ("Sliver creatures you control have outlast {2}"). Cutting a Granter removes that ability from every recipient, so its keep/cut value is the granted ability's quality relative to the Granter's cost — never the strength of its own body.

### Card IR & signals

**Signal key**:
The canonical id of a Signal (e.g. `coin_flip`, `token_maker`) — the contract between the detector (`signals.py`) and the exploitation map (`signal_specs/`, which maps it to an avenue). Cross-file keys live as constants in `signal_keys.py`.

**Key-agreement gate**:
The import-time assertion in `signal_specs/core.py` that every producible static key resolves to a spec. Its input is the served-key manifest (a hand-maintained literal — keeping it honest against the lane code is a test discipline, not a derivation; see ADR-0014).

**Folded object**:
A commander's effective Signal set extends to objects its plan deterministically brings into play — a ventured dungeon, an emblem, a meld result (Acererak + Tomb of Annihilation → lifegain synergy invisible from Acererak's own text). Commander-only; the 99 never fold.

**Detriment-directed targeting**:
The scoping convention that a bare "target player" on a detrimental effect reads as opponent-directed for signal purposes (`detriment_directed_scope`).

**Card IR**:
The structured parse deck-forge reasons over instead of re-grepping oracle text: a typed mirror of phase-rs's own parse, plus a derived **concept overlay** that maps its nodes into the ~80-concept synergy vocabulary a Signal key queries. The overlay's output per card face is a **concept tree** — the corrected tree `_card_ir.trees.trees_for` returns (mtg-utils CONTEXT: Corrected tree), which `signal_trees_for` extends into the signal tree the lane package (`_analysis/lanes/`) queries over (ADR-0047). Unlike a regex it binds the *operand* a card scales with and the *scope* of an effect, so a Signal key becomes a query over structure rather than a substring match.

**Bridge** (ledgered, self-retiring):
A sanctioned text-regex read for a mechanic phase-rs doesn't yet parse structurally, living entirely in one central ledger row (gap rationale, bounded match, the signal key and scope it serves — ADR-0048) — gap-gated (it only fires where the structural read is absent) and scheduled to retire once phase's parse catches up; retiring one is deleting its row. Not a "fallback": every bridge is enumerated and adjudicated, never leftover tech-debt.

### Roles & surfaces

**Session-agent**:
The interactive Claude Code session that supplies the judgment the deterministic core cannot — scoping Signals, proposing novel Synergy patterns, writing "why it fits," judging rules interactions, curating the next avenue. Runs on interactive subscription billing.

**Deterministic core**:
The agent-less Python layer (wraps `mtg-utils`) that does card search, curve/mana audit, combo lookup, and pricing. Always available; the source of every real card the Session-agent grounds its patterns against.

**Backend hub**:
The local process that owns canonical session state, hosts the Deterministic core, serves the browser surface, and is the message bus between the browser and the Session-agent.

**Handoff** / **Import**:
A **Handoff** is a one-click route from a finished deck OUT into another repo tool. A *run-here handoff* (goldfish, proxies) is pure local compute the hub runs in-process, no LLM needed. A *session handoff* (strategy guide, store-sourcing) needs reasoning or a headed browser, so it routes to the attached Session-agent and greys out when detached. An **Import** is the inbound mirror — bringing an external decklist or Collection IN, parsed by the Deterministic core, no LLM. An import always mints a NEW build rather than overwriting the live one, and never guesses a commander.

**Analysis package** (`mtg_utils/_analysis/`, ADR-0050):
The deck-analysis substrate — signals, lanes, specs, bridges, synthesis, the membership floor, template roles, role budgets, candidate ranking, rate, staples — as pure functions of card records and concept trees. Shared by the hub, the deterministic tuner and the deck CLIs as peers; `_deck_forge` is the hub only and nothing imports the hub.

**Engine module** (`engine.py`):
The deck-analysis surface inside the hub — snapshot, ranked Signals, Avenues, finalize report, partner search — as free functions over a `ForgeState`, so they read state at call time and can't desync from the mutable session.

**Views module** (`views.py`):
The serialization seam owning the card shapes the browser SPA consumes — one atomic `project` plus the deck/search/candidate/combo variants.

**Transport adapter**:
The FastAPI route closures in `app.py`: parse payload → call the Engine → **commit** → return. The commit (`_commit`, ADR-0053) is the one tail every state-changing route shares: persist the build when the deck changed, take the snapshot, broadcast it over SSE. Holds no deck logic: a deck rule the Engine refuses raises `DeckRuleError`, which one exception handler maps to a 400 (ADR-0013, finished 2026-09-12).

### Gates & accuracy

**Curve gate**:
The hard land-count check (Burgess/Karsten for commander, constructed formula for 60-card). Below the floor the deck holds a persistent FAIL that blocks marking the deck finished until an explicit override.

**Effective commander cost**:
The earliest turn on which a deck expects to afford its commander — the smallest turn T such that the printed mana value, minus the expected value of the commander's own cost-reduction operand given the cards the deck expects to have cast by then, floored at the colored pips, is at most T. Never above the printed mana value, never below the residual cost. The quantity the **Curve gate**'s commander-cost term models; printed mana value is what it degrades to when the commander has no such clause or the reduction can't be modelled, and the degrade is always reported, never silent.

**Land band**:
The one land-count readout for a deck — `mana_audit`'s `land_band` `{floor, top, flood, count, status}` (ADR-0041, finished 2026-09-12). `floor` is the gate (FAIL only below it); `top` is the target: for the Commander family the higher of raw Burgess (over the effective commander cost) and the Karsten-adjusted count, `floor` the lower of the two; the constructed target for 60-card decks; `flood` is the Flood line; `status` is PASS / WARN / FAIL / FLOOD, where only FAIL gates. Every surface reads it — the Budgets panel's lands row (`slot_budgets` requires it), the finalize gate, the footer pill and Mana Gate modal, the tuner and the CLIs — and none re-derives any part of it.
_Avoid_: "recommended land count" / "land count floor" as separate facts (the retired top-level keys), computing the flood line or Burgess in the SPA or an agent.

**Flood line**:
The land band's `flood` edge (`top + 2`). Above it the deck is over-landed and gets a soft FLOOD status plus a "Trim lands" action — never blocks finalize, since an all-lands combo deck is a legitimate build.

**No-listing card**:
A card for which neither bulk data nor the live price API returns a price. Treated as likely scarce/expensive, never as free ($0).

### Deterministic tuning

The vocabulary of the agent-less deck-evaluation pass that scores a deck and proposes budgeted swaps (the "Tune" surface) — pure Deterministic core compute, runnable with no session attached.

**Tune**:
The agent-less, hub-side evaluation-and-swap pass. Three layers: diagnose (Shape + Efficiency/Template deviation/Focus panels + Commander fit + a severity-ranked issues list), cut candidates, and budgeted swaps (a cut+add pair per top issue). Proposes only; the human confirms each swap, "applies all," or **rejects** an add — a rejected card is sent as `exclude` with every later run of this build, so the swap engine never sources it again and the same slot goes to the next-ranked candidate (the run is deterministic and the hub memoizes the combo lookup per deck content, so every other swap holds); when no affordable alternative exists the note says so, naming the rejection. Rejections live in the browser per build; `deck-tune --exclude` is the CLI's form.

**Remedy** (`_tuner/issues.py`, ADR-0052):
What the Tune swap engine may do about one issue — where the add comes from, which cut pool pays for it, how candidates rank — decided once, when the issue is diagnosed. An issue with no Remedy (a misfit commander, a voltron plan with no commander-damage rule, a Grant-covered role) is the builder's to read; no swap path sources anything for it.

**Spine**:
The mandatory scaffolding every deck needs regardless of Shape. A hard-counted tier (lands, ramp, card draw, interaction, board wipes — counterspells fold into interaction) measured against the Template, and a conditional tier (win conditions, protection) surfaced as Shape-scaled advisory flags. Exempt from the focus judgment — running your interaction never reads as "spread too thin."

**Template role** (`_analysis/roles.py`, ADR-0051):
What one card does for the Template — `lands`, `ramp`, `card_draw`, `interaction`, `board_wipe` (a card may fill several), plus the advisory "protects". Each role is a view over the signal path (a preset, sharpened by the card's IR where it carries more), so what a Slot *counts* and what the Tuner *sources* for it are the same read. A land is never ramp: it is the mana base, counted by the `lands` role and the Land band. A card the signal path cannot see at all answers ramp from oracle text — the one documented degrade.

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
How far the deck's Spine role counts sit outside the Template bands — 0 within the band, otherwise the distance to the nearest edge. The hard-counted roles drive deviation; the conditional roles surface as Shape-scaled advisory flags, not deviation, and an advisory template row is reported beside them (`advisory`), never as a deviation.

**Calibration**:
The tuner's floors per Family (`_tuner/calibration.py`) — front-load, top-end, the Focus tiers, closers, protection, the voltron read — stated at the family template's base size and scaled to the deck's, so a 60-card deck is held to 60-card norms rather than 0.6 of a Commander deck's. Also where the Commander-only axes are switched off (`commander_axes`, `playrate_meaningful`) rather than left to no-op. Every slot count is in copies: a 4-of fills four slots.

**Commander fit**:
How well the current commander's signal-derived avenues align with the deck's dominant viable avenues — a cheap default-diagnostic flag ("serves 1 of your 3 viable avenues"). Its opt-in companion ranks alternative commanders to the deck you already built, each shown with its identity cost (in-deck cards that fall out of color identity on the switch).

**Bracket-constraint gate**:
A check, parameterized by a target Commander bracket (1-5), that flags deck elements exceeding that bracket's official WotC allowances — Game Changers count, mass land denial, extra-turn cards, two-card infinite combos. Orthogonal to Template deviation (permission, not density). The **target** bracket is what the builder aims for; the **detected** bracket is `detect_bracket`'s descriptive inference of the deck's natural bracket from the same signals — a deck can detect as Bracket 3 while the builder targets Bracket 2.