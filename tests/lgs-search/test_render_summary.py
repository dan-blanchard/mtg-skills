"""Tests for `_render_summary` — the markdown output the orchestrator prints."""

from __future__ import annotations

from unittest.mock import MagicMock

from mtg_utils.lgs_search import _render_summary


def _stub_adapter(name: str, display_name: str):
    a = MagicMock()
    a.name = name
    a.display_name = display_name
    return a


def test_render_summary_with_two_marketplaces(monkeypatch):
    """Standard case — both TCG and MP available; cheapest wins, comparison shown."""
    monkeypatch.setattr(
        "mtg_utils.lgs_search.LGS_ADAPTERS",
        {"tgp": _stub_adapter("tgp", "The Gathering Place")},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.MARKETPLACE_ADAPTERS",
        {
            "tcgplayer": _stub_adapter("tcgplayer", "TCGPlayer"),
            "manapool": _stub_adapter("manapool", "Mana Pool"),
        },
    )
    marketplace = {
        "tcgplayer": {"total": 54.75, "items_subtotal": 50.0, "shipping": 4.75},
        "manapool": {"total": 48.10, "items_subtotal": 45.0, "shipping": 3.10},
        "chosen": "manapool",
    }
    out = _render_summary([], marketplace, {})
    assert "Mana Pool" in out
    assert "chosen over TCGPlayer" in out
    assert "$48.10" in out
    assert "$54.75" in out


def test_render_summary_handles_single_marketplace(monkeypatch):
    """Latent footgun guard — if MARKETPLACE_ADAPTERS is ever pruned to one
    entry (or the loser key is missing from `marketplace`), summary should
    not crash.
    """
    monkeypatch.setattr(
        "mtg_utils.lgs_search.LGS_ADAPTERS", {},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.MARKETPLACE_ADAPTERS",
        {"manapool": _stub_adapter("manapool", "Mana Pool")},
    )
    marketplace = {
        "manapool": {"total": 48.10, "items_subtotal": 45.0, "shipping": 3.10},
        "chosen": "manapool",
    }
    out = _render_summary([], marketplace, {})
    assert "Mana Pool" in out
    assert "only Marketplace option" in out
    assert "$48.10" in out


def test_render_summary_no_marketplace_section_when_none(monkeypatch):
    """When no Marketplace cards were allocated, the Marketplace section is omitted."""
    monkeypatch.setattr(
        "mtg_utils.lgs_search.LGS_ADAPTERS",
        {"tgp": _stub_adapter("tgp", "The Gathering Place")},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.MARKETPLACE_ADAPTERS",
        {
            "tcgplayer": _stub_adapter("tcgplayer", "TCGPlayer"),
            "manapool": _stub_adapter("manapool", "Mana Pool"),
        },
    )
    out = _render_summary([], None, {})
    assert "TCGPlayer" not in out
    assert "Mana Pool" not in out
