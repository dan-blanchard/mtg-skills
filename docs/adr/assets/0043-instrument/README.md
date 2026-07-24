# ADR-0043 measurement instruments (committed for verifiability)

The acceptance instruments and protocol state for the ADR-0042/0043
discovery program. Committed here (colocated with the ADR they implement)
after the 2026-07-23 gate-(b) review found the instrument "cited as
committed but not findable" — session scratch dirs are not audit
surfaces.

- `harness.py` — the 20-commander EDHREC discovery-study harness
  (pools/recall/drift). Network-fetching, cache-dir-relative; run from
  `mtg-utils` with this dir on `sys.path`. NEVER imported by production
  code or tests.
- `ledger_ordering.py` — the ledger ordering score: within each pair-row
  class per panel deck, the fraction of (adjudicated-survivor,
  adjudicated-kill) pairs the production sort orders correctly.
  Committed-config baseline (2026-07-23): 0.464 over 521 pairs.
- `verdict-ledger.json` — 380 frozen adjudications (grounded v2 panel
  protocol: verbatim oracle quotes, rules-lookup citations, unanimous
  freeze / split re-adjudicate-once). The protocol's source of truth,
  rebuilt verbatim from workflow journals.
- `ordering-scores.jsonl` — instrument measurement log.

These are measurement artifacts, not shipped code: no skill declares
them, CI does not run them, and the paths inside assume a configured
MTGJSON bulk plus the study cache.
