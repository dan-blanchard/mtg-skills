"""Shared types, Protocol, and helpers for store adapters."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Protocol, TypedDict, runtime_checkable

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


@runtime_checkable
class StoreAdapter(Protocol):
    name: str
    display_name: str
    kind: Literal["lgs", "online"]
    base_url: str

    def name_for_search(self, card_name: str) -> str: ...
    def search(
        self,
        page,
        card_name: str,
        *,
        qty: int,
        prefs: SearchPrefs,
    ) -> list[Listing]: ...
    def add_to_cart(self, page, listing: Listing, qty: int) -> AddToCartResult: ...
    def open_handoff(self, profile_dir: Path) -> None: ...
    def get_existing_cart(self, page) -> list[Listing]: ...
    def clear_cart(self, page) -> None: ...
    def is_logged_in(self, page) -> bool: ...
    def open_login(self, profile_dir: Path) -> None: ...


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

    if prefs.get("prefer_set"):
        prefer = prefs["prefer_set"].upper()
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
