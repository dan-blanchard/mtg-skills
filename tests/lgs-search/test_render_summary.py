"""Tests for `_render_summary` — the markdown output the orchestrator prints."""

from __future__ import annotations

from unittest.mock import MagicMock

from mtg_utils.lgs_search import _render_summary


def _stub_adapter(name: str, display_name: str):
    a = MagicMock()
    a.name = name
    a.display_name = display_name
    return a


def test_render_summary_with_two_online_stores(monkeypatch):
    """Standard case — both TCG and MP available; cheapest wins, comparison shown."""
    monkeypatch.setattr(
        "mtg_utils.lgs_search.STORE_REGISTRY",
        {
            "tgp": _stub_adapter("tgp", "The Gathering Place"),
            "tcgplayer": _stub_adapter("tcgplayer", "TCGPlayer"),
            "manapool": _stub_adapter("manapool", "Mana Pool"),
        },
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.ONLINE_STORES",
        ["tcgplayer", "manapool"],
    )
    online = {
        "tcgplayer": {"total": 54.75, "items_subtotal": 50.0, "shipping": 4.75},
        "manapool": {"total": 48.10, "items_subtotal": 45.0, "shipping": 3.10},
        "chosen": "manapool",
    }
    out = _render_summary([], online, {})
    assert "Mana Pool" in out
    assert "chosen over TCGPlayer" in out
    assert "$48.10" in out
    assert "$54.75" in out


def test_render_summary_handles_single_online_store(monkeypatch):
    """Latent footgun guard — if ONLINE_STORES is ever pruned to one entry
    (or the loser key is missing from `online`), summary should not crash.
    """
    monkeypatch.setattr(
        "mtg_utils.lgs_search.STORE_REGISTRY",
        {"manapool": _stub_adapter("manapool", "Mana Pool")},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.ONLINE_STORES",
        ["manapool"],
    )
    online = {
        "manapool": {"total": 48.10, "items_subtotal": 45.0, "shipping": 3.10},
        "chosen": "manapool",
    }
    out = _render_summary([], online, {})
    assert "Mana Pool" in out
    assert "only online option" in out
    assert "$48.10" in out


def test_render_summary_no_online_section_when_no_online(monkeypatch):
    """When no online cards were allocated, the online section is omitted."""
    monkeypatch.setattr(
        "mtg_utils.lgs_search.STORE_REGISTRY",
        {"tgp": _stub_adapter("tgp", "The Gathering Place")},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.ONLINE_STORES",
        ["tcgplayer", "manapool"],
    )
    out = _render_summary([], None, {})
    assert "TCGPlayer" not in out
    assert "Mana Pool" not in out
