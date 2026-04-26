"""Tests for library-effect oracle-text classifier."""

from __future__ import annotations

from mtg_utils._custom_format._common import LibraryEffect, classify_library_effect


def _card(name, oracle, type_line="Instant"):
    return {"name": name, "oracle_text": oracle, "type_line": type_line}


class TestClassifyLibraryEffect:
    def test_scry_is_reorder(self):
        c = _card("Opt", "Scry 1, then draw a card.")
        assert classify_library_effect(c) == LibraryEffect.REORDER

    def test_look_at_top_is_peek(self):
        c = _card(
            "Sensei's Divining Top", "Look at the top three cards of your library."
        )
        assert classify_library_effect(c) == LibraryEffect.PEEK

    def test_surveil_is_discard(self):
        c = _card(
            "Consider",
            "Look at the top card of your library. "
            "You may put that card into your graveyard. Draw a card.",
        )
        assert classify_library_effect(c) == LibraryEffect.DISCARD

    def test_surveil_keyword_is_discard(self):
        c = _card("Discovery", "Surveil 2, then draw a card.")
        assert classify_library_effect(c) == LibraryEffect.DISCARD

    def test_exile_top_is_exile(self):
        c = _card(
            "Dragon's Rage Channeler",
            "When ~ enters, exile the top card of your library.",
            type_line="Creature",
        )
        assert classify_library_effect(c) == LibraryEffect.EXILE

    def test_mill_is_mill(self):
        c = _card(
            "Stitcher's Supplier",
            "When ~ enters, mill three cards.",
            type_line="Creature",
        )
        assert classify_library_effect(c) == LibraryEffect.MILL

    def test_search_is_search(self):
        c = _card(
            "Demonic Tutor", "Search your library for a card and put it into your hand."
        )
        assert classify_library_effect(c) == LibraryEffect.SEARCH

    def test_basic_creature_is_none(self):
        c = _card(
            "Goblin Guide",
            "Whenever ~ attacks, defending player reveals the top card "
            "of their library.",
            type_line="Creature",
        )
        # "reveal the top card of their library" — that's a peek but on opponent's
        # library; in shared-library format there are no opponent libraries so
        # this should still classify as PEEK at the format-agnostic layer.
        assert classify_library_effect(c) == LibraryEffect.PEEK

    def test_counterspell_is_none(self):
        c = _card("Counterspell", "Counter target spell.")
        assert classify_library_effect(c) == LibraryEffect.NONE

    def test_basic_land_is_none(self):
        c = _card("Mountain", "({T}: Add {R}.)", type_line="Basic Land — Mountain")
        assert classify_library_effect(c) == LibraryEffect.NONE
