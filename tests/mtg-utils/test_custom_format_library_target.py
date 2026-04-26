"""Tests for the library-effect zone-target heuristic."""

from __future__ import annotations

from mtg_utils._custom_format._common import (
    CardMetadata,
    LibraryEffect,
    Zone,
    choose_library_target,
)


def _meta(name, *, cmc=2, is_land=False, library_effect=LibraryEffect.NONE):
    return CardMetadata(
        name=name,
        cmc=cmc,
        color_identity=frozenset(),
        produced_mana=(),
        is_land=is_land,
        library_effect=library_effect,
        archetype_matches=frozenset(),
    )


class TestChooseLibraryTarget:
    def test_peek_targets_draw_pile(self):
        # Marketplace is face-up — peeking is wasted there.
        market = [_meta("Big", cmc=5)]
        z = choose_library_target(LibraryEffect.PEEK, marketplace=market)
        assert z == Zone.DRAW_PILE

    def test_reorder_targets_draw_pile(self):
        market = [_meta("Big", cmc=5)]
        z = choose_library_target(LibraryEffect.REORDER, marketplace=market)
        assert z == Zone.DRAW_PILE

    def test_mill_targets_draw_pile(self):
        market = [_meta("Big", cmc=5)]
        z = choose_library_target(LibraryEffect.MILL, marketplace=market)
        assert z == Zone.DRAW_PILE

    def test_discard_targets_marketplace_with_high_value(self):
        # Marketplace has a 5-CMC playable — denial worth it.
        market = [_meta("Smol", cmc=1), _meta("Big", cmc=5)]
        z = choose_library_target(LibraryEffect.DISCARD, marketplace=market)
        assert z == Zone.MARKETPLACE

    def test_discard_targets_draw_pile_when_marketplace_low_value(self):
        # All low-CMC chaff in marketplace — cycle the draw pile instead.
        market = [_meta("Smol1", cmc=1), _meta("Smol2", cmc=1)]
        z = choose_library_target(LibraryEffect.DISCARD, marketplace=market)
        assert z == Zone.DRAW_PILE

    def test_exile_uses_same_threshold_as_discard(self):
        market = [_meta("Big", cmc=5)]
        z_exile = choose_library_target(LibraryEffect.EXILE, marketplace=market)
        z_discard = choose_library_target(LibraryEffect.DISCARD, marketplace=market)
        assert z_exile == z_discard == Zone.MARKETPLACE

    def test_search_returns_draw_pile_default(self):
        # Format-disallowed but harness still needs a deterministic answer.
        market = [_meta("Big", cmc=5)]
        z = choose_library_target(LibraryEffect.SEARCH, marketplace=market)
        assert z == Zone.DRAW_PILE
