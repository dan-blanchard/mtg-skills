"""Shared types, Protocol, and helpers for store adapters."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    from playwright.sync_api import Page


def attr_str(value: str | list[str] | None) -> str:
    """Coerce a BeautifulSoup attribute (str, multi-valued list, or missing)
    to a plain string so callers can ``.strip()`` / membership-test safely."""
    if value is None:
        return ""
    return value if isinstance(value, str) else " ".join(value)


def name_matches(requested: str, listing: str) -> bool:
    """Whether a store listing's (set/foil-stripped) name is the requested card.

    Exact match on the canonical-folded names — NOT substring containment, which
    wrongly admits any listing the query is a substring of (searching "Island"
    would otherwise match "Island Sanctuary", "Reliquary Tower", etc.). Split /
    modal-DFC / adventure cards are tolerated by matching on any shared ``//`` face,
    so a deck's "Fire // Ice" still matches a store that lists just "Fire".
    """
    from mtg_utils.names import normalize_card_name

    r = normalize_card_name(requested)
    n = normalize_card_name(listing)
    if r == n:
        return True
    r_faces = {normalize_card_name(p) for p in requested.split("//") if p.strip()}
    n_faces = {normalize_card_name(p) for p in listing.split("//") if p.strip()}
    return bool(r_faces & n_faces)


CONDITION_ORDER = ["NM", "LP", "MP", "HP"]


class SearchPrefs(TypedDict):
    max_condition: Literal["nm", "lp", "mp", "hp", "any"]
    allow_foil: bool
    prefer_set: str | None


class Listing(TypedDict):
    store: str
    card_name: str
    set_code: str
    condition: str
    foil: bool
    price: float
    qty_available: int
    listing_id: str
    url: str


class Line(TypedDict):
    card_name: str
    qty: int


class AddToCartResult(TypedDict):
    success: bool
    qty_added: int
    cart_url: str


class OptimizedLine(TypedDict):
    card_name: str
    qty: int
    unit_price: float
    seller: str


class OptimizedCart(TypedDict):
    store: str
    total: float
    items_subtotal: float
    shipping: float
    lines: list[OptimizedLine]
    unfound: list[str]
    cart_url: str


class StoreSelectorError(Exception):
    def __init__(self, store: str, selector: str, url: str) -> None:
        super().__init__(f"[{store}] selector {selector!r} not found at {url}")
        self.store = store
        self.selector = selector
        self.url = url


class LoginRequiredError(Exception):
    def __init__(self, store: str) -> None:
        super().__init__(f"[{store}] login required")
        self.store = store


class CartNotEmptyError(Exception):
    """Raised by an online optimizer when the cart already has items.

    MP's /add-deck appends to the existing cart rather than replacing it,
    so any pre-existing items poison the optimizer's totals. The
    orchestrator catches this in optimize_online's per-store loop and
    surfaces a punch-list entry telling the user to clear the cart
    before re-running.
    """

    def __init__(self, store: str, n_items: int, cart_url: str) -> None:
        super().__init__(
            f"[{store}] cart already has {n_items} item(s) — clear at "
            f"{cart_url} before re-running so the optimizer compares "
            "against your submission only",
        )
        self.store = store
        self.n_items = n_items
        self.cart_url = cart_url


StorefrontKind = Literal["lgs", "marketplace"]


@runtime_checkable
class StoreSession(Protocol):
    """Lifecycle methods every Storefront has — auth, cart inspection,
    cart clearing, headed-window handoff, name canonicalization. The
    cross-kind iteration sites (cart-pollution sweep, login pre-flight,
    Phase 7 handoff, grand-total report) only depend on this surface.
    See lgs-search/CONTEXT.md for the domain language.
    """

    name: str
    display_name: str
    kind: StorefrontKind
    base_url: str

    def name_for_search(self, card_name: str) -> str: ...
    def get_existing_cart(self, page: Page) -> list[Listing]: ...
    def clear_cart(self, page: Page) -> None: ...
    def is_logged_in(self, page: Page) -> bool: ...
    def open_login(self, profile_dir: Path) -> None: ...
    def open_handoff(self, profile_dir: Path) -> None: ...


@runtime_checkable
class LGSAdapter(StoreSession, Protocol):
    """A StoreSession whose shopping flow is per-item: `search` returns
    Listings; `add_to_cart` adds one Listing at a time. The Storefront
    is a single physical shop with its own first-party inventory.
    """

    kind: Literal["lgs"]

    def search(
        self,
        page: Page,
        card_name: str,
        *,
        qty: int,
        prefs: SearchPrefs,
    ) -> list[Listing]: ...
    def add_to_cart(
        self, page: Page, listing: Listing, qty: int
    ) -> AddToCartResult: ...


@runtime_checkable
class MarketplaceAdapter(StoreSession, Protocol):
    """A StoreSession whose shopping flow is bulk:
    `bulk_submit_and_optimize` submits an entire want-list and runs the
    site's seller-consolidation optimizer. The Storefront is an
    aggregator over many third-party sellers.
    """

    kind: Literal["marketplace"]

    def bulk_submit_and_optimize(
        self,
        page: Page,
        lines: list[Line],
    ) -> OptimizedCart: ...


def cache_dir() -> Path:
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    if base:
        return Path(base)
    return Path.home() / ".cache" / "mtg-skills"


def profile_dir_for(store: str) -> Path:
    p = cache_dir() / "lgs-profiles" / store
    p.mkdir(parents=True, exist_ok=True)
    return p


_MAX_COND_INDEX = {
    "nm": 0,
    "lp": 1,
    "mp": 2,
    "hp": 3,
    "any": 3,
}


def _set_age_rank(set_code: str) -> int:
    """Heuristic newest-on-tie ordering. Larger = newer.

    The orchestrator passes Scryfall's `released_at` when available;
    when only the set code is on the listing we approximate by string
    comparison (alphabetic three-letter codes are roughly chronological
    in the modern era; truly exotic codes default to 0).
    """
    return sum(ord(c) for c in set_code.upper()) if set_code else 0


def pick_best_listing(
    listings: list[Listing],
    *,
    qty: int,
    prefs: SearchPrefs,
) -> Listing | None:
    """Pick the best listing per the spec's precedence rules.

    Precedence (top-down):
      1. Drop foils, unless `allow_foil` is set or no non-foil exists.
      2. Drop conditions worse than `max_condition`.
      3. Drop listings without enough `qty_available` for the request.
      4. If `prefer_set` matches an in-stock surviving listing, prefer it.
      5. Cheapest unit price wins.
      6. On price tie: non-foil > foil > NM > LP > MP > HP > newest set.

    Returns None when no listing satisfies the filters.
    """
    if not listings:
        return None

    max_idx = _MAX_COND_INDEX.get(prefs["max_condition"], 3)

    def cond_idx(listing: Listing) -> int:
        try:
            return CONDITION_ORDER.index(listing["condition"].upper())
        except ValueError:
            return 99

    pool = [x for x in listings if cond_idx(x) <= max_idx and x["qty_available"] >= qty]
    if not pool:
        return None

    non_foil = [x for x in pool if not x["foil"]]
    if non_foil and not prefs.get("allow_foil"):
        pool = non_foil
    # else: keep both (allow_foil) or only foils (no non_foil exists) — price wins

    if prefer_set := prefs.get("prefer_set"):
        prefer = prefer_set.upper()
        in_set = [x for x in pool if x["set_code"].upper() == prefer]
        if in_set:
            pool = in_set

    # Sort key: rule 5 (price) → rule 6a (non-foil < foil) →
    # rule 6b (NM < LP < MP < HP via cond_idx) → rule 6c (newer set wins).
    pool.sort(
        key=lambda x: (
            x["price"],
            x["foil"],
            cond_idx(x),
            -_set_age_rank(x["set_code"]),
        ),
    )
    return pool[0]
