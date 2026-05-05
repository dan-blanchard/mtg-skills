# Context Map

This monorepo hosts five MTG skills; each is its own bounded context
with its own vocabulary. Architecture work should ground in the
relevant context and only edit terms inside it.

## Contexts

- [lgs-search](./lgs-search/CONTEXT.md) — sourcing a card list across
  local game stores and online marketplaces, allocating to minimize
  cost, populating checkout carts.

## Pending

The other skills (deck-wizard, cube-wizard, rules-lawyer,
mtg-utils) don't yet have CONTEXT.md files. Add them lazily when an
architecture conversation surfaces a term that the skill's prose
doesn't already pin down.

## Cross-context relationships

None established yet. The skills share the `mtg_utils` Python
package (CLI scripts and library modules) but operate as independent
agents with distinct workflows.
