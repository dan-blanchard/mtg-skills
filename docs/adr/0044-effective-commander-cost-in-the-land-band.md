# Effective commander cost replaces printed mana value in the land band

The Lord of the Eagles ({7}{U}{U}, "costs {X} less to cast, where X is the total power
of creatures you control with flying") drove the land band's Burgess term to 41 lands
for a tempo deck whose commander is a 2–4 mana play on any real board; the agent had to
override the Curve gate by hand (Competitive Brawl build, 2026-09-09). Roughly 25
commander-eligible cards carry such a self-discount, and phase-rs parses every one of
them structurally (a `ModifyCost{Reduce}` static over `SelfRef` with a typed
`dynamic_count` operand) — the gap was ours: the crosswalk deliberately drops SelfRef
cost reductions because they are not the build-around `cost_reduction` lane.

**Decision.** The Burgess term becomes the **effective commander cost** (see
`deck-forge/CONTEXT.md`): the earliest turn T at which printed mana value minus the
floored expected value of the commander's own cost-reduction operand, never below the
colored pips, is at most T. The expectation is closed-form — hypergeometric draws over
7 + (T−1) cards on the play, no mulligan, one land per turn, matching cards cast
cheapest-first within the cumulative mana of turns 1..T−1 (turn T is reserved for the
commander), summing printed power or counting bodies. Population membership is read
from the hydrated record (type line, printed keywords, printed power), the operand from
phase's IR through the existing lookup. Scope is the commander's OWN clause only, and
only battlefield-population operands (`PropertyAggregate`, `ObjectCount`); every other
shape, a missing IR, or a clause-less commander degrades to printed mana value with a
reported status, never silently. One producer: a shared helper called from
`mana-audit`; the tuner, deck-forge's Curve gate and deck-wizard inherit through the
ADR-0041 band. FAIL semantics are unchanged; both band edges move with the term.

**Considered and rejected.** Goldfish simulation for the expectation (honest about
variance, but pulls a seeded simulator into a gate that is pure arithmetic — it stays
the Step-13 playtest tool); the residual cost at the affordable turn as the term (3 for
the Lord — undercounts, since the flyers that earn the discount consumed turns 1–3's
mana; the affordable turn is the "lands by when" quantity Burgess actually proxies);
precomputing into the hydrated cache (the value depends on the whole deck, not the
card); computing in the tuner only (two land bands for one deck — the contradiction
ADR-0041 removed).

**Deferred, each its own decision when a real deck hits it.** Graveyard/zone-count
operands (Karador, Yuma — need a self-mill model), deck-side reducers of the commander
(Warden of Evos Isle, medallions — each must resolve first), cost cheats (the tuner's
`cost_cheat_waiver` stays as is), anthems and granted keywords (the estimate stays on
printed values, conservatively), and interaction (the number is an uninteracted-curve
figure and says so).

**Consequences.** `mana-audit` takes its first dependency on the phase card-data
download (lazy, sha-verified, no cargo); offline it degrades to printed MV with
`status: unmodelled (no IR)`. The mana JSON grows a `commander_cost` block (printed,
effective, residual, status, per-turn table). Tests pinning the raw-Burgess value for a
self-discount commander re-pin; the Lord, Ghalta and an `ObjectCount` commander join the
committed card snapshot so the IR read runs in CI. deck-wizard's SKILL.md stops asking
the agent to compute Burgess by hand and points at `mana-audit`'s number.
