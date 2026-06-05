"""Production wiring: build a ``ForgeState`` backed by real Scryfall bulk data.

If no bulk data is on disk, the state degrades to an agent-less, search-disabled
mode (``bulk_available=False``) so the hub still starts and the search endpoint can
fail loudly with a "run download-bulk" message rather than silently returning empty.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from mtg_utils import card_search, combo_search
from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards
from mtg_utils.card_classify import extract_price
from mtg_utils.card_search import SKIP_LAYOUTS


def _combos(deck: dict) -> dict:
    return combo_search.combo_search(deck)


def build_by_name(cards: list[dict]) -> dict[str, dict]:
    """Index real cards by their EXACT (proper-case) name, deduped to the cheapest
    printing — mirroring what ``card_search`` returns, so a card that appears in
    search results is always addable and hydrates with matching art/price.

    (``deck.load_bulk_indexes`` keys by *lowercased* name, which does not match the
    proper-case names search emits and users type — hence this dedicated index.)
    """
    best: dict[str, dict] = {}
    for card in cards:
        name = card.get("name")
        if not name or card.get("layout") in SKIP_LAYOUTS:
            continue
        if card.get("set_type") in ("token", "memorabilia"):
            continue
        if name not in best:
            best[name] = card
            continue
        cur, new = extract_price(best[name]), extract_price(card)
        if new is not None and (cur is None or new < cur):
            best[name] = card
    return best


def _builds_dir() -> Path:
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    root = Path(base) if base else Path.home() / ".cache" / "mtg-skills"
    return root / "deck-forge" / "builds"


def default_state(fmt: str = "commander") -> ForgeState:
    """Build the live backend state, loading bulk data when available."""
    store = BuildStore(_builds_dir())
    build_id = uuid.uuid4().hex[:8]
    bulk_path = default_bulk_path()
    if bulk_path is not None and bulk_path.exists():
        by_name = build_by_name(load_bulk_cards(bulk_path))

        def search_fn(**kwargs: object) -> list[dict]:
            return card_search.search_cards(bulk_path, **kwargs)

        return ForgeState(
            by_name=by_name,
            search_fn=search_fn,
            session=DeckSession(fmt),
            bulk_available=True,
            combos_fn=_combos,
            store=store,
            build_id=build_id,
        )

    return ForgeState(
        by_name={},
        search_fn=lambda **_: [],
        session=DeckSession(fmt),
        bulk_available=False,
        combos_fn=_combos,
        store=store,
        build_id=build_id,
    )
