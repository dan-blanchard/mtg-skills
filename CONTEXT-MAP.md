# Context Map

This monorepo hosts seven MTG skills; each is its own bounded context
with its own vocabulary. Architecture work should ground in the
relevant context and only edit terms inside it.

## Contexts

- [lgs-search](./lgs-search/CONTEXT.md) — sourcing a card list across
  local game stores and online marketplaces, allocating to minimize
  cost, populating checkout carts.
- [cube-wizard](./cube-wizard/CONTEXT.md) — designing, balancing, and
  stress-testing MTG cubes. Owns the theme preset / stated archetype
  / gauntlet archetype / shape vocabulary.
- [proxy-printer](./proxy-printer/CONTEXT.md) — rendering printable
  PDF proxies. Owns the local catalog / attributed catalog / lookup
  chain / artist credit / signature vocabulary.
- [deck-strat](./deck-strat/CONTEXT.md) — producing Strategy Guides
  for finished Commander / Brawl / Historic Brawl decks. Read-only
  on the deck. Owns the strategy guide / core spine / conditional
  section / role grouping / Rules Audit vocabulary.
- [deck-forge](./deck-forge/CONTEXT.md) — collaborative, visual
  deckbuilding (human + assistant build together in a browser). Owns
  the Signal / Synergy package / Candidate / Slot / Template / Curve
  gate / HydratedDeck vocabulary, plus the deterministic Tune
  vocabulary (Spine / Engine card / Filler / Shape / Efficiency /
  Focus / Template deviation / Commander fit).

## Architecture decisions

ADRs live in [`docs/adr/`](./docs/adr/). Sequential numbering. Read
these before re-suggesting an architectural change — several
load-bearing decisions (Storefront protocol split, gauntlet archetype
unification, the deliberate absence of a resume path, the hybrid
rules-lawyer integration model in deck-strat) are recorded there.

## Pending

The other skills (deck-wizard, rules-lawyer, mtg-utils) don't yet have
CONTEXT.md files. Add them lazily when an architecture conversation
surfaces a term that the skill's prose doesn't already pin down.

## Cross-context relationships

- **cube-wizard ↔ rules-lawyer** — cube-wizard's tuning pipeline
  invokes rules-lawyer (via the Skill tool) for trigger-interaction,
  timing, and replacement-effect questions during archetype review.
- **deck-strat ↔ rules-lawyer** — hybrid integration (ADR-0008).
  deck-strat re-declares `rules-lookup` / `rulings-lookup` /
  `download-rules` in its `pyproject.toml` for routine claim
  verification; escalates to the rules-lawyer skill via Skill-tool
  invocation for multi-rule timing / layer / stack questions during
  drafting.
- **deck-strat → deck-wizard** — composes sequentially, not nested.
  Users run `/deck-wizard` for tuning, then `/deck-strat` on the
  finished deck. Both share the working dir and the SHA-keyed
  hydrated cache, so deck-strat reuses deck-wizard's parse + hydrate
  output transparently. No Skill-tool invocation between them.
- **deck-forge ↔ deck-wizard** (ADR-0023 → ADR-0029, ADR-0030) — the
  deterministic tuning core (`mtg_utils/_tuner/`, `HydratedDeck →
  scorecard + swaps`), built skill-agnostic, is now wired as
  deck-wizard's Step-6 spine via a thin `deck-tune` CLI adapter
  (Commander family only): deck-wizard offloads role counts / curve /
  focus / cut+add proposal to it and keeps the LLM for judgment + the
  self-grill. The shared `tune()` was IR-backed and enriched for *both*
  consumers (full mana audit, curve histogram, combo surfacing +
  combo-piece cut protection, Game-Changer count) and gained a
  target-bracket constraint gate (ADR-0030, orthogonal to ADR-0024's
  Shape-scaled role bands). cut-check (trigger multiplication) and
  archetype-audit (arbitrary-theme density) are NOT subsumed — cut-check
  survives Steps 5/7, archetype-audit is demoted to optional.
- **cube-wizard ↔ lgs-search** — independent today; a cube author
  could in principle pipe a "wishlist" cube diff into lgs-search,
  but no automated bridge exists.
- **All skills** share the `mtg_utils` Python package (CLI scripts
  + library modules at `mtg-utils/src/mtg_utils/`).
