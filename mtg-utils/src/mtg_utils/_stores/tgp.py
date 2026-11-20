"""The Gathering Place adapter (BigCommerce storefront + LGS Companion search).

TGP's search page is a client-side app (``#lgsc-search-app``, 2026-11) that
reads the LGS Companion search API; the server-rendered ``article.card``
tiles the adapter used to parse are gone. Search reads that API directly:

    GET https://lgsc-search.lgs-companion.com/search-name
        ?store_hash=pe0wln3ao8&q=<name>&stock_filter=in_stock
        &include_variants=true&limit=48&page=<n>...

Each product is one printing — ``card_name``, ``set_name``, ``card_number``
and ``card_code`` (set + number + finish letter, ``THB258N``), ``finish``
("Normal" / "Foil" / ...), ``variant`` ("Full Art", "None") — and carries
one ``available_variants`` row per language and condition, with its stock
(``inventory_level``), price and BigCommerce product / variant ids. Each
purchasable English row becomes one Listing, so the condition, stock and
price are the row's own. A $9,999.00 row is TGP's placeholder for a listing
it won't sell (seen on 32 LP Hare Apparent), never a price.

Cart adds go through the BigCommerce Storefront cart API
(``/api/storefront/carts``) by product and variant id, so the condition the
sweep picked is the one added.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from mtg_utils._stores._common import (
    AddToCartResult,
    HeadedWindows,
    Listing,
    SearchPrefs,
    StoreSelectorError,
    attr_str,
    name_matches,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page


_BASE_URL = "https://the-gathering-place.mybigcommerce.com"
_SEARCH_API = "https://lgsc-search.lgs-companion.com/search-name"
_STORE_HASH = "pe0wln3ao8"
_PAGE_LIMIT = 48  # the API's maximum
_MAX_PAGES = 6
_RATE_LIMIT_RETRIES = 5
#: TGP prices a row it won't sell at $9,999.00.
_PLACEHOLDER_PRICE = 9999.0

_TGP_CONDITION_TO_SHORT = {
    "Near-Mint": "NM",
    "Near Mint": "NM",
    "Lightly-Played": "LP",
    "Lightly Played": "LP",
    "Moderately-Played": "MP",
    "Moderately Played": "MP",
    "Heavily-Played": "HP",
    "Heavily Played": "HP",
    "Damaged": "HP",
}

_PARENS_RE = re.compile(r"\(([^()]*)\)")

# Adds one line to the session's cart, creating the cart when there is none.
# Returns the HTTP status of the add.
_ADD_JS = """
async ([productId, variantId, quantity]) => {
  const opts = {credentials: 'same-origin'};
  const carts = await (await fetch('/api/storefront/carts', opts)).json();
  const url = carts.length
    ? `/api/storefront/carts/${carts[0].id}/items`
    : '/api/storefront/carts';
  const r = await fetch(url, {
    ...opts,
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({lineItems: [{productId, variantId, quantity}]}),
  });
  return r.status;
}
"""


def search_url(query: str, page_no: int) -> str:
    """The search API URL for one page of in-stock results for *query*."""
    params = {
        "store_hash": _STORE_HASH,
        "q": query,
        "allow_empty": "false",
        "include_variants": "true",
        "include_facets": "false",
        "stock_filter": "in_stock",
        "sort": "featured",
        "stock_first": "true",
        "page": page_no,
        "limit": _PAGE_LIMIT,
        "visible_only": "true",
        "currency_code": "USD",
    }
    return f"{_SEARCH_API}?{urlencode(params)}"


def _set_code(product: dict) -> str:
    """The printing's set code: ``card_code`` less its number and finish letter
    (``THB258N`` -> ``THB``), else the first parenthetical of the product name
    ("Sol Ring (C20) (#252)" -> ``C20``)."""
    code = product.get("card_code") or ""
    number = str(product.get("card_number") or "")
    if number and code[:-1].endswith(number) and len(code) > len(number) + 1:
        return code[: -len(number) - 1]
    match = _PARENS_RE.search(product.get("product_name") or "")
    return match.group(1).strip() if match else ""


def _finish(raw: str | None) -> str:
    """TGP's finish ("Normal", "Foil", "Ripple Foil", "Etched Foil") as
    "nonfoil" / "etched" / "foil"; every non-normal treatment is a foil."""
    text = (raw or "Normal").strip().lower()
    if text == "normal":
        return "nonfoil"
    return "etched" if "etched" in text else "foil"


def _variant_labels(product: dict) -> list[str]:
    variant = (product.get("variant") or "").strip()
    return [] if variant in {"", "None"} else [variant]


def parse_products(
    payload: dict, requested_name: str, *, base_url: str = _BASE_URL
) -> list[Listing]:
    """One Listing per purchasable English condition row of every product
    named *requested_name* in a search API page."""
    listings: list[Listing] = []
    for product in payload.get("products") or []:
        name = product.get("card_name") or ""
        if not name or not name_matches(requested_name, name):
            continue
        finish = _finish(product.get("finish"))
        for row in product.get("available_variants") or []:
            listing = _row_listing(product, row, name, finish, base_url)
            if listing is not None:
                listings.append(listing)
    return listings


def _row_listing(
    product: dict, row: dict, name: str, finish: str, base_url: str
) -> Listing | None:
    condition = _TGP_CONDITION_TO_SHORT.get(row.get("condition") or "")
    price = float(row.get("price") or 0)
    stock = int(row.get("inventory_level") or 0)
    if (
        condition is None
        or (row.get("language") or "English") != "English"
        or not row.get("is_purchasable", True)
        or stock < 1
        or price <= 0
        or price >= _PLACEHOLDER_PRICE
    ):
        return None
    product_id = row.get("bc_product_id") or product.get("bc_product_id")
    variant_id = row.get("bc_variant_id")
    if not product_id or not variant_id:
        return None
    return Listing(
        store="tgp",
        card_name=name,
        set_code=_set_code(product),
        condition=condition,
        foil=finish != "nonfoil",
        price=price,
        qty_available=stock,
        listing_id=f"{product_id}:{variant_id}",
        url=f"{base_url}{product.get('product_url') or ''}",
        collector_number=str(product.get("card_number") or ""),
        set_name=product.get("set_name") or "",
        finish=finish,
        variant_labels=_variant_labels(product),
    )


class _TGPAdapter(HeadedWindows):
    name = "tgp"
    display_name = "The Gathering Place"
    kind: Literal["lgs"] = "lgs"
    base_url = _BASE_URL
    cart_path = "/cart.php"
    login_path = "/login.php"

    def name_for_search(self, card_name: str) -> str:
        # The API's fuzzy match ranks a two-faced card's front face; the
        # listing's full name still matches on any shared face.
        return card_name.split(" // ", maxsplit=1)[0]

    def search(
        self,
        page: Page,
        card_name: str,
        *,
        qty: int,
        prefs: SearchPrefs,
    ) -> list[Listing]:
        """Every in-stock listing of *card_name*, paging the search API (48
        a page) until the results run out. Prefs and qty are applied
        downstream by ``pick_best_listing``."""
        del qty, prefs
        query = self.name_for_search(card_name)
        listings: list[Listing] = []
        for page_no in range(1, _MAX_PAGES + 1):
            url = search_url(query, page_no)
            payload = self._get_json(page, url)
            if "products" not in payload:
                raise StoreSelectorError(self.name, "products", url)
            listings.extend(parse_products(payload, card_name))
            total = int((payload.get("pagination") or {}).get("total") or 0)
            if page_no * _PAGE_LIMIT >= total:
                break
        return listings

    def _get_json(self, page: Page, url: str) -> dict:
        """GET one search page. The API allows about 15 requests a minute and
        answers the rest 429 with a Retry-After (60 s, seen 2026-11); wait it
        out and retry, up to ``_RATE_LIMIT_RETRIES`` times."""
        response = page.request.get(url, timeout=20000)
        for _ in range(_RATE_LIMIT_RETRIES):
            if response.status != 429:
                break
            retry_after = str(response.headers.get("retry-after", ""))
            wait_s = int(retry_after) if retry_after.isdigit() else 60
            page.wait_for_timeout(min(wait_s, 120) * 1000)
            response = page.request.get(url, timeout=20000)
        if not response.ok:
            raise StoreSelectorError(self.name, f"HTTP {response.status}", url)
        return response.json()

    def add_to_cart(self, page: Page, listing: Listing, qty: int) -> AddToCartResult:
        """Add *qty* of the listing's product variant through the Storefront
        cart API. The page must be on the store's origin (the orchestrator
        has it on the cart page by now)."""
        product_id, _, variant_id = listing["listing_id"].partition(":")
        if not variant_id:
            raise StoreSelectorError(self.name, "product:variant id", listing["url"])
        status = page.evaluate(_ADD_JS, [int(product_id), int(variant_id), qty])
        success = status in (200, 201)
        return AddToCartResult(
            success=success,
            qty_added=qty if success else 0,
            cart_url=self.cart_url,
        )

    def get_existing_cart(self, page: Page) -> list[Listing]:
        """Inspect the cart page and return one stub Listing per cart item.

        Only the card_name field is populated; cart pollution detection
        only needs to know that the cart is non-empty.
        """
        if hasattr(page, "goto"):
            page.goto(self.cart_url, wait_until="domcontentloaded")
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
                    url=self.cart_url,
                )
            )
        return out

    def clear_cart(self, page: Page) -> None:
        if hasattr(page, "goto"):
            page.goto(self.cart_url, wait_until="domcontentloaded")
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


ADAPTER = _TGPAdapter()
