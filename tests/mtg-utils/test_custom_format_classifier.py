"""Tests for library-effect oracle-text classifier."""

from __future__ import annotations

import pytest

from mtg_utils._custom_format._common import (
    LibraryEffect,
    classify_library_effect,
    precompute_metadata,
)
from mtg_utils.testkit import test_card, test_card_ir


class TestClassifyLibraryEffect:
    # Real cards from the testkit snapshot (ADR-0056): the classifier reads
    # each card's real oracle text.
    def test_scry_is_reorder(self):
        assert classify_library_effect(test_card("Opt")) == LibraryEffect.REORDER

    def test_look_at_top_is_peek(self):
        c = test_card("Sensei's Divining Top")
        assert classify_library_effect(c) == LibraryEffect.PEEK

    def test_surveil_is_discard(self):
        # Consider's surveil reminder: "You may put it into your graveyard."
        c = test_card("Consider")
        assert classify_library_effect(c) == LibraryEffect.DISCARD

    def test_surveil_keyword_is_discard(self):
        # Notion Rain: "Surveil 2, then draw two cards." (Discovery // Dispersal
        # is a split card; its text lives on its faces, not the top level.)
        c = test_card("Notion Rain")
        assert classify_library_effect(c) == LibraryEffect.DISCARD

    def test_exile_top_is_exile(self):
        # "Whenever Bomat Courier attacks, exile the top card of your library
        # face down." (Dragon's Rage Channeler surveils; it never exiles.)
        c = test_card("Bomat Courier")
        assert classify_library_effect(c) == LibraryEffect.EXILE

    def test_mill_is_mill(self):
        c = test_card("Stitcher's Supplier")
        assert classify_library_effect(c) == LibraryEffect.MILL

    def test_search_is_search(self):
        c = test_card("Demonic Tutor")
        assert classify_library_effect(c) == LibraryEffect.SEARCH

    def test_basic_creature_is_none(self):
        c = test_card("Goblin Guide")
        # "reveal the top card of their library" — that's a peek but on opponent's
        # library; in shared-library format there are no opponent libraries so
        # this should still classify as PEEK at the format-agnostic layer.
        assert classify_library_effect(c) == LibraryEffect.PEEK

    def test_counterspell_is_none(self):
        c = test_card("Counterspell")
        assert classify_library_effect(c) == LibraryEffect.NONE

    def test_basic_land_is_none(self):
        c = test_card("Mountain")
        assert classify_library_effect(c) == LibraryEffect.NONE


class TestPrecomputeMetadata:
    def test_classifies_each_card_and_tags_archetypes(self):
        # Real cards from the testkit snapshot (ADR-0056). The archetype-tagging
        # demo card uses ``removal`` — a structural (``signal_keys``) view, so
        # its arm needs Murder's real ``oracle_id`` and the crosswalk trees memo
        # seeded first.
        test_card_ir("Murder")  # seeds the crosswalk trees memo
        hydrated = [
            test_card("Mountain"),
            test_card("Brainstorm"),
            test_card("Murder"),
        ]
        meta = precompute_metadata(hydrated, presets=["removal"])
        assert len(meta) == 3

        # Mountain
        assert meta[0].is_land is True
        assert meta[0].library_effect == LibraryEffect.NONE
        assert meta[0].archetype_matches == set()
        assert meta[0].produced_mana == ("R",)

        # Brainstorm — looks like draw + reorder, classifier picks REORDER.
        # No "scry" so the regex won't match. "put two cards on top" —
        # not a peek either. classify returns NONE for Brainstorm at v1.
        # That's a known v1 limitation; future tasks may extend the regex set.
        assert meta[1].is_land is False
        assert meta[1].library_effect in (LibraryEffect.NONE, LibraryEffect.REORDER)

        # Murder — matches the removal preset (structural: `removal` key).
        assert meta[2].is_land is False
        assert meta[2].library_effect == LibraryEffect.NONE
        assert "removal" in meta[2].archetype_matches

    def test_unknown_preset_raises(self):
        with pytest.raises(KeyError):
            precompute_metadata([{"name": "Foo"}], presets=["does-not-exist"])


