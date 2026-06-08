"""Production wiring: build a ``ForgeState`` backed by real Scryfall bulk data.

If no bulk data is on disk, the state degrades to an agent-less, search-disabled
mode (``bulk_available=False``) so the hub still starts and the search endpoint can
fail loudly with a "run download-bulk" message rather than silently returning empty.
"""

from __future__ import annotations

import functools
import os
import uuid
from pathlib import Path

from mtg_utils import card_search, combo_search, mark_owned
from mtg_utils._deck_forge import collection
from mtg_utils._deck_forge.collection import CollectionStore
from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards
from mtg_utils.card_classify import extract_price
from mtg_utils.card_search import SKIP_LAYOUTS
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.names import build_name_alias_map


def _combos(deck: dict, by_name: dict[str, dict]) -> dict:
    # Build a HydratedDeck so combo_search can validate template requirements
    # (e.g. "a Persist Creature") against the deck — without records, near-miss
    # detection falls back to counting named cards only and over-reports near-misses.
    return combo_search.combo_search(HydratedDeck.from_parsed(deck, by_name))


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


def _deck_forge_dir() -> Path:
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    root = Path(base) if base else Path.home() / ".cache" / "mtg-skills"
    return root / "deck-forge"


def _builds_dir() -> Path:
    return _deck_forge_dir() / "builds"


def resume_or_new(store: BuildStore, fmt: str) -> tuple[DeckSession, str, str]:
    """Resume the most recent saved build, or start a fresh one. Returns
    (session, build_id, build_name). Auto-resume means relaunching continues your
    deck instead of minting a new 'Untitled' every time."""
    builds = store.list()  # newest first
    if builds:
        record = store.load(builds[0]["id"])
        if record is not None:
            return (
                DeckSession.from_deck_dict(record.get("deck") or {}),
                record.get("id", builds[0]["id"]),
                record.get("name", "Untitled"),
            )
    return DeckSession(fmt), uuid.uuid4().hex[:8], "Untitled"


def _no_search(**_: object) -> list[dict]:
    return []


def _load_collections(
    store: CollectionStore,
    name_aliases: dict[str, str] | None = None,
) -> tuple[dict[str, dict], dict[str, tuple]]:
    """Load both Collection slots and precompute each slot's ownership lookup once, so a
    per-snapshot ownership check stays O(deck size) (ADR-0018). ``name_aliases`` (built
    from bulk) threads Arena printed_name / flavor_name matching into the lookup."""
    # Drop quantity-0 (un-owned / wishlist) rows up front so size, ownership, and
    # discovery all see owned-only — even for collections saved before this rule.
    collections = {
        slot: collection.owned_only(pile) for slot, pile in store.load().items()
    }
    index = {
        slot: mark_owned.owned_lookup(pile, name_aliases=name_aliases or None)
        for slot, pile in collections.items()
    }
    return collections, index


def default_state(fmt: str = "commander") -> ForgeState:
    """Build the live backend state, loading bulk data when available."""
    store = BuildStore(_builds_dir())
    session, build_id, build_name = resume_or_new(store, fmt)
    collection_store = CollectionStore(_deck_forge_dir() / "collection.json")
    bulk_path = default_bulk_path()
    by_name: dict[str, dict] = {}
    search = _no_search
    available = False
    # Built from bulk so the Collection's ownership matching honors Arena printed_name /
    # flavor_name aliases (ADR-0018). Empty without bulk → DFC-only matching (fine).
    name_aliases: dict[str, str] = {}
    if bulk_path is not None and bulk_path.exists():
        by_name = build_by_name(load_bulk_cards(bulk_path))

        # partial keeps search_cards's typed keyword signature (a `**kwargs:
        # object` wrapper would widen every arg to `object` and fail the checker).
        search = functools.partial(card_search.search_cards, bulk_path)

        name_aliases = build_name_alias_map(bulk_path)
        available = True

    collections, collection_index = _load_collections(collection_store, name_aliases)

    return ForgeState(
        by_name=by_name,
        search_fn=search,
        session=session,
        bulk_available=available,
        combos_fn=lambda deck: _combos(deck, by_name),
        store=store,
        build_id=build_id,
        build_name=build_name,
        collection_store=collection_store,
        collections=collections,
        collection_index=collection_index,
        name_aliases=name_aliases,
        bulk_path=bulk_path if available else None,
    )
