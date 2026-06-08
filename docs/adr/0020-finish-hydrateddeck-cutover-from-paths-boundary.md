# Finish the HydratedDeck cutover; `from_paths` is the read boundary only for non-content-addressed CLIs

ADR-0012 moved the deck-analysis functions onto a single `HydratedDeck` value and
introduced three construction adapters — `from_session` (in-process), `from_parsed(
by_name=… | records=…)` (the low-level seam), and `from_paths(deck_path, hydrated_path)`
("the CLI adapter, the one untrusted-JSON boundary"). The one-commit cutover migrated
~30 sites but left three stragglers on the old `(deck, list[dict | None])` shape —
`card_summary`, `deck_diff`, `build_deck` — and shipped `from_paths` with **zero
callers**: every migrated CLI read its own JSON and called `from_parsed(records=)`
instead. A later architecture review noticed both gaps.

## Decision

Finish the cutover, and resolve what `from_paths` is actually for.

- **`deck_diff` takes two `HydratedDeck`s** (`deck_diff(old, new)`); its two
  `build_card_lookup` joins move into the value. Its `main` is a pure
  read→construct→echo with no other use of the input, so it builds both sides via
  **`from_paths`** — becoming its first real caller.

- **`card_summary` stays a list renderer** — a *cache viewer* whose dominant job is
  dumping an arbitrary hydrated file supplied with **no deck**, which a deck-scoped
  `HydratedDeck` cannot represent (no deck-less constructor; `.records` would drop
  cache cards in no deck and dedup). Only its `--sideboard` branch (which *has* a deck)
  builds a `HydratedDeck` via `from_paths` and reads
  `entries(zones=("sideboard",))`, replacing the bespoke `_filter_to_section` join. A
  deliberately **half-migrated** function — the asymmetry reflects that it is a cache
  viewer, not deck analysis.

- **`build_deck` returns `(HydratedDeck, unmatched)`** via `from_parsed(new_deck,
  by_name=merged_index)` — the **trusted** path, because the merged records (input
  hydrated + freshly-looked-up `extra_hydrated`) are assembled in-process, where the
  `records=` stub-guard (for untrusted JSON) does not apply. It is the **producer
  exception**: it mutates the deck and resolves adds *between* read and construct, so it
  can neither take nor be built by `from_paths`; it *mints* the records the analysis
  functions later consume. The `total_cards` / `total_sideboard` rewrite folds inside so
  the returned `.deck` is final (previously the CLI did it post-call — the legality-audit
  `deck_minimum` regression).

- **`from_paths` is the boundary only for CLIs that do not content-address their
  output.** The four already-migrated analysis CLIs — `deck_stats`, `mana_audit`,
  `legality_audit`, `combo_search` — **keep `from_parsed(records=)`, correct by
  necessity**: each SHA-keys a disposable output-cache path from the *raw input bytes*
  (`_default_output_path(deck_content, hydrated_content, …)`), so it must hold the bytes.
  `from_paths` reads the files and hides the bytes, so adopting it there would force a
  wasteful double-read of 100 KB+ hydrated files. The fault line is **content-addressing**,
  not house style: hold-your-bytes CLIs use `from_parsed(records=)`; pure read→construct
  CLIs (`deck_diff`, `card_summary`-sideboard) use `from_paths`. `from_parsed(records=)`
  thus stays the live untrusted-JSON join for the content-addressed fleet, and is also
  `from_paths`'s own engine.

## Why not sweep every CLI onto `from_paths`

It looked uniform but isn't viable: the analysis fleet is content-addressed and
genuinely needs the input bytes for its SHA-keyed cache. Forcing `from_paths` there means
either a double file read, or relocating the hash onto the parsed value (changing every
cache key and coupling output-path logic to `HydratedDeck`) — churn on green code for a
cosmetic win. The honest outcome makes `from_paths` real exactly where it fits (0 → 2
callers) and *documents* why the rest keep `from_parsed(records=)`.

## Why `build_deck` returns the value via `by_name`, not `records=`

`records=` is the untrusted constructor (it RAISEs on deck-entry stubs); using it on data
we just assembled in-process misuses that guard. `by_name` is the trusted path, projects
to the final deck's distinct names, and yields a strictly cleaner `new-hydrated.json` (no
`None`s, deck-ordered, cut-card records dropped). Downstream consumers re-project to
`new-deck.json` names, so dropping cut-card records is safe — confirmed no consumer reads
`new-hydrated.json` for the pre-cut card set.

## Behavior change

Under `--sideboard` / `deck-diff`, a stale or stub hydrated file (deck-entry stubs where
records belong) now RAISEs `ValueError` via `from_paths`, where the old `_filter_to_section`
/ parallel-list path silently produced an empty or odd result. An improvement, but
user-visible.

## Known limit

An add whose `lookup_single` never resolved is in the deck but absent from `build_deck`'s
returned `.records` — the same parallel-list gap as before, now behind the value and
queryable via `.has_records`. Closing it would require moving network I/O into
`build_deck`, which breaks its purity; deliberately not done.

## What this stops re-suggesting

- Don't "finish consistency by moving the analysis CLIs onto `from_paths`" — they're
  content-addressed and must hold their input bytes for the SHA-keyed cache.
- Don't "make `card_summary` take a `HydratedDeck`" or add a deck-less constructor — it's
  a deck-less cache viewer; the half-migration is correct.
- Don't "fix" `build_deck` back to the `(deck, records, unmatched)` triple — the single
  value is the point, and it's the producer exception to the `from_paths` boundary.
- Don't delete `from_paths` as unused — it now has the two callers it was designed for.
