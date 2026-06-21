# 28. Consume phase-rs (bump the tag); structure the tail in Python supplement.py — do not fork the Rust grammar

Date: 2026-06-21

Status: Accepted

Relates to: [0027](0027-card-ir-replaces-regex-detection.md) (the regex→IR
cutover this parser strategy serves).

## Context

ADR-0027 commits us to retiring oracle-text **detection** regexes in favor of a
Card IR projected from phase-rs's parse. phase-rs (`github.com/phase-rs/phase`,
pinned in `_phase.py::PHASE_TAG`) is an external Rust MTG engine whose nom grammar
we consume by reading the `card-data.json` it generates; `_card_ir/project.py`
maps phase effect types into our IR, and `_card_ir/supplement.py` re-parses the
clauses phase leaves as `Effect::Unimplemented` into real IR nodes.

During the cutover a fair question arose: **since we build the sidecar anyway, why
maintain two parsers (Rust phase-rs + Python supplement.py)? Wouldn't it be
simpler to add our parsing as modifications to phase-rs's Rust grammar?** The
pipeline does parse each card twice — once in phase's ~285K-LOC nom grammar, then
again in supplement.py (~1.4K LOC) for the Unimplemented tail, which by its own
docstring "mirrors phase's own shape (imperative.rs + token.rs)." The duplication
is real, so the question deserved a grounded answer rather than an instinct.

Two facts, verified against the live phase-rs source and the GitHub release feed,
decide it:

1. **phase-rs couples parse output to the engine's type system.** The parser emits
   into the engine's own `Effect` enum (682 variants, `#[serde(tag="type")]`),
   which is **not** `#[non_exhaustive]` and is matched exhaustively across ~690
   resolver arms (`game/effects/mod.rs`). Adding a *new* mechanic as a typed node
   requires adding an enum variant **and** satisfying every exhaustive match in
   the engine to compile — paying full engine-plumbing cost for a capability the
   synergy classifier never runs. "Coverage" in phase is explicitly
   engine-registry membership (`game/coverage.rs`), confirming phase only adds a
   grammar rule once it implements the *engine* for that mechanic — so its parse
   coverage trails the live card pool by design.
2. **phase-rs releases multiple times per week**, and its changelog is dominated by
   `fix(parser):` entries that map directly onto our open gaps (v0.2.2, 2026-06-20:
   "deal damage equal to their power", "combat damage is dealt to you" trigger,
   "as long as it's modified/enchanted" conditions, double-keyword-grant /
   toughness-anthem / vigilance-grant regressions). A fork would mean perpetually
   rebasing patches onto a 285K-LOC grammar + 682-variant enum against a torrent of
   exactly the fixes we want to *inherit*.

Crucially, phase already hands us the recoverable structure for free and in-band:
unparsed clauses serialize as `Effect::Unimplemented { description: "…line
failed…: <CLAUSE>" }` inside the `card-data.json` we already read, so supplement.py
re-parses a **stable diagnostic format**, not scraped text.

## Decision

**Consume phase-rs as a pinned, regularly-bumped dependency. Grow detection
coverage in our Python layers (`project.py` binding + `supplement.py` clause
rules). Do not fork the Rust grammar.** The supplement.py parser is the
synergy-parse source of truth for the Unimplemented tail; phase is consumed, never
modified in-tree.

Each remaining cutover gap is triaged into one of three quadrants (use
`_deck_forge/phase_crosscheck.py` as the classifier):

1. **Phase leaves it `Unimplemented`** (raw clause preserved) → a `supplement.py`
   ClauseRule that emits a typed IR node. The default.
2. **Phase types it correctly but our lane doesn't read it** → a `project.py` /
   `_EFFECT_CATEGORY` binding fix. Cheapest; no new grammar.
3. **Phase *mis-types* it into a wrong-but-typed variant** → the one class
   supplement.py structurally cannot catch (project.py only routes
   `other`/`Unimplemented` bodies to the recoverer). Handle via a thin build-time
   `.patch` applied in `_phase.install_phase()` (only for an existing-variant fix
   needed now) or an upstream PR; otherwise accept the lane gap until the next
   `PHASE_TAG` bump.

The kept-mirror home (`_IR_KEPT_DETECTORS`) is reserved for atomic named-keyword /
ability-word mechanics where the word *is* the structure (celebration, coven, the
bends) — not for decomposable mechanics, which get a real supplement/project
structuring instead.

**Bumping `PHASE_TAG` is a first-class, recurring action**, run as a validated
spike (rebuild sidecar → diff `card-data.json` shape → parse_confidence delta →
global no-flood across all migrated keys → suites → re-triage the queue), because
upstream parser fixes routinely close our gaps for free. The sidecar is stamped
with `phase_tag` so a bump auto-invalidates it.

## Consequences

- We keep one-line version bumps and zero rebase burden; the Python layer stays
  the fast, low-skill-barrier iteration surface (no Rust compile + no 91 MB / 35k-
  card `card-data.json` regeneration per grammar tweak).
- We accept that detection has two parsers (phase + supplement) that can diverge on
  the Unimplemented tail; `phase_crosscheck.py` makes the divergence visible and
  governed rather than silent.
- The mis-typed-variant class (quadrant 3) is a known blind spot of the
  supplement-only approach; it is handled by thin patch / upstream PR, tracked, not
  papered over.
- Bumps carry shape-change risk (a minor bump like v0.1→v0.2 may reshape
  `card-data.json`), mitigated by the validated-spike protocol above.

**Revisit trigger:** if our coverage gaps migrate predominantly to the
existing-variant mis-parse class, escalate to a standing build-time patch set; if
they become *new playable mechanics phase has no variant for*, reconsider
upstreaming or a fork. As a low-effort long-horizon hedge, file an upstream issue
asking phase to mark `Effect` `#[non_exhaustive]` (or add a parse-only AST node),
which would collapse "new mechanic" into the cheap column.

## Alternatives considered

- **Fork phase-rs's grammar and retire supplement.py (the proposal).** Rejected.
  It is genuinely the single-source-of-truth win, and the "two parsers for one
  language" critique is accurate. But the `Effect` enum's exhaustive engine
  coupling makes new-mechanic parse rules pay an engine tax we never use; the edit
  loop is a multi-minute Rust compile + full card-data regeneration; and the weekly
  release cadence turns a fork into permanent rebase against the fixes we want to
  consume. The decisive asymmetry: we parse for *synergy classification*, never to
  *play*, so the engine coupling is cost without benefit.
- **Thin build-time Rust patch instead of a full fork.** Kept as the quadrant-3
  tool, not the primary surface — it avoids a divergent tree while still reaching
  the mis-typed-variant class when needed.
- **Status quo, never bump.** Rejected: forgoes the steady stream of upstream
  parser fixes that close our gaps for free; we were ~20 releases stale (v0.1.60
  while v0.2.2 shipped) and several open queue items are already fixed upstream.

Note: CLAUDE.md and older task notes reference "phase v0.1.19" — stale; the code
and install are on v0.1.60 (and this ADR sanctions bumping further). Correct that
reference when next editing CLAUDE.md.
