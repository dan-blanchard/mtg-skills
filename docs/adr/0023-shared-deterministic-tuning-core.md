# A shared, deterministic tuning core (HydratedDeck → scorecard + swaps)

deck-wizard's tuner is a 13-step **agent-driven** pipeline: the LLM counts roles,
eyeballs the curve, judges focus, and proposes cuts/adds across many round-trips. Most of
that is mechanical work an LLM is slow and expensive at and that needs no judgment — and
deck-forge wants the same evaluation as a fast, always-available button, runnable with no
session attached (the deterministic-only mode of ADR-0010).

**Decision.** Build the tuner as a **deterministic, skill-agnostic core** —
`tune(HydratedDeck, params) -> (scorecard, swaps)` — that names cards (the Deterministic
core is allowed to; only the Session-agent cannot, ADR-0009). Concretely:

- It lives in a neutral `mtg_utils/_tuner/` package (sibling of `_deck_forge` / `_stores`
  / `_custom_format`), **not** inside `_deck_forge`, and takes the shared `HydratedDeck`
  value (ADR-0012/0020) — the deck shape both deck-forge and deck-wizard already speak —
  never `ForgeState` or any browser type.
- deck-forge is **consumer #1**: `POST /api/tune` is a thin Transport adapter
  (`ForgeState → hydrate → tuner core → wire shape`, per ADR-0013), and the Tune surface
  runs **hub-side, detached** — it works with no agent attached, living in the
  always-visible left column rather than the attach-gated rail.
- deck-wizard is the **planned consumer #2**: its tuner pipeline will offload the
  mechanical steps (role counting, curve/efficiency, focus, cut/add proposal) to this
  core and keep the LLM only for genuine judgment. Because the boundary is `HydratedDeck`,
  that adoption is nearly free.
- It adds **no new card-matching logic** — it reuses `role_of`, `score_candidate`/`serves`,
  `slot_budgets`, `find_candidates`, and Commander Spellbook combos, all of which bottom
  out in `theme_presets`.

**Why this is the right call.** The slowness and cost of deck-wizard's tuner come from
routing mechanical work through an LLM; the fix is to move that work to deterministic code
once and share it, rather than re-implementing it per skill. Keying the boundary on
`HydratedDeck` (not `ForgeState`) is the single choice that makes the core reusable —
deck-forge's route degrades to an adapter, and deck-wizard inherits the engine without
reaching into deck-forge. It also satisfies the billing constraint (ADR-0010): the heavy
analysis is zero-marginal-cost deterministic compute, leaving the agent's tokens for the
judgment only it can supply.

**Known caveat.** The focus metric needs the signal/avenue engine, which today lives in
`_deck_forge/signals.py`. `_tuner/` importing it is mechanically fine (one symlinked
`mtg_utils` package), but it makes deck-forge's signal engine de-facto shared infra.
Graduating signals to a neutral home is deliberately **deferred** until deck-wizard
actually adopts the core — noted here so the eventual move is a known follow-up, not a
surprise.

**What this stops re-suggesting.** Don't weld the tuner to `ForgeState` or the browser
"because deck-forge is the only caller today" — that silently forecloses the deck-wizard
reuse this ADR exists to enable. Don't re-add agent-driven mechanical analysis to
deck-wizard's tuner without first asking whether this deterministic core already covers
it. And don't build a second tuning / template / role-classification system in either
skill — there is one core.
