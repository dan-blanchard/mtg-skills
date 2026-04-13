"""Smoke tests: verify the deck-tuner package installs and key entry points resolve."""

from mtg_utils.format_config import FORMAT_CONFIGS, is_constructed_format
from mtg_utils.mana_audit import constructed_land_target


class TestImports:
    def test_constructed_formats_exist(self):
        for fmt in ("standard", "pioneer", "modern", "premodern", "legacy", "vintage"):
            assert fmt in FORMAT_CONFIGS
            assert is_constructed_format(fmt)

    def test_commander_formats_not_constructed(self):
        for fmt in ("commander", "brawl", "historic_brawl"):
            assert not is_constructed_format(fmt)


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
