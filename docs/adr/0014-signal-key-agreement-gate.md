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

## Addendum (2026-07-24): the derivation guarantee lapsed at the crosswalk migration

Surfaced by an architecture review of the signal stack, and measured rather than
argued. Nothing here reverses the decision above — the gate is still the right
instrument — but two of its stated properties no longer hold, and one obvious
repair is ruled out by measurement.

**1. "Derived, so it can never lag" is no longer true.** The Decision above rests
on `producible_static_keys()` being derived by unioning the *producer tables*. That
held while producers were data (`_DETECTORS`, `_HAND_FLOOR`, `SWEEP_DETECTORS`
carry their own keys). ADR-0039 made the crosswalk the only serving path, and its
producers are 269 lane *functions* whose keys are literals in code. The union now
folds in `crosswalk_signals.PORTED_KEYS` — a hand-maintained 571-line literal of
369 keys. So the gate's input can lag the detectors, which is exactly what the
derivation was chosen to prevent. The docstring still claims otherwise.

**2. `PORTED_KEYS`' filter role is dead scaffolding.** It was the strangler's
arbiter — "serve only what we've ported, let legacy serve the rest." ADR-0039
deleted the legacy arm. The filter is now applied *twice* (`extract_crosswalk_
signals`'s own `add`, then again in `signals._add`), no caller in `src/` or
`tests/` ever passes a non-default `keys=`, and it drops nothing: over both fixture
corpora (2,448 + 993 cards) the set of emitted-but-undeclared keys is empty.

**3. The hygiene test that guards it is tautological.**
`test_all_emitted_keys_are_in_the_ported_set` asserts `_keys(name) <= PORTED_KEYS`,
but `_keys` calls `extract_crosswalk_signals`, which already filters to
`PORTED_KEYS`. The assertion cannot fail for any card or any lane. Verified by
registering a lane emitting an unported key: the signal is silently dropped,
nothing is raised, and the test still passes.

**What this stops re-suggesting.** Don't "derive the served-key set statically from
the lane code." Measured 2026-07-24 at v0.35.2: an AST sweep of
`crosswalk_signals.py` for literal `Signal(...)` key arguments recovers 259 distinct
keys and leaves **70 of 369 uncovered**, because keys also arrive from module-level
tables, `signal_keys.*` attributes, imported mirrors, and the membership floor in
`_signals_ir`. Widening the sweep to the six sibling modules cuts the gap to 32 but
inflates the over-approximation from 92 to **656 non-key strings** — which, fed to
the gate, would demand specs for hundreds of things that are not keys. The keys are
not statically recoverable without executing the code. A runtime harvest over the
fixture corpora is accurate for what fires (368 of 369) but *under*-approximates by
construction, so it cannot be the gate's input either: `counter_hate` fires on no
fixture card in either corpus and would silently leave the manifest.

**The shape of a future fix,** if one is wanted: delete the filter and the `keys=`
parameter (dead scaffolding, provably inert), keep the key set as an explicit
manifest renamed off "ported" whose only job is feeding this gate, and add a corpus
harness asserting both directions — `harvest ⊆ manifest` (an undeclared key fails
loudly, closing the silent-orphan path the filter's removal would otherwise reopen)
and `manifest − harvest ⊆ {counter_hate}` (a stale key fails loudly). Hand-maintained
but verified, which is strictly better than today's unverified-plus-vacuous-test.
Deferred 2026-07-24: the bug is latent, not live, and the edit lands in the repo's
hottest file (151 of the last 200 commits).
