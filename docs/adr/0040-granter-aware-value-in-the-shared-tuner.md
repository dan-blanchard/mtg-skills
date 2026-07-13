# Granter-aware value in the shared tuner (quality table over playrate)

A deterministic-vs-agent tuning benchmark on a Sliver Weftwinder Historic Brawl deck
(2026-07-13) exposed a systematic value-model failure in the shared tuner: tribal decks
are **Granter**-dense (most Slivers grant an ability to every other Sliver), and the
tuner judged those cards as weak *bodies* with fringe *playrate* — condemning cards
whose real value is the granted ability (and, separately, flagging a `card_draw`
shortfall in a deck whose commander grants a draw to every tribe body that enters).
Playrate was the primary condemnation and `is_fringe(None) → True`, so every
digital-only card (EDHREC has no Arena population) auto-read as barely-played.

**Decision.** Card value in the tuner becomes granter-aware, in five parts:

1. **Grant-covered roles** (see `deck-forge/CONTEXT.md`): Slot bands stay literal card
   counts — a mass grant never moves the number. Coverage is surfaced alongside the
   count and *downgrades* the role's shortfall to advisory; it never suppresses it.
   Capacity-counting (fractional per-body credit) was rejected as an unfalsifiable
   knob that would also make the same 99 re-score whenever the commander changes.
2. **Granter value = granted-ability quality relative to the Granter's cost**, judged
   by a small curated ability-quality table (premium / solid / weak-conditional),
   NOT by the Granter's body or playrate. Anti-synergy predicates (conditions that
   flip an ability's sign in context) are added only for *observed* misleads —
   first: a hellbent-gated grant under a draw-engine commander. Long-term direction
   (user-stated): grow the predicates, shrink the table; the table is the pragmatic
   spine because a full predicate system is a large undertaking.
3. **Grant-recipient protection is NOT blanket.** Every tribe body cashes the
   commander's grant once on entry — that baseline cancels out when comparing tribe
   members, so single bodies stay exactly as cuttable as before (the benchmark's
   correct cuts survive). Only cards producing grant cashes *above* the one-body
   baseline get a value boost: multi-body makers of the granted subject (token
   makers), re-entry mechanics (warp / unearth / blink / self-bounce), copy effects.
4. **Playrate demotions.** For Granters, playrate may break ties, never condemn.
   A null `edhrec_rank` on a **digital-medium** deck is *no data* (cannot condemn —
   EDHREC is a paper-EDH population); on paper it remains fringe-evidence. Ranked
   non-Granter engine cards keep the existing test on both mediums.
5. **Closer counting reuses the same table.** Each ability carries a `closer` flag
   (double strike / extra combat / team-unblockable: yes; vigilance / first strike:
   no; haste: no on its own). A Granter granting a closer-grade ability counts as
   ONE closer regardless of recipient count. ADR-0024's advisory/protection
   semantics are unchanged — only the count gets honest (the benchmark deck read
   "2 closers" while holding team double strike twice).

**Prerequisite (extraction).** Tribe-scoped grants currently flatten to bare
`type_matters` — Bonescythe Sliver emits nothing carrying "double strike". The grant
*payload* must be surfaced by the crosswalk before any quality read; this ships with
the new `type_changers` signal (scope `you`, subject `''` = chosen type / `all` =
every type, single-target excluded, **zone reach modeled from v1** — battlefield-only
vs all-zone — because cost-reducer and cast-from-zone serve arms only combo with
all-zone changers like Leyline of Transformation, the benchmark's falsely-"filler"
build-around). Signal emission stays strict (a recipient never *emits* the granted
ability); all grant-awareness lives in the scorecard/value layer above emission.

**Companion behavior refinements** decided in the same session, recorded here rather
than as separate ADRs (reversible tunings, same motivating benchmark): an *emerging*
tribal theme requires ≥1 payoff card naming the tribe (changelings otherwise
manufacture an emerging flag for every tribe at once — the "Bird tribal" phantom);
and at focus verdict FOCUSED, a role-fix swap add must serve ≥1 viable avenue
whenever any in-budget candidate does, with the zero-avenue fallback allowed but
labeled in the swap reason (SPREAD-THIN / SPINE-LED behavior unchanged).
