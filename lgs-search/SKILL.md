---
name: lgs-search
description: Search The Gathering Place + Atomic Empire (LGS) and TCGPlayer + Mana Pool (online) for an MTG card list, allocate to minimize total cost across at most three carts, and hand off pre-loaded headed browser windows for checkout.
compatibility: Requires Python 3.12+, uv, and Playwright (Chromium).
license: 0BSD
---

# LGS Search

Source an MTG card list across the two local game stores (The Gathering Place, Atomic Empire) and the two big online catalogs (TCGPlayer, Mana Pool), allocating to minimize total cost. The user ends up checking out at most three carts: TGP, AE, and one of (TCGPlayer | Mana Pool), whichever is cheaper for the spillover.

## The Iron Rule

**NEVER report a price the CLI did not return.** Every price in the
summary must come from a real Playwright search/cart result. Scryfall
USD is used internally as a proxy for the LGS-vs-online spill check —
it does NOT appear in the report. Out-of-stock and unfindable lists
must reflect actual page outcomes, not training-data guesses.

## Setup (First Run)

```bash
uv sync --directory <skill-install-dir>
uv run --directory <skill-install-dir> playwright install chromium

# One-time login per store (saves to ~/.cache/mtg-skills/lgs-profiles/<store>/):
lgs-search login --store tgp
lgs-search login --store atomic_empire
lgs-search login --store tcgplayer
lgs-search login --store manapool
```

If you skip the explicit logins, the orchestrator will pop a headed
window the first time it detects "not logged in" — slightly more
disruptive but functionally equivalent.

## Workflow

### Phase 1 — Resolve input

Accept either a parsed-deck JSON or a plain text list (one card per
line, optional `Nx` prefix). Mainboard + sideboard are summed. Basic
lands (Plains, Island, Swamp, Mountain, Forest, Wastes) are filtered
out by default and surfaced in the summary; pass `--include-basics`
to override. Snow basics (Snow-Covered Plains etc.) are NOT skipped.

### Phase 2 — LGS sweep

Both LGS are queried for every card in parallel via a thread pool
with per-store concurrency caps. Results are kept as the cheapest
listing matching the user's preferences (condition, foil, preferred
set). Failures fall through to None and that store is treated as
"not in stock" for the card.

### Phase 3 — Allocate

For each card:

- If neither LGS has it OR the online price (Scryfall USD proxy) is
  much cheaper (default: >20% OR >$2), the card spills to the online
  bucket.
- Otherwise: cheapest LGS wins. If both LGS prices are within $1 or
  10%, the card is consolidated to the LGS with the higher running
  cart total to minimize trips.
- Quantity > 1: split across stores when no single store can fill the
  full quantity. Residual goes online.

### Phase 4 — Online optimize

The spillover list is submitted to TCGPlayer Mass Entry and Mana
Pool's `/add-deck`. Each site's optimizer runs (consolidates
sellers, computes shipping). The cart with the lower **items +
shipping** total is selected. Tax is computed at checkout.

### Phase 5 — Confirmation gate + cart build

The full markdown allocation is printed; default-N prompt asks
whether to proceed. Pass `--yes` to skip the prompt; pass `--dry-run`
to stop after generating the allocation without touching any cart.

Before any cart is touched, every target store's cart is inspected.
If any cart is non-empty, the run aborts with a clear message naming
the polluted store(s); pass `--clear-existing-carts` to empty them
automatically before adding.

### Phase 6 — Unfindable + relaxed retry

Cards that no store can source after Phase 5 are listed. The user is
prompted to retry with relaxed constraints (allow MP/HP, allow foil,
drop preferred-set bias). `--retry-relaxed` automates one such retry.

### Phase 7 — Handoff

For each store with a non-empty cart, a headed Chromium window is
launched on the cart URL using the store's persistent profile. The
user reviews and checks out manually. Pass `--no-handoff` to skip.

## Flag reference

```
lgs-search \
  --input <deck.json | cards.txt> \
  [--collection <collection.json>]
  [--bulk-data <default-cards.json>]
  [--condition {nm,lp,mp,hp,any}]   # default: lp (worst condition allowed)
  [--allow-foil]
  [--prefer-set <SET>]
  [--lgs-online-threshold-pct 20]
  [--lgs-online-threshold-usd 2.00]
  [--consolidate-threshold-pct 10]
  [--consolidate-threshold-usd 1.00]
  [--no-handoff]
  [--dry-run]
  [--retry-relaxed]
  [--clear-existing-carts]
  [--include-basics]
  [--yes]
  [--search-timeout-seconds 20]
  [--cart-timeout-seconds 30]
  [--max-retries 3]
  [--output-dir <dir>]
  [--resume <prior-allocation.json>]
```

## Failure modes

- **Site selectors changed.** Adapter raises `StoreSelectorError` with
  the failed selector and the URL where it was missed. The orchestrator
  surfaces the error and aborts the sweep for that store; it does NOT
  silently skip cards.
- **Login expired.** Detected per-store via `is_logged_in`. The lazy
  fallback launches a headed login window mid-run; close it once
  signed in and the run resumes.
- **Cart line-item caps.** Some stores cap line items per cart. If
  hit, the adapter partial-fills and reports a residual; the residual
  is logged in the sidecar and surfaced in the summary.
- **HTTP 429 / rate limit.** Respected via `Retry-After` or 30s
  default; 3 consecutive 429s on one store skips that store with a
  warning.
- **Cart-add failure during Phase 5.** Fatal. Sidecar is saved so the
  user can `--resume` after fixing.

## Hand-back to deck-wizard / cube-wizard

This skill never modifies decks. Unfindable cards are surfaced in the
markdown summary — the calling skill or the user decides whether to
substitute. There is no automatic "swap in a similar card" path.
