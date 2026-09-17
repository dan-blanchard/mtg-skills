# The hub commits in one place, and Commander discovery owns its cache

Two pieces of the deck-forge hub had an interface every caller had to uphold by hand.

**The commit tail.** After a state change a route must persist the build (if the DECK
changed), take the snapshot, and broadcast it to every open browser. `app.py` hand-wrote
that tail per route: 17 `hub.publish(json.dumps(snap))`, 12 `_autosave(state)`, each with
its own variation (the lane routes don't save, `trim-lands` saves conditionally, a load
must not save). "Become a different build" was a second four-step invariant — session,
id, name, runtime lanes — repeated at four sites. Both had already failed: f04b1b16
(lanes leaked across builds on new / import / load) and 0140f0ea (autosave re-created a
deleted build's id). Autosave was asserted at 2 of 12 sites; no test asserted any
mutation route published. The lane routes and the build lifecycle were the last state
transitions written inside route closures, reachable only over HTTP.

**Decision.** `app._commit(state, *, persist=True, **extra)` is the tail, written once —
still in the transport adapter, where ADR-0013 puts side effects. `engine.switch_build`
is the one place the hub becomes a different build; `add_agent_avenue`, `remove_avenue`
and `toggle_avenue_focus` finish ADR-0013: every state transition is an engine
function. A route is parse → call → `_commit`. Deleting the live build now broadcasts
too (other open tabs kept showing the deleted build).

**Commander discovery.** About 470 of `engine.py`'s 1,721 lines were one concept with
its own change-driver — Support depth, Novelty, a pool-density sweep, a per-collection
served-name scan, two sidecars — with its cache spread over five `ForgeState` fields,
the load → compute → save-if-grown protocol copied verbatim into two functions, and its
invalidation living in `set_collection` / `clear_collection`. Its tests reached past the
interface 16 times. Discovery runs in the threadpool and a ~65s warm runs as a
background task after an import; nothing locked the dicts they shared, and the served
cache was keyed by slot — so a warm still running for collection A could `setdefault`
back the slot entry that importing collection B had just popped, and B's discovery read
A's names.

**Decision.** `_deck_forge/discovery.py` owns it behind three entry points —
`discover_commanders`, `warm`, `owned_commander_records`. `ForgeState.discovery` is one
`DiscoveryCache` with its own lock: dict reads and writes happen under it, the scans
outside it (a lane computed twice is benign, a torn dict is not). A collection's
served-name sets are keyed by the collection's own content, in memory as on disk, so
there is no invalidation step to forget and a late warm can only ever fill its own
collection's entry. `engine.py` drops to ~1,300 lines; `ForgeState.active_slot` is a
property so the slot rule has one home both modules read.

**Considered and rejected.** A `DeckEngine` class wrapping state plus commit (ADR-0013
chose free functions; the commit tail is transport, not a deck rule). Keeping the slot
key and adding a generation counter (one more thing each writer must remember to
check). A lock around the whole discovery call (serialises a 65s warm against every
foreground discover).
