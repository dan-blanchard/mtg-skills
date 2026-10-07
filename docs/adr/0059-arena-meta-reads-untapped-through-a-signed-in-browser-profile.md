# Arena meta reads Untapped through a signed-in browser profile

The deck tools had no read of the Arena ladder. Tuning a Competitive Brawl deck meant
an agent driving Chrome through Untapped.gg's Premium pages, scraping React state and
pasting numbers into notes. EDHREC play rate, the one population signal the tuner had,
is paper multiplayer EDH, so it was already switched off for one-on-one games. Arena
decks were tuned with no population at all.

**Decision.** `arena-meta` reads Untapped's Premium meta API directly, and the tuner,
deck-forge and deck-strat read its cache.

- **Access (verified live 2026-10-04 and 2026-10-05).** The Premium endpoints take
  session cookies only, with no bearer token, and only after a real page load has
  refreshed the session. A bare call with the same cookies gets a 403. So
  `arena-meta --login` opens a visible Playwright browser on a persistent profile
  (`<cache>/untapped/profile`) once. Each fetch reopens it headless, loads one
  Untapped page, and calls the API through that context's request API. A 403 means
  "sign in again". Playwright is imported only on that path, so a skill that never
  fetches never needs a browser.
- **The queue.** `Format.arena_event` names Arena's event for each format's Bo1 queue
  (`Brawl_Ladder`, `Ladder`, `Explorer_Ladder` for Pioneer, `Play_Brawl_Historic`…).
  `Format.arena_event_for(bo3=True)` gives the `Traditional_` twin; a Brawl queue
  has none. Untapped has no event parameter: `meta-periods/active` lists one period
  per event name, the newest is the current meta, and `--previous` reads its
  predecessor. A ranked ladder takes `RankingClassScopeFilter=BRONZE_TO_MYTHIC`. An
  unranked `Play_*` queue takes `ALL` and reports one bucket, `all`, which every
  read uses whatever ranks were asked for.
- **Decklists.** Each published list is a V4 deckstring of Arena titleIds, read from
  Untapped's own encoder (`_arena_meta/deckstring.py`). The titleIds are named
  through Untapped's public `cards.json` (titleId → grpids) and
  `CardPool.by_arena_id`, so names match every other deck tool. Arena's
  `loc_en.json` title is the fallback.
- **The reads (`_arena_meta/meta.py`, pure).** They default to Platinum and up
  (`--ranks` overrides) with a Mythic column beside them:
  - meta archetypes ranked by the Wilson lower bound (at least 250 matches);
  - the field (at least a 1% share of the matches);
  - an archetype's core (cards in at least 40% of its lists, weighted by matches,
    with the average copies);
  - the lists a collection can build within a wildcard allowance.

  Ownership and cost are the one rule: `Format.coverage` through
  `price_check.arena_wildcard_cost`, over `CardPool.rarity_index(arena_only=True)`.
- **Which meta archetype a deck is.** On a Brawl ladder, the archetype whose lists
  lead with the same commander(s); a partner pair Untapped files under one of the two
  matches on either. On a 60-card ladder, the archetype whose lists share most of the
  deck's nonland cards (the match-weighted mean of each list's share). Below 40% the
  deck matches none rather than being forced into one. `--meta` / `--archetype` names
  one instead.
- **The tuner reads it from the cache, never by fetching.** `TuneParams.meta` (a
  `MetaContext`) applies to a digital build only, because the ladder is a digital
  deck's population:
  - Each nonland class carries its `meta_share`. An Engine card in under 5% of the
    archetype's lists is low-value, in place of the EDHREC fringe read.
    `CardClass.least_played_key` orders every least-played-first cut by it.
  - The archetype's nonland core cards the deck lacks (top five) become
    `meta_core_missing` issues. Severity is `round(8 × share)`, and the remedy is a
    search for exactly that card, the near-miss combo's path.
  - The scorecard gains a `meta` section: the archetype, its record, its core, the
    missing core (lands included) and the low-share cards.

  Untapped publishes lists for a fraction of its archetypes (2026-10-07: 103 of
  1104 on `Brawl_Ladder`), often one thin list, so the tuner reads an archetype only
  when its published lists hold at least the ranking's floor, 250 matches, at
  Platinum and up (`meta.tunable`, measured by `meta.list_sample`). One 21-match
  list would otherwise condemn every card it lacks. The report and the panel show a
  thin core with its sample and `tunable`'s answer, never judging it again. With no
  cache, no match, or a thin sample, the tuner runs exactly as before. `deck-tune
  --meta auto|off|<name>` and the hub's `meta_archetype` choose.
- **deck-forge** reads only the cache too: a Tune click never waits on a browser.
  `GET /api/meta` serves the Meta panel (field, ranking, the deck's match and its
  core, the buildable lists). `POST /api/meta/refresh` is the one fetch.
  `POST /api/meta/login` opens the sign-in window on the user's machine, since the
  hub runs locally.

Snapshots are cached 24 hours, `--previous` included, since after a set release
"previous" names a new period; a period pinned by id is kept for good. One cache
serves the CLI, the tuner and the hub, and `untapped.deck_queue` picks the queue for
all of them, so they agree. `Format.arena_queues` orders a deck's queues: Bo3 first
for a constructed deck with a sideboard, then the other as a read-only fallback. A
fetch always fills the deck's own queue.

**Considered.**
- Driving the Premium pages with Claude in Chrome every time. It is agent-only and
  slow, and it can't run from deck-forge or `deck-tune`.
- Calling the API with exported cookies and no browser. It fails: the session must be
  refreshed by a page load.
- Fetching live on Tune when the cache is stale. A browser start would stall the hub.
- Untapped's archetype tag names for the Brawl match. The decks' own commanders are
  exact, and the tags carry Alchemy `A-` names.

**Consequences.** Untapped can change its API or deckstring version without notice. A
decode error skips that list, and an unsupported version raises
`DeckstringError`. `tests/mtg-utils/test_arena_meta.py` pins real V4 strings, so a
format change shows up as a fixture to refresh. The stats are Untapped's sample,
players running its tracker, not all of Arena.
