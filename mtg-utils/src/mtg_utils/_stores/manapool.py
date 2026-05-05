"""Mana Pool adapter (manapool.com).

Live-discovered flow (2026-05):
1. POST list → `https://manapool.com/add-deck`
   - Fill the single `<textarea>` with `qty CardName` lines
     (format: `quantity name [set] number`; bracketed set is optional).
   - Click `button:has-text("Optimize Price")` → /optimizer.
2. On `/optimizer`:
   - Click `button:has-text("Optimize N items")` to start the optimization.
   - The page renders three alternative carts: "Lowest price",
     "Fewest packages", "Balanced". Each populates a Total ($X.XX),
     Packages (N), Subtotal ($X.XX), Shipping ($X.XX), Singles fee.
3. Pick the cheapest by Total, click its `Accept` button to commit.

The optimizer is asynchronous; the "Still searching" placeholder text
remains even after numeric values populate. The adapter polls for
actual `$N.NN` Total values (not the `-` placeholder) before reading.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from bs4 import BeautifulSoup

from mtg_utils._stores._common import (
    AddToCartResult,
    Line,
    Listing,
    OptimizedCart,
    SearchPrefs,
    StoreSelectorError,
)

_BASE_URL = "https://manapool.com"

_PRICE_RE = re.compile(r"\$([\d,]+\.\d{2})")
_OPTIMIZE_BTN_RE = re.compile(r"Optimize \d+ items?")


def _money(text: str) -> float:
    return float(text.replace(",", "").replace("$", ""))


def _parse_optimizer_alternatives(html: str) -> list[dict]:
    """Parse the three optimizer alternatives.

    Each alternative is anchored by a heading line — "Lowest price",
    "Fewest packages", or "Balanced" — followed by an Accept block with
    the numeric values. Returns one dict per alternative with keys: name,
    total, packages, subtotal, shipping, singles_fee.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = text.split("\n")
    alternatives = []
    headings = ("Lowest price", "Fewest packages", "Balanced")
    for i, line in enumerate(lines):
        if line.strip() not in headings:
            continue
        # Look ahead up to 30 lines for the price values. The page renders
        # values as $X.XX once populated, or "-" while still searching.
        window = lines[i : min(len(lines), i + 32)]
        block_text = "\n".join(window)
        # The first $X.XX after the heading is the Total.
        price_matches = _PRICE_RE.findall(block_text)
        if not price_matches:
            # Still computing; this alternative isn't ready.
            continue
        # Total is the first $X.XX. Some text concatenations show "$X$Y"
        # (new vs old); the first match wins (= new optimized total).
        total = _money(price_matches[0])
        # Subtotal and shipping are the 2nd and 3rd money values.
        subtotal = _money(price_matches[1]) if len(price_matches) > 1 else 0.0
        shipping = _money(price_matches[2]) if len(price_matches) > 2 else 0.0
        alternatives.append(
            {
                "name": line.strip(),
                "total": total,
                "subtotal": subtotal,
                "shipping": shipping,
            }
        )
    return alternatives


