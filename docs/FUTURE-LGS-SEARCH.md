# Build-out kit — safe Australian LGS search (future work)

This is the instruction kit for rebuilding a card-sourcing skill **safely**, after the original
`lgs-search` + `mtg_utils/_stores/` subsystem was removed. Read `SECURITY-REVIEW.md` first for the
"why". When you're ready to build this, hand this file to Claude and say "let's build the AU LGS
search from the kit."

---

## 1. What was removed, and exactly why

Removed in the security pass (commit that added this file):

- `lgs-search/` — the skill directory (SKILL.md, CONTEXT.md, pyproject.toml, uv.lock, src symlink).
- `mtg-utils/src/mtg_utils/_stores/` — the adapters: `_common.py`, `tgp.py`, `atomic_empire.py`,
  `tcgplayer.py`, `manapool.py`, `__init__.py`.
- `mtg-utils/src/mtg_utils/lgs_search.py` — the orchestrator CLI.
- `tests/lgs-search/` — all adapter + orchestrator tests.
- The `lgs-search` entry point (was in `lgs-search/pyproject.toml`) and the CI step that ran its
  tests (`.github/workflows/ci.yml`).

**Why:** the old code (a) used Playwright `launch_persistent_context(profile_dir)` to keep
**logged-in** browser profiles on disk under `~/.cache/mtg-skills/lgs-profiles/<store>/` — i.e. it
stored credential-equivalent session cookies for four real US commerce accounts, unencrypted; and
(b) **mutated those live accounts** via `add_to_cart` / `clear_cart` (which deletes cart items) /
`bulk_submit_and_optimize`. That is the "automated ordering + confidential data" surface we
deliberately eliminated. It was also hard-wired to **USD** and **US** storefronts.

To see the old implementation for reference, check out the commit before the removal:

```bash
git log --oneline -- lgs-search mtg-utils/src/mtg_utils/_stores    # find the last commit that had it
git show <that-commit>:mtg-utils/src/mtg_utils/_stores/_common.py  # read a file without restoring it
```

The old `_common.py` is the most reusable artifact — see §4.

---

## 2. Design rules for the replacement (non-negotiable)

These are the safety invariants. The new skill MUST satisfy all of them:

1. **No login, ever.** Query only public product/price pages. No account, no auth flow, no OAuth,
   no saved password.
2. **No persisted browser profile.** If a browser is used at all, use an **ephemeral** context
   (`browser.new_context()` with no `user_data_dir`), disposed at the end of the run. Nothing
   credential-like is written to disk. Prefer plain `requests`/`httpx` over Playwright wherever the
   store's pages are server-rendered — no browser = no cookie jar at all.
3. **No account mutation.** No add-to-cart against a logged-in account, no clear-cart, no checkout,
   no "buy". The skill's output is a **shopping plan for you to act on manually**.
4. **"Cart for review" = a plan, not an action.** Two acceptable output shapes:
   - **Plan (preferred):** a markdown/JSON table of `card → store → price (AUD + USD) → product URL`.
     You click the links and add to cart yourself.
   - **Pre-filled ephemeral cart (optional):** open a throwaway browser window with items added via
     the store's *public* cart (guest cart, no login), left on the cart page for you to review and
     check out by hand. Still no login, still no auto-checkout.
5. **AUD-first, USD reference.** Show both. See §5.
6. **Fail loud, never guess a price.** Keep the old "Iron Rule": never report a price a real query
   didn't return. Out-of-stock / not-found must reflect the actual page.
7. **Respect robots/ToS and rate limits.** No anti-bot evasion, no captcha circumvention, honest
   `User-Agent` that identifies the tool, conservative throttling, honor `Retry-After`.

---

## 3. Target Australian storefronts (to confirm with you at build time)

The old skill targeted US stores. The replacement should target AU shops **you actually buy from**.
Candidates to discuss (confirm which you want; each needs its own adapter):

- Good Games
- Gameology
- Guf (gufgames)
- Card Merchant / Kadon
- Total Cards
- Titan Cards
- Binder POS-based single-vendor shops (many AU LGS run BinderPOS — a shared adapter may cover
  several at once, a big win)

**Action for build time:** you tell me the 2–4 AU shops you use; we pick which are scrapable from
public pages and build one adapter each (or one BinderPOS adapter if they share that platform).

