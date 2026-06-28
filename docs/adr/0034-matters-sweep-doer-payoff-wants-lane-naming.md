# 34. The `_matters` sweep: lane names encode role (doer / payoff / wants)

Date: 2026-06-28

Status: Accepted

Relates to: [0031](0031-strict-signal-membership-adjacency-in-subavenues.md) (strict
membership — this is the naming layer that makes "strict membership" legible; refines
0031's clone worked-example into the split below).

## Context

Signal lane keys historically all ended in `_matters` regardless of what their strict
membership actually fired on. That collided with the repo's own convention — a
`<mechanic>_matters` lane is supposed to mean "cards that **care about / are rewarded
by / want** the mechanic" (a *payoff* lane), not "cards that **do** it" (a *doer/maker*
lane). A 124-lane audit found the `_matters` suffix was doing triple duty:

- **Payoff** lanes where the name is honest (`lifegain_matters` fires on "whenever you
  gain life", `attack_matters` on combat-trigger payoffs) — **46 lanes**.
- **Doer** lanes mis-wearing `_matters` (`clone_matters`'s strict membership is cards
  that *become a copy*; `edict_matters` is cards that *do* an edict; `mill_matters` is
  cards that *mill*) — the name reads like a payoff but the cards are enablers.
- **Mixed** lanes that fire on *both* a maker arm and a payoff arm under one name
  (`treasure_matters` = "create a Treasure" makers **and** "sacrifice a Treasure"
  payoffs) — **~44 lanes**.

`clone_matters` was the motivating case: its strict (deck-aggregate) membership is 130
*become-a-copy* doers, but a `clone_matters` name reads as "a deck that wants clones,"
and an `include_membership` cross-open piled **1557** *worth-copying commanders* (Kiki-
Jiki, Obeka, Gyruda) into the same key — cards that don't clone anything, they're good
*targets* to clone. One key, two unrelated populations, a name that fit neither.

(The investigation also corrected ADR-0031's mechanism note: the worth-copying overlap
was never `_recover_clone_creature` leaking `clone` onto `CopyTokenOf` cards — the
structural arm already vetoes token-copies, so deck-aggregate membership was *already*
strict. The overlap lived entirely in the `include_membership` cross-open. The fix is
naming, not a recovery change.)

## Decision

Lane keys encode the card's **role** w.r.t. the mechanic. Three suffixes plus two
special buckets:

- **`<x>_makers`** — the card *performs* the mechanic (the doer/enabler). `clone_makers`,
  `edict_makers`, `mill_makers`, `token_copy_makers`.
- **`<x>_matters`** — the *payoff* side: the card is rewarded by, triggers off, or
  references the mechanic happening. This is the only honest use of `_matters`.
- **`wants_<x>`** — the card's own identity makes a deck *want* the mechanic done to/around
  it (a benefit/target lane, typically an `include_membership` cross-open). `wants_cloning`
  = a worth-copying commander; it opens the clone-enabler avenue but is **not** a
  `clone_makers`.
- **role-density lanes** (`removal`, `ramp`, `tutor`, …) — deck-construction roles every
  deck needs that feed *slot budgets*, not synergy avenues. They drop the suffix entirely
  (bare role name), because they were never "matters" lanes.
- **keyword-have lanes** (a card statically *has* `banding` / `islandwalk` / `flash` with
  no doer/payoff axis) — their own bucket, `has_<keyword>`, distinct from makers.

A **mixed** lane splits at the **emission arm**, not per card: the maker arm emits
`<x>_makers`, the payoff arm keeps `<x>_matters`. The split is gate-verified
**set-equal**: `members(<x>_makers) ∪ members(<x>_matters)` equals the old `<x>_matters`
membership over the commander-legal corpus (no card lost or gained). A `wants_<x>` split
is verified the same way against the pre-split key.

The serve layer is unaffected in spirit: a deck's avenue still offers makers + payoffs +
good targets together (clone's "Clones / copies" avenue serves all three). What changes
is that **membership** is now a clean per-role truth, and the avenue composes the roles
explicitly instead of one over-broad key conflating them.

## Considered options

- **Leave the names, document the ambiguity** — rejected: `_matters` keeps meaning three
  things, every "should X fire Y?" stays a judgment call, and the motivating `clone`
  confusion (a name that fits neither of its two populations) is unaddressed.
- **Rename only the pure-doer offenders, leave mixed lanes** — rejected: a mixed
  `_matters` still contains doers, so the suffix still doesn't reliably mean "payoff." To
  make `_matters` *mean* payoff everywhere, every doer dimension must move out, including
  inside mixed lanes.
- **Split membership *and* the serve avenue** (separate maker/payoff/wants avenues in the
  UI) — rejected as a goal: the user-facing avenue legitimately wants makers + payoffs +
  targets together; only *membership* needs the role split.

## Consequences

- A clean decision rule for every future "should X emit Y?": classify X's role
  (does it / is rewarded by it / wants it done to it) and pick the suffix; cross-archetype
  reach is a SubAvenue, never an emission.
- 78 of 124 lanes change (32 doer renames, 46 splits) plus the role-density and
  keyword-have rebuckets, each landed gate-verified set-equal against the **MTGJSON**
  baseline (ADR-0033 moved the corpus; the Scryfall-era counts are stale). Pilot:
  `clone_matters` → `clone_makers` (130) + `wants_cloning` (1557), union = 1684 = the old
  key, voltron unchanged at 2428.
- Membership becomes audit-able against the actual mechanic (rules-lawyer + real oracle,
  ADR-0027's Iron Law), independent of deck-archetype intuition — which is what archetype
  detection, the agreement gate, and any future IR consumer need.
