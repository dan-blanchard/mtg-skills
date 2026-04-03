"""Tests for deck list parser."""

import json

from click.testing import CliRunner

from commander_utils.parse_deck import main, parse_deck


class TestParseMoxfield:
    def test_parses_commander(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        assert result["commanders"] == ["Korvold, Fae-Cursed King"]

    def test_parses_cards(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Viscera Seer" in card_names
        assert "Blood Artist" in card_names
        assert "Sol Ring" in card_names
        assert "Command Tower" in card_names

    def test_excludes_commander_from_cards(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" not in card_names

    def test_quantities(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        cards_by_name = {c["name"]: c for c in result["cards"]}
        assert cards_by_name["Viscera Seer"]["quantity"] == 1

    def test_partner_commanders(self, partner_deck):
        result = parse_deck(partner_deck)
        assert sorted(result["commanders"]) == [
            "Thrasios, Triton Hero",
            "Tymna the Weaver",
        ]


class TestParseMTGO:
    def test_parses_cards(self, mtgo_deck):
        result = parse_deck(mtgo_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in card_names
        assert "Viscera Seer" in card_names

    def test_no_commander_without_section(self, mtgo_deck):
        result = parse_deck(mtgo_deck)
        assert result["commanders"] == []


class TestParsePlainText:
    def test_parses_names(self, plain_deck):
        result = parse_deck(plain_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in card_names
        assert "Viscera Seer" in card_names

    def test_default_quantity_one(self, plain_deck):
        result = parse_deck(plain_deck)
        for card in result["cards"]:
            assert card["quantity"] == 1


class TestParseCSV:
    def test_parses_csv(self, csv_deck):
        result = parse_deck(csv_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in card_names
        assert "Sol Ring" in card_names

    def test_csv_handles_commas_in_card_names(self, csv_deck):
        """Card names with commas (e.g., 'Korvold, Fae-Cursed King') must survive CSV parsing."""
        result = parse_deck(csv_deck)
        cards_by_name = {c["name"]: c for c in result["cards"]}
        assert "Korvold, Fae-Cursed King" in cards_by_name
        assert cards_by_name["Korvold, Fae-Cursed King"]["quantity"] == 1


class TestSetCodeStripping:
    def test_strips_moxfield_set_codes(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "1 Obeka, Splitter of Seconds (OTJ) 222\n"
            "1 Ancestral Vision (TSR) 52\n"
            "1 Sphinx of the Second Sun (PLST) CMR-99\n"
        )
        result = parse_deck(deck_path)
        names = [c["name"] for c in result["cards"]]
        assert "Obeka, Splitter of Seconds" in names
        assert "Ancestral Vision" in names
        assert "Sphinx of the Second Sun" in names


class TestFormatDetection:
    def test_detects_moxfield(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        assert len(result["commanders"]) > 0

    def test_detects_csv(self, csv_deck):
        result = parse_deck(csv_deck)
        assert len(result["cards"]) > 0


class TestCLI:
    def test_outputs_json(self, moxfield_deck):
        runner = CliRunner()
        result = runner.invoke(main, [str(moxfield_deck)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "commanders" in data
        assert "cards" in data
