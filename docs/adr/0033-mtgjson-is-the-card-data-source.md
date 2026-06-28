# 33. MTGJSON AllPrintings is the card-data source; an adapter preserves the Scryfall record shape

Date: 2026-06-28

Status: Accepted

Relates to: [0005](0005-bulk-loader-primary-scryfall-http-fallback.md) (bulk-primary
+ Scryfall-HTTP-fallback — this redefines "bulk" as MTGJSON, keeps the HTTP fallback),
[0027](0027-card-ir-replaces-regex-detection.md) / [0028](0028-consume-phase-rs-not-fork.md)
(the Card IR is already projected from phase-rs, which parses MTGJSON oracle text — so
this aligns the structured-field record with the IR's own corpus). Supersedes the
2026-06-19 "HYBRID-GO, DEFER" spike conclusion.

## Context

A 2026-06-19 spike evaluated MTGJSON as the card-data source and landed on
"hybrid, defer": adopt MTGJSON only for a few gameplay fields, keep Scryfall for
prices / rarity / set / images / tokens "because MTGJSON lacks them." That premise
was wrong — it evaluated the print-*agnostic* **AtomicCards** file, not
**AllPrintings**. Verified against live MTGJSON v5.3.0:

- AllPrintings' per-printing `Card (Set)` carries the entire print layer: `rarity`,
  `setCode`, `number`, `availability`, `finishes`, `language`, `artist`,
  `frameVersion`, plus `identifiers` (scryfallId/scryfallOracleId/mtgArenaId/…).
- Arena name aliasing is present: `printedName` (added v5.3.0), `flavorName`,
  `mtgArenaId`, `foreignData`.
- Prices are *richer* than Scryfall — AllPrices(Today): tcgplayer / cardkingdom /
  cardmarket / **manapool** (v5.3.0) / cardhoarder, **retail + buylist**,
  normal/foil/etched, 90-day history (vs Scryfall's single-source point-in-time).
- `rulings` are inline (Scryfall needs a per-card API call).
- The card pool joins cleanly by `scryfallOracleId` (100% of commander-legal cards;
  34,612 oracle_ids cover every real card; the Scryfall-only oracle_ids are
  art_series / emblems / memorabilia).

The **only** genuine Scryfall-exclusive is image **URLs**, and those reconstruct
deterministically from `identifiers.scryfallId` via the public Scryfall CDN. So
MTGJSON is effectively a superset; the hybrid was an artifact of the Atomic-only view.

## Decision

**Make MTGJSON `AllPrintings` (+ `AllPricesToday`) the single card-data bulk source.
A pure adapter at the `bulk_loader` seam translates each MTGJSON record into the same
Scryfall-shaped dict the ~30 downstream read-sites already consume, so call sites stay
unchanged.** Scryfall's HTTP API is retained only as the thin per-card fallback of
ADR-0005 (for the rare card MTGJSON does not carry); the Scryfall *bulk* download is
no longer required.

Implementation:

- `download-mtgjson` (mirrors `download-bulk`): fetches `AllPrintings.json.gz` +
  `AllPricesToday.json.gz` to `~/.cache/mtg-skills/mtgjson/`, 24h freshness, eager
  sidecar build.
- `_mtgjson/adapter.py` — pure per-card translation; `_mtgjson/load.py` — flattens the
  set-keyed document to the flat list.
- `bulk_loader.py` is the seam: `default_bulk_path()` prefers the MTGJSON file (Scryfall
  bulk is a graceful fallback); `_read_source` translates when the path is
  `AllPrintings.json`; the sidecar caches the *translated* records (load stays ~0.4s).
  `SIDECAR_VERSION` bumped to 2; sidecar staleness keys on both source files so a daily
  price refresh invalidates it.

The non-obvious reshapes the adapter absorbs (each verified against live data):

1. **DFC collapse** by `otherFaceIds` UUID linkage (not `name` — names repeat across
   printings): the two faces of transform/modal_dfc/split/adventure/flip/aftermath/
   reversible merge into one record with `card_faces[]`; meld pieces stay separate
   (their links never form a shared key), matching Scryfall.
2. **Layout-aware top-level fields**: Scryfall populates top-level `power`/`toughness`
   (flip, adventure), `mana_cost` (front for flip, `"A // B"` for adventure/split/
   aftermath), and `colors` (those four) but leaves them on `card_faces` for true
   two-face cards — replicated so `card_pt_int` / pip-counting / color reads don't
   regress.
3. **Oracle-level legalities**: MTGJSON legality is *per-printing*, so an oversized /
   30th-Anniversary / gold-border printing reads `not_legal` for a format the card is
   otherwise legal in. Aggregate most-permissively across a card's printings, fill
   omitted formats `not_legal`, lowercase values, and gate the Arena-only formats on
   Arena availability.
4. **Prices** joined from AllPricesToday by uuid → Scryfall's flat `prices.{usd,
   usd_foil,usd_etched,eur,eur_foil,tix}`.
5. **image_uris** reconstructed from `scryfallId` (front/back faces).
6. **Tokens + meld** `all_parts` rebuilt from `relatedCards.tokens` + `otherFaceIds`
   (the `combo_piece` checklist links Scryfall carries are dropped — nothing reads them).

## Verification

- **Signal parity**: every card in the committed test snapshot was translated from live
  MTGJSON and run through `extract_signals_hybrid` over the *same* projected IR —
  **717/717 signal-identical** with the prior Scryfall records, 0 type_line/cmc diffs.
- **Legality**: across 30,969 commander-legal cards, MTGJSON-aggregated legality agrees
  with Scryfall **exactly** for commander / legacy / vintage / modern / pioneer /
  standard / pauper. The only differences are ~0.09% in Arena formats
  (historic/timeless/historic-brawl), all MTGJSON-*more*-permissive and dominated by
  brand-new sets the local Scryfall data predates (currency, not error) — MTGJSON never
  *under*-marks a Scryfall-legal card.
- Full suites green (mtg-utils + deck-forge) with MTGJSON live as the bulk source and
  against the MTGJSON-regenerated snapshot.

## Consequences

- **Currency**: new sets are legal/priced the day MTGJSON publishes, without waiting on a
  Scryfall bulk refresh.
- **Richer economics available** (multi-provider, buylist, manapool) and **inline
  rulings** — not yet wired into consumers, but now in-band for later.
- **Alignment**: the structured-field record and the phase-rs Card IR now derive from the
  same Oracle corpus, eliminating any text/IR drift (the spike's flagship payoff).
- **Costs**: `AllPrintings` is ~609 MB uncompressed (vs Scryfall ~500 MB) and the sidecar
  build runs the translate step (~8s, one-time per download); image URLs are reconstructed
  rather than read; ~0.09% Arena-format legality may read more-permissive than Scryfall.
- The committed test snapshot is now MTGJSON-sourced; `build-card-snapshot`'s source swap
  (foretold in `testkit.py`) is realized. The committed IR slices are unchanged.

## Alternatives considered

- **Hybrid enrichment (the spike's Phase A/B).** Rejected: the superset finding removes
  its rationale (there is no print/economic layer Scryfall uniquely provides except image
  URLs, which reconstruct from an id), and the IR project (ADR-0027) already delivered the
  "no oracle drift" payoff that motivated the deferred Phase B.
- **Keep Scryfall bulk as primary, MTGJSON for a few fields.** Rejected by the owner in
  favor of a single source.
- **Reshape every call site to a native MTGJSON shape.** Rejected: the adapter-at-the-seam
  keeps the blast radius to one module and preserves the proven downstream behavior.
- **Land it behind a `CARD_SOURCE` flag, flip after a parity window.** Considered; owner
  chose the all-at-once switch given the 717/717 parity + green suites.
