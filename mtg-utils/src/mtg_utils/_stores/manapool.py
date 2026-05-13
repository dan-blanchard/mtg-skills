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
    CartNotEmptyError,
    Line,
    Listing,
    OptimizedCart,
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
    "Fewest packages", or "Balanced" — followed by a block of labels
    (Total / Packages / Subtotal / Shipping / Singles fee) and then
    the values. Live MP shows each numeric metric as a new+old pair
    (optimized then baseline); some test fixtures emit a simplified
    one-value-per-metric form. We detect which by counting dollar
    values within the bounded per-alternative window.

      Live MP (≥6 dollar values per alternative):
        [Total_new, Total_old, Subtotal_new, Subtotal_old,
         Shipping_new, Shipping_old, SinglesFee_new, SinglesFee_old]
        → take new values at even indices [0, 2, 4].

      Simplified (3 dollar values):
        [Total, Subtotal, Shipping]
        → take consecutive indices [0, 1, 2].

    The previous parser used a 32-line lookahead window that bled into
    the next alternative's values; we now bound at the next heading so
    each alternative's prices are isolated.

    Returns one dict per alternative with keys: name, total, subtotal,
    shipping. Alternatives that haven't populated the full set yet are
    skipped.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = text.split("\n")
    alternatives = []
    headings = ("Lowest price", "Fewest packages", "Balanced")
    for i, line in enumerate(lines):
        if line.strip() not in headings:
            continue
        # Bound the window at the next heading so cross-alternative
        # prices don't leak in.
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if lines[j].strip() in headings:
                end = j
                break
        block_text = "\n".join(lines[i + 1 : end])
        prices = _PRICE_RE.findall(block_text)
        if len(prices) >= 6:
            # Live new+old-pair layout.
            total = _money(prices[0])
            subtotal = _money(prices[2])
            shipping = _money(prices[4])
        elif len(prices) >= 3:
            # Simplified layout (test fixtures, possibly older live theme).
            total = _money(prices[0])
            subtotal = _money(prices[1])
            shipping = _money(prices[2])
        else:
            # Optimizer still searching; this alternative isn't ready.
            continue
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
    kind: Literal["marketplace"] = "marketplace"
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

        The MP /add-deck submit *appends* to the existing cart rather
        than replacing it, and the resulting optimizer page totals
        reflect the entire cart (pre-existing items + new submission).
        That makes any pre-existing cart contents poison the optimizer
        comparison — verified live: 5 leftover Sol Rings turned a
        1-card optimization from $2.43 into $39.91. Pre-flight a
        pollution check and raise if non-empty so the orchestrator
        can route the user to clear before optimizing.
        """
        # Step 0 — pollution pre-flight
        existing = self.get_existing_cart(page)
        if existing:
            raise CartNotEmptyError(
                self.name,
                len(existing),
                f"{self.base_url}/cart",
            )

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
        # KNOWN LIMITATION: MP's "Clear cart" button is broken in MP itself
        # under our Playwright session — clicking it fires two Sentry error
        # reports (ingest.sentry.io) and a no-op `synchronize_cart_metadata`
        # RPC with `{"changes":[]}`, but the cart contents never change.
        # The button isn't blocked by automation detection per se — it's
        # the SvelteKit handler throwing an exception that gets swallowed.
        # Direct API clear via `synchronize_cart_items` would require
        # reverse-engineering the Supabase RPC payload format and inferring
        # current cart inventory IDs; not done.
        #
        # Live workaround: the orchestrator's pollution check still fires
        # on a non-empty MP cart, prompts the user to empty it in the open
        # headed window, and waits for Enter — annoying but not blocking.
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
