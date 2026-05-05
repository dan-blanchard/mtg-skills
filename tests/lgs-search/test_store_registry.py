"""Tests for STORE_REGISTRY contents."""

from __future__ import annotations

from mtg_utils._stores import LGS_STORES, ONLINE_STORES, STORE_REGISTRY


def test_registry_has_expected_stores():
    assert set(STORE_REGISTRY) == {"tgp", "atomic_empire", "tcgplayer", "manapool"}


def test_lgs_split():
    assert set(LGS_STORES) == {"tgp", "atomic_empire"}
    assert set(ONLINE_STORES) == {"tcgplayer", "manapool"}


def test_each_adapter_has_required_attrs():
    for adapter in STORE_REGISTRY.values():
        assert adapter.name in STORE_REGISTRY
        assert adapter.kind in {"lgs", "online"}
        assert adapter.display_name
        assert adapter.base_url.startswith("http")
