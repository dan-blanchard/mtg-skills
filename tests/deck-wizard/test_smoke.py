"""Smoke tests: verify the deck-wizard package installs and key modules resolve."""

from mtg_utils.formats import FORMATS
from mtg_utils.mana_audit import constructed_land_target


class TestFormats:
    def test_arena_formats(self):
        for fmt in ("standard", "alchemy", "historic", "timeless", "pioneer"):
            assert FORMATS[fmt].is_arena

    def test_paper_formats(self):
        for fmt in ("modern", "premodern", "legacy", "vintage"):
            assert not FORMATS[fmt].is_arena

    def test_constructed_formats_exist(self):
        for fmt in ("standard", "pioneer", "modern", "premodern", "legacy", "vintage"):
            assert FORMATS[fmt].is_constructed

    def test_commander_formats_exist(self):
        for fmt in ("commander", "brawl", "historic_brawl"):
            assert not FORMATS[fmt].is_constructed

    def test_all_constructed_have_sideboard(self):
        for fmt in FORMATS.values():
            if fmt.is_constructed:
                assert fmt.sideboard_size == 15, f"{fmt.name} missing sideboard"


class TestCommanderModules:
    def test_commander_specific_modules_importable(self):
        from mtg_utils import edhrec_lookup, find_commanders, set_commander

        assert callable(edhrec_lookup.main)
        assert callable(find_commanders.main)
        assert callable(set_commander.main)


class TestConstructedLandTarget:
    def test_baseline_24(self):
        result = constructed_land_target(ramp_count=0, avg_cmc=3.0)
        assert result == 24

    def test_ramp_reduces(self):
        result = constructed_land_target(ramp_count=4, avg_cmc=3.0)
        assert result < 24

    def test_clamped_low(self):
        result = constructed_land_target(ramp_count=20, avg_cmc=1.5)
        assert result >= 20

    def test_clamped_high(self):
        result = constructed_land_target(ramp_count=0, avg_cmc=5.0)
        assert result <= 27
