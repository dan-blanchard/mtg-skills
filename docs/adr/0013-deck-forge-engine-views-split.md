# deck-forge splits into engine / views / transport, not one app module

deck-forge's `app.py` had grown to ~850 lines mixing two responsibilities: FastAPI
route handlers (transport) and a large body of deck-analysis + wire-serialization logic
that took a `ForgeState` (not a `Request`) and returned plain dicts. The only test
surface for that logic was the HTTP route — `TestClient(build_app(state)).get(...)` — or
reaching into `app.py` privates.

**Decision.** Three modules:

- **`engine.py`** — deck analysis over `ForgeState` as **free functions** (`snapshot`,
  `ranked_deck_signals`, `avenues`, `finalize_state`, `legality_warnings`,
  `partner_search`, `hydrate`, `deck_color_identity`, `explore_filters`, …). The
  interface is the test surface.
- **`views.py`** — wire serialization: one atomic `project` plus the four card-view
  shapes (`result_view` / `card_view` / `candidate_view` / `combo_card_view`) and
  `deck_view`.
- **`app.py`** — the transport adapter: route closures that parse the payload, call
  engine/views, apply side effects (mutation, `_autosave`, `hub.publish`, the
  `bulk_available`/zone `Response` guards), and return.

**Why free functions, not a `DeckEngine` class.** `ForgeState.session` is mutable and
every mutation route edits it in place. A class caching a `HydratedDeck` at construction
would desync on the next add/remove; a free function reads `state` at call time and
can't go stale. The only thing a class buys — a per-request HydratedDeck/ranking cache —
is worthless here (a snapshot is built once per request and discarded; no hot loop), so
the trade (a structural safety property for a non-win) is bad.

**Why views is its own module.** The four card-view serializers had already drifted in
source — the deck zone carried `{name, quantity, unknown, …}`, search/packages/explore
carried `{name, …}` with no `quantity`/`unknown`, and combos carried `{name, in_deck,
…}`. Deck-math and the wire contract have different change-drivers (MTG analysis vs the
Svelte SPA) and different reviewers, so they belong in different modules; centralizing
the projection means a new display field is one edit, not five.

**What this stops re-suggesting.** Don't fold the serializers back into `engine.py` for
one fewer file (it recouples the frontend contract to deck-math), and don't reintroduce
a stateful `DeckEngine` class over the mutable session. The candidate pipeline
(`search_fn → rank_candidates → cap → serialize`) deliberately stays route-side for now;
extracting it is a separate, smaller deepening.
