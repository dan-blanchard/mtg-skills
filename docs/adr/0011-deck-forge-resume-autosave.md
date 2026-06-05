# deck-forge autosaves and resumes, departing from ADR-0003

ADR-0003 established that lgs-search has no resume path: its sidecar is a write-only
audit record, and a failed run is fixed and re-run from scratch. A future
architecture pass touching deck-forge will notice that precedent and may try to
apply it here. This ADR records why deck-forge deliberately goes the other way.

**Decision.** The Backend hub continuously autosaves canonical session state (the
deck, scoped Signals, Slot budgets, and the decision history) to disk, and keeps a
library of multiple named builds. Closing the browser or terminal and reopening
resumes exactly where the user left off.

**Why this is the right call — and why it differs from lgs-search.** lgs-search is
an *operational* flow: a ~5-minute headless checkout run with a clear end state,
where "resume from the middle" added ~150 LOC of state machine propping up
zero-caller code. deck-forge is a *creative* flow that spans hours or days — a
100-card Commander deck is rarely finished in one sitting, and each Signal/Candidate
decision is expensive human thought we must not throw away. The two tools have
opposite session economics, so the no-resume reasoning of ADR-0003 does not
transfer. State here is also genuinely incremental and cheap to persist (it is the
deck plus a few derived structures), not a multi-phase external-side-effect machine.

**What this stops re-suggesting.** Don't "align deck-forge with the repo's
no-resume convention (ADR-0003)" — the convention is scoped to operational checkout
flows, not creative authoring tools. Conversely, keep autosave *cheap and
crash-safe* (atomic writes); don't grow it into a heavyweight phase/state machine
beyond what resuming a deck edit actually needs.
