"""TCGPlayer adapter (Mass Entry → Cart → Cart Optimizer flow).

Live-discovered flow (2026-05):
1. POST list → `https://www.tcgplayer.com/massentry`
   - Fill `[contenteditable=true].mass-entry-input` with `qty CardName` lines.
   - Click `button.mass-entry__body__actions--submit` (text "Add to Cart").
   - Browser navigates to `/cart`.
2. From `/cart`, click the inline `button:has-text("Optimize")` to navigate
   to `/cart/optimizer`.
3. On `/cart/optimizer`, click the action `Optimize` button (only one
   visible button with that text on the page).
4. The optimizer renders three alternative carts: "TCGplayer Direct",
   "Verified Sellers", "Any Seller". Each shows `Cart Subtotal: $X.XX`.
5. Pick the cheapest, click its `Select this cart` button. The user's
   cart now reflects that optimized basket.

This module returns an `OptimizedCart` with the cheapest total
(items + shipping). `add_to_cart` is a no-op because the cart is
already populated by `bulk_submit_and_optimize`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from bs4 import BeautifulSoup

from mtg_utils._stores._common import (
    CartNotEmptyError,
    Line,
    Listing,
    OptimizedCart,
    StoreSelectorError,
)

_BASE_URL = "https://www.tcgplayer.com"

_PRICE_RE = re.compile(r"\$([\d,]+\.\d{2})")
_PACKAGES_RE = re.compile(r"Packages\s*\n\s*(\d+)", re.IGNORECASE)


def _money(text: str) -> float:
    return float(text.replace(",", "").replace("$", ""))


def _parse_optimizer_alternatives(html: str) -> list[dict]:
    """Parse the optimizer-results page into a list of cart alternatives.

    Each alternative has keys: subtotal, packages, items, item_total,
    shipping. Only the cards under a "Select this cart" button are
    returned — the "Current Cart" panel uses "Keep this cart" and is
    excluded.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = text.split("\n")
    alternatives = []
    for i, line in enumerate(lines):
        if line.strip() != "Cart Subtotal:":
            continue
        # Subtotal is on the next line.
        if i + 1 >= len(lines):
            continue
        sub_match = _PRICE_RE.search(lines[i + 1])
        if not sub_match:
            continue
        # Only count alternatives — i.e. blocks ending in "Select this cart".
        # Look ahead 1-3 lines for that anchor.
        is_selectable = False
        for j in range(i + 2, min(len(lines), i + 5)):
            if "Select this cart" in lines[j]:
                is_selectable = True
                break
            if "Keep this cart" in lines[j]:
                break
        if not is_selectable:
            continue
        subtotal = _money(sub_match.group(1))
        # Walk back up to ~14 lines for the surrounding numbers.
        window = lines[max(0, i - 14) : i]
        packages = _extract_after_label(window, "Packages")
        items = _extract_after_label(window, "Items")
        item_total = _extract_money_after_label(window, "Item Total")
        shipping = _extract_money_after_label(window, "Shipping")
        alternatives.append(
            {
                "subtotal": subtotal,
                "packages": packages,
                "items": items,
                "item_total": item_total,
                "shipping": shipping,
            }
        )
    return alternatives


def _extract_after_label(window: list[str], label: str) -> int | None:
    for i, line in enumerate(window):
        if line.strip() == label and i + 1 < len(window):
            try:
                return int(window[i + 1].strip())
            except ValueError:
                return None
    return None


def _extract_money_after_label(window: list[str], label: str) -> float | None:
    for i, line in enumerate(window):
        if label in line:
            # The money may be on the same line or the next line.
            same_line = _PRICE_RE.search(line)
            if same_line:
                return _money(same_line.group(1))
            if i + 1 < len(window):
                m = _PRICE_RE.search(window[i + 1])
                if m:
                    return _money(m.group(1))
    return None


