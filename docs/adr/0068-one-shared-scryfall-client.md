# One shared Scryfall client

ADR-0005 keeps Scryfall a fallback: card data comes from the bulk. Six sites still
talk to Scryfall: `scryfall_lookup.fetch_card` (`/cards/named`, the bulk's
cache-miss path), `price_check._api_price_lookup` (the same read, for a null bulk
price), `rulings_lookup` (`/cards/:id/rulings`), `card_symbols` (symbol SVGs on
`svgs.scryfall.io`), `guide_card_hovers` (card images on `cards.scryfall.io`) and
`art_fetcher`'s subtype catalogs (`/catalog/*`). They were built three ways:
`fetch_card` and `_api_price_lookup` were line-for-line copies with no timeout and
no retry; rulings had a 15 s timeout and no retry; the other three used
`_http.HttpFetcher`, each with a different throttle (0.05 s, 0.1 s, none: the
catalog loop sent six requests with no gap). None sent a deliberate `Accept`
header (`requests` sends `Accept: */*` by default). They identified
themselves as `commander-utils/0.1.0`, a name from before the repo was renamed, or
as the art fetcher's `mtg-utils/art-fetcher`. The rulings cache and the
`scryfall-lookup --batch` result files lived under `$TMPDIR`, the latter with no
lifetime.

**Decision (Dan, 2026-11-27).**

1. **One shared Scryfall client, used by every site, with its caches unified under
   the project cache directory.** `mtg_utils._scryfall.ScryfallClient` is an
   `HttpFetcher` configured once for Scryfall. Its caches live under
   `<cache_root>/scryfall/`, one subdirectory per site.
2. **The identity sent to Scryfall is `mtg-utils/<package version>`,** read from
   the installed package's metadata (`importlib.metadata`). The version is that
   of whichever installed distribution ships `mtg_utils`: each skill installs the
   package under its own name (`mtg-utils`, `deck-wizard`, …), so a deck-wizard
   run reports deck-wizard's version. Every `pyproject.toml` is at 0.1.0 today.
   With no distribution found it is `mtg-utils/unknown`. It replaces
   `commander-utils/0.1.0` for Scryfall. `mtg-utils/art-fetcher` stays for the
   ASCII-art sites it was meant for; Scryfall no longer receives it.

**Scryfall's limits** (scryfall.com/docs/api/rate-limits, "Rate Limits"):

- `/cards/search`, `/cards/named`, `/cards/random` and `/cards/collection`: 2
  requests per second;
- every other API endpoint: 10 requests per second;
- the `*.scryfall.io` file hosts (images, symbol SVGs): no rate limit;
- a client over a limit gets HTTP 429 and is locked out for 30 seconds, and
  continuing to send requests while locked out may result in a temporary or
  permanent ban.

The API page (scryfall.com/docs/api, "API Documentation") requires a `User-Agent`
naming the application and an `Accept` header. It names
`application/json;q=0.9,*/*;q=0.8` (and `*/*`) as acceptable values. *Source note:*
the 2026-11-27 review read both pages. A second fetch from this machine was refused
(HTTP 403), so the lines above are the review's reading, not a verbatim quote.

**The client** (`_scryfall.py`, built on `_http.HttpFetcher`, which gained the
options it lacked: headers, a `(connect, read)` timeout, a `pace` hook before each
network attempt, a `backoff` policy, a `check` on a body before it is cached, an
injectable session and backoff sleep, a per-call lifetime and refresh; and
`RequestGap`, a pacer with a gap per lane):

- `get_json(path_or_url, *, params=None, cache=None, not_found_none=False)` and
  `get_bytes(...)`. A path is under `https://api.scryfall.com`. A 404 raises like
  any HTTP error unless `not_found_none`. `cache=Cache(key, max_age_seconds,
  refresh)` caches that call under the client's directory. `get_json` raises
  `requests.JSONDecodeError` for a body that is not JSON. That is the type
  `Response.json()` raised before, a `RequestException` every caller already
  catches. Such a body is never cached, and a cached copy that no longer decodes is
  dropped and fetched again.
