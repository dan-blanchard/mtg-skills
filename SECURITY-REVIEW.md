# Security Review — mtg-skills (personal safety-first fork)

**Repo:** `reveversant/mtg-skills_edit` · branch `claude/nifty-franklin-ytn9d1`
**Reviewed at commit:** `b08cafd`
**Date:** 2026-09-11
**Reviewer scope:** Full source read of `mtg-utils/src/mtg_utils/**` (the shared package every
skill symlinks), the six skill wrappers, and the deck-forge FastAPI backend.
**Your stated goals:** (1) AUD pricing / AUD vendors instead of USD, (2) no automated ordering,
(3) an "extremely safe" version with no access to anything confidential, PII, or damaging.

---

## 1. Executive summary

The MTG data/analysis core of this repo (deck parsing, stats, mana math, rules lookup, cube tools,
proxy printing, playtest sim) is **low risk**: it reads and writes local JSON/text, talks only to
well-known MTG data sources over HTTPS, ships **no committed secrets or PII**, and the local web
server defaults to loopback. Nothing in the core exfiltrates your data.

The risk is concentrated in **one subsystem — `lgs-search` and its `_stores/` adapters** — which is
precisely the part that conflicts with all three of your goals. It:

- **automates actions on your real, logged-in store accounts** (adds to cart, *deletes items from
  your live cart*, submits want-lists) — this is the "automated ordering / damaging" surface;
- **stores authenticated store session cookies unencrypted on disk** in a predictable path — this is
  the "confidential" surface; whoever can read that folder can act as you on those stores; and
- is **hard-wired to USD and to US storefronts** (TCGPlayer, Mana Pool, The Gathering Place, Atomic
  Empire), with Scryfall USD as a hidden allocation input — this is the "I want AUD" mismatch.

**Highest-leverage recommendation:** delete `lgs-search/` and `mtg-utils/src/mtg_utils/_stores/`
entirely (and their entry points). That single change removes the automated ordering, the stored
store credentials, the Playwright/persistent-profile machinery, and the USD-vendor coupling in one
stroke — and it is the cleanest path to the "extremely safe" build you asked for. Everything else
below is secondary hardening.

**Overall risk posture:** _Moderate as shipped, driven almost entirely by `lgs-search`. Low once
that subsystem is removed._

---

## 2. Trust model — what leaves your machine, what is stored locally

### 2.1 Outbound network endpoints (complete inventory)

Every host the code contacts, and why:

| Host | Purpose | Payload that leaves your machine |
|---|---|---|
| `api.scryfall.com`, `cards.scryfall.io` | Card data / bulk download | Card **names** you look up |
| `mtgjson.com` | Bulk card + price data (ADR-0033) | Nothing sensitive (bulk pull) |
| `json.edhrec.com` | Commander recommendations | Your **commander / card names** |
| `backend.commanderspellbook.com` | Combo detection | Your **deck's card list** (POST) |
| `cubecobra.com` | Cube fetch | Cube IDs you request |
| `magic.wizards.com`, `mtg.wiki` | Comprehensive Rules text | Nothing sensitive |
| `github.com`, `raw.githubusercontent.com` | phase-rs binaries + card-data | Nothing sensitive |
| `asciiart.website`, `www.asciiart.eu` | Proxy ASCII art | Card **subtype/name** search terms |
| `www.tcgplayer.com`, `manapool.com`, `www.atomicempire.com`, `the-gathering-place.mybigcommerce.com` | **Storefronts** | Your **want-list** + authenticated **session cookies** |

**Key finding:** no endpoint is an analytics/telemetry/exfil sink. The only places your *private
deck contents* leave the machine are (a) Commander Spellbook combo search
(`combo_search.py:168`), (b) the storefront want-list submissions, and (c) incidental card-name
lookups to Scryfall/EDHREC. None of this is PII, but if you consider your deck lists private, note
that combo search and store search transmit them.

**Your `brady.harrison.is@gmail.com` address, your name, and any account identity are never read or
transmitted by this code.** The store logins are done by *you* in a browser window; the code never
sees your username/password (see 2.3).

### 2.2 Local files the code reads (potential personal-data surface)

