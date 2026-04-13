"""Tests for format_config module."""

from commander_utils.format_config import FORMAT_CONFIGS, get_format_config


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