class _TCGPlayerAdapter:
    name = "tcgplayer"
    display_name = "TCGPlayer"
    kind: Literal["marketplace"] = "marketplace"
    base_url = _BASE_URL

    def name_for_search(self, card_name: str) -> str:
        # TCG Mass Entry chokes on the canonical " // " split notation.
        # Front-face only.
        return card_name.split(" // ", 1)[0]

    def bulk_submit_and_optimize(
        self,
        page,
        lines: list[Line],
    ) -> OptimizedCart:
        """Submit the line list and run TCG's cart optimizer.

        Side effect: the user's cart at TCG ends up populated with the
        cheapest optimizer alternative. `open_handoff` will then point
        the headed browser at /cart for checkout.

        Mass Entry appends to the existing cart, so any pre-existing
        items skew the optimizer's totals. Pre-flight a pollution check
        and raise CartNotEmptyError if non-empty (verified live on Mana
        Pool; same shape applies to TCG since both use append-on-submit).
        """
        # Step 0 — pollution pre-flight
        existing = self.get_existing_cart(page)
        if existing:
            raise CartNotEmptyError(
                self.name, len(existing), f"{self.base_url}/cart",
            )

        # Step 1 — Mass Entry
        page.goto(
            f"{self.base_url}/massentry",
            wait_until="networkidle",
            timeout=30000,
        )
        page.wait_for_selector(
            "[contenteditable=true].mass-entry-input",
            timeout=15000,
        )
        page.wait_for_timeout(500)
        bulk_text = "\n".join(
            f"{ln['qty']} {self.name_for_search(ln['card_name'])}" for ln in lines
        )
        page.locator("[contenteditable=true].mass-entry-input").first.fill(bulk_text)
        page.wait_for_timeout(300)
        page.locator(
            "button.mass-entry__body__actions--submit",
        ).first.click()
        page.wait_for_url("**/cart", timeout=30000)
        page.wait_for_timeout(2000)

        # Step 2 — navigate to optimizer
        page.locator('button:has-text("Optimize")').first.click()
        page.wait_for_url("**/cart/optimizer", timeout=30000)
        page.wait_for_timeout(2000)

        # Step 3 — run optimization
        opt_btn = page.locator('button:has-text("Optimize")').last
        opt_btn.click()
        page.wait_for_timeout(8000)  # optimizer typically takes 3-8s

        html = page.content()
        alternatives = _parse_optimizer_alternatives(html)
        if not alternatives:
            raise StoreSelectorError(self.name, "Cart Subtotal", page.url)
        # Pick cheapest
        cheapest = min(alternatives, key=lambda a: a["subtotal"])

        # Step 4 — click "Select this cart" matching the cheapest subtotal
        # Each alternative's button is "Select this cart"; the index of the
        # cheapest alternative tells us which button to click.
        cheapest_idx = alternatives.index(cheapest)
        select_btns = page.locator('button:has-text("Select this cart")')
        if cheapest_idx < select_btns.count():
            select_btns.nth(cheapest_idx).click()
            page.wait_for_timeout(3000)

        return OptimizedCart(
            store=self.name,
            total=cheapest["subtotal"],
            items_subtotal=cheapest.get("item_total") or 0.0,
            shipping=cheapest.get("shipping") or 0.0,
            lines=[],  # Per-line breakdown not extracted in v1.
            unfound=[],  # TCG flags unmatched lines on /massentry; v1 tolerates loss.
            cart_url=f"{self.base_url}/cart",
        )

    # -- Protocol stubs (online adapter; per-card search is unused) --

    def open_handoff(self, profile_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,
            )
            ctx.new_page().goto(f"{self.base_url}/cart")
            ctx.wait_for_event("close", timeout=0)

    def get_existing_cart(self, page) -> list[Listing]:
        if hasattr(page, "goto"):
            page.goto(f"{self.base_url}/cart", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        soup = BeautifulSoup(page.content(), "html.parser")
        # Cart items render via React; the safest signal is "Subtotal:" text
        # absent → empty cart, present → has items. For pollution detection
        # we only need to know empty-vs-not.
        text = soup.get_text(" ", strip=True)
        if "Your Cart is empty" in text or "Cart is empty" in text:
            return []
        # A populated cart shows "Items\n<N>" with N >= 1. Conservatively,
        # if "Subtotal" appears, return one stub to flag non-empty.
        if "Subtotal" in text and "$" in text:
            return [
                Listing(
                    store=self.name,
                    card_name="(unknown)",
                    set_code="",
                    condition="NM",
                    foil=False,
                    price=0.0,
                    qty_available=1,
                    listing_id="",
                    url=f"{self.base_url}/cart",
                )
            ]
        return []

    def clear_cart(self, page) -> None:
        if hasattr(page, "goto"):
            page.goto(f"{self.base_url}/cart", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        # "Remove all items" button on the cart page wipes the cart in one click.
        btn = page.locator('button:has-text("Remove all items")').first
        if btn.count() > 0:
            btn.click()
            page.wait_for_timeout(2000)
            # Confirm dialog if any
            confirm = page.locator('button:has-text("Confirm")').first
            if confirm.count() > 0 and confirm.is_visible():
                confirm.click()
                page.wait_for_timeout(1500)

    def is_logged_in(self, page) -> bool:
        soup = BeautifulSoup(page.content(), "html.parser")
        text = soup.get_text(" ", strip=True)
        # "Sign In" in header without "Sign Out" → logged out.
        return not ("Sign In" in text and "Sign Out" not in text)

    def open_login(self, profile_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,
            )
            ctx.new_page().goto(f"{self.base_url}/login")
            ctx.wait_for_event("close", timeout=0)


ADAPTER = _TCGPlayerAdapter()
