# lgs-search has no resume path; the sidecar is write-only audit

The original sidecar schema carried a phase state machine
(`search_complete | allocation_complete | cart_build_in_progress | done`)
plus a `phase_progress` per-store progress dict, an `input_hash` for
change detection, a `next_phase_actions` table, and a `--resume` user-
facing flag. The actual resume code path printed
"Resume: replays summary; partial cart resume not yet wired." and
exited; `phase_progress` was never populated.

We shed the entire state machine. The sidecar at
`<output-dir>/lgs-cart-allocation.json` is now a write-only audit
record carrying just version + timestamp + allocation + chosen
marketplace + unfindable + basic_lands_needed. There is no resume
path; if a run fails mid-build, the user fixes the underlying issue
and re-runs from scratch.

**Why this is the right call right now:** the actual failure modes
encountered (TCG captcha, TGP add_to_cart timeout, MP cart pollution)
all need code or UX fixes, not "resume from the middle." Re-running a
31-card list from scratch is ~5 minutes of headless searches. The
~150 LOC of schema + 8 state-machine tests were propping up code
with zero production callers — tested-but-dead.

**What this stops re-suggesting:** future architecture passes will
notice the sidecar's relatively flat shape and might propose adding
phase tracking + resume. Don't, unless a real use case has surfaced
(e.g., a Phase 4 optimizer that takes 5+ minutes, or a Phase 5 cart
build that actually benefits from resuming after partial failure).
The atomic-write infrastructure is still here — extending it later
is cheap.
