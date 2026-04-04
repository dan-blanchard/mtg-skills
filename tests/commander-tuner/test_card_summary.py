"""Tests for compact card summary formatter."""

import json

from click.testing import CliRunner

from commander_utils.card_summary import card_summary, main


class TestCardSummary:
    def test_contains_card_names(self, hydrated_cards):
        hydrated = hydrated_cards
        output = card_summary(hydrated)
        assert "Sol Ring" in output
        assert "Command Tower" in output
        assert "Korvold, Fae-Cursed King" in output

    def test_lands_only(self, hydrated_cards):
        hydrated = hydrated_cards
        output = card_summary(hydrated, lands_only=True)
        assert "Command Tower" in output
        assert "Overgrown Tomb" in output
        assert "Sol Ring" not in output
        assert "Viscera Seer" not in output

    def test_nonlands_only(self, hydrated_cards):
        hydrated = hydrated_cards
        output = card_summary(hydrated, nonlands_only=True)
        assert "Command Tower" not in output
        assert "Overgrown Tomb" not in output
        assert "Sol Ring" in output

    def test_type_filter(self, hydrated_cards):
        hydrated = hydrated_cards
        output = card_summary(hydrated, type_filter="Creature")
        assert "Korvold, Fae-Cursed King" in output
        assert "Viscera Seer" in output
        assert "Sol Ring" not in output
        assert "Command Tower" not in output

    def test_no_prices_or_legalities(self, hydrated_cards):
        hydrated = hydrated_cards
        output = card_summary(hydrated)
        assert "prices" not in output
        assert "legalities" not in output

    def test_filters_none_entries(self):
        hydrated = [
            None,
            {
                "name": "Sol Ring",
                "mana_cost": "{1}",
                "cmc": 1.0,
                "type_line": "Artifact",
                "oracle_text": "{T}: Add {C}{C}.",
            },
            None,
        ]
        output = card_summary(hydrated)
        assert "Sol Ring" in output

    def test_does_not_truncate_moderate_oracle_text(self):
        text_500 = "x" * 500
        hydrated = [
            {
                "name": "Test Card",
                "mana_cost": "{1}",
                "cmc": 1.0,
                "type_line": "Instant",
                "oracle_text": text_500,
            }
        ]
        output = card_summary(hydrated)
        assert "..." not in output
        assert text_500 in output

    def test_truncates_very_long_oracle_text(self):
        text_1500 = "x" * 1500
        hydrated = [
            {
                "name": "Test Card",
                "mana_cost": "{1}",
                "cmc": 1.0,
                "type_line": "Instant",
                "oracle_text": text_1500,
            }
        ]
        output = card_summary(hydrated)
        assert "..." in output


class TestCLI:
    def test_outputs_text_not_json(self, hydrated_cards, tmp_path):
        hydrated = hydrated_cards
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(main, [str(hydrated_path)])
        assert result.exit_code == 0
        # Should NOT be valid JSON — it's a text table
        try:
            json.loads(result.output)
            is_json = True
        except json.JSONDecodeError:
            is_json = False
        assert not is_json

    def test_lands_only_flag(self, hydrated_cards, tmp_path):
        hydrated = hydrated_cards
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(main, [str(hydrated_path), "--lands-only"])
        assert result.exit_code == 0
        assert "Command Tower" in result.output
        assert "Sol Ring" not in result.output

    def test_nonlands_only_flag(self, hydrated_cards, tmp_path):
        hydrated = hydrated_cards
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(main, [str(hydrated_path), "--nonlands-only"])
        assert result.exit_code == 0
        assert "Command Tower" not in result.output

    def test_type_flag(self, hydrated_cards, tmp_path):
        hydrated = hydrated_cards
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(main, [str(hydrated_path), "--type", "Creature"])
        assert result.exit_code == 0
        assert "Viscera Seer" in result.output
        assert "Sol Ring" not in result.output
