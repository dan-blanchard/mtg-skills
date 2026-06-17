"""Atomic Empire adapter (atomicempire.com).

Uses the documented REST shortcuts for cart manipulation when possible:
- `GET /Cart/AddToCart?itemType=4&itemID={id}&quantity={n}` for adds
- `POST /Cart/RemoveFromCart` for removes (DOM-driven; XHR fires on click)

Search hits `Card/List?txt={query}` (NOT `text=` — that returns no results
for card singles) and parses `div.row.item-row` elements. Each in-stock
row carries `input[name="itemid"]` with the cart-add ID; OOS rows lack it.

Auth detection is pragmatic: AE renders both Sign-in and Sign-out links
in the DOM (toggled via JS), so static parsing can't distinguish auth
state. We assume logged in and let the orchestrator's lazy-fallback
catch real auth failures via cart-add response codes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from bs4 import BeautifulSoup, Tag

from mtg_utils._stores._common import (
    AddToCartResult,
    Listing,
    SearchPrefs,
    StoreSelectorError,
    attr_str,
    name_matches,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page


_BASE_URL = "https://www.atomicempire.com"

_PRICE_RE = re.compile(r"\$([\d,]+\.\d{2})")

# AE labels conditions as compound ranges (e.g. "SP/NM" = Slightly Played to
# Near Mint). The buyer typically receives the BETTER end of the range.
_AE_CONDITION_TO_SHORT = {
    "NM": "NM",
    "SP/NM": "NM",
    "NM/SP": "NM",
    "SP": "LP",
    "PL": "MP",
    "PL/SP": "LP",
    "MP/PL": "MP",
    "HP": "HP",
    "DMG": "HP",
}


def _parse_title(title: str) -> tuple[str, bool, bool]:
    """Parse AE title 'Sol Ring' or '[FOIL] Sol Ring (WPN)' → (name, foil, etched).

    Returns the cleaned card name (set/parens stripped, foil prefix stripped),
    the foil flag, and an etched-foil flag (etched is treated like foil for
    pricing but tracked separately for the future).
    """
    foil = False
    etched = False
    cleaned = title.strip()
    # Strip leading [FOIL] or [ETCHED] tags
    while cleaned.startswith("["):
        idx = cleaned.find("]")
        if idx < 0:
            break
        tag = cleaned[1:idx].strip().upper()
        if tag == "FOIL":
            foil = True
        elif tag == "ETCHED":
            etched = True
            foil = True  # Etched foil counts as foil for our purposes
        cleaned = cleaned[idx + 1 :].strip()
    # Strip trailing parenthetical (set or variant marker)
    cleaned = re.sub(r"\s*\([^()]*\)\s*$", "", cleaned).strip()
    return cleaned, foil, etched


def _money(text: str) -> float:
    return float(text.replace(",", ""))


class _AtomicEmpireAdapter:
    name = "atomic_empire"
    display_name = "Atomic Empire"
    kind: Literal["lgs"] = "lgs"
    base_url = _BASE_URL

    def name_for_search(self, card_name: str) -> str:
        return card_name

    def search(
        self,
        page: Page,
        card_name: str,
        *,
        qty: int,
        prefs: SearchPrefs,
    ) -> list[Listing]:
        del qty, prefs  # filtered downstream by pick_best_listing
        query = self.name_for_search(card_name).replace(" ", "+")
        url = f"{self.base_url}/Card/List?txt={query}"
        if hasattr(page, "goto"):
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(800)
        return self._parse_search(page.content(), card_name, url)

    def _parse_search(
        self,
        html: str,
        requested_name: str,
        url: str,
    ) -> list[Listing]:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("div.row.item-row")
        if not rows:
            page_text = soup.get_text(" ", strip=True).lower()
            if "no results" in page_text or "0 results" in page_text:
                return []
            raise StoreSelectorError(self.name, "div.row.item-row", url)

        listings: list[Listing] = []
        for row in rows:
            listing = self._parse_row(row, requested_name)
            if listing is not None:
                listings.append(listing)
        return listings

    def _parse_row(self, row: Tag, requested_name: str) -> Listing | None:
        itemid_el = row.select_one('input[name="itemid"]')
        if not itemid_el:
            return None  # Out of stock
        itemid = attr_str(itemid_el.get("value")).strip()
        if not itemid:
            return None
        title_el = row.select_one("h5 a")
        if not title_el:
            return None
        full_title = title_el.get_text(strip=True)
        name, foil, _etched = _parse_title(full_title)
        if not name_matches(requested_name, name):
            return None
        # Set link example: <a href="/Card/List?set=Mystery Booster 2">...</a>
        set_el = row.select_one('a[href*="/Card/List?set="]')
        set_text = set_el.get_text(strip=True) if set_el else ""
        # Price text: "SP/NM - $5.35" embedded in a <strong> in the row.
        price_strong = row.find("strong", string=_PRICE_RE)  # ty: ignore[no-matching-overload]
        if not price_strong:
            return None
        price_text = price_strong.get_text(" ", strip=True)
        price_match = _PRICE_RE.search(price_text)
        if not price_match:
            return None
        price = _money(price_match.group(1))
        if price <= 0:
            return None
        # Condition: "SP/NM - $5.35" → "SP/NM"
        cond_part = price_text.split("-")[0].strip().upper()
        condition = _AE_CONDITION_TO_SHORT.get(cond_part, "LP")
        return Listing(
            store=self.name,
            card_name=name,
            set_code=set_text,  # AE uses set NAME, not 3-letter code; fine as-is
            condition=condition,
            foil=foil,
            price=price,
            qty_available=999,  # AE doesn't expose qty cap on search; default high
            listing_id=itemid,
            url=f"{self.base_url}/Card/{itemid}",
        )

    def add_to_cart(self, page: Page, listing: Listing, qty: int) -> AddToCartResult:
        """Use AE's REST endpoint via Playwright's request context.

        page.request preserves the persistent profile's cookies, so the add
        runs as the logged-in user.
        """
        url = (
            f"{self.base_url}/Cart/AddToCart"
            f"?itemType=4&itemID={listing['listing_id']}&quantity={qty}"
        )
        response = page.request.get(url, timeout=20000)
        success = response.ok
        return AddToCartResult(
            success=success,
            qty_added=qty if success else 0,
            cart_url=f"{self.base_url}/Cart",
        )

    def open_handoff(self, profile_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,
            )
            ctx.new_page().goto(f"{self.base_url}/Cart")
            ctx.wait_for_event("close", timeout=0)

    def get_existing_cart(self, page: Page) -> list[Listing]:
        if hasattr(page, "goto"):
            page.goto(f"{self.base_url}/Cart", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
        soup = BeautifulSoup(page.content(), "html.parser")
        # Cart line items have an .remove-item link per row.
        remove_links = soup.select("a.remove-item")
        out: list[Listing] = []
        for link in remove_links:
            row = link.find_parent(class_=re.compile(r"row|cart-item"))
            name_el = row.select_one("h5 a, .item-name") if row else None
            name = name_el.get_text(strip=True) if name_el else "(unknown)"
            out.append(
                Listing(
                    store=self.name,
                    card_name=name,
                    set_code="",
                    condition="NM",
                    foil=False,
                    price=0.0,
                    qty_available=1,
                    listing_id="",
                    url=f"{self.base_url}/Cart",
                )
            )
        return out

    def clear_cart(self, page: Page) -> None:
        if hasattr(page, "goto"):
            page.goto(f"{self.base_url}/Cart", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
        # Click each remove link; XHR fires POST /Cart/RemoveFromCart followed
        # by GET /Cart/ReloadSidebar.
        for _ in range(50):
            link = page.locator("a.remove-item").first
            if link.count() == 0:
                break
            link.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(300)

    def is_logged_in(self, page: Page) -> bool:
        # Pragmatic: AE renders both Sign-in and Sign-out links in the DOM
        # toggled via JS, so static parsing can't distinguish state. We
        # assume logged in. The orchestrator's lazy-fallback handles real
        # auth failures via the cart-add HTTP response.
        return True

    def open_login(self, profile_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,
            )
            ctx.new_page().goto(f"{self.base_url}/Account/Login")
            ctx.wait_for_event("close", timeout=0)


ADAPTER = _AtomicEmpireAdapter()
