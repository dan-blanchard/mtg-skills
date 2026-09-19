# Limited is a pool-bounded Format family: sealed / draft build from an opened pool

A sealed or draft deck is built from the cards a player opened, plus basic lands
(CR 100.2b). Nothing in the toolchain modelled that: a 40-card pool had to borrow a
constructed format (`--format timeless --deck-size 40`), so `legality-audit` applied
the 4-copy limit and the 15-card sideboard cap to a deck whose rules have neither,
nothing checked that the deck was drawn from the pool, `mana-audit` read the
universal 17-land default as over-landed (the constructed formula scaled down), and
deck-forge's Find and Tune searched the whole card database for a build that may
only run what was opened. `docs/plans/limited-sealed-support.md` recorded the gaps
from a live Sealed session; ADR-0054 gave every format family its own template and
left `limited` as the family to follow.

**Decision.** Limited is the third Format family, and what bounds it is the pool.

- **Two formats, one family.** `sealed` and `draft` are Formats with `family ==
  "limited"`: a 40-card minimum (`min_deck_size`), no copy limit (`max_copies`
  None — as many duplicates as the product included), no sideboard cap
  (`sideboard_size` None — the sideboard IS the unused pool, CR 100.4b), and no
  legality key (`pool_bounded`). Their `legality` is "legal" for any record because a
  limited deck's legality is pool MEMBERSHIP, which `legality_audit.check_pool_
  containment` audits instead (every copy in the main deck and sideboard is in the
  pool at that quantity; basics excepted, by record or by name).
- **The pool is the fifth zone.** `pool` joins `ZONES` (hydrated by the one seam,
  ADR-0046; the sidecar version bumps), counted by none of the deck analyses — every
  reader of "the deck" walks the zones it means (`HydratedDeck.deck_records`, the
  counted deck), never the all-zones bookkeeping list. `parse-deck --format sealed`
  pools every card a list holds across its Deck and Sideboard sections, keeping the
  split where the list has headers; a bare list or `--pool-only` is all pool.
- **The sideboard is derived.** In the hub a pool-bounded build's sideboard is the
  pool less the main deck (`DeckSession.derived_sideboard`) — emitted, never stored,
  never written to. "The sideboard is the unused pool" holds by construction; a cut is
  just leaving the deck; a card played from the pool or the sideboard is an add the
  pool bounds; the pool itself never shrinks or grows by a move. Entering a
  pool-bounded format pools everything the build holds; leaving one stores the
  derived sideboard and empties the pool.
- **The pool is the copy limit.** `engine.copy_limit` reads the pool's count for a
  pool-bounded build (basics unlimited), so the ONE add rule (`check_copy_add`) is
  also containment, Find strips by it, and the tuner's per-name copy model takes the
  pool as `available` and owns all of it (an opened pool is never crafted or bought:
  no wildcard or USD readout).
- **Find and Tune search the pool and nothing else.** `engine.search_for` is the
  bulk-backed `search_fn` for a format whose pool is the database, and
  `card_search.filter_records` — the ONE filter implementation `search_cards` itself
  runs after its bulk scan — over the opened pool's records otherwise, with the game
  gate off (the records are the pool, whatever game they were opened in). The
  deterministic core still names every card; it just cannot name one the builder did
  not open.
- **The mana band is the limited norm.** `mana_audit.limited_land_target`: 17 per 40,
  a 16–18 band (one fewer for a low curve or real ramp, one more for a top-heavy
  pool), never the constructed formula scaled down. The FAIL floor is one below the
  target but never below the band's own minimum (16 per 40): a 16-land target does
  not make 15 lands merely a warning.
- **Two read-only readouts, agent-free.** `set-scan --set CODE` (what a set holds:
  removal by rarity, sweepers, evasion, the biggest bodies, the curve — over
  `CardPool.set_records`, the index a set filter needs) and `pool-colors` /
  the snapshot's pool panel (every mono colour and colour pair the pool supports —
  playables, creatures, removal, evasion, power-4-plus bodies, rares — on equal
  footing, before any opinion). Removal and sweepers are the template roles
  (ADR-0051); evasion is the record's keywords. A one-click seed fills a first 40 in
  chosen colours from the pool's own cards plus basics — a starting point, never a
  finished deck. The SPA reads `pool_bounded` / `family` from the served row like every
  other family fact (ADR-0054).

**Considered and rejected.** Borrowing a constructed format at 40 cards (the
status quo: wrong copy limit, wrong sideboard cap, no containment, a wrong land
band, and a database-wide Find). A `--pool <file>` flag on `legality-audit` (the
pool rides inside the deck JSON as a zone, so the audit reads it like any other).
A stored sideboard plus a "cards + sideboard ⊆ pool" rule (double bookkeeping;
every UI move becomes remove-then-add; the derived sideboard makes the invariant
structural). A faked legality key for limited (membership is the question, and a
set's legality status is not). A size floor in `is_valid_deck_size` (a build's
size is its target; the 40-card floor is `deck_minimum`'s, as for constructed).

**Consequences.** `Family` gains `limited`; `Format.max_copies`, `sideboard_size` and
`legality_key` are Optional and every reader is None-safe (an unlimited copy count
reads as unlimited in the SPA, which takes every copy limit from the served row and
derives none). `filter_records` is the seam a second record-bounded search (a cube,
a collection) can reuse. The seed replaces the main deck and keeps
what it replaced for one undo (a first draft, never a finished deck); a paper sealed pool's printings are what was opened, so
`card-search --format sealed` is never Arena-gated. Non-goals: pack generation and
draft simulation (cube-wizard's), a matchup model, ranking the colour pairs
(enumerated on equal footing; the choice is the builder's).
