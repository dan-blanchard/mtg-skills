# deck-forge extracts the candidate pipeline into engine.find_candidates and deletes the superseded routes

ADR-0013 split deck-forge into `engine` (deck analysis as free functions over
`ForgeState`), `views` (wire serialization), and `app` (thin transport adapters), and
explicitly **parked** one deepening: "the candidate pipeline (`search_fn → rank_candidates
→ cap → serialize`) deliberately stays route-side for now; extracting it is a separate,
smaller deepening." Four routes — `/api/search`, `/api/packages`, `/api/explore`,
`/api/find` — each re-inlined that skeleton, and `in_deck = set(state.session.card_names())`
was recomputed in four places. ADR-0015 had meanwhile unified the browser onto a single
**Find surface**, leaving three of those routes with no caller.

## Decision

Extract the pipeline, and delete what ADR-0015 already superseded.

- **`engine.find_candidates(state, params) -> CandidatePage`** is the pipeline, as a free
  function over `ForgeState` (ADR-0013: not a class — the session is mutable). It owns the
  three-way Find branch (focused-avenue OR-merge / filter-only manual search / idle),
  in-deck stripping, `scoring_basis` + `rank_candidates` (with ADR-0019 color widening),
  and the paging window. Its glue (`_FIND_POOL`, `has_user_filters`, `refine_filters`, the
  branch selector) moves into `engine`; the steps it composes were already public
  primitives (`hydrate`, `ranked_deck_signals`, `avenues`, `scoring_basis`,
  `explore_filters`, `staple_pool`, `rank_candidates`).

- **`/api/find` becomes a true transport adapter** (~14 lines): guard bulk → adapt payload
  → call `engine.find_candidates` → serialize rows via `views.candidate_view` → return.

- **Delete `/api/search`, `/api/packages`, `/api/explore`** (and the `ExplorePayload`
  model). Verified dead: the SPA's only card-finding calls are `api.find`, `api.card`,
  `api.combos` (grep of `frontend/src` for `api.search`/`packages`/`explore` is empty; the
  Search/Synergies components ADR-0015 retired are gone). They are not folded into the
  extraction — ADR-0015 already said "explore folds into search" and "don't reintroduce a
  Synergies/Packages tab."

## The forks, and how they were resolved

1. **Seam stop (load-bearing).** `find_candidates` returns **ranked records** — a
   `CandidatePage` of `rank_candidates` rows (`{card, score}`) — and the route serializes
   via `views.candidate_view`. It does NOT return serialized wire dicts. ADR-0013 made
   `views` a separate module *because* deck-math and the Svelte contract have different
   change-drivers; an engine function returning `candidate_view` dicts would recouple
   ranking to the frontend projection — the exact thing ADR-0013 forbids. `find_candidates`
   is now tested on selection/ordering; `views` stays the single projection seam.

2. **One deep function, private glue** — not a composable public `build_pool / strip / rank
   / page` kit. The steps are already primitives; re-exposing the glue just re-parks the
   duplication one level down. There is one live caller (`/api/find`), so no second caller
   demands a kit.

3. **Ownership moves into `views.candidate_view(row, fmt, *, owned_qty=None)`**, mirroring
   `card_view` (which already emits the identical `{owned, owned_qty}` pair). This kills the
   route's post-serialize mutation and keeps Collection-slot ownership out of the selection
   engine. Absent `owned_qty` emits no keys, so the wire shape stays byte-compatible.

4. **`/api/search` is deleted, not unified** behind a "raw / no-rank" flag — it's dead, and
   forcing the degenerate no-rank case through a rank-shaped function would pollute it with a
   path nothing exercises.

5. **`FindParams` is a plain engine dataclass; the route adapts `SearchPayload → FindParams`**
   via `app._find_params`. ADR-0013's rule is "engine takes a `ForgeState`, not a Request";
   importing the pydantic `SearchPayload` into engine would invert that. The field mapping is
   transport-adapter work, so it lives in `app.py` where `SearchPayload` is defined.

## Test surface

The branch matrix, in-deck stripping, focused-avenue crediting, staples resolution,
paper_only propagation, and paging math become **direct `engine.find_candidates` tests**
(`test_find_candidates.py`) — no HTTP — which is ADR-0013's "interface IS the test surface"
intent. Serialization invariants (projection/images, format-aware `can_be_commander`, the
new `owned_qty` annotation, the no-bulk 503) stay HTTP-level in `test_find.py`. The
live-invariant tests that were only pinned through the deleted routes (staples credited
on-theme, paper_only, no-bulk 503, in-deck exclusion) were **migrated before deletion**, not
dropped.

## Consequences / deferred

- `views.result_view` survives (still used by `/api/card`). `_PACKAGE_LIMIT` dies with the
  routes; `_EXPLORE_POOL` moves to `engine` as `_FIND_POOL`.
- **Frontend `api.js` cleanup is deferred.** `api.search`/`packages`/`explore` remain
  defined in `frontend/src/lib/api.js` (and bundled in the committed `dist`) but now point at
  removed routes. They have **no call sites**, so the served app is unaffected; removing them
  needs a `dist` rebuild (bundle churn) and is left as a separate frontend pass. A reviewer
  grepping `dist/` for those strings is seeing dead bundled helpers, not live calls.

## What this stops re-suggesting

- Don't re-inline the candidate pipeline into the route "for one fewer indirection" — the
  single delegated call, testable without HTTP, is the whole win (ADR-0013's parked work).
- Don't make `find_candidates` return serialized `candidate_view` dicts — that recouples the
  engine to the wire contract (fork 1).
- Don't restore `/api/search` / `/api/packages` / `/api/explore` — they are ADR-0015 dead
  code; `/api/find` is the one card-finding surface.
- Don't import `SearchPayload` into `engine` — keep `FindParams` + the `app`-side adapter.
