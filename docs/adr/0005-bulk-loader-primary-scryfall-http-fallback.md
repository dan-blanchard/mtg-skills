# Card-data lookups go through bulk_loader; HTTP is fallback only

The Scryfall REST API is the obvious way to fetch card data — it's
documented, fast, and well-maintained. Most MTG tools call it directly.
This repo deliberately doesn't.

**Decision:** Routine card-data access (oracle text, prices, type lines,
color identity, set codes, etc.) goes through
`mtg_utils.bulk_loader.load_bulk_cards`, which reads the daily-refreshed
`default-cards.json` (~500 MB) with a pickled-sidecar index for ~5–10x
warm-load speedup over re-parsing the JSON. **No new code path should
add a Scryfall HTTP call for routine lookups** — extend the bulk_loader
or add a sidecar index instead.

**Carve-outs (legitimate HTTP usage):**

- `download_bulk.py` — one-time / daily bulk-data refresh. The HTTP call
  here is *how* the bulk file gets populated; it's setup, not runtime.
- `scryfall_lookup.py` — fallback when a name isn't in the bulk dump
  (e.g., a brand-new card released since the last refresh). Strictly a
  cache-miss path.
- `rulings_lookup.py` — per-card oracle rulings. Scryfall has no bulk
  dump for rulings; the rulings_lookup CLI hits `/cards/:id/rulings`
  with a 30-day file cache to keep the request count low.

**Why this is the right call:** the bulk path is faster (no network
round-trip), works offline (which the lgs-search Phase-2 sweep relies
on for 62 sequential card lookups), avoids rate limits (Scryfall asks
for 50–100ms gaps; 31-card batches would burn a couple of seconds just
on throttling), and is reproducible (`compute_input_hash` on a card
list returns the same value regardless of when the orchestrator runs).

**What this stops re-suggesting:** future code reviews looking at
`card-search` or `scryfall-lookup` and asking "why don't we just hit
the API?" or "wouldn't `httpx` be simpler than this 500 MB cache?" —
the cache *is* the simplification. Calling the API directly would
turn every batch into a rate-limit-bounded sequence of round-trips.
