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


_BASE_URL = "https://the-gathering-place.mybigcommerce.com"

_PRICE_RANGE_RE = re.compile(r"\$([\d,]+\.\d{2})\s*-\s*\$([\d,]+\.\d{2})")
_SINGLE_PRICE_RE = re.compile(r"\$([\d,]+\.\d{2})")
_PARENS_RE = re.compile(r"\s*\(([^()]*)\)")
_AVAIL_RE = re.compile(r"available\s+(\d+)", re.IGNORECASE)

_TGP_CONDITION_TO_SHORT = {
    "Near-Mint": "NM",
    "Near Mint": "NM",
    "Lightly-Played": "LP",
    "Lightly Played": "LP",
    "Moderately-Played": "MP",
    "Moderately Played": "MP",
    "Heavily-Played": "HP",
    "Heavily Played": "HP",
}

_SHORT_TO_INDEX = {"NM": 0, "LP": 1, "MP": 2, "HP": 3}


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
        data_name = attr_str(el.get("data-name")).strip()
        if not data_name:
            return None
        name, set_code, foil = _parse_data_name(data_name)
        if not name_matches(requested_name, name):
            return None
        text = el.get_text(" ", strip=True)
        if "out of stock" in text.lower():
            return None
        # `data-product-price` is the canonical BigCommerce single price.
        # The displayed text range ($X - $Y) sometimes includes prices of
        # variants no longer in stock, which would over- or under-report
        # the actual cart-time cost. Fall back to the displayed range only
        # when data-product-price is missing.
        raw = attr_str(el.get("data-product-price")).strip()
        try:
            price = _money(raw)
        except ValueError:
            m = _PRICE_RANGE_RE.search(text) or _SINGLE_PRICE_RE.search(text)
            if not m:
                return None
            price = _money(m.group(1))
        if price <= 0:
            return None
        link = el.select_one("a.card-figure__link") or el.select_one("a")
        href = attr_str(link.get("href")) if link else ""
        product_url = href or self.base_url
        listing_id = attr_str(el.get("data-entity-id")).strip()
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

    def parse_product_variants(
        self,
        html: str,
        *,
        max_condition: str = "any",
    ) -> list[dict]:
        """Parse the product page's bulk-variant-picker into structured rows.

        Returns one dict per in-stock variant matching the max_condition
        cap, ordered cheapest first. Each dict has keys: condition (NM/LP/...),
        price (float), qty_available (int), data_index (str), language (str).
        """
        soup = BeautifulSoup(html, "html.parser")
        picker = soup.select_one("div#bulk-variant-picker")
        if not picker:
            return []
        cap = _SHORT_TO_INDEX.get(max_condition.upper(), 99)
        out = []
        for row in picker.select("tr.bulk-row[data-index]"):
            cond_el = row.select_one("span.bulk-cond")
            price_el = row.select_one("td.bulk-price")
            avail_el = row.select_one("div.avail-badge")
            lang_el = row.select_one("span.bulk-lang")
            if not (cond_el and price_el and avail_el):
                continue
            cond_short = _TGP_CONDITION_TO_SHORT.get(
                cond_el.get_text(strip=True),
                "",
            )
            if not cond_short or _SHORT_TO_INDEX[cond_short] > cap:
                continue
            avail_text = avail_el.get_text(" ", strip=True)
            avail_match = _AVAIL_RE.search(avail_text)
            qty_avail = int(avail_match.group(1)) if avail_match else 0
            if qty_avail < 1:
                continue
            price_match = _SINGLE_PRICE_RE.search(price_el.get_text(strip=True))
            if not price_match:
                continue
            out.append(
                {
                    "condition": cond_short,
                    "price": _money(price_match.group(1)),
                    "qty_available": qty_avail,
                    "data_index": row.get("data-index", ""),
                    "language": lang_el.get_text(strip=True) if lang_el else "English",
                }
            )
        out.sort(key=lambda v: (v["price"], _SHORT_TO_INDEX[v["condition"]]))
        return out

    def add_to_cart(self, page: Page, listing: Listing, qty: int) -> AddToCartResult:
        """Navigate to the product URL and add the cheapest in-stock variant.

        Selection of the variant on the product page is best-effort: we
        pick the cheapest in-stock row that still satisfies the listing's
        condition floor (the listing was filtered by `pick_best_listing`
        upstream, but the product page may have moved since the search).
        Falls back to the first variant if no exact match.
        """
        page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("tr.bulk-row[data-index]", timeout=15000)
        page.wait_for_timeout(300)
        # Pick variant: prefer one matching the listing's condition or better.
        variants = self.parse_product_variants(
            page.content(),
            max_condition=listing.get("condition", "any"),
        )
        if not variants:
            # Try without the condition cap as a last-ditch fallback.
            variants = self.parse_product_variants(page.content())
        if not variants:
            raise StoreSelectorError(self.name, "tr.bulk-row", listing["url"])
        chosen = variants[0]
        # Click the + button on the chosen row qty times.
        idx = chosen["data_index"]
        plus_btn = page.locator(
            f"tr.bulk-row[data-index='{idx}'] button.bulk-btn[data-act=plus]",
        )
        for _ in range(qty):
            plus_btn.click()
            page.wait_for_timeout(100)
        # Capture the cart counter before clicking so we can poll for it
        # to change. BigCommerce's `networkidle` never settles on this site
        # (analytics long-polls keep the network active indefinitely), so
        # wait_for_load_state was timing out at 20s on every successful add.
        try:
            before_count = (
                page.locator(".cart-quantity").first.inner_text(timeout=2000).strip()
            )
        except Exception:  # noqa: BLE001
            before_count = ""
        add_btn = page.locator("button#bulkAddBtn")
        add_btn.click()
        confirmed = False
        try:
            page.wait_for_function(
                "(prev) => "
                "(document.querySelector('.cart-quantity')?.textContent || '')"
                ".trim() !== prev",
                arg=before_count,
                timeout=10000,
            )
            confirmed = True
        except Exception:  # noqa: BLE001
            # The confirmation wait timed out (XHR slow, or .cart-quantity renamed).
            # Settle briefly, then best-effort re-read: only claim success if the
            # cart count actually changed. Reporting success=True unconditionally
            # would mask a genuine add failure as a silent no-op.
            page.wait_for_timeout(1500)
            try:
                after = (
                    page.locator(".cart-quantity")
                    .first.inner_text(timeout=2000)
                    .strip()
                )
                confirmed = bool(after) and after != before_count
            except Exception:  # noqa: BLE001
                confirmed = False
        return AddToCartResult(
            success=confirmed,
            qty_added=qty if confirmed else 0,
            cart_url=f"{self.base_url}/cart.php",
        )

    def open_handoff(self, profile_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(profile_dir), headless=False)
            ctx.new_page().goto(f"{self.base_url}/cart.php")
            # Block until the user closes the window.
            ctx.wait_for_event("close", timeout=0)

    def get_existing_cart(self, page: Page) -> list[Listing]:
        """Inspect the cart page and return one stub Listing per cart item.

        Only the card_name field is populated; cart pollution detection
        only needs to know that the cart is non-empty.
        """
        if hasattr(page, "goto"):
            page.goto(f"{self.base_url}/cart.php", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
        soup = BeautifulSoup(page.content(), "html.parser")
        # Empty-cart heuristic: the cart-empty fixture contains "empty" text
        # and lacks individual cart items. BigCommerce stencil typically uses
        # `.cart-item` or `tr.cart-item` for line items.
        rows = soup.select(".cart-item, tr.cart-item")
        out: list[Listing] = []
        for row in rows:
            name_el = row.select_one(
                ".cart-item-name, .cart-item-title, h4 a, a.cart-item-link",
            )
            if not name_el:
                continue
            out.append(
                Listing(
                    store=self.name,
                    card_name=name_el.get_text(strip=True),
                    set_code="",
                    condition="NM",
                    foil=False,
                    price=0.0,
                    qty_available=1,
                    listing_id="",
                    url=f"{self.base_url}/cart.php",
                )
            )
        return out

    def clear_cart(self, page: Page) -> None:
        if hasattr(page, "goto"):
            page.goto(f"{self.base_url}/cart.php", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
        # Per line: `button.cart-remove` carries `data-confirm-delete` and
        # spawns a BigCommerce "reveal" modal containing
        # `button.confirm` ("OK"). Both clicks are dispatched through JS:
        # the sticky header / modal-background overlay break Playwright's
        # standard click hit-testing, and the confirm button is layered in
        # a way that .is_visible() returns false even when it works.
        for _ in range(50):
            remove_btn = page.locator("button.cart-remove").first
            if remove_btn.count() == 0:
                break
            page.evaluate("document.querySelector('button.cart-remove')?.click()")
            page.wait_for_timeout(600)
            page.evaluate("document.querySelector('.modal button.confirm')?.click()")
            page.wait_for_timeout(800)

    def is_logged_in(self, page: Page) -> bool:
        """Detect logged-in state from header navigation links.

        Logged-out: header has a 'login.php' link with text "LOGIN" or "Sign in".
        Logged-in: header has a 'logout.php' link or "/account.php" (no login link).
        """
        soup = BeautifulSoup(page.content(), "html.parser")
        # If a logout link exists anywhere, we're logged in.
        if soup.select_one('a[href*="logout"]'):
            return True
        # If only login/register links exist, we're logged out.
        login_links = soup.select('a[href*="/login.php"]')
        if login_links:
            # Any link that's a plain login (not the register variant) means logged out.
            for link in login_links:
                href = attr_str(link.get("href"))
                if "create_account" not in href and link.get_text(strip=True):
                    return False
        # Ambiguous — assume logged in to avoid a spurious login prompt.
        # The lazy fallback in the orchestrator will catch real auth failures.
        return True

    def open_login(self, profile_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(profile_dir), headless=False)
            ctx.new_page().goto(f"{self.base_url}/login.php")
            ctx.wait_for_event("close", timeout=0)


ADAPTER = _TGPAdapter()
