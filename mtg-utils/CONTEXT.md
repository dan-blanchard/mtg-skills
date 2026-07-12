# mtg-utils Context

The bounded context for the shared `mtg_utils` package. Created lazily (per
CONTEXT-MAP.md) when the ADR-0038 architecture conversation surfaced Card IR
terms no prose pinned down; other term clusters join as conversations resolve
them.

## Language

### Card IR

**Concept overlay**:
The crosswalk's decoration layer over the verbatim phase mirror: per preserved
node position, a `ConceptNode` records what the substrate node *means*
(concept, role, scope, subject) without owning or altering the node itself.
The overlay is ours to write; the mirror is phase's verbatim parse.
_Avoid_: "the tree" alone (ambiguous with the mirror), "annotation" (suggests
optional metadata — lanes read nothing else).

**Substrate purity**:
The invariant that every phase mirror node present before an overlay stage is
present after it, same object identity — no mutation, removal, or
impersonation of phase's parse. Decoration is unconstrained; the substrate is
inviolate.
_Avoid_: "immutability" (the overlay layer is also frozen; purity is about the
*phase* nodes specifically).

**Recovery stage**:
The overlay stage that gives Unimplemented clauses a real reading: it parses
the clause text with the clause grammar and re-decorates the node's
`ConceptNode`, recording which rule fired (`recovered_by`). Substrate-wide —
signal lanes and compat consumers both see recovered readings.
_Avoid_: "supplement" (the old-IR path's envelope around the same grammar),
"synthesis" (adds nodes; recovery rewrites decoration in place).

**Re-decoration**:
Rewriting a `ConceptNode`'s decoration in place — new concept/scope/subject,
same underlying mirror node — so a recovered clause keeps its true ability
position and substrate purity holds by construction. The recovery stage's only
write operation.
_Avoid_: "node replacement" (the mirror node is never replaced), "patching"
(vague).

**Clause grammar**:
The shared pure text→structure clause parser (prefix peeling + verb dispatch)
that turns an English clause phase couldn't parse into a structured reading.
One core, one emitter since ADR-0039 step 7: the recovery stage re-decorates
`ConceptNode`s (the old-IR supplement's `Effect.category` re-tag emitter died
with the legacy builder). The substrate's gap-filler; rules retire as phase
learns their clauses.
_Avoid_: "the supplement parser" (names the dead old-IR envelope, not the
shared core), "regex bridge" (the interim per-key marker pattern this
replaces).

**Token allowlist**:
The recovery emitter's set of admitted grammar tokens — the measured rollout
frontier. The grammar may parse more than the allowlist admits; a token enters
only with corpus measurement and pinned tests behind it.
_Avoid_: "feature flag" (it's per-token and permanent-until-superseded, not an
on/off switch).

**Reference arm**:
A tree-synthesis arm for a cares-about *reference* — text that names a
mechanic without performing it (so there is no effect clause to parse). The
irreducible remainder of synthesis after effect clauses moved to the recovery
stage.
_Avoid_: "marker arm" (the retired interim pattern where effect clauses also
got synthesized markers).

**Text-only face tree**:
A zero-unit `ConceptTree` for a multi-face card half phase never emits ANY
record for at all (no node to recover — a fourth residue class the recovery
stage can't reach). Built from the bulk (MTGJSON) record's own `card_faces`
text: `units=()`, `oracle` set to the bulk face text verbatim. Carries no
typed substrate, so it feeds only the b12 byte-mirror lanes and
`tree_synthesis`'s bucket-B arms that read `tree.oracle` directly — never a
structural (unit-scoped) lane, which has nothing to read on an empty tree.
_Avoid_: "synthesized tree" (nothing is synthesized — the whole tree is
untyped bulk text, not a decorated phase node), "phase tree" (there is no
phase record behind it at all).

**Dropped clause**:
A clause phase parsed AROUND: the card's tree exists, but this clause left no
node at all — not even an Unimplemented residue — so it survives only in the
oracle text. The third residue class (after Unimplemented residue and the
missing face), and the one bucket-(c) synthesis exists for.
_Avoid_: "parser failure" (phase didn't fail; it silently omitted),
"parser-blocked" (the text is still reachable — nothing blocks reading it).

**Straggler**:
A clause the shared clause grammar cannot tokenize *yet* — the grammar's
growth frontier, not a permanent gap. A straggler card is served by a
ledgered bridge until its grammar verb lands, at which point the bridge's
gap-gate finds structure and stands down.
_Avoid_: "unparseable" (only unparsed-so-far), "blocked" (nothing waits on
anyone else — the verb is ours to write).

**Ledgered bridge**:
A corpus-bounded text read serving an enumerated straggler set: gap-gated (it
runs only where the tree provably lacks the clause), ledgered (each ties to a
named grammar TODO or upstream report), and self-retiring (the gap-gate
stands it down the moment structure arrives; the convergence check makes any
laggard visible). Same matching technology as a regex detector; opposite
scope and lifecycle.
_Avoid_: "regex bridge" (the retired per-key marker pattern), "fallback"
(hides that each instance is enumerated, pinned, and scheduled to die).

**Graduation**:
The event where a substrate improvement (recovery row, grammar verb, phase
fix) closes a gap some gap-gated arm existed for: the arm stands down
automatically and its MECHANISM pins must be rewritten to assert the new
structural direction — membership never changes. Suppressing the structural
read to keep an old pin green is never the fix.
_Avoid_: "regression" (the pins fail because the substrate improved).

**KEPT twelve**:
The 12 signal keys deliberately left on the legacy serving arm at the Stage-2
port (in `MIGRATED_KEYS`, never in `_PORTED_KEYS_STAGE3`): base_power_matters,
big_mana, cheat_from_top, copy_limit, damage_redirect, excess_damage,
extra_draw_step, free_cast, ki_counter_matters, kicked_spell_matters,
land_destruction, named_synergy. Outside the `_STAGE4_RESIDUAL` ledger, so
the grind's residual count understates the legacy-served surface by exactly
this set; they promote by ADDITION to the ported set, not removal from the
residual one. ADR-0039 W8 PROMOTED all 12 — cheat_from_top (already
byte-identical via the shared `_apply_membership_floor`, a pure key-slice
change), copy_limit (a new `ConceptTree.many_copies` typed field),
base_power_matters / damage_redirect (a graduated `PtComparison.scope`
structural read + a ledgered bridge, and a b12 byte-identical mirror,
respectively), extra_draw_step (a typed-node extension of the existing
`_extra_upkeep_end` beginning-phase decomposition), excess_damage /
kicked_spell_matters / free_cast (byte-identical KEPT-MIRROR text scans, the
same tier as the pre-existing `_MINUS_COUNTER_KEPT_RX` rows), land_destruction
/ big_mana (both already `_apply_membership_floor`-served, pure key-slice
changes), ki_counter_matters (a `ki_counter_kind_refs` deep-walk sibling of
the oil arm reaching a trigger's own `condition` field), and named_synergy (a
ledgered bridge — the typed `Named` node is corpus-verified too overloaded,
~9x blast radius, to read directly yet). No permanent KEPT lane remains; a
handful of adjudicated-genuine beyond-legacy gains surfaced along the way (a
DFC face-name join fix, a base-P/T-reference sacrifice cost, among others).
_Avoid_: "residuals" (residuals are tracked; these were invisible to that
ledger until 2026-07-11).
