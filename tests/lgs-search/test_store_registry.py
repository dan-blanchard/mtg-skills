"""Tests for the LGS_ADAPTERS / MARKETPLACE_ADAPTERS registries."""

from __future__ import annotations

from mtg_utils._stores import (
    LGS_ADAPTERS,
    LGS_STORES,
    MARKETPLACE_ADAPTERS,
    MARKETPLACE_STORES,
    iter_storefronts,
    lookup,
)


def test_registries_have_expected_storefronts():
    assert set(LGS_ADAPTERS) == {"tgp", "atomic_empire"}
    assert set(MARKETPLACE_ADAPTERS) == {"tcgplayer", "manapool"}


def test_storefront_lists_match_registries():
    assert set(LGS_STORES) == set(LGS_ADAPTERS)
    assert set(MARKETPLACE_STORES) == set(MARKETPLACE_ADAPTERS)


def test_lgs_adapters_declare_lgs_kind():
    for adapter in LGS_ADAPTERS.values():
        assert adapter.kind == "lgs"
        assert adapter.display_name
        assert adapter.base_url.startswith("http")


def test_marketplace_adapters_declare_marketplace_kind():
    for adapter in MARKETPLACE_ADAPTERS.values():
        assert adapter.kind == "marketplace"
        assert adapter.display_name
        assert adapter.base_url.startswith("http")


def test_iter_storefronts_yields_every_adapter():
    seen = dict(iter_storefronts())
    assert set(seen) == {"tgp", "atomic_empire", "tcgplayer", "manapool"}


def test_lookup_resolves_either_kind():
    assert lookup("tgp") is LGS_ADAPTERS["tgp"]
    assert lookup("tcgplayer") is MARKETPLACE_ADAPTERS["tcgplayer"]


def test_lookup_raises_on_unknown_storefront():
    import pytest

    with pytest.raises(KeyError):
        lookup("not-a-storefront")
