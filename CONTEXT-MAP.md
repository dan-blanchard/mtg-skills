# Context Map

This monorepo hosts six MTG skills; each is its own bounded context
with its own vocabulary. Architecture work should ground in the
relevant context and only edit terms inside it.

## Contexts

- [lgs-search](./lgs-search/CONTEXT.md) — sourcing a card list across
  local game stores and online marketplaces, allocating to minimize
  cost, populating checkout carts.
- [cube-wizard](./cube-wizard/CONTEXT.md) — designing, balancing, and
  stress-testing MTG cubes. Owns the theme preset / stated archetype
  / gauntlet archetype / shape vocabulary.

## Architecture decisions

ADRs live in [`docs/adr/`](./docs/adr/). Sequential numbering. Read
these before re-suggesting an architectural change — several
load-bearing decisions (Storefront protocol split, gauntlet archetype
unification, the deliberate absence of a resume path) are recorded
there.

## Pending

The other skills (deck-wizard, rules-lawyer, proxy-printer, mtg-utils)
don't yet have CONTEXT.md files. Add them lazily when an architecture
conversation surfaces a term that the skill's prose doesn't already
pin down.

## Cross-context relationships

- **cube-wizard ↔ rules-lawyer** — cube-wizard's tuning pipeline
  invokes rules-lawyer (via the Skill tool) for trigger-interaction,
  timing, and replacement-effect questions during archetype review.
- **cube-wizard ↔ lgs-search** — independent today; a cube author
  could in principle pipe a "wishlist" cube diff into lgs-search,
  but no automated bridge exists.
- **All skills** share the `mtg_utils` Python package (CLI scripts
  + library modules at `mtg-utils/src/mtg_utils/`).
