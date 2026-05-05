"""Per-Storefront adapters for lgs-search.

Two typed registries — `LGS_ADAPTERS` and `MARKETPLACE_ADAPTERS` —
plus an iterator (`iter_storefronts`) that yields every adapter as
its narrowest type for cross-kind lifecycle work (cart-pollution
sweep, login pre-flight, Phase 7 handoff, grand-total reporting).
See lgs-search/CONTEXT.md for the LGS / Marketplace / StoreSession
domain language.
"""

from __future__ import annotations

from collections.abc import Iterator

from mtg_utils._stores import atomic_empire, manapool, tcgplayer, tgp
from mtg_utils._stores._common import LGSAdapter, MarketplaceAdapter, StoreSession

LGS_ADAPTERS: dict[str, LGSAdapter] = {
    tgp.ADAPTER.name: tgp.ADAPTER,
    atomic_empire.ADAPTER.name: atomic_empire.ADAPTER,
}

MARKETPLACE_ADAPTERS: dict[str, MarketplaceAdapter] = {
    tcgplayer.ADAPTER.name: tcgplayer.ADAPTER,
    manapool.ADAPTER.name: manapool.ADAPTER,
}

LGS_STORES: list[str] = list(LGS_ADAPTERS)
MARKETPLACE_STORES: list[str] = list(MARKETPLACE_ADAPTERS)


def iter_storefronts() -> Iterator[tuple[str, StoreSession]]:
    """Yield (name, adapter) for every Storefront, narrowed to the
    StoreSession surface. Use for cross-kind lifecycle work where the
    caller only needs auth / cart / handoff methods.
    """
    yield from LGS_ADAPTERS.items()
    yield from MARKETPLACE_ADAPTERS.items()


def lookup(name: str) -> StoreSession:
    """Resolve a Storefront name from either registry. Raises
    KeyError if `name` is not a known Storefront.
    """
    if name in LGS_ADAPTERS:
        return LGS_ADAPTERS[name]
    if name in MARKETPLACE_ADAPTERS:
        return MARKETPLACE_ADAPTERS[name]
    msg = f"unknown Storefront: {name!r}"
    raise KeyError(msg)