| Reader | Reads | Transmitted off-machine? |
|---|---|---|
| `mtga_import.py:162-183` | MTG Arena `Player.log` from your home dir | **No** — parsed locally into a collection map |
| `mark_owned.py`, `find_commanders.py` | A collection CSV/JSON you point them at | **No** — local intersection only |
| `bulk_loader.py`, `rules_lookup.py` | Cached bulk/rules data under `~/.cache/mtg-skills/` | No |

These are local-only. `Player.log` can contain your Arena activity, but nothing here ships it
anywhere. They are low risk and safe to keep if you use those features.

### 2.3 The crown-jewel asset: stored store session cookies

`profile_dir_for()` (`_stores/_common.py:207`) creates
`~/.cache/mtg-skills/lgs-profiles/<store>/` and Playwright's
`launch_persistent_context(profile_dir)` (e.g. `_stores/tgp.py:299`) persists **authenticated
session cookies** for TCGPlayer, Mana Pool, The Gathering Place, and Atomic Empire there, in
cleartext, indefinitely.

- The code **never captures your password** — you log in interactively in a headed window
  (`open_login`, `_stores/tgp.py:381`). Good.
- But the resulting **session cookies are as good as a login** for the life of the session. Any
  local process, backup, synced dotfiles folder, or another user on the machine that can read that
  directory can impersonate you on those stores — view saved shipping addresses, payment methods on
  file, order history, and place orders. **This is the single most confidential/damaging artifact
  the app creates.**
- It is correctly **git-ignored** (`.cache/` in `.gitignore`), so it won't be committed — verified
  no profile/cookie/`.env`/collection/`Player.log` files are tracked in the repo.

---

## 3. Findings (severity-ranked for a personal, safety-first deployment)

### H1 — Automated mutation of your live, logged-in store accounts *(directly contradicts "no automated ordering")*
**Where:** `_stores/tgp.py:221` (`add_to_cart`), `:340` (`clear_cart`); `_stores/atomic_empire.py:177`,
`:233`; `_stores/manapool.py` (`bulk_submit_and_optimize`), `:291` (`clear_cart`);
`_stores/tcgplayer.py:268`; orchestrated by `lgs_search.py`.
**Risk:** The tool programmatically **adds items to** and **deletes items from** your real carts, and
submits want-lists that append to your live cart. `clear_cart` iterates and removes up to 50 line
items (`tgp.py:350`) — a destructive action on your account state. It stops short of *placing* an
order (checkout is manual in the Phase-7 headed handoff), but "no automated ordering" is only half
true today: it automates everything up to the checkout button, destructively.
**Recommendation:** Remove the subsystem (see §5). If you keep it, at minimum gate `add_to_cart` /
`clear_cart` behind an explicit per-action confirmation and never pass `--clear-existing-carts`.

### H2 — Unencrypted, long-lived authenticated store cookies at rest *(the "confidential" surface)*
**Where:** `_stores/_common.py:207`; every `launch_persistent_context(...)` call site.
**Risk:** See §2.3. Session cookies for four real commerce accounts sit in a predictable path with no
encryption and no expiry management.
**Recommendation:** Remove the subsystem. If kept: store profiles under a `0700` directory, document
that they are credential-equivalent, and add a `logout`/`purge-profiles` command so you can wipe
them after a shopping session.

### M1 — USD-only pricing and US-only vendors *(the "I want AUD" mismatch)*
**Where:** `price_check.py` (`price_usd`, `:349`, `:448` `--budget` in USD); the Scryfall `usd`
proxy that silently drives store allocation (`lgs-search/SKILL.md` Phase 3); `_stores/_common.py:12`
(`PRICE_RE` parses `$`); all four store adapters are US storefronts.
**Risk:** Not a vulnerability, but a correctness/trust issue for you: allocation decisions are made
against **US dollar** prices from Scryfall and US retailers, and the "$" parser assumes USD. There is
**no AUD data source anywhere in the repo**, and none of the vendors are Australian.
**Recommendation:** This is *net-new work*, not a toggle — Scryfall does not publish AUD, so AUD
pricing/vendors would mean integrating an AU price source and AU store adapters (or dropping
automated pricing entirely and treating prices as manual). Cheapest safe path: remove the store
subsystem and, if you want budget checks, keep `price_check` but relabel/convert or feed it AUD
figures yourself.

