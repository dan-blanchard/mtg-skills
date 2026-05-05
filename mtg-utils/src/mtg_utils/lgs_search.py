"""lgs-search orchestrator CLI.

Workflow: input → LGS sweep → allocate → online optimize → confirm →
build carts → handoff. See specs/2026-05-04-lgs-search-design.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from mtg_utils._sidecar import atomic_write_json
from mtg_utils._stores._common import Listing
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
    store: str  # "tgp" | "atomic_empire" | "online"
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
         (per cfg's pct/usd thresholds), spill the whole card line to "online".
      3. Otherwise pick cheapest LGS. If both LGS are "close" by cfg's
         consolidate thresholds, prefer the LGS with the higher running cart
         total to minimize trips.
      4. If chosen store can't fill the requested qty, fall through to the
         next-cheapest store; residual that no store can fill goes online.
    """
    running_totals: dict[str, float] = dict.fromkeys(_LGS_KEYS, 0.0)
    out: list[AllocatedCard] = []

    for row in rows:
        candidates = {k: row[k] for k in _LGS_KEYS if row[k] is not None}
        sorted_keys = sorted(candidates, key=lambda k: candidates[k]["price"])

        cheapest_lgs = (
            candidates[sorted_keys[0]]["price"] if sorted_keys else float("inf")
        )

        if _spill_triggered(cheapest_lgs, row["scryfall_usd"], cfg):
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=row["qty"],
                    store="online",
                    listing=None,
                )
            )
            continue

        if not sorted_keys:
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=row["qty"],
                    store="online",
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
                    store="online",
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
# Sidecar I/O and resume rules
# ---------------------------------------------------------------------------

SIDECAR_VERSION = 1


class PhaseProgress(TypedDict, total=False):
    status: Literal["pending", "partial", "complete"]
    items_added: int
    remaining: list


class Sidecar(TypedDict, total=False):
    version: int
    generated_at: str
    input_hash: str
    phase: Literal[
        "search_complete",
        "allocation_complete",
        "cart_build_in_progress",
        "done",
    ]
    phase_progress: dict[str, PhaseProgress]
    allocation: list[dict]
    online_optimizer_results: dict | None
    unfindable: list[str]
    basic_lands_needed: dict[str, int]


