# deck-forge guards signal keys with an import-time gate, not a registry

A signal `key` (e.g. `coin_flip`, `token_maker`) is a contract between `signals.py`
(which emits `Signal(key=...)`) and `signal_specs.py` (which maps `(key, scope)` to an
avenue spec). It lived as a bare magic string in both, so adding a detector but
forgetting its spec produced a **silent** no-avenue: extraction worked, `spec_for`
returned `None`, and the avenue was just dropped (`continue`) with no error.

**Decision.** A lightweight key-agreement **gate**, not a co-located registry:

- `signal_keys.py` — `Final[str]` constants for the cross-file keys (the four
  subject keys named in both modules). VALUE = the on-the-wire key, so it's
  runtime-identical; the NAME gives a typo a compile-time death (`AttributeError`).
- `signals.producible_static_keys()` — the set of subject-less keys the extractor
  can emit, excluding the subject keys (which resolve dynamically via
  `_subject_spec`, not a static spec). It is `lanes.manifest.SERVED_SIGNAL_KEYS`
  minus the subject keys — a **hand-maintained manifest** (369 keys) covering the
  269 structural lane functions, whose keys are literals in code rather than
  table data. A hand-maintained manifest can drift from the lane code it
  mirrors, so a corpus test (`test_every_emitted_key_is_manifest_served`)
  asserts over the full committed snapshot that every emitted key is
  manifest-served — drift fails loudly in CI, not silently at serve time.
- An import-time assertion at the bottom of `signal_specs.py` requires every producible
  key to resolve to a spec. It fires at import — which `app.py`, `ranking.py`, and every
  test trigger transitively — so a forgotten spec fails loudly, not silently. A readable
  test twin (`test_every_producible_key_resolves_to_a_spec`) replaces the old hand-typed
  `test_all_new_floor_keys_have_specs`, whose 12 literal keys were exactly the drift this
  removes.

**Why not a co-located registry** (one record holding each key's detector + spec). The
fragile seam is narrow — only the ~33 hand-written `signals.py` ↔ `signal_specs.py`
agreements can orphan; the ~150 mined sweep keys are mechanized by the auto-registration
loop and can't, and the 4 subject keys resolve dynamically. A registry would relocate
~600 lines across two ~1000-line files and risk an import cycle (today `signals.py` does
not import `signal_specs.py`; the gate keeps that one-way) to harden the safe majority,
and it fits the imperative detectors (tier-1 lambdas, vocab-gated subject detectors,
full-text matchers) badly — forcing them into a data record *reduces* locality.

**Scope / limit.** The gate catches *presence* (the key resolves to some spec), not
*correctness* (the spec has the right regex/avenue) — which stays the job of the
behavioral serve/served tests. That's acceptable: the documented failure mode is the
silent no-avenue, a presence failure.

**What this stops re-suggesting.** Don't "co-locate detector + spec into one registry
record so adding a signal is one entry" — the churn/cycle cost isn't proportional to a
33-key seam the gate already guards. And don't merge `_sweep_detectors.py` (detection
data) with `signal_specs.py` (the exploitation map); that seam is clean. Don't "derive
the served-key set statically from the lane code" either: an AST sweep of
the lane modules for literal `Signal(...)` key arguments recovers only 259 of 369
keys (the rest arrive from module-level tables, `signal_keys.*` attributes, imported
mirrors, and the `_signals_ir` membership floor), widening the sweep to sibling modules
cuts the gap but inflates the over-approximation to 656 non-key strings, and a runtime
harvest over the fixture corpora under-approximates by construction (`counter_hate`
fires on no fixture card in either corpus and would silently leave the manifest). The
keys are not statically recoverable without executing the code.

**Executed 2026-07-25.** The manifest's former role as the strangler's arbiter
("serve only what we've ported") was dead scaffolding once ADR-0039 deleted the
legacy arm — the filter applied twice, no caller passed a non-default `keys=`,
and the guarding test was tautological. The fix landed with the post-migration
consolidation: the in-extractor filter and the `keys=` parameter are deleted
(measured no-ops — the manifest equalled the producible union exactly, 360 ==
360), the set is renamed `SERVED_SIGNAL_KEYS` (home: `lanes/manifest.py`), and
the corpus test above covers the harvest ⊆ manifest direction over every
snapshot card.

*Amended 2026-07-24; original decision revised in place.*
