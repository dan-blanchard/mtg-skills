"""Smoke tests: verify the deck-builder package installs and key modules resolve."""

from commander_utils.format_config import FORMAT_CONFIGS, is_arena_format


class TestImports:
    def test_arena_formats(self):
        for fmt in ("standard", "alchemy", "historic", "timeless"):
            assert is_arena_format(fmt)

    def test_paper_formats(self):
        for fmt in ("pioneer", "modern", "legacy", "vintage"):
            assert not is_arena_format(fmt)

    def test_all_constructed_have_sideboard(self):
        for fmt, cfg in FORMAT_CONFIGS.items():
            if not cfg.get("has_commander", True):
                assert cfg["sideboard_size"] == 15, f"{fmt} missing sideboard"
