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
- `signals.producible_static_keys()` — the set of subject-less keys a detector can
  emit, **derived** by unioning the existing producer tables (so it can never lag the
  detectors) and excluding the subject keys (which resolve dynamically via
  `_subject_spec`, not a static spec).
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
data) with `signal_specs.py` (the exploitation map); that seam is clean.
