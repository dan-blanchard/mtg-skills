"""Tests for format_config module."""

from mtg_utils.format_config import (
    COMMANDER_FORMATS,
    FORMAT_CONFIGS,
    get_format_config,
    is_arena_format,
    is_arena_only_format,
    is_commander_format,
    is_constructed_format,
)


class TestFormatConfigs:
    def test_commander_defaults(self):
        cfg = FORMAT_CONFIGS["commander"]
        assert cfg["deck_size"] == 100
        assert cfg["life_total"] == 40
        assert cfg["multiplayer_life_total"] == 40
        assert cfg["commander_damage"] is True
        assert cfg["legality_key"] == "commander"
        assert cfg["planeswalker_commander_requires_text"] is True
        assert cfg["free_mulligan"] is False
        assert cfg["colorless_any_basic"] is False

    def test_brawl_defaults(self):
        cfg = FORMAT_CONFIGS["brawl"]
        assert cfg["deck_size"] == 60
        assert cfg["life_total"] == 25
        assert cfg["multiplayer_life_total"] == 30
        assert cfg["commander_damage"] is False
        assert cfg["legality_key"] == "standardbrawl"
        assert cfg["planeswalker_commander_requires_text"] is False
        assert cfg["free_mulligan"] is True
        assert cfg["colorless_any_basic"] is True

    def test_historic_brawl_defaults(self):
        cfg = FORMAT_CONFIGS["historic_brawl"]
        assert cfg["deck_size"] == 100
        assert cfg["life_total"] == 25
        assert cfg["multiplayer_life_total"] == 30
        assert cfg["commander_damage"] is False
        assert cfg["legality_key"] == "brawl"
        assert cfg["planeswalker_commander_requires_text"] is False
        assert cfg["free_mulligan"] is True
        assert cfg["colorless_any_basic"] is True


class TestCommanderFamily:
    def test_commander_formats_is_every_format_with_a_command_zone(self):
        assert COMMANDER_FORMATS == (
            "commander",
            "brawl",
            "historic_brawl",
            "competitive_brawl",
        )
        for fmt in COMMANDER_FORMATS:
            assert is_commander_format(fmt)
            assert not is_constructed_format(fmt)
        assert not is_commander_format("modern")
        assert not is_commander_format("bogus")

    def test_competitive_brawl_is_arena_only(self):
        assert is_arena_format("competitive_brawl")
        assert is_arena_only_format("competitive_brawl")
        # Brawl / Historic Brawl are Arena formats that ALSO exist in paper.
        assert is_arena_format("historic_brawl")
        assert not is_arena_only_format("historic_brawl")
        assert not is_arena_only_format("commander")


class TestGetFormatConfig:
    def test_defaults_to_commander(self):
        cfg = get_format_config({})
        assert cfg["deck_size"] == 100
        assert cfg["legality_key"] == "commander"

    def test_reads_format_from_deck(self):
        cfg = get_format_config({"format": "brawl"})
        assert cfg["deck_size"] == 60
        assert cfg["legality_key"] == "standardbrawl"

    def test_deck_size_override(self):
        cfg = get_format_config({"format": "historic_brawl", "deck_size": 60})
        assert cfg["deck_size"] == 60
        assert cfg["legality_key"] == "brawl"

    def test_returns_copy_not_original(self):
        cfg1 = get_format_config({"format": "commander"})
        cfg1["deck_size"] = 999
        cfg2 = get_format_config({"format": "commander"})
        assert cfg2["deck_size"] == 100

    def test_unknown_format_raises(self):
        import pytest

        with pytest.raises(ValueError, match="Unknown format"):
            get_format_config({"format": "made_up_format"})
