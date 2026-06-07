"""lgs-search orchestrator CLI.

Workflow: input → LGS sweep → allocate → online optimize → confirm →
build carts → handoff. See specs/2026-05-04-lgs-search-design.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from mtg_utils._sidecar import atomic_write_json
from mtg_utils._stores._common import Line, Listing
from mtg_utils.names import normalize_card_name

BASIC_LAND_NAMES = frozenset(
    {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"},
)


class NeededCard(TypedDict):
    card_name: str
    qty: int


def _parse_text_line(line: str) -> NeededCard | None:
    from mtg_utils.parse_deck import _strip_set_code

    line = line.strip()
    if not line or line.startswith(("#", "//")):
        return None
    parts = line.split(maxsplit=1)
    if len(parts) == 1:
        return NeededCard(card_name=_strip_set_code(parts[0]), qty=1)
    head, rest = parts
    if head.rstrip("xX").isdigit():
        qty = int(head.rstrip("xX"))
        return NeededCard(card_name=_strip_set_code(rest.strip()), qty=qty)
    return NeededCard(card_name=_strip_set_code(line), qty=1)


def _read_text_list(path: Path) -> list[NeededCard]:
    cards: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_text_line(line)
        if parsed is None:
            continue
        cards[parsed["card_name"]] = cards.get(parsed["card_name"], 0) + parsed["qty"]
    return [NeededCard(card_name=n, qty=q) for n, q in cards.items()]


def _read_deck_json(path: Path) -> list[NeededCard]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cards: dict[str, int] = {}
    for entry in data.get("commanders") or []:
        # parse-deck emits [{"name", "quantity"}]; tolerate bare strings too.
        if isinstance(entry, str):
            cards[entry] = cards.get(entry, 0) + 1
        else:
            name = entry["name"]
            qty = int(entry.get("quantity", entry.get("qty", 1)))
            cards[name] = cards.get(name, 0) + qty
    for entry in (data.get("cards") or []) + (data.get("sideboard") or []):
        name = entry["name"]
        qty = int(entry.get("quantity", entry.get("qty", 1)))
        cards[name] = cards.get(name, 0) + qty
    return [NeededCard(card_name=n, qty=q) for n, q in cards.items()]


def _looks_like_json(path: Path) -> bool:
    if path.suffix.lower() == ".json":
        return True
    head = path.read_text(encoding="utf-8", errors="ignore")[:64].lstrip()
    return head.startswith(("{", "["))


def _subtract_collection(
    cards: list[NeededCard],
    collection_path: Path,
) -> list[NeededCard]:
    """Subtract owned copies. Names are normalized via `normalize_card_name`
    on both sides so Arena-aliased exports (which strip diacritics) line up
    with bulk-data canonical spellings.
    """
    coll = json.loads(collection_path.read_text(encoding="utf-8"))
    raw_owned: dict[str, int] = {}
    if isinstance(coll, dict):
        raw_owned = {k: int(v) for k, v in coll.items()}
    else:
        for row in coll:
            name = row.get("name")
            if not name:
                continue
            raw_owned[name] = raw_owned.get(name, 0) + int(row.get("qty", 1))
    owned: dict[str, int] = {}
    for name, qty in raw_owned.items():
        key = normalize_card_name(name)
        owned[key] = owned.get(key, 0) + qty
    result: list[NeededCard] = []
    for c in cards:
        remaining = c["qty"] - owned.get(normalize_card_name(c["card_name"]), 0)
        if remaining > 0:
            result.append(NeededCard(card_name=c["card_name"], qty=remaining))
    return result


def resolve_input(
    input_path: Path,
    *,
    collection_path: Path | None,
    include_basics: bool,
) -> tuple[list[NeededCard], dict[str, int]]:
    """Resolve input → (cards-to-buy, basic-lands-needed-summary).

    Accepts either a parsed-deck JSON (`{"commanders": [...], "cards": [...],
    "sideboard": [...]}`) or a plain text list (one entry per line, optional
    `Nx ` or `N ` quantity prefix). Mainboard + sideboard are summed. If
    `collection_path` points at a JSON file mapping card name → owned qty
    (or a list of `{"name": ..., "qty": ...}` rows), owned copies are
    subtracted before returning. Basic lands are filtered out and surfaced
    in the second return value unless `include_basics` is True. Snow basics
    are not filtered.
    """
    if _looks_like_json(input_path):
        raw = _read_deck_json(input_path)
    else:
        raw = _read_text_list(input_path)
    if collection_path:
        raw = _subtract_collection(raw, collection_path)
    if include_basics:
        return raw, {}
    basics: dict[str, int] = {}
    cards: list[NeededCard] = []
    for c in raw:
        if c["card_name"] in BASIC_LAND_NAMES:
            basics[c["card_name"]] = basics.get(c["card_name"], 0) + c["qty"]
        else:
            cards.append(c)
    return cards, basics


def summarize_basics(basics: dict[str, int]) -> str:
    if not basics:
        return ""
    lines = [f"  - {qty}x {name}" for name, qty in sorted(basics.items())]
    return "Basic lands needed (not searched):\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3: per-card allocation
# ---------------------------------------------------------------------------


class SearchResultRow(TypedDict):
    card_name: str
    qty: int
    tgp: Listing | None
    atomic_empire: Listing | None
    scryfall_usd: float


class AllocatedCard(TypedDict):
    card_name: str
    qty: int
    store: str  # "tgp" | "atomic_empire" | "marketplace"
    listing: Listing | None  # None for online (resolved in Step 4)


@dataclass(frozen=True)
class AllocationConfig:
    lgs_online_threshold_pct: float
    lgs_online_threshold_usd: float
    consolidate_threshold_pct: float
    consolidate_threshold_usd: float


# TODO: replace with `_stores.LGS_STORES` once Task 12 wires the registry.
_LGS_KEYS = ("tgp", "atomic_empire")


def _spill_triggered(
    cheapest_lgs: float,
    online_proxy: float,
    cfg: AllocationConfig,
) -> bool:
    # OR semantics intentional; see specs/2026-05-04-lgs-search-design.md
    # "Default thresholds". Trivially-cheap cards may spill on the pct branch
    # alone — accepted as noise.
    if cheapest_lgs <= 0:
        return False
    if online_proxy <= 0:
        # Unknown online price (lookup miss / no Scryfall data). We have no
        # signal to spill on; keep the card at the LGS.
        return False
    pct_save = (cheapest_lgs - online_proxy) / cheapest_lgs * 100
    usd_save = cheapest_lgs - online_proxy
    return (
        pct_save >= cfg.lgs_online_threshold_pct
        or usd_save >= cfg.lgs_online_threshold_usd
    )


def _close_enough(price_a: float, price_b: float, cfg: AllocationConfig) -> bool:
    # OR semantics intentional; "close" means within EITHER threshold so the
    # consolidation tie-break fires on small differences regardless of scale.
    diff = abs(price_a - price_b)
    cheaper = min(price_a, price_b)
    pct = (diff / cheaper * 100) if cheaper > 0 else 0
    return diff <= cfg.consolidate_threshold_usd or pct <= cfg.consolidate_threshold_pct


def allocate(
    rows: list[SearchResultRow],
    cfg: AllocationConfig,
) -> list[AllocatedCard]:
    """Step 3 of the workflow. Assign each (card, qty) to a store or split.

    Per-card decision tree:
      1. Compute the cheapest in-stock LGS candidate.
      2. If online (Scryfall USD proxy) is much cheaper than the cheapest LGS
         (per cfg's pct/usd thresholds), spill the whole card line to "marketplace".
      3. Otherwise pick cheapest LGS. If both LGS are "close" by cfg's
         consolidate thresholds, prefer the LGS with the higher running cart
         total to minimize trips.
      4. If chosen store can't fill the requested qty, fall through to the
         next-cheapest store; residual that no store can fill goes online.
    """
    running_totals: dict[str, float] = dict.fromkeys(_LGS_KEYS, 0.0)
    out: list[AllocatedCard] = []

    for row in rows:
        candidates = {k: v for k in _LGS_KEYS if (v := row[k]) is not None}
        sorted_keys = sorted(candidates, key=lambda k: candidates[k]["price"])

        cheapest_lgs = (
            candidates[sorted_keys[0]]["price"] if sorted_keys else float("inf")
        )

        if _spill_triggered(cheapest_lgs, row["scryfall_usd"], cfg):
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=row["qty"],
                    store="marketplace",
                    listing=None,
                )
            )
            continue

        if not sorted_keys:
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=row["qty"],
                    store="marketplace",
                    listing=None,
                )
            )
            continue

        # Trip-consolidation tie-break: among LGS prices that are "close",
        # prefer the store with the higher running total so far.
        if len(sorted_keys) > 1:
            a, b = sorted_keys[0], sorted_keys[1]
            if (
                _close_enough(candidates[a]["price"], candidates[b]["price"], cfg)
                and running_totals[b] > running_totals[a]
            ):
                sorted_keys = [b, a]

        # Quantity-aware fill across stores
        remaining = row["qty"]
        for key in sorted_keys:
            if remaining <= 0:
                break
            avail = candidates[key]["qty_available"]
            take = min(avail, remaining)
            if take <= 0:
                continue
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=take,
                    store=key,
                    listing=candidates[key],
                )
            )
            running_totals[key] += take * candidates[key]["price"]
            remaining -= take

        if remaining > 0:
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=remaining,
                    store="marketplace",
                    listing=None,
                )
            )

    return out


def assert_no_duplicates_invariant(
    needed: list[NeededCard],
    allocated: list[AllocatedCard],
) -> None:
    """Each (card, copy) is assigned to exactly one store. Sum-of-qtys per
    card name must equal the requested qty.
    """
    needed_qty = {c["card_name"]: c["qty"] for c in needed}
    actual: dict[str, int] = {}
    for a in allocated:
        actual[a["card_name"]] = actual.get(a["card_name"], 0) + a["qty"]
    if needed_qty != actual:
        diff = {
            k: (needed_qty.get(k, 0), actual.get(k, 0))
            for k in set(needed_qty) | set(actual)
            if needed_qty.get(k, 0) != actual.get(k, 0)
        }
        msg = f"allocation invariant violated: needed_vs_actual={diff!r}"
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Sidecar I/O — write-only audit record of one orchestrator run
# ---------------------------------------------------------------------------

SIDECAR_VERSION = 1


class Sidecar(TypedDict, total=False):
    """JSON envelope written to ``--output-dir/lgs-cart-allocation.json``
    after Phase 3 completes. Records what the run decided so the user (or
    a downstream tool) can inspect the allocation, the chosen Marketplace,
    and any unfindable cards. The sidecar is never read by the orchestrator
    itself — there's no resume path; if a run fails mid-build, fix the
    underlying issue and re-run from scratch.
    """

    version: int
    generated_at: str
    allocation: list[dict]
    online_optimizer_results: dict | None
    unfindable: list[str]
    basic_lands_needed: dict[str, int]


def now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_sidecar(path: Path, sc: Sidecar) -> None:
    """Atomic-rename write so concurrent readers can't see a partial file.

    Delegates to the shared `atomic_write_json` helper, which uses a
    per-call NamedTemporaryFile so concurrent writers don't collide on
    the same `.tmp` name.
    """
    atomic_write_json(path, sc)


# ---------------------------------------------------------------------------
# Step 2: LGS sweep (ThreadPoolExecutor)
# ---------------------------------------------------------------------------

from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: E402
from threading import Semaphore  # noqa: E402

from mtg_utils._stores import (  # noqa: E402
    LGS_ADAPTERS,
    LGS_STORES,
    MARKETPLACE_ADAPTERS,
    MARKETPLACE_STORES,
    lookup,
)
from mtg_utils._stores._common import (  # noqa: E402
    SearchPrefs,
    pick_best_listing,
)


def sweep_lgs(
    cards: list[NeededCard],
    *,
    scryfall_usd_lookup: dict[str, float],
    prefs: SearchPrefs,
    max_workers: int = 8,
    per_store_concurrency: int = 4,
    page_factory=None,
    sequential: bool = False,
    progress=None,
) -> list[SearchResultRow]:
    """Search every LGS for every card; return one SearchResultRow per card.

    `page_factory` is a callable `(store_name) -> Page-like` injected for
    testability. In production the orchestrator passes a real Playwright
    page-pool factory; tests pass a mock. When None, this function calls
    each adapter's `search` with `page=None` (adapters tolerate it for
    their fixture-based tests but real adapters will need real pages).

    `sequential=True` bypasses the ThreadPoolExecutor and runs every
    (card, store) search in the caller's thread. Use this when the
    page_factory hands out sync-Playwright pages — sync Playwright is
    not safe to use across threads.
    """

    def _search_one(card, store):
        adapter = LGS_ADAPTERS[store]
        try:
            page = page_factory(store) if page_factory else None
            listings = adapter.search(
                page,
                card["card_name"],
                qty=card["qty"],
                prefs=prefs,
            )
        except Exception:  # noqa: BLE001
            return card["card_name"], store, None
        chosen = pick_best_listing(listings, qty=card["qty"], prefs=prefs)
        return card["card_name"], store, chosen

    results: dict[tuple[str, str], Listing | None] = {}
    if sequential:
        for card in cards:
            for store in LGS_STORES:
                name, store_, listing = _search_one(card, store)
                results[(name, store_)] = listing
                if progress:
                    progress(name, store_, listing)
    else:
        semaphores = {name: Semaphore(per_store_concurrency) for name in LGS_STORES}

        def _search_one_locked(card, store):
            with semaphores[store]:
                return _search_one(card, store)

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [
                ex.submit(_search_one_locked, card, store)
                for card in cards
                for store in LGS_STORES
            ]
            for fut in as_completed(futures):
                name, store, listing = fut.result()
                results[(name, store)] = listing

    rows: list[SearchResultRow] = []
    for card in cards:
        rows.append(
            SearchResultRow(
                card_name=card["card_name"],
                qty=card["qty"],
                tgp=results.get((card["card_name"], "tgp")),
                atomic_empire=results.get((card["card_name"], "atomic_empire")),
                scryfall_usd=scryfall_usd_lookup.get(card["card_name"], 0.0),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Step 4: Online optimizer
# ---------------------------------------------------------------------------

from mtg_utils._stores._common import OptimizedCart  # noqa: E402


def optimize_marketplace(
    marketplace_lines: list[Line],
    *,
    page_factory=None,
) -> dict | None:
    """Submit `marketplace_lines` to each Marketplace adapter and pick
    the cheapest total.

    Returns dict mapping store name to OptimizedCart, plus 'chosen' key
    naming the cheapest. Returns None when there are no Marketplace
    lines or when every Marketplace fails (login required, captcha,
    selectors moved).

    Per-store failures are caught and logged so one broken adapter doesn't
    sink the others — common case is TCGPlayer's anti-bot blocking
    Playwright's persistent_context, in which case Mana Pool still runs.
    """
    if not marketplace_lines:
        return None
    results: dict[str, OptimizedCart] = {}
    for store, adapter in MARKETPLACE_ADAPTERS.items():
        page = page_factory(store) if page_factory else None
        try:
            results[store] = adapter.bulk_submit_and_optimize(
                page,
                marketplace_lines,
            )
        except Exception as exc:  # noqa: BLE001
            click.echo(
                f"[{store}] marketplace optimizer failed: "
                f"{str(exc).splitlines()[0][:200]}",
                err=True,
            )
    if not results:
        return None
    chosen = min(results, key=lambda s: results[s]["total"])
    return {**results, "chosen": chosen}


# ---------------------------------------------------------------------------
# Step 5: Confirmation gate + cart-pollution check
# ---------------------------------------------------------------------------


class CartPollutionError(Exception):
    pass


def check_carts_empty(targets: list[tuple]) -> None:
    """Raise CartPollutionError if any target store's cart is non-empty.

    `targets` is a list of (store_name, adapter, page) tuples.
    """
    polluted = []
    for store, adapter, page in targets:
        existing = adapter.get_existing_cart(page)
        if existing:
            polluted.append((store, len(existing)))
    if polluted:
        details = ", ".join(f"{s} ({n} items)" for s, n in polluted)
        msg = (
            f"Cart pollution: {details}. "
            "Check out / clear those carts manually OR re-run with "
            "--clear-existing-carts to empty them automatically."
        )
        raise CartPollutionError(msg)


def confirm_proceed(summary: str, *, yes: bool) -> bool:
    if yes:
        return True
    print(summary)
    answer = input("Build carts? [y/N]: ").strip().lower()
    return answer == "y"


# ---------------------------------------------------------------------------
# Step 6: Relax prefs (retry-relaxed)
# ---------------------------------------------------------------------------


def relax_prefs(_prefs: SearchPrefs) -> SearchPrefs:
    """Return a new SearchPrefs with all constraints dropped, for retry-relaxed."""
    return SearchPrefs(
        max_condition="any",
        allow_foil=True,
        prefer_set=None,
    )


# ---------------------------------------------------------------------------
# Step 7: Handoff to browsers
# ---------------------------------------------------------------------------


def handoff_to_browsers(targets: list[tuple]) -> None:
    """Launch a headed browser per target.

    `targets` = [(store, adapter, profile_dir)]
    """
    for _store, adapter, profile_dir in targets:
        adapter.open_handoff(profile_dir)


def _build_lgs_carts_and_handoff(
    allocation,
    *,
    clear_existing: bool,
    no_handoff: bool,
) -> dict[str, list[tuple[str, str]]]:
    """Phase 5+7 for LGS stores: open one headed Chromium per store, populate
    the cart, then leave the window pointed at the cart for checkout.

    Login is lazy: when `is_logged_in(page)` returns False, the user is
    prompted to sign in via the open headed window. AE's `is_logged_in`
    is a no-op stub (the static DOM doesn't expose state), so AE auth
    failures surface as `add_to_cart` HTTP errors instead.

    Returns a dict mapping store -> list of (card_name, error_message)
    so the caller can surface a punch list.
    """
    from playwright.sync_api import sync_playwright

    by_store: dict[str, list] = {}
    for a in allocation:
        if a["store"] in LGS_STORES and a.get("listing"):
            by_store.setdefault(a["store"], []).append(a)

    failures: dict[str, list[tuple[str, str]]] = {}
    if not by_store:
        return failures

    for store, adapter in LGS_ADAPTERS.items():  # registry order for stable UX
        items = by_store.get(store)
        if not items:
            continue
        profile = profile_dir_for(store)
        click.echo(f"\n=== {adapter.display_name}: {len(items)} cards ===")
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile),
                headless=False,
            )
            page = ctx.new_page()

            # Login pre-flight. Some adapters (AE) always return True here
            # because static DOM can't distinguish state; that's fine — we
            # rely on cart-add response codes for those.
            page.goto(adapter.base_url, wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            if not adapter.is_logged_in(page):
                click.echo(
                    f"[{store}] not logged in. Sign in via the open window, "
                    "then press Enter here to continue.",
                )
                input()
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(500)
                if not adapter.is_logged_in(page):
                    click.echo(
                        f"[{store}] still not logged in; skipping cart build "
                        "for this store. Re-run after fixing.",
                        err=True,
                    )
                    failures.setdefault(store, []).extend(
                        (a["card_name"], "login") for a in items
                    )
                    ctx.close()
                    continue

            # Cart-pollution check
            existing = adapter.get_existing_cart(page)
            if existing:
                if clear_existing:
                    click.echo(
                        f"[{store}] clearing {len(existing)} existing item(s)...",
                    )
                    adapter.clear_cart(page)
                else:
                    click.echo(
                        f"[{store}] cart has {len(existing)} item(s) already. "
                        "Empty it in the open window (or re-run with "
                        "--clear-existing-carts), then press Enter.",
                    )
                    input()
                    if adapter.get_existing_cart(page):
                        click.echo(
                            f"[{store}] cart still not empty; aborting this store.",
                            err=True,
                        )
                        failures.setdefault(store, []).extend(
                            (a["card_name"], "cart not empty") for a in items
                        )
                        ctx.close()
                        continue

            # Add items
            cart_url = f"{adapter.base_url}/cart"  # adapter-specific override below
            for a in items:
                listing = a["listing"]
                try:
                    result = adapter.add_to_cart(page, listing, a["qty"])
                    if result.get("success"):
                        click.echo(
                            f"  + {a['card_name']} x{a['qty']} "
                            f"(${listing['price']:.2f})",
                        )
                        cart_url = result.get("cart_url") or cart_url
                    else:
                        msg = "add_to_cart returned success=False"
                        click.echo(f"  ! {a['card_name']}: {msg}", err=True)
                        failures.setdefault(store, []).append((a["card_name"], msg))
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc).splitlines()[0][:200]
                    click.echo(f"  ! {a['card_name']}: {msg}", err=True)
                    failures.setdefault(store, []).append((a["card_name"], msg))

            if no_handoff:
                ctx.close()
                continue

            # Handoff — point the open window at the cart and block until close.
            try:
                page.goto(cart_url, wait_until="domcontentloaded", timeout=20000)
            except Exception as exc:  # noqa: BLE001
                click.echo(
                    f"[{store}] couldn't navigate to cart: {exc}",
                    err=True,
                )
            click.echo(
                f"[{store}] cart populated. Review and check out in the open "
                "window. Close the window to continue.",
            )
            with contextlib.suppress(Exception):
                ctx.wait_for_event("close", timeout=0)

    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

import click  # noqa: E402

from mtg_utils._stores._common import profile_dir_for  # noqa: E402


@click.group(invoke_without_command=True)
@click.option("--input", "input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--collection", type=click.Path(exists=True, path_type=Path), default=None
)
@click.option("--bulk-data", type=click.Path(path_type=Path), default=None)
@click.option(
    "--condition",
    default="lp",
    type=click.Choice(["nm", "lp", "mp", "hp", "any"]),
)
@click.option("--allow-foil", is_flag=True)
@click.option("--prefer-set", default=None)
@click.option("--lgs-online-threshold-pct", default=20.0, type=float)
@click.option("--lgs-online-threshold-usd", default=2.00, type=float)
@click.option("--consolidate-threshold-pct", default=10.0, type=float)
@click.option("--consolidate-threshold-usd", default=1.00, type=float)
@click.option("--no-handoff", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.option("--retry-relaxed", is_flag=True)
@click.option("--clear-existing-carts", is_flag=True)
@click.option("--include-basics", is_flag=True)
@click.option("--yes", is_flag=True, help="skip the pre-cart-build confirmation prompt")
@click.option("--search-timeout-seconds", default=20, type=int)
@click.option("--cart-timeout-seconds", default=30, type=int)
@click.option("--max-retries", default=3, type=int)
@click.option(
    "--output-dir",
    default=Path.cwd,  # called at invocation time, not import time
    type=click.Path(path_type=Path),
)
@click.pass_context
def main(ctx, **kwargs):
    """Search LGS + online stores; allocate; build carts."""
    if ctx.invoked_subcommand is not None:
        return
    if kwargs.get("input_path") is None:
        click.echo("--input is required", err=True)
        ctx.exit(2)
    _run_orchestrator(**kwargs)


@main.command()
@click.option(
    "--store",
    required=True,
    type=click.Choice(["tgp", "atomic_empire", "tcgplayer", "manapool"]),
)
def login(store: str) -> None:
    """Open a headed browser for one-time login at a Storefront."""
    adapter = lookup(store)
    profile = profile_dir_for(store)
    click.echo(f"Opening {adapter.display_name} login. Close the window when done.")
    adapter.open_login(profile)


# ---------------------------------------------------------------------------
# Orchestrator helpers
# ---------------------------------------------------------------------------


import contextlib  # noqa: E402
from contextlib import contextmanager  # noqa: E402


@contextmanager
def _playwright_pages(stores: list[str], *, headless: bool = True):
    """Open one persistent_context + one page per store; yield a page_factory.

    Persistent profiles live at `~/.cache/mtg-skills/lgs-profiles/<store>/`
    so any login state persists across runs. A store whose profile fails to
    open (e.g., singleton-lock contention from a stale Chromium) is skipped
    with a warning — the orchestrator treats its searches as "not in stock".

    Sync Playwright is not thread-safe across instances; the returned
    factory must be used from the thread that entered this context.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        contexts: dict = {}
        pages: dict = {}
        for store in stores:
            profile = profile_dir_for(store)
            try:
                ctx = p.chromium.launch_persistent_context(
                    str(profile),
                    headless=headless,
                )
                pages[store] = ctx.new_page()
                contexts[store] = ctx
            except Exception as exc:  # noqa: BLE001
                click.echo(
                    f"[lgs-search] could not open profile for {store}: {exc}",
                    err=True,
                )

        def factory(store: str):
            return pages.get(store)

        try:
            yield factory
        finally:
            for ctx in contexts.values():
                with contextlib.suppress(Exception):
                    ctx.close()


import os  # noqa: E402


def _locate_bulk_data() -> Path | None:
    """Find a Scryfall ``default-cards.json`` in common locations.

    The spill check needs this file to compute cheapest-printing USD; without
    it the proxy is 0.0 for every card and ALL cards stay at LGS (silent
    no-spill) — verified live on a 31-card run that overpaid ~$43 because
    `--bulk-data` wasn't passed.

    Search order (first hit wins):

      1. ``$MTG_SKILLS_BULK_DATA`` (explicit override, full path)
      2. ``$MTG_SKILLS_CACHE_DIR/default-cards.json``
      3. ``~/.cache/mtg-skills/default-cards.json`` (the cache_dir convention
         shared with the persistent Playwright profiles)
      4. ``$CWD/default-cards.json`` (where ``download-bulk`` puts files
         by default)
      5. ``$CWD/.cache/default-cards.json`` (in-repo cache convention)
      6. Newest ``default-cards*.json`` in any of the directories above
         (some users keep dated copies, e.g. default-cards-20260214220913.json)

    Returns the Path of the most recently modified hit, or None if nothing
    is found. Caller is expected to print a loud warning when None.
    """
    explicit = os.environ.get("MTG_SKILLS_BULK_DATA")
    if explicit:
        p = Path(explicit).expanduser()
        if p.exists():
            return p

    cache_env = os.environ.get("MTG_SKILLS_CACHE_DIR")
    candidates_dirs: list[Path] = []
    if cache_env:
        candidates_dirs.append(Path(cache_env))
    candidates_dirs += [
        Path.home() / ".cache" / "mtg-skills",
        Path.cwd(),
        Path.cwd() / ".cache",
    ]
    # Also walk a few parents of cwd looking for an in-repo .cache; common
    # case is invoking the skill from a subdirectory of the repo where
    # download-bulk was run at the repo root.
    cwd = Path.cwd()
    for parent in (cwd.parent, cwd.parent.parent):
        if parent != cwd:
            candidates_dirs.append(parent)
            candidates_dirs.append(parent / ".cache")

    seen: set[Path] = set()
    matches: list[Path] = []
    for d in candidates_dirs:
        if d in seen:
            continue
        seen.add(d)
        if not d.exists():
            continue
        # Exact name first, then dated variants.
        exact = d / "default-cards.json"
        if exact.exists():
            matches.append(exact)
        try:
            for p in d.glob("default-cards*.json"):
                if p != exact:
                    matches.append(p)
        except OSError:
            continue

    if not matches:
        return None
    # Newest wins so dated dumps don't shadow a fresh-named file.
    return max(matches, key=lambda p: p.stat().st_mtime)


def _scryfall_usd_lookup(bulk_path: Path | None, names: list[str]) -> dict[str, float]:
    """Cheapest non-foil non-digital USD across ALL printings of each name.

    Used as the "online proxy" in the spill check (`_spill_triggered`). Uses
    the cheapest printing — not the default printing — because online
    optimizers (TCG, Mana Pool) pick from any printing, so the proxy should
    reflect the lowest price an optimizer might plausibly find. The default
    printing often:
      * has no USD recorded (e.g. Beast Within's default has no `usd`,
        but its cheap reprints are $0.50), or
      * is the original expensive run, masking cheap reprints (e.g. Kessig
        Wolf Run: default ~$15, cheapest reprint $0.30).

    Returns 0.0 for unknown / unpriced cards; the allocator treats 0.0 as
    "no signal" and won't spill on it.
    """
    if bulk_path is None or not bulk_path.exists():
        return dict.fromkeys(names, 0.0)
    try:
        from mtg_utils.bulk_loader import load_bulk_cards

        data = load_bulk_cards(bulk_path)
    except (ValueError, OSError):
        return dict.fromkeys(names, 0.0)
    if not isinstance(data, list):
        return dict.fromkeys(names, 0.0)
    name_set = set(names)
    min_by_name: dict[str, float] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        n = row.get("name")
        if n not in name_set:
            continue
        if row.get("digital"):
            continue
        # Non-foil cardstock: the cheapest of usd/usd_etched is what a buyer
        # would actually pay; usd_foil is excluded so allow_foil=False
        # remains the proxy's default mode.
        prices = row.get("prices") or {}
        for key in ("usd", "usd_etched"):
            raw = prices.get(key)
            if not raw:
                continue
            try:
                price = float(raw)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            cur = min_by_name.get(n)
            if cur is None or price < cur:
                min_by_name[n] = price
    return {name: min_by_name.get(name, 0.0) for name in names}


def _render_summary(allocation, marketplace, basics) -> str:
    """Render the markdown summary printed to stdout."""
    lines = ["## Cart allocation"]
    by_store: dict[str, list] = {}
    for a in allocation:
        by_store.setdefault(a["store"], []).append(a)
    for store, items in by_store.items():
        if store == "marketplace":
            continue
        adapter = LGS_ADAPTERS.get(store) or MARKETPLACE_ADAPTERS.get(store)
        name = adapter.display_name if adapter else store
        total = sum((a["listing"] or {}).get("price", 0) * a["qty"] for a in items)
        lines.append(f"\n{name} - {len(items)} cards, ${total:.2f}")
        for a in items:
            li = a["listing"] or {}
            lines.append(
                f"  + {a['card_name']} ({li.get('condition', '?')}) - "
                f"${li.get('price', 0):.2f}",
            )
    spillover_items = by_store.get("marketplace", [])
    if spillover_items and not marketplace:
        # Dry-run path: spillover list with no prices (iron rule — never
        # report a price the CLI did not return). User re-runs without
        # --dry-run to get optimizer totals.
        lines.append(
            f"\nMarketplace spillover - {len(spillover_items)} cards "
            "(price TBD; re-run without --dry-run for optimizer totals)",
        )
        for a in spillover_items:
            lines.append(f"  + {a['card_name']} x{a['qty']}")
    if marketplace and marketplace.get("chosen"):
        chosen = marketplace["chosen"]
        result = marketplace[chosen]
        # Other Marketplaces in the registry, excluding the chosen one.
        # Robust to single-Marketplace configurations (no IndexError if
        # MARKETPLACE_ADAPTERS is ever pruned to one entry).
        losers = [
            s
            for s in MARKETPLACE_ADAPTERS
            if s != chosen and s in marketplace and isinstance(marketplace[s], dict)
        ]
        if losers:
            loser = losers[0]
            comparison = (
                f"chosen over {MARKETPLACE_ADAPTERS[loser].display_name}: "
                f"${result['total']:.2f} vs ${marketplace[loser]['total']:.2f}"
            )
        else:
            comparison = f"only Marketplace option, ${result['total']:.2f}"
        lines.append(
            f"\n{MARKETPLACE_ADAPTERS[chosen].display_name} "
            f"({comparison}) - items+shipping; tax computed at checkout",
        )
    if basics:
        lines.append("")
        lines.append(summarize_basics(basics))
    return "\n".join(lines)


def _run_orchestrator(
    *,
    input_path,
    collection,
    bulk_data,
    condition,
    allow_foil,
    prefer_set,
    lgs_online_threshold_pct,
    lgs_online_threshold_usd,
    consolidate_threshold_pct,
    consolidate_threshold_usd,
    no_handoff,
    dry_run,
    retry_relaxed,
    clear_existing_carts,
    include_basics,
    yes,
    search_timeout_seconds,
    cart_timeout_seconds,
    max_retries,
    output_dir,
):
    # Flags still not wired: retry-relaxed (Phase 6), per-step timeouts, and
    # the explicit cart-add retry counter. Warn so users don't silently expect
    # behavior that isn't there yet.
    not_yet_wired = []
    if retry_relaxed:
        not_yet_wired.append("--retry-relaxed")
    if search_timeout_seconds != 20:
        not_yet_wired.append("--search-timeout-seconds")
    if cart_timeout_seconds != 30:
        not_yet_wired.append("--cart-timeout-seconds")
    if max_retries != 3:
        not_yet_wired.append("--max-retries")
    if not_yet_wired:
        click.echo(
            f"Note: {', '.join(not_yet_wired)} not yet wired. "
            "Flag accepted but has no effect.",
            err=True,
        )
    del search_timeout_seconds, cart_timeout_seconds, max_retries
    del retry_relaxed

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = output_dir / "lgs-cart-allocation.json"

    cards, basics = resolve_input(
        input_path,
        collection_path=collection,
        include_basics=include_basics,
    )
    names = [c["card_name"] for c in cards]
    # Auto-detect bulk data when not explicitly passed. Without it, the
    # cheapest-printing proxy is 0.0 for every card and the spill check
    # has no signal — every card stays at LGS, including ones that are
    # 5-30x cheaper online. Loud warning when nothing's found so the
    # silent-no-spill failure mode of an earlier run can't recur.
    if bulk_data is None:
        bulk_data = _locate_bulk_data()
        if bulk_data is not None:
            click.echo(
                f"Auto-detected bulk data: {bulk_data}",
                err=True,
            )
        else:
            click.echo(
                "WARNING: no Scryfall bulk data found in any of "
                "$MTG_SKILLS_BULK_DATA, $MTG_SKILLS_CACHE_DIR, "
                "~/.cache/mtg-skills/, $CWD, or $CWD/.cache. The spill "
                "check will have no online-price signal — every "
                "in-stock LGS listing will win and you may overpay "
                "by 5-30x on cards with cheap reprints. Run "
                "`download-bulk` (or pass --bulk-data) before re-running "
                "for accurate allocation.",
                err=True,
            )
    usd_lookup = _scryfall_usd_lookup(bulk_data, names)

    prefs: SearchPrefs = {
        "max_condition": condition,
        "allow_foil": allow_foil,
        "prefer_set": prefer_set,
    }

    # Open a Playwright session for the LGS sweep. In dry-run we deliberately
    # do NOT include Marketplaces — Phase 4 populates the Marketplace cart,
    # which `--dry-run` promises not to do. Online price comparison falls
    # back to the Scryfall USD proxy already used internally for the spill
    # check.
    session_stores = list(LGS_STORES)
    if not dry_run:
        session_stores += list(MARKETPLACE_STORES)

    progress_count = {"done": 0}
    total_searches = len(cards) * len(LGS_STORES)

    def _progress(name, store, listing):
        progress_count["done"] += 1
        marker = "+" if listing else "-"
        click.echo(
            f"  [{progress_count['done']:>3}/{total_searches}] {marker} {store:<14} "
            f"{name}",
            err=True,
        )

    click.echo(
        f"Searching {len(cards)} cards across {len(LGS_STORES)} LGS "
        f"({total_searches} requests)...",
        err=True,
    )
    with _playwright_pages(session_stores, headless=True) as page_factory:
        rows = sweep_lgs(
            cards,
            scryfall_usd_lookup=usd_lookup,
            prefs=prefs,
            page_factory=page_factory,
            sequential=True,
            progress=_progress,
        )
        cfg = AllocationConfig(
            lgs_online_threshold_pct=lgs_online_threshold_pct,
            lgs_online_threshold_usd=lgs_online_threshold_usd,
            consolidate_threshold_pct=consolidate_threshold_pct,
            consolidate_threshold_usd=consolidate_threshold_usd,
        )
        allocation = allocate(rows, cfg)
        assert_no_duplicates_invariant(cards, allocation)

        marketplace_lines: list[Line] = [
            {"card_name": a["card_name"], "qty": a["qty"]}
            for a in allocation
            if a["store"] == "marketplace"
        ]
        if dry_run:
            marketplace = None  # do not touch Marketplace carts in dry-run
        else:
            marketplace = optimize_marketplace(
                marketplace_lines,
                page_factory=page_factory,
            )

    sc: Sidecar = {
        "version": SIDECAR_VERSION,
        "generated_at": now_iso(),
        "allocation": [dict(a) for a in allocation],
        "online_optimizer_results": marketplace,
        "unfindable": [
            a["card_name"]
            for a in allocation
            if a["store"] == "marketplace"
            and marketplace
            and a["card_name"]
            in marketplace.get(marketplace["chosen"], {}).get("unfound", [])
        ],
        "basic_lands_needed": basics,
    }
    write_sidecar(sidecar_path, sc)
    click.echo(_render_summary(allocation, marketplace, basics))

    if dry_run:
        return
    if not confirm_proceed("Proceed with cart build?", yes=yes):
        click.echo("Aborted at confirmation gate.")
        return

    # Phase 5+7: build LGS carts in headed Chromium windows, then leave each
    # window open on the cart for review/checkout. The Marketplace cart was
    # already populated by Phase 4 (optimize_marketplace); we hand it off
    # via the adapter's open_handoff which spawns its own headed window.
    lgs_failures = _build_lgs_carts_and_handoff(
        allocation,
        clear_existing=clear_existing_carts,
        no_handoff=no_handoff,
    )

    if marketplace and marketplace.get("chosen") and not no_handoff:
        chosen = marketplace["chosen"]
        adapter = MARKETPLACE_ADAPTERS[chosen]
        click.echo(
            f"\n=== {adapter.display_name}: opening cart in headed window ===",
        )
        try:
            adapter.open_handoff(profile_dir_for(chosen))
        except Exception as exc:  # noqa: BLE001
            click.echo(
                f"[{chosen}] handoff window failed: {exc}",
                err=True,
            )

    if lgs_failures:
        click.echo("\nCart-build failures:", err=True)
        for store, fails in lgs_failures.items():
            click.echo(f"  {store}: {len(fails)} failed", err=True)
            for name, reason in fails:
                click.echo(f"    - {name}: {reason}", err=True)
