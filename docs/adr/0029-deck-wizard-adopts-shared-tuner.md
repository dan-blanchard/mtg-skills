# deck-wizard adopts the shared deterministic tuner (enriched for both consumers)

ADR-0023 built the deterministic tuner (`tune(HydratedDeck, params) -> {scorecard,
swaps}`) skill-agnostic, with deck-forge as consumer #1 and deck-wizard the **planned
consumer #2 — "not yet wired."** This wires it, and enriches the shared core so the
adoption is worth making.

**Decision.**

- **Transport.** deck-wizard consumes the tuner through a new thin `deck-tune` CLI
  adapter (`deck-tune <deck.json> <hydrated.json> [--budget --max-swaps --shape
  --bracket]` → scorecard + swaps JSON) — the CLI analogue of deck-forge's
  `POST /api/tune` Transport adapter (ADR-0013). It injects `card_search` as
  `search_fn` and `combo-search` as `combos_fn`. **Commander / Brawl / Historic Brawl
  only** — it hard-refuses 60-card constructed, because the tuner is commander-shaped
  (the Command Zone template at `budgets.COMMANDER_TEMPLATE`, the Burgess land target,
  and `commander_fit` have no constructed meaning; a 60-card Burn deck would get a
  misleading scorecard).

- **The tuner becomes IR-backed.** `tune()` resolved its deck signals through the regex
  path (`rank_deck_signals(...)` with no `ir_for` at `tune.py`) — the one signal-
  extraction hole left after ADR-0027. Resolve `ir_for` **internally** at that call (no
  signature change; the candidate-scoring paths — `score_candidate`, `rank_candidates`,
  `role_of` — already self-resolve via `_deck_forge._ir_lookup.ir_for`). Provisioning
  the Card IR sidecar is **load-bearing**: with no sidecar, *every* signal path — not
  just the patched one — returns `None` and degrades to regex, so the `deck-tune`
  adapter must `ensure_card_ir()` (best-effort, warn-and-fall-back) before running.
  deck-forge already builds the sidecar at launch (`production.default_state`), so
  patching the one call gives deck-forge IR-backed focus for free.

- **The tuner is the deterministic spine of deck-wizard Step 6.** For commander decks,
  one `deck-tune` call replaces the piecemeal, agent-driven mechanical work of Step 6
  (role density, curve/tempo, archetype-coherence focus, cut selection, synergy-ranked
  adds). The agent's job shifts to *judging the scorecard and vetting the candidate
  swaps* through the per-card Cut Checklist; the Self-Grill (Step 8) and the
  Dan-drives-the-choices contract stay. The standalone `deck-signals` / `slot-budgets`
  / `deck-rank` CLIs drop out of Step 6 (the tuner calls those functions directly); they
  remain only as ad-hoc diagnostics + smoke tests, with no other pipeline consumer.

- **The tuner is enriched in the one core, not deck-wizard's edge (both consumers
  benefit).** `tune()`'s scorecard gains: the full `mana_audit` (color balance /
  Burgess / untapped quality, not only `recommended_land_count`); the curve histogram
  (`deck_stats` is already called — stop discarding it); combo surfacing **and
  combo-piece cut protection** (`swaps.cut_candidates` becomes combo-aware — today it is
  combo-blind and can propose cutting a combo piece, a real deck-forge bug); and the
  Game-Changer count + bracket *detection*. The bracket-*constraint* gate is ADR-0030.

**Scope boundaries (the explicit no-s).**

- **cut-check is not subsumed.** No tuner code computes per-card commander
  trigger-multiplication (Obeka / Isshin "deal N to each opponent" × multiplier ×
  opponents); the nearest tuner features are boolean role/payoff classification, never a
  multiplied value. cut-check survives as deck-wizard's Step 5/7 judgment-support tool,
  and is later rebuilt on the Card IR — a separate, non-blocking continuation of
  ADR-0027, *after* this adoption.
- **archetype-audit is demoted, not dropped.** `focus` measures commander-signal
  concentration (each name once); archetype-audit measures arbitrary user-`--theme`
  density + bridge cards + copy-count. Different questions. archetype-audit becomes an
  *optional* deck-wizard diagnostic; the CLI stays (deck-strat, deck-forge, and
  cube-wizard all declare it).
- **Role bands stay Shape-scaled.** This adds no bracket-scaled role density — ADR-0024
  stands; the bracket axis is ADR-0030.
- **60-card constructed stays agent-driven.** Extending the tuner to a constructed
  template is a future effort, not this one.

**Why this is the right call.** ADR-0023's whole rationale — deck-wizard's tuner is slow
and expensive because mechanical work is routed through an LLM; fix it once and share it
— only pays off when deck-wizard actually adopts. The `HydratedDeck` boundary makes the
adoption a thin adapter. Putting the enrichment in the shared core keeps "one core"
honest: deck-forge's Tune surface gets the mana base, curve, and combo-protection for
free, and there is no second tuning system.

**Consequences.** ADR-0023's deferred caveat — graduating the signal engine out of
`_deck_forge` to a neutral home — now triggers, since `_tuner` (which deck-wizard now
reaches) imports `_deck_forge.signals`. Tracked as a follow-up, not done here.

**What this stops re-suggesting.** Don't re-add agent-driven mechanical role-counting /
drafting to deck-wizard Step 6 — the tuner owns it. Don't describe the spine as leaving
the agent "only judgment": the mana-base color balance, the curve histogram, and combo
surfacing are *emitted by the tuner but still read by the agent*, and bracket compliance
is its own gate (ADR-0030), not a role band. Don't reflexively delete the orphaned
`deck-signals` / `slot-budgets` / `deck-rank` CLIs. Don't try to fold cut-check's
trigger-multiplication or archetype-audit's arbitrary-theme density into the tuner —
they answer questions it deliberately doesn't.