### M2 — Local deck-forge server has no auth, no CORS policy, no CSRF protection
**Where:** `deck_forge_server.py:39` (`--host` overridable), `:68` (`uvicorn.run`); `_deck_forge/app.py`
(no `CORSMiddleware`, no auth dependency on ~40 routes including `POST /api/collection/import`,
`POST /api/builds/import`, `DELETE /api/builds/{id}`, `POST /api/deck/*`).
**Risk:** Defaults to `127.0.0.1` (good), but while the server is running, **any website you visit in
the same browser can issue state-changing `POST`s to `http://127.0.0.1:8765`** (classic local-server
CSRF — simple form posts need no CORS preflight). An attacker page can't *read* responses, but can
mutate your working deck, import/overwrite your collection, or delete saved builds. Passing
`--host 0.0.0.0` widens this to your whole LAN. **No RCE** — the `/api/handoff/*` endpoints are pure
in-process compute (`app.py:429-470`), no subprocess spawning.
**Recommendation:** Keep the default loopback bind; add a guard/warning if `--host` is non-loopback;
optionally add a random per-launch token the SPA echoes in a header, and reject requests missing it.
Low urgency for a single-user local machine, but it's the one "damaging" vector in the core.

### M3 — Untrusted pickle deserialization of on-disk cache sidecars
**Where:** `_sidecar.py:177` (`pickle.load`), reached via `bulk_loader.py:121`, `rules_lookup.py:432`,
`_mtgjson/rulings_index.py:76`.
**Risk:** The tools cache parsed data as pickled sidecars (`*.idx.pkl`, CR parse, rulings index) and
`pickle.load` them on warm start. `pickle.load` on attacker-controlled bytes is **arbitrary code
execution**. The files are written by the tool itself under your cache dir, so the practical vector
is *another local process/user writing a malicious sidecar* (or a synced/shared cache dir), not a
remote one. Real but local.
**Recommendation:** Prefer JSON sidecars where the shape allows; failing that, keep the cache dir
`0700` and treat `~/.cache/mtg-skills/` as trusted-only. Don't share/sync that directory.

### L1 — Supply chain: `cargo build` of a third-party repo; conditional hash check
**Where:** `_phase.py:325` (`git clone` `phase-rs/phase` @ `v0.66.0`), `:356` (`cargo build --release`),
`:487` (`if expected:` — sha256 verify is **skipped when the manifest omits a hash**).
**Risk:** `playtest-install-phase` compiles and runs Rust from an external GitHub repo. Card-data is
sha256-verified **only if** the release manifest includes a hash; a manifest without one downloads
unverified. Opt-in (playtesting only), pinned to a tag — trust is in `phase-rs/phase`.
**Recommendation:** Make verification unconditional (fail if `sha256` is absent). Skip
`playtest-install-phase` entirely if you don't playtest — nothing else needs the Rust toolchain.

### L2 — `curl` fallback allows argument injection via crafted URL
**Where:** `_http.py:62` (`_fetch_with_curl`), used by `web_fetch.py`, `cubecobra_fetch.py`.
**Risk:** URL is passed as a positional arg (list form, no `shell=True`, so **no shell injection**),
but a URL beginning with `-` could be parsed by curl as an option. URLs here come from your input /
known hosts, so exposure is minor.
**Recommendation:** Pass `--` before the URL, or validate `url.startswith(("http://","https://"))`.

### L3 — `art_fetcher` defaults its cache to `/tmp`
**Where:** `art_fetcher.py:1431` — `Path(os.environ.get("MTG_SKILLS_CACHE_DIR") or "/tmp")`.
**Risk:** When `MTG_SKILLS_CACHE_DIR` is unset it writes ASCII-art files to a predictable, often
world-readable `/tmp` path (symlink/temp-race territory), inconsistent with the `~/.cache/mtg-skills`
default used elsewhere. Low impact (ASCII art), but avoidable.
**Recommendation:** Default to `~/.cache/mtg-skills/` like the other modules.

