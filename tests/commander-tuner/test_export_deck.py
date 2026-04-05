"""Tests for export_deck module."""

import json

from click.testing import CliRunner

from commander_utils.export_deck import export_moxfield, main

SAMPLE_DECK = {
    "commanders": [{"name": "Kalain, Reclusive Painter", "quantity": 1}],
    "cards": [
        {"name": "Sol Ring", "quantity": 1},
        {"name": "Swamp", "quantity": 8},
        {"name": "Mountain", "quantity": 7},
    ],
    "total_cards": 17,
}


class TestExportMoxfield:
    def test_outputs_quantity_name_lines(self):
        result = export_moxfield(SAMPLE_DECK)
        lines = result.strip().split("\n")
        assert lines[0] == "1 Kalain, Reclusive Painter"
        assert lines[1] == "1 Sol Ring"
        assert lines[2] == "8 Swamp"
        assert lines[3] == "7 Mountain"

    def test_commanders_come_first(self):
        result = export_moxfield(SAMPLE_DECK)
        lines = result.strip().split("\n")
        assert "Kalain" in lines[0]

    def test_line_count_matches_entries(self):
        result = export_moxfield(SAMPLE_DECK)
        lines = result.strip().split("\n")
        assert len(lines) == 4

    def test_empty_deck(self):
        result = export_moxfield({"commanders": [], "cards": []})
        assert result == ""


class TestCLI:
    def test_outputs_text(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(SAMPLE_DECK))
        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path)])
        assert result.exit_code == 0
        assert "1 Sol Ring" in result.output
        assert "1 Kalain, Reclusive Painter" in result.output
