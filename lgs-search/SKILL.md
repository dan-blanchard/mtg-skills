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

## Running the orchestrator

The orchestrator is a normal long-running CLI that opens headed
Chromium windows during Phase 5 / Phase 7. It is **safe to launch
from a Bash subprocess**; the user closes the headed windows in the
OS to advance, and the subprocess sees the close events without any
terminal interaction. Do NOT reflexively ask the user to invoke with
the `!` prefix — that's only needed when something reads from
**stdin**, and with `--yes` skipping the initial confirmation plus
already-saved logins plus clean carts, no `input()` prompts fire.

Recommended invocation for an agent:

```bash
uv run --directory <skill-install-dir> lgs-search \
    --input <list> --output-dir <dir> --yes
```

Use `run_in_background=True` and tail the output file if you need to
report progress. Only fall back to suggesting `! lgs-search ...` when
you have a specific reason to expect a stdin prompt (login fallback
firing on an unlogged-in store, or a cart-pollution prompt without
`--clear-existing-carts`).

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

- If neither LGS has it OR the online price proxy is much cheaper
  (default: >20% OR >$2), the card spills to the online bucket.
- Otherwise: cheapest LGS wins. If both LGS prices are within $1 or
  10%, the card is consolidated to the LGS with the higher running
  cart total to minimize trips.
- Quantity > 1: split across stores when no single store can fill the
  full quantity. Residual goes online.

The online price proxy is the **cheapest non-foil non-digital USD
across all printings** of each card (from Scryfall bulk data), not
the default printing's USD. Default-printing prices often miss cheap
reprints (e.g. Beast Within's default has no `usd`, but its cheap
reprint is $0.50; Kessig Wolf Run's default is ~$15, cheapest
reprint $0.30). Without bulk data the proxy is 0.0 — the spill check
goes silent and every in-stock LGS listing wins, even when MP/TCG
would be 5-30x cheaper.

The orchestrator **auto-detects** `default-cards.json` on startup
(searches `$MTG_SKILLS_BULK_DATA`, `$MTG_SKILLS_CACHE_DIR`,
`~/.cache/mtg-skills/`, `$CWD`, `$CWD/.cache`, plus parents up two
levels). When nothing is found, it prints a loud warning explaining
the silent-no-spill failure mode and pointing at `download-bulk`.
Don't pass `--bulk-data` unless you need a specific path.

### Phase 4 — Online optimize

The spillover list is submitted to TCGPlayer Mass Entry and Mana
Pool's `/add-deck`. Each site's optimizer runs (consolidates
sellers, computes shipping). The cart with the lower **items +
shipping** total is selected. Tax is computed at checkout.

Both Marketplaces' bulk-submit endpoints **append to the existing
cart** rather than replacing it, so the optimizer's totals reflect
the WHOLE cart (pre-existing items + new submission). The adapter
runs a `get_existing_cart` pre-flight at the top of
`bulk_submit_and_optimize` and raises `CartNotEmptyError` when
non-empty; the orchestrator catches this in `optimize_marketplace`'s
per-store loop, prints a clear "[store] cart already has N items"
error, and continues with whichever Marketplace still works.

If you see this error, the user must clear the polluted cart before
re-running. MP's UI "Clear cart" button is broken in MP itself
(verified: the click fires Sentry errors and a no-op metadata-sync
RPC), so the user clears MP manually in the headed handoff window.
TGP's `clear_cart` works programmatically and is invoked when
`--clear-existing-carts` is passed.

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
- **Marketplace cart pollution.** `bulk_submit_and_optimize` raises
  `CartNotEmptyError` if the Marketplace's cart already has items
  (Phase 4 would mix the user's pre-existing items into the optimizer
  comparison). The orchestrator skips that Marketplace and continues
  with the other; user clears manually before re-running.
- **TCGPlayer captcha.** TCG's anti-bot detects Playwright's
  persistent_context and blocks login (verified). The
  per-store-failure-tolerant `optimize_marketplace` skips TCG with a
  logged message and lets MP win by default. Don't waste time trying
  to log in to TCG headed — the captcha can't be cleared.
- **MP "Clear cart" no-op.** MP's own SvelteKit handler for the
  Clear cart button throws (Sentry-reported) and the cart never
  changes. `--clear-existing-carts` falls back to a manual prompt for
  MP. The user clears in the headed cart window and presses Enter.
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
