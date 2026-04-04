"""Tests for deck statistics calculator."""

import json

from click.testing import CliRunner

from commander_utils.deck_stats import deck_stats, main
from commander_utils.parse_deck import parse_deck


class TestDeckStats:
    def test_total_cards(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(deck, hydrated)
        # 1 commander + 10 cards = 11
        assert result["total_cards"] == 11

    def test_land_count(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(deck, hydrated)
        # Command Tower + Overgrown Tomb
        assert result["land_count"] == 2

    def test_creature_count(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(deck, hydrated)
        # Korvold (commander, creature), Viscera Seer, Blood Artist, Sakura-Tribe Elder
        assert result["creature_count"] == 4

    def test_ramp_count(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(deck, hydrated)
        # Sol Ring, Sakura-Tribe Elder, Cultivate, Ashnod's Altar
        assert result["ramp_count"] == 4

    def test_avg_cmc_nonlands(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(deck, hydrated)
        # Nonland cards: Korvold(5), Viscera Seer(1), Blood Artist(2),
        # Sakura-Tribe Elder(2), Deadly Rollick(4), Cultivate(3),
        # Sol Ring(1), Ashnod's Altar(3), Dictate of Erebos(5)
        # = 26 / 9 = 2.89 (rounded)
        expected = round(26.0 / 9, 2)
        assert result["avg_cmc"] == expected

    def test_curve_populated(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(deck, hydrated)
        assert isinstance(result["curve"], dict)
        # CMC 1 should have Sol Ring + Viscera Seer = 2
        assert result["curve"][1] == 2

    def test_color_sources(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(deck, hydrated)
        # Command Tower -> any, Overgrown Tomb -> B,G, Sol Ring -> C, Ashnod's Altar -> C
        assert "any" in result["color_sources"]
        assert "B" in result["color_sources"]
        assert "G" in result["color_sources"]


class TestCLI:
    def test_outputs_valid_json(self, moxfield_deck, hydrated_cards, tmp_path):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), str(hydrated_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_cards" in data
        assert "land_count" in data
        assert "avg_cmc" in data