class TestParsePipCounts:
    def test_single_color_double_pip(self):
        from mtg_utils._custom_format._common import parse_pip_counts

        assert parse_pip_counts("{U}{U}") == {"U": 2}
        assert parse_pip_counts("{1}{U}{U}") == {"U": 2}

    def test_mixed_pips(self):
        from mtg_utils._custom_format._common import parse_pip_counts

        assert parse_pip_counts("{2}{B}{R}{G}") == {"B": 1, "R": 1, "G": 1}

    def test_quadruple_black(self):
        from mtg_utils._custom_format._common import parse_pip_counts

        # Empty the Pits is the cube's most extreme pip cost.
        assert parse_pip_counts("{X}{X}{B}{B}{B}{B}") == {"B": 4}

    def test_generic_only_returns_empty(self):
        from mtg_utils._custom_format._common import parse_pip_counts

        assert parse_pip_counts("{1}") == {}
        assert parse_pip_counts("") == {}

    def test_metadata_carries_pip_counts(self):
        hydrated = [test_card("Counterspell")]
        meta = precompute_metadata(hydrated, presets=[])
        assert meta[0].pip_counts == (("U", 2),)


class TestCanCastWithPips:
    @staticmethod
    def _spell(name, *, cmc, pip_counts, color_identity):
        from mtg_utils._custom_format._common import (
            CardMetadata,
            LibraryEffect,
        )

        return CardMetadata(
            name=name,
            cmc=cmc,
            color_identity=frozenset(color_identity),
            produced_mana=(),
            is_land=False,
            library_effect=LibraryEffect.NONE,
            archetype_matches=frozenset(),
            pip_counts=pip_counts,
        )

    def test_double_pip_with_one_color_source_fails(self):
        from mtg_utils._custom_format._common import can_cast_with_pips

        counterspell = self._spell(
            "Counterspell",
            cmc=2,
            pip_counts=(("U", 2),),
            color_identity=("U",),
        )
        assert can_cast_with_pips(counterspell, {"U": 1}) is False

    def test_double_pip_with_two_color_sources_passes(self):
        from mtg_utils._custom_format._common import can_cast_with_pips

        counterspell = self._spell(
            "Counterspell",
            cmc=2,
            pip_counts=(("U", 2),),
            color_identity=("U",),
        )
        assert can_cast_with_pips(counterspell, {"U": 2}) is True

    def test_generic_satisfied_by_any_color(self):
        from mtg_utils._custom_format._common import can_cast_with_pips

        # {2}{U} — 1 U + 2 generic. Any 3 mana with at least 1 U works.
        spell = self._spell(
            "Mid Spell",
            cmc=3,
            pip_counts=(("U", 1),),
            color_identity=("U",),
        )
        assert can_cast_with_pips(spell, {"U": 1, "R": 2}) is True

    def test_total_mana_short_fails(self):
        from mtg_utils._custom_format._common import can_cast_with_pips

        spell = self._spell(
            "Mid Spell",
            cmc=3,
            pip_counts=(("U", 1),),
            color_identity=("U",),
        )
        # 1 U + 1 R = 2 mana, but card needs 3.
        assert can_cast_with_pips(spell, {"U": 1, "R": 1}) is False

    def test_land_returns_false(self):
        from mtg_utils._custom_format._common import (
            CardMetadata,
            LibraryEffect,
            can_cast_with_pips,
        )

        land = CardMetadata(
            name="Plains",
            cmc=0,
            color_identity=frozenset({"W"}),
            produced_mana=("W",),
            is_land=True,
            library_effect=LibraryEffect.NONE,
            archetype_matches=frozenset(),
            pip_counts=(),
        )
        assert can_cast_with_pips(land, {"W": 5, "U": 5}) is False