def compute_input_hash(cards: list[dict]) -> str:
    """SHA-256 over the canonicalized card list. Order- and case-independent.

    Card names are normalized via `mtg_utils.names.normalize_card_name`
    (NFKD ASCII-fold + lowercase) before hashing so cosmetic edits to the
    deck input (re-casing, whitespace) don't trip the --resume hash gate.
    """
    canon = sorted((normalize_card_name(c["card_name"]), int(c["qty"])) for c in cards)
    payload = json.dumps(canon, ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_sidecar(path: Path, sc: Sidecar) -> None:
    """Atomic-rename write so concurrent readers can't see a partial file.

    Delegates to the shared `atomic_write_json` helper, which uses a
    per-call NamedTemporaryFile so concurrent writers don't collide on
    the same `.tmp` name.
    """
    atomic_write_json(path, sc)


def load_sidecar(path: Path) -> Sidecar:
    sc = json.loads(path.read_text(encoding="utf-8"))
    if sc.get("version") != SIDECAR_VERSION:
        msg = (
            f"unsupported sidecar version {sc.get('version')};"
            f" expected {SIDECAR_VERSION}"
        )
        raise ValueError(msg)
    return sc


def assert_hash_matches(*, sidecar: Sidecar, cards: list[dict]) -> None:
    """Reject ``--resume`` if the input deck has changed since sidecar was written."""
    expected = compute_input_hash(cards)
    if sidecar.get("input_hash") != expected:
        msg = (
            f"input hash mismatch: sidecar={sidecar.get('input_hash')} "
            f"current={expected}"
        )
        raise ValueError(msg)


def next_phase_actions(sc: Sidecar) -> list[str]:
    """Given a sidecar's phase, return the list of remaining workflow steps."""
    phase = sc["phase"]
    if phase == "search_complete":
        return ["allocate", "confirm", "build_carts", "handoff"]
    if phase == "allocation_complete":
        return ["confirm", "build_carts", "handoff"]
    if phase == "cart_build_in_progress":
        return ["resume_carts", "handoff"]
    if phase == "done":
        return []
    msg = f"unknown sidecar phase {phase!r}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Step 2: LGS sweep (ThreadPoolExecutor)
# ---------------------------------------------------------------------------

from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: E402
from threading import Semaphore  # noqa: E402

from mtg_utils._stores import LGS_STORES, STORE_REGISTRY  # noqa: E402
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
) -> list[SearchResultRow]:
    """Search every LGS for every card; return one SearchResultRow per card.

    `page_factory` is a callable `(store_name) -> Page-like` injected for
    testability. In production the orchestrator passes a real Playwright
    page-pool factory; tests pass a mock. When None, this function calls
    each adapter's `search` with `page=None` (adapters tolerate it for
    their fixture-based tests but real adapters will need real pages).
    """
    semaphores = {name: Semaphore(per_store_concurrency) for name in LGS_STORES}

    def _search_one(card, store):
        adapter = STORE_REGISTRY[store]
        with semaphores[store]:
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
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [
            ex.submit(_search_one, card, store)
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

from mtg_utils._stores import ONLINE_STORES  # noqa: E402
from mtg_utils._stores._common import OptimizedCart  # noqa: E402


def optimize_online(
    online_lines: list[dict],
    *,
    page_factory=None,
) -> dict | None:
    """Submit `online_lines` to each online adapter and pick the cheapest total.

    Returns dict mapping store name to OptimizedCart, plus 'chosen' key
    naming the cheapest. Returns None when there are no online lines.
    """
    if not online_lines:
        return None
    results: dict[str, OptimizedCart] = {}
    for store in ONLINE_STORES:
        adapter = STORE_REGISTRY[store]
        page = page_factory(store) if page_factory else None
        results[store] = adapter.bulk_submit_and_optimize(page, online_lines)
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
@click.option(
    "--resume",
    "resume_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
@click.pass_context
def main(ctx, **kwargs):
    """Search LGS + online stores; allocate; build carts."""
    if ctx.invoked_subcommand is not None:
        return
    if kwargs.get("input_path") is None and kwargs.get("resume_path") is None:
        click.echo("--input is required (or use --resume)", err=True)
        ctx.exit(2)
    _run_orchestrator(**kwargs)


@main.command()
@click.option(
    "--store",
    required=True,
    type=click.Choice(["tgp", "atomic_empire", "tcgplayer", "manapool"]),
)
def login(store: str) -> None:
    """Open a headed browser for one-time login at a store."""
    adapter = STORE_REGISTRY[store]
    profile = profile_dir_for(store)
    click.echo(f"Opening {adapter.display_name} login. Close the window when done.")
    adapter.open_login(profile)


# ---------------------------------------------------------------------------
# Orchestrator helpers
# ---------------------------------------------------------------------------


def _scryfall_usd_lookup(bulk_path: Path | None, names: list[str]) -> dict[str, float]:
    """Best-effort: read prices.usd from Scryfall bulk data for the given names.

    Goes through the shared `bulk_loader.load_bulk_cards` so we get the
    pickled-sidecar cache (~5-10x faster on warm load) instead of re-reading
    a 150 MB JSON file every invocation. Returns 0.0 for unknown cards (the
    allocator's spill check guards against spilling on unknown-online-price;
    see _spill_triggered).
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
    by_name: dict[str, dict] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        n = row.get("name")
        if n in name_set and n not in by_name:
            by_name[n] = row
    out: dict[str, float] = {}
    for name in names:
        row = by_name.get(name) or {}
        usd = (row.get("prices") or {}).get("usd")
        try:
            out[name] = float(usd) if usd else 0.0
        except (TypeError, ValueError):
            out[name] = 0.0
    return out


def _render_summary(allocation, online, basics) -> str:
    """Render the markdown summary printed to stdout."""
    lines = ["## Cart allocation"]
    by_store: dict[str, list] = {}
    for a in allocation:
        by_store.setdefault(a["store"], []).append(a)
    for store, items in by_store.items():
        if store == "online":
            continue
        adapter = STORE_REGISTRY.get(store)
        name = adapter.display_name if adapter else store
        total = sum((a["listing"] or {}).get("price", 0) * a["qty"] for a in items)
        lines.append(f"\n{name} - {len(items)} cards, ${total:.2f}")
        for a in items:
            li = a["listing"] or {}
            lines.append(
                f"  + {a['card_name']} ({li.get('condition', '?')}) - "
                f"${li.get('price', 0):.2f}",
            )
    if online and online.get("chosen"):
        chosen = online["chosen"]
        result = online[chosen]
        # Other online stores in the registry, excluding the chosen one.
        # Robust to single-online-store configurations (no IndexError if
        # ONLINE_STORES is ever pruned to one entry).
        losers = [
            s
            for s in ONLINE_STORES
            if s != chosen and s in online and isinstance(online[s], dict)
        ]
        if losers:
            loser = losers[0]
            comparison = (
                f"chosen over {STORE_REGISTRY[loser].display_name}: "
                f"${result['total']:.2f} vs ${online[loser]['total']:.2f}"
            )
        else:
            comparison = f"only online option, ${result['total']:.2f}"
        lines.append(
            f"\n{STORE_REGISTRY[chosen].display_name} "
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
    resume_path,
):
    # v1: the live cart-build path (after the confirmation gate) is stubbed,
    # so the timeout/retry/clear-cart/retry-relaxed flags can't take effect
    # yet. Warn explicitly when a user passes any of them so they don't
    # silently expect behavior that isn't wired.
    not_yet_wired = []
    if retry_relaxed:
        not_yet_wired.append("--retry-relaxed")
    if clear_existing_carts:
        not_yet_wired.append("--clear-existing-carts")
    if search_timeout_seconds != 20:
        not_yet_wired.append("--search-timeout-seconds")
    if cart_timeout_seconds != 30:
        not_yet_wired.append("--cart-timeout-seconds")
    if max_retries != 3:
        not_yet_wired.append("--max-retries")
    if not_yet_wired:
        click.echo(
            f"Note: {', '.join(not_yet_wired)} not yet wired in v1 "
            "(live cart-build orchestration is a stub). Flag accepted but "
            "has no effect.",
            err=True,
        )
    del search_timeout_seconds, cart_timeout_seconds, max_retries
    del clear_existing_carts, retry_relaxed

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = output_dir / "lgs-cart-allocation.json"

    if resume_path:
        click.echo("Resume: replays summary; partial cart resume not yet wired.")
        return

    cards, basics = resolve_input(
        input_path,
        collection_path=collection,
        include_basics=include_basics,
    )
    names = [c["card_name"] for c in cards]
    usd_lookup = _scryfall_usd_lookup(bulk_data, names)

    prefs: SearchPrefs = {
        "max_condition": condition,
        "allow_foil": allow_foil,
        "prefer_set": prefer_set,
    }

    rows = sweep_lgs(cards, scryfall_usd_lookup=usd_lookup, prefs=prefs)
    cfg = AllocationConfig(
        lgs_online_threshold_pct=lgs_online_threshold_pct,
        lgs_online_threshold_usd=lgs_online_threshold_usd,
        consolidate_threshold_pct=consolidate_threshold_pct,
        consolidate_threshold_usd=consolidate_threshold_usd,
    )
    allocation = allocate(rows, cfg)
    assert_no_duplicates_invariant(cards, allocation)

    online_lines = [
        {"card_name": a["card_name"], "qty": a["qty"]}
        for a in allocation
        if a["store"] == "online"
    ]
    online = optimize_online(online_lines)

    sc: Sidecar = {
        "version": SIDECAR_VERSION,
        "generated_at": now_iso(),
        "input_hash": compute_input_hash(cards),
        "phase": "allocation_complete",
        "phase_progress": {},
        "allocation": [dict(a) for a in allocation],
        "online_optimizer_results": online,
        "unfindable": [
            a["card_name"]
            for a in allocation
            if a["store"] == "online"
            and online
            and a["card_name"] in online.get(online["chosen"], {}).get("unfound", [])
        ],
        "basic_lands_needed": basics,
    }
    write_sidecar(sidecar_path, sc)
    click.echo(_render_summary(allocation, online, basics))

    if dry_run:
        return
    if not confirm_proceed("Proceed with cart build?", yes=yes):
        click.echo("Aborted at confirmation gate.")
        return

    # Cart build, retry-relaxed, handoff: stubbed for v1. The dry-run path
    # is the integration-tested path; live cart build is verified manually.
    if not no_handoff:
        click.echo("(Live cart-build + handoff not yet wired in v1.)")
