"""Smoke tests: verify the deck-builder package installs and key modules resolve."""

from mtg_utils.format_config import FORMAT_CONFIGS, is_arena_format, is_constructed_format


class TestImports:
    def test_arena_formats(self):
        for fmt in ("standard", "alchemy", "historic", "timeless", "pioneer"):
            assert is_arena_format(fmt)

    def test_paper_formats(self):
        for fmt in ("modern", "premodern", "legacy", "vintage"):
            assert not is_arena_format(fmt)

    def test_all_constructed_have_sideboard(self):
        for fmt, cfg in FORMAT_CONFIGS.items():
            if not cfg.get("has_commander", True):
                assert cfg["sideboard_size"] == 15, f"{fmt} missing sideboard"

    def test_commander_formats_exist(self):
        for fmt in ("commander", "brawl", "historic_brawl"):
            assert fmt in FORMAT_CONFIGS
            assert not is_constructed_format(fmt)

    def test_commander_specific_modules_importable(self):
        from mtg_utils import edhrec_lookup, find_commanders, set_commander

        assert callable(edhrec_lookup.main)
        assert callable(find_commanders.main)
        assert callable(set_commander.main)
