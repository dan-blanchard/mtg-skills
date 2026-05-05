"""Per-store adapters for lgs-search."""

from __future__ import annotations

from mtg_utils._stores import atomic_empire, manapool, tcgplayer, tgp

STORE_REGISTRY = {
    tgp.ADAPTER.name: tgp.ADAPTER,
    atomic_empire.ADAPTER.name: atomic_empire.ADAPTER,
    tcgplayer.ADAPTER.name: tcgplayer.ADAPTER,
    manapool.ADAPTER.name: manapool.ADAPTER,
}

LGS_STORES = [name for name, a in STORE_REGISTRY.items() if a.kind == "lgs"]
ONLINE_STORES = [name for name, a in STORE_REGISTRY.items() if a.kind == "online"]
