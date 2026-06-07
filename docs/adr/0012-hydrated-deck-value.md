# Deck analysis takes a HydratedDeck, not a (deck, hydrated) pair

The deck-attribute functions (`deck_stats`, `detect_bracket`, `mana_audit`,
`reconcile_basic_lands`, `legality_audit`, `combo_search`, `run_cut_check`) each took a
parsed-deck dict **and** a parallel list of hydrated Scryfall records. The invariant
"hydrated is the join of the deck's names against bulk data" was part of the interface
but unenforced, so every caller had to uphold it; the join was re-implemented in three
places with two disagreeing missing-name conventions (`DeckSession.hydrated` dropped,
`production._combos` None-padded); and `card_classify.check_hydration` was a runtime
guard bolted onto three call sites to detect the recurring "passed the un-hydrated
deck" bug.

**Decision.** Introduce a single immutable `HydratedDeck` value that owns the join.
The analysis functions take a `HydratedDeck` as their one argument. A desynced pair is
unconstructable, so `check_hydration` is **deleted**.

- **Construction adapters.** Three classmethods funnel into one private `__init__` that
  enforces the invariant once: `from_session(session, by_name)` (deck-forge, in-process
  — build one per request and thread it, collapsing ~10 re-derivations),
  `from_paths(deck_path, hydrated_path)` (CLI — the one boundary that reads untrusted
  on-disk JSON), and `from_parsed(deck, by_name=…, *, records=…)` (the shared low-level
  seam).
- **DROP convention.** Un-hydratable names are absent from `.records` / `.expanded()`,
  never `None`; the lone `None` lives at `.by_name.get(name)`, the already-handled miss
  path. This retires the `list[dict | None]` signatures and the untested None-pad.
- **Typed degraded mode.** `.has_records` is the queryable successor to the guard's
  WARN (False only when a non-empty deck has no joined records), distinct from an empty
  deck. `__iter__`/`__len__` are drop-in sugar over `.records`; `__bool__` is *not*
  records-truthiness (it would re-conflate empty-deck with no-bulk).
- **Re-homed RAISE.** The "deck stubs where records belong" `ValueError` moves from the
  three scattered guards to `from_paths`/`from_parsed(records=…)` — the only place
  untrusted data enters — so a corrupt hydrated file still fails loud.
- **Analyses stay free functions.** `deck_stats(hd)`, `mana_audit(hd)`, … remain the
  seam; `HydratedDeck` is a pure join, never a memoized analysis facade (which would
  diverge the test surface and silently cache stale results off a mutable session).

**Scope (the explicit no).** Deck-domain only — commanders/cards/sideboard. The
cube-wizard family (`archetype_audit`, `cube_*`) joins a flat pool with no zones, lives
in a different bounded context, and never touched `check_hydration`; it keeps
`build_card_lookup` public, and a future `CubePool` can mirror this pattern if a second
cube consumer justifies it.

**Considered and rejected.** A `records(include_missing=…)` kwarg (re-leaks the
drop-vs-pad choice per call); `bool(hd)` as the degraded signal (conflates empty-deck
with no-bulk); memoized bound-method analyses on the value (facade + mutable-session
caching footgun); a transitional dual-accept shim (re-introduces the very two-shape
surface this removes). Migration is a one-commit cutover (~4 guard tests deleted, ~30
construct-the-value-differently, ~280 unchanged) plus one new test pinning the DROP
convention at the `from_session` join.
