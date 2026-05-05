"""The Gathering Place adapter (BigCommerce stencil).

Search-page only for v1: each in-stock `article.card` becomes one Listing,
priced at the low end of the displayed range. Condition is reported as "NM"
(unknown — TGP shows the price range across all in-stock variants without
condition labels on the search page). Cart-add navigates to the product page
and uses the per-variant table, so the actual cheapest qualifying variant
gets added at cart-time. The price reported during the sweep is therefore
the BEST possible price; the cart may add a higher-priced variant if NM-only
is required and the cheapest variant is LP.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from bs4 import BeautifulSoup, Tag

from mtg_utils._stores._common import (
    AddToCartResult,
    Listing,
    SearchPrefs,
    StoreSelectorError,
)

_BASE_URL = "https://the-gathering-place.mybigcommerce.com"

_PRICE_RANGE_RE = re.compile(r"\$([\d,]+\.\d{2})\s*-\s*\$([\d,]+\.\d{2})")
_SINGLE_PRICE_RE = re.compile(r"\$([\d,]+\.\d{2})")
_PARENS_RE = re.compile(r"\s*\(([^()]*)\)")


def _parse_data_name(data_name: str) -> tuple[str, str, bool]:
    """Parse `data-name` like 'Sol Ring (C20) (#252)' → ('Sol Ring', 'C20', False).

    Strips trailing parenthetical chunks. Recognizes '(Foil)' as a foil marker
    rather than a set code. The first non-foil parenthetical group becomes
    the set code; the leading text becomes the name.
    """
    foil = False
    set_code = ""
    chunks = _PARENS_RE.findall(data_name)
    name = _PARENS_RE.sub("", data_name).strip()
    for chunk in chunks:
        cleaned = chunk.strip()
        if cleaned.lower() == "foil":
            foil = True
            continue
        if cleaned.startswith("#"):
            # Collector number, ignore.
            continue
        if not set_code:
            set_code = cleaned
    return name, set_code, foil


def _money(text: str) -> float:
    return float(text.replace(",", ""))


class _TGPAdapter:
    name = "tgp"
    display_name = "The Gathering Place"
    kind: Literal["lgs", "online"] = "lgs"
    base_url = _BASE_URL

    def name_for_search(self, card_name: str) -> str:
        return card_name

    def search(
        self,
        page,
        card_name: str,
        *,
        qty: int,
        prefs: SearchPrefs,
    ) -> list[Listing]:
        # qty respected at add_to_cart; prefs handled downstream by pick_best_listing.
        del qty, prefs
        query = self.name_for_search(card_name).replace(" ", "+")
        url = f"{self.base_url}/search.php?search_query={query}"
        if hasattr(page, "goto"):
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(800)  # BigCommerce hydration
        return self._parse_search(page.content(), card_name, page.url)

    def _parse_search(self, html: str, requested_name: str, url: str) -> list[Listing]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("article.card")
        if not cards:
            # Could be a real "no results" page; check before crying selector.
            page_text = soup.get_text(" ", strip=True).lower()
            if "0 results" in page_text or "no results" in page_text:
                return []
            raise StoreSelectorError(self.name, "article.card", url)

        listings: list[Listing] = []
        for el in cards:
            listing = self._parse_card(el, requested_name)
            if listing is not None:
                listings.append(listing)
        return listings

    def _parse_card(self, el: Tag, requested_name: str) -> Listing | None:
        data_name = (el.get("data-name") or "").strip()
        if not data_name:
            return None
        name, set_code, foil = _parse_data_name(data_name)
        if requested_name.lower() not in name.lower():
            return None
        text = el.get_text(" ", strip=True)
        if "out of stock" in text.lower():
            return None
        # Price-range low end is the cheapest variant; fall back to single price.
        m = _PRICE_RANGE_RE.search(text)
        if m:
            price = _money(m.group(1))
        else:
            single = _SINGLE_PRICE_RE.search(text)
            if not single:
                return None
            price = _money(single.group(1))
        if price <= 0:
            return None
        link = el.select_one("a.card-figure__link") or el.select_one("a")
        product_url = link.get("href") if link else self.base_url
        listing_id = (el.get("data-entity-id") or "").strip()
        if not listing_id:
            return None
        return Listing(
            store=self.name,
            card_name=name,
            set_code=set_code,
            condition="NM",  # TGP search page doesn't expose per-variant condition
            foil=foil,
            price=price,
            qty_available=999,  # Not exposed on search page; assume sufficient
            listing_id=listing_id,
            url=product_url,
        )

    # Cart, login, handoff stubbed for Task 7.
    def add_to_cart(self, page, listing: Listing, qty: int) -> AddToCartResult:
        raise NotImplementedError("Task 7 wires this up.")

    def open_handoff(self, profile_dir: Path) -> None:
        raise NotImplementedError("Task 7 wires this up.")

    def get_existing_cart(self, page) -> list[Listing]:
        raise NotImplementedError("Task 7 wires this up.")

    def clear_cart(self, page) -> None:
        raise NotImplementedError("Task 7 wires this up.")

    def is_logged_in(self, page) -> bool:
        raise NotImplementedError("Task 7 wires this up.")

    def open_login(self, profile_dir: Path) -> None:
        raise NotImplementedError("Task 7 wires this up.")


ADAPTER = _TGPAdapter()
