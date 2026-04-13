"""Tests for deck statistics calculator."""

import json

from click.testing import CliRunner

from mtg_utils.deck_stats import deck_stats, main, render_text_report
from mtg_utils.parse_deck import parse_deck


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


class TestAlternativeCostCards:
    def test_detects_suspend_cards(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(deck, alt_cost_cards)
        alt = {c["name"]: c for c in result["alternative_cost_cards"]}
        assert "Star Whale" in alt
        assert any(a["type"] == "suspend" for a in alt["Star Whale"]["alt_costs"])

    def test_detects_suspend_cost(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(deck, alt_cost_cards)
        alt = {c["name"]: c for c in result["alternative_cost_cards"]}
        star_whale_suspend = next(
            a for a in alt["Star Whale"]["alt_costs"] if a["type"] == "suspend"
        )
        assert "{1}{U}" in star_whale_suspend["cost"]

    def test_detects_evoke(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(deck, alt_cost_cards)
        alt = {c["name"]: c for c in result["alternative_cost_cards"]}
        assert "Fury" in alt
        assert any(a["type"] == "evoke" for a in alt["Fury"]["alt_costs"])

    def test_excludes_non_alt_cost_keywords(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(deck, alt_cost_cards)
        alt = {c["name"]: c for c in result["alternative_cost_cards"]}
        # Ward, Flying, Vigilance, Trample, Double strike, Delve are NOT alternative costs
        assert "Sol Ring" not in alt
        assert "Command Tower" not in alt
        assert "Goldvein Hydra" not in alt
        assert "Murderous Cut" not in alt

    def test_omits_cards_without_alt_costs(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(deck, alt_cost_cards)
        alt_names = {c["name"] for c in result["alternative_cost_cards"]}
        assert "Sol Ring" not in alt_names
        assert "Command Tower" not in alt_names


class TestSideboardStats:
    def test_sideboard_stats_present(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
            "sideboard": [
                {"name": "Smash", "quantity": 3},
                {"name": "Bolt", "quantity": 2},
            ],
        }
        hydrated = [
            {"name": "Lightning Bolt", "cmc": 1.0, "type_line": "Instant"},
            {"name": "Smash", "cmc": 2.0, "type_line": "Instant"},
            {"name": "Bolt", "cmc": 1.0, "type_line": "Instant"},
        ]
        result = deck_stats(deck, hydrated)
        assert result["sideboard_total"] == 5
        assert result["sideboard_curve"] == {1: 2, 2: 3}

    def test_no_sideboard_stats_when_empty(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
            "sideboard": [],
        }
        hydrated = [
            {"name": "Lightning Bolt", "cmc": 1.0, "type_line": "Instant"},
        ]
        result = deck_stats(deck, hydrated)
        assert "sideboard_total" not in result

    def test_no_sideboard_stats_when_absent(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
        }
        hydrated = [
            {"name": "Lightning Bolt", "cmc": 1.0, "type_line": "Instant"},
        ]
        result = deck_stats(deck, hydrated)
        assert "sideboard_total" not in result

    def test_sideboard_text_report(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Bolt", "quantity": 4}],
            "sideboard": [{"name": "Smash", "quantity": 3}],
        }
        hydrated = [
            {"name": "Bolt", "cmc": 1.0, "type_line": "Instant"},
            {"name": "Smash", "cmc": 2.0, "type_line": "Instant"},
        ]
        result = deck_stats(deck, hydrated)
        report = render_text_report(result)
        assert "Sideboard: 3 cards" in report


class TestCLI:
    def test_text_report_and_json_file(self, moxfield_deck, hydrated_cards, tmp_path):
        from conftest import json_from_cli_output

        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main, [str(deck_path), str(hydrated_path), "--output", str(output_path)]
        )
        assert result.exit_code == 0
        assert "deck-stats:" in result.output
        assert "Avg CMC" in result.output
        assert "Full JSON:" in result.output

        data = json_from_cli_output(result)
        assert "total_cards" in data
        assert "land_count" in data
        assert "avg_cmc" in data