---

## 4. Architecture to reuse (and what to drop from the old shape)

The old `_stores/_common.py` Protocol split is a sound starting point — **keep the search half,
delete the account half.**

**Keep / adapt:**
- `Listing` TypedDict (store, card_name, set_code, condition, foil, price, qty_available, url).
- `SearchPrefs` (max_condition, allow_foil, prefer_set).
- `pick_best_listing()` precedence logic (foil → condition → qty → prefer_set → cheapest).
- `name_matches()` (canonical-fold exact match, DFC face tolerance) — reuse `mtg_utils.names`.
- A per-store `search(card, prefs) -> list[Listing]` method.
- The `PRICE_RE` money parser — but generalize it for AUD (`A$`, `$`, `AUD`).

**Delete / never reintroduce:**
- `StoreSession` lifecycle auth methods: `is_logged_in`, `open_login`, `open_handoff` (as a
  *logged-in* handoff), `get_existing_cart`, `clear_cart`.
- `add_to_cart` against an authenticated session, `bulk_submit_and_optimize`.
- `profile_dir_for()` and every `launch_persistent_context(...)` call.
- `LoginRequiredError`, `CartNotEmptyError` and the whole cart-pollution machinery.

**New module layout suggestion:**

```
mtg-utils/src/mtg_utils/_lgs_au/
  __init__.py          # registry of enabled AU adapters
  _common.py           # Listing, SearchPrefs, pick_best_listing, AUD/USD money parse, Adapter Protocol (search-only)
  binderpos.py         # shared adapter for BinderPOS-platform shops (parametrized by base_url)
  <store>.py           # one module per bespoke store
mtg-utils/src/mtg_utils/lgs_search.py   # new orchestrator: resolve list -> search all -> allocate -> emit PLAN
```

New skill dir `lgs-search/` with SKILL.md rewritten to the §2 rules, `pyproject.toml` re-declaring
the `lgs-search` entry point, tests under `tests/lgs-search/`, and the CI step restored in
`.github/workflows/ci.yml`.

---

## 5. Pricing: AUD + USD

The core (Task 2 of the security pass) added a shared converter — reuse it:

- `mtg_utils.fx.usd_to_aud(usd: float) -> float` reads the rate from `MTG_SKILLS_AUD_PER_USD`
  (env var) or a config default. **No live FX call by default** (keeps the safe/offline posture).
- Show every card as e.g. `Sol Ring — A$1.82 (US$1.20 ref)`.
- USD reference comes from Scryfall bulk (`usd`, cheapest non-foil printing) exactly as the old
  spill-proxy did — but it is now a *comparison reference*, not the source of truth. The **AU store's
  own AUD price** (scraped) is the real number for allocation; Scryfall USD→AUD is the sanity check.
- Optional future toggle: `--live-fx` to fetch the daily rate from an FX endpoint (adds one outbound
  host; document it as a network-surface change before enabling).

---

## 6. Testing (no real network — same rule as the rest of the repo)

- Reuse the `FakeFetcher` pattern (was in `tests/proxy-printer/_fake_fetcher.py`) — dict-backed,
  returns canned HTML per URL. Capture a few real public product pages once, save as fixtures under
  `tests/lgs-search/fixtures/`, and parse those. No live calls in CI.
- Test the allocator, `pick_best_listing`, AUD conversion, and the plan renderer deterministically.
- `prek.toml` still allows ~1 MiB fixtures (was bumped for the old HTML fixtures); reuse that.

---

## 7. Definition of done for the rebuild

- [ ] 2–4 AU store adapters, search-only, no auth, no cart mutation.
- [ ] Ephemeral browser context (or pure HTTP) — nothing persisted to disk.
- [ ] Orchestrator emits a **review plan** (table + product URLs); optional guest-cart handoff, never
      auto-checkout.
- [ ] AUD + USD shown on every line via `mtg_utils.fx`.
- [ ] Honest UA, throttling, robots/ToS respected; no captcha/anti-bot evasion.
- [ ] Tests green with `FakeFetcher`, CI step restored.
- [ ] `SECURITY-REVIEW.md` re-checked: no new stored-credential or account-mutation surface.