### L4 (informational) — Anti-bot / TLS-fingerprint evasion & ToS
**Where:** `_http.py:49` (spoofed browser UA), `_fetch_with_curl` `--compressed`; `lgs-search/SKILL.md`
documents that TCGPlayer's captcha "can't be cleared" and the flow routes around it.
**Risk:** Not a security risk *to you*, but the storefront automation and UA spoofing likely violate
those sites' Terms of Service and could get your accounts flagged/banned — an account-safety concern
worth flagging given your "safe to use" goal.

### Positives confirmed (no action needed)
- No secrets, tokens, `.env`, cookies, collection dumps, or `Player.log` committed to the repo.
- deck-forge binds `127.0.0.1` by default; handoff endpoints are in-process (no subprocess RCE).
- No `eval`/`exec`/`os.system`/`shell=True` anywhere; all subprocess calls use list-form argv.
- The `WEBSITE_SEARCH_SECRET` in `art_fetcher.py:92` is a public client-side constant, correctly
  documented as "not a real secret."
- phase card-data download *is* sha256-verified when the manifest provides the hash.

---

## 4. Attack-surface summary by subsystem

| Subsystem | Network egress | Local sensitive access | Automation of live accounts | Verdict |
|---|---|---|---|---|
| Deck / cube / rules / stats / mana / combo | Read-only MTG data (+ deck list to Spellbook) | Collection/Player.log (local only) | None | **Low** |
| proxy-printer / art-fetcher | ASCII-art sites | Cache writes (L3) | None | **Low** |
| playtest (phase) | GitHub | cargo build (L1) | None | **Low, opt-in** |
| deck-forge server | None (serves local SPA) | Collection import/build files | None (in-process) | **Low–Med (M2)** |
| **lgs-search / _stores** | **4 storefronts + auth cookies** | **Stored store credentials (H2)** | **Yes — carts (H1)** | **Moderate–High** |

---

## 5. Recommended "extremely safe" configuration (mapped to your three goals)

Ranked by leverage. #1 satisfies most of your requirements by itself.

1. **Delete the storefront subsystem** — remove `lgs-search/` and
   `mtg-utils/src/mtg_utils/_stores/`, and drop `lgs-search` / store entry points from the relevant
   `pyproject.toml` files.
   → Eliminates **H1** (automated ordering), **H2** (stored store credentials), the storefront data
   egress, the Playwright persistent-profile machinery, and the USD-vendor coupling (**M1**). This is
   the direct answer to *"no automated ordering"* and *"no access to anything confidential."*

2. **Decide the AUD story deliberately** (**M1**). There is no AUD source in the repo. Options:
   (a) drop automated pricing entirely and treat card prices as manual/AUD you supply; or (b) if you
   want automated AUD pricing later, that's a new integration against an AU price source + AU store
   adapters — a feature build, not a config flag. Recommend (a) for the safe build.

3. **Harden the deck-forge server** (**M2**): keep the loopback default, warn/refuse on a
   non-loopback `--host`, and optionally add a per-launch token check. Or simply don't run it, or run
   it only when needed.

4. **Lock down the cache dir** (**M3**, **L3**): keep `~/.cache/mtg-skills/` at `0700`, set
   `MTG_SKILLS_CACHE_DIR` explicitly, don't sync/share it. Consider migrating pickle sidecars to JSON.

5. **Skip `playtest-install-phase`** unless you playtest (**L1**); if you do, make the sha256 check
   unconditional. Add `--` before the URL in the curl fallback (**L2**).

6. **Optional, per your comfort:** if you want *zero* local personal-data reads, also drop
   `mtga_import` (reads `Player.log`). It's local-only and low risk, so this is a preference, not a
   security necessity.

---

## 6. Residual risk after applying §5 (#1–#5)

- Card-name / deck-list lookups still go to Scryfall, EDHREC, and (if you use combo search) Commander
  Spellbook. These are card names, not PII — but if deck privacy matters, be aware combo search POSTs
  your list. All other traffic is read-only public MTG data over HTTPS.
- No stored credentials, no automated commerce actions, no PII egress remain.
- Local-only files (collection, cache) stay on disk under your control.

Net: with the storefront subsystem removed and the cache dir locked down, this fork has **no path to
your accounts, payment details, or identity**, and performs **no automated purchasing** — matching
your "extremely safe" bar.
