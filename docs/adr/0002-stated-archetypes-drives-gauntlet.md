# stated_archetypes is the source of truth for the gauntlet

Pre-2026-05, the gauntlet had its own parallel archetype list
(`cube.gauntlet_archetypes` field, plus per-format defaults at
`mtg_utils/data/gauntlets/<format>.json`) using the canonical four
strategies (aggro/midrange/control/combo) hardcoded in `score_card`. The
field overlap with the cube's `designer_intent.stated_archetypes` plus the
`preset` field overload (theme-preset names vs `score_card` strategies)
created a real failure mode: a "Tokens" gauntlet archetype with
`preset: "tokens"` would silently hit `score_card`'s else branch and
produce a meaningless deck.

We unified: `stated_archetypes` is now the source of truth. The gauntlet
auto-infers per-archetype build specs (colors + curve_target) from the
cube's actual card pool, with an optional `gauntlet:` block on each
stated_archetype entry as escape hatch. The `preset` field on the
remaining bundled per-format defaults was renamed to `shape` to remove
the namespace overload, and `score_card`'s silent fallback was removed —
unknown shape contributes nothing instead of pretending to score.

`cube.gauntlet_archetypes` was hard-deleted (no migration) on user
direction: the field had no real consumers yet. Bundled per-format files
are kept as fallbacks for stock cubes that haven't filled in
`stated_archetypes`. See `cube-wizard/CONTEXT.md` for the resulting
language ("theme preset" vs "stated archetype" vs "gauntlet archetype"
vs "shape").

**What this stops re-suggesting:** future architecture passes might
spot the parallel archetype lists and re-propose unification. Done.
They might also spot the `preset` overload and re-propose the rename.
Done.