- It also satisfies the `Fetcher` protocol (`fetch(url, cache_key)` at the
  client's own lifetime), so the sites that take a `Fetcher` default to a client
  and their tests still pass a fake.
- **Pace:** one process-wide pacer (`_scryfall.GAP`), on a monotonic clock and
  shared by every client, with a gap per endpoint class between request starts.
  The four search-class paths get 550 ms (their own lane, beside the API lane).
  Every API request gets 110 ms. The file hosts get a 50 ms courtesy gap, our
  choice, since Scryfall sets no limit there. That is a tenth over each published
  minimum, because the limit runs on the server's clock, not ours. Two sites
  called back to back still keep it.
- **Timeout:** 5 s to connect, 30 s to read. **Retries:** one. After a 429 the
  client waits its `Retry-After` (seconds or an HTTP date, capped at 120 s), else
  30 s, the lockout. After a connection error or a timeout it waits 2 s. Any other
  HTTP error raises at once.
- **Scryfall unavailable:** a request that still fails after its retry, on a
  429, a connection error or a timeout, trips one process-wide latch. Every later
  network request, from any site, then fails at once with
  `_scryfall.ScryfallUnavailable`, a `requests.ConnectionError`, which every
  caller already handles. `lookup_cards` records each remaining name as missing,
  and `SymbolSet.load` warns once and prints text. Cache hits still serve. The
  latch clears only in a new process, or through `reset_unavailable()` in tests.
  `card_symbols` keeps its own loop-local stop after the first failure: it still
  gives one warning per run, and it also stops a `Fetcher` that isn't the
  client.
- **Accept:** `application/json;q=0.9,*/*;q=0.8` for the API and `*/*` for the
  file hosts, both values Scryfall's API page accepts.
- **Error handling stays each caller's,** as before: `fetch_card` returns `None`
  on a 404 and raises otherwise; `lookup_cards` turns one name's failure into a
  missing name; `card_symbols` warns and prints `{CODE}` text; `art_fetcher`
  exits non-zero.

**Caches** (all under `<cache_root>/scryfall/`; entries in the old places are
not migrated, so they are fetched again once):

| Site | Directory | Lifetime |
|---|---|---|
| rulings | `rulings/<oracle_id>.json` (the raw response) | 30 days; `--refresh` |
| symbols | `card-symbols/<CODE>.svg` | 365 days |
| card images | `card-images/<scryfall-id>.jpg` | 365 days |
| catalogs | `catalog/<catalog>.json` | 7 days |
| `scryfall-lookup --batch` | `lookup/hydrated-<sha>.json` (default `--cache-dir`) | 24 h; expired files pruned on each write |

The batch files are this tool's own result files, not Scryfall responses. They
got a lifetime because they no longer sit in a temp dir that the OS empties. 24 h
matches the bulk's own freshness window: a name the bulk lacked was fetched from
Scryfall, and its prices age as the bulk's do.

**Behaviour changed on purpose.**

- Named lookups (`fetch_card`, the price fallback) are paced at 550 ms. They used
  to sleep 100 ms plus the round trip, which could exceed 2 a second. They now time
  out, where they used to wait forever, and they retry once. Rulings' timeout went
  from 15 s to (5 s, 30 s), and they retry once too.
- The catalog loop is now paced at 110 ms. Symbols and images wait 50 ms, not
  0.05 s and 0.1 s of sleep before each request. `build_hovers`' extra `throttle`
  defaults to none.
- **Worst-case wait with Scryfall unreachable** (one failing request; a 100-name
  `scryfall-lookup --batch` with no bulk):

  | | refused | connect hangs | read hangs | 429 lockout |
  |---|---|---|---|---|
  | before ADR-0068 | ~0.1 s; 100 quick failures | no timeout: forever | forever | 1 failure per name |
  | first cut of this client (2 retries, 5 s / 10 s, 30 s timeout) | 15 s; 25 min | 105 s; ~3 h | 105 s; ~3 h | 15 s each; 25 min, sent through the lockout |
  | now | 2 s; 2 s | 12 s; 12 s | 62 s; 62 s | 30 s; 30 s |

  "Now" is two attempts and one wait for the first failing request. The other 99
  names fail at once on the latch.
- A card with no Scryfall `id` gets no rulings from the API path even if a cached
  copy exists. The cache is keyed by `oracle_id`, but the request needs the `id`,
  and every Scryfall card record carries one.
- The catalogs no longer follow `fetch-art --cache-dir`. That option still holds
  the ASCII-art responses.

**Kept for compatibility:** `scryfall_lookup.fetch_card` (patched by tests,
imported by `HydratedDeck.acquire`) and `price_check._api_price_lookup` are thin
wrappers over `_scryfall.fetch_named`, the single `/cards/named` read.
`rulings_lookup._fetch_rulings` keeps its name. `RATE_LIMIT_DELAY` and
`SCRYFALL_NAMED_URL` are gone; nothing outside the two copies used them.

**Tests** never reach Scryfall or the user's cache. `tests/conftest.py` gives every
test a pacer and backoff that never wait, a clear unavailable latch and its own
Scryfall cache directory, unless the test sets `MTG_SKILLS_CACHE_DIR` itself. The `scryfall_wire` fixture answers a client's
requests below a real `requests.Session`, so headers, pacing, retries and the
cache run as they do in production.