class _ManaPoolAdapter:
    name = "manapool"
    display_name = "Mana Pool"
    kind: Literal["lgs", "online"] = "online"
    base_url = _BASE_URL

    def name_for_search(self, card_name: str) -> str:
        # Mana Pool's bulk parser accepts the canonical name with " // ".
        return card_name

    def bulk_submit_and_optimize(
        self,
        page,
        lines: list[Line],
    ) -> OptimizedCart:
        """Submit the line list and run Mana Pool's optimizer.

        Returns an OptimizedCart with the cheapest alternative's totals
        and selects it on the live page so the user's checkout cart
        reflects the optimized basket.
        """
        # Step 1 — Mass entry. networkidle doesn't reliably settle on MP
        # (live-pricing JS keeps pinging in the background), so wait until
        # DOM is ready and then synchronize on the textarea selector.
        page.goto(
            f"{self.base_url}/add-deck",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        page.wait_for_selector("textarea", timeout=15000)
        page.wait_for_timeout(500)
        bulk_text = "\n".join(
            f"{ln['qty']} {self.name_for_search(ln['card_name'])}" for ln in lines
        )
        page.locator("textarea").first.fill(bulk_text)
        page.wait_for_timeout(300)
        page.locator('button:has-text("Optimize Price")').first.click()
        page.wait_for_url("**/optimizer", timeout=30000)
        page.wait_for_timeout(2000)

        # Step 2 — Click "Optimize N items"
        go_btn = page.locator("button").filter(has_text=_OPTIMIZE_BTN_RE).first
        if go_btn.count() == 0:
            raise StoreSelectorError(self.name, "Optimize N items button", page.url)
        go_btn.click()

        # Step 3 — Poll for alternatives to populate.
        # Each alternative starts with a "-" placeholder for prices;
        # we wait for at least one alternative to show $X.XX.
        alternatives: list[dict] = []
        for _ in range(20):  # up to ~40s
            page.wait_for_timeout(2000)
            html = page.content()
            alternatives = _parse_optimizer_alternatives(html)
            if alternatives:
                break

        if not alternatives:
            raise StoreSelectorError(self.name, "optimizer alternatives", page.url)

        cheapest = min(alternatives, key=lambda a: a["total"])

        # Step 4 — Click the Accept button under the cheapest alternative.
        # Each Accept follows its alternative's heading; selecting by index
        # under the heading position is safest.
        cheapest_idx = alternatives.index(cheapest)
        accept_btns = page.locator('button:has-text("Accept")')
        if cheapest_idx < accept_btns.count():
            accept_btns.nth(cheapest_idx).click()
            page.wait_for_timeout(3000)

        return OptimizedCart(
            store=self.name,
            total=cheapest["total"],
            items_subtotal=cheapest["subtotal"],
            shipping=cheapest["shipping"],
            lines=[],  # Per-line breakdown not extracted in v1.
            unfound=[],  # MP flags unmatched lines on /add-deck; v1 tolerates loss.
            cart_url=f"{self.base_url}/cart",
        )

    # -- Protocol stubs (online adapter; per-card search is unused) --

    def search(
        self,
        page,
        card_name: str,
        *,
        qty: int,
        prefs: SearchPrefs,
    ) -> list[Listing]:
        msg = "Mana Pool is an online adapter; use bulk_submit_and_optimize"
        raise NotImplementedError(msg)

    def add_to_cart(
        self,
        page,
        listing: Listing,
        qty: int,
    ) -> AddToCartResult:
        msg = "Mana Pool is an online adapter; cart populated by bulk flow"
        raise NotImplementedError(msg)

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
        text = soup.get_text(" ", strip=True)
        if "Your cart is empty" in text or "cart is empty" in text.lower():
            return []
        # Conservative non-empty stub for pollution detection.
        if "$" in text and "Subtotal" in text:
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
        # KNOWN LIMITATION: MP's "Clear cart" button has a Svelte click
        # handler that silently no-ops under Playwright (verified via
        # synthetic MouseEvents AND real Locator.click — the cart never
        # changes). The orchestrator's pollution check still fires, prompts
        # the user to clear manually in the open headed window, and waits
        # for Enter — so a polluted MP cart is annoying but not blocking.
        # If you re-investigate: per-item remove buttons are also not
        # discoverable in the cart's React component tree from outside.
        if hasattr(page, "goto"):
            page.goto(f"{self.base_url}/cart", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        clear = page.locator(
            'button:has-text("Clear cart"), button:has-text("Empty cart")',
        ).first
        if clear.count() > 0:
            try:
                clear.click()
            except Exception:  # noqa: BLE001
                return
            page.wait_for_timeout(1500)
            confirm = page.locator('button:has-text("Confirm")').first
            if confirm.count() > 0 and confirm.is_visible():
                confirm.click()
                page.wait_for_timeout(1500)

    def is_logged_in(self, page) -> bool:
        soup = BeautifulSoup(page.content(), "html.parser")
        text = soup.get_text(" ", strip=True)
        return not ("Sign In" in text and "Sign Out" not in text)

    def open_login(self, profile_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,
            )
            ctx.new_page().goto(f"{self.base_url}/sign-in")
            ctx.wait_for_event("close", timeout=0)


ADAPTER = _ManaPoolAdapter()
