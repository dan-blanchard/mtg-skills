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
One core, two emitters: the old-IR supplement re-tags `Effect.category`; the
recovery stage re-decorates `ConceptNode`s. The substrate's gap-filler; rules
retire as phase learns their clauses.
_Avoid_: "the supplement parser" (names the old-IR envelope, not the shared
core), "regex bridge" (the interim per-key marker pattern this replaces).

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
