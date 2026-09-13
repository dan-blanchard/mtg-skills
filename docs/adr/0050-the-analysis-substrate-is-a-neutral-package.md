# The deck-analysis substrate is a neutral package, not deck-forge's

ADR-0023 built the deterministic tuner as a neutral `_tuner/` package but named a
caveat: the signal engine it needs lived in `_deck_forge/`, making deck-forge's signals
"de-facto shared infra", and it deferred graduating them to a neutral home "until
deck-wizard actually adopts the core". deck-wizard adopted it in ADR-0029. By the
2026-09-12 review, seven of the tuner's ten modules imported deck-forge internals, and
so did `commander_cost`, `theme_presets`, `cut_check`, `deck_rank`, `deck_signals`,
`slot_budgets` and the testkit — none of them a deck-forge consumer. Of `_deck_forge`'s
62 modules, 50 (about 55k lines: signals, lanes, specs, bridges, synthesis, the
membership floor, budgets, ranking, rate, staples) had no dependency on the hub at all.

**Decision.** Those modules move, unchanged, to `mtg_utils/_analysis/`: `signals`,
`signal_base`, `signal_keys`, `signal_specs/`, `lanes/`, `tree_synthesis/`,
`bridge_ledger`, `text_reads`, `membership_floor`, `_sweep_detectors`, `_subtypes`,
`signal_trees`, `signals_index`, `ident_provenance`, `pair_reads`, `rate`,
`limiter_discounts`, `budgets`, `ranking`, `staples`. `_deck_forge/` keeps the hub:
`app`, `engine`, `views`, `state`, `production`, `persistence`, `collection`,
`agent_bridge`, `events`, `images`, `phase_crosscheck`. The compat-Card resolver
`ir_for` moves to `_card_ir/compat_lookup.py` beside the tree owner: the compat `Card`
and the concept trees are the two products of one substrate. Dependencies now point one
way — `_deck_forge` and `_tuner` both import `_analysis`, which imports `_card_ir`;
nothing imports the hub. The full-snapshot corpus dump is byte-identical.

`propose_swaps` takes a frozen `SwapContext` (the deck facts and the purse) instead of
18 keyword arguments — the "one context" the review asked for.

**Considered and rejected.** Moving only the seven modules the tuner imports (the moved
package would still import the lanes' own dependencies from the hub's package);
`_signals` as the name (undersells budgets, ranking, rate and staples); `_core` (the
CONTEXT term "Deterministic core" also covers `card_search` and `theme_presets`, which
stay put).
