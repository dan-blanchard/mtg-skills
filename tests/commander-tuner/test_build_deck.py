"""Tests for build_deck module."""

import json
from unittest.mock import patch

from click.testing import CliRunner

from commander_utils.build_deck import build_deck, main


class TestBuildDeck:
    def test_basic_cut_and_add(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [
                {"name": "Sol Ring", "quantity": 1},
                {"name": "Bad Card", "quantity": 1},
            ],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Sol Ring", "cmc": 1, "type_line": "Artifact"},
            {"name": "Bad Card", "cmc": 3, "type_line": "Creature"},
            {"name": "Good Card", "cmc": 2, "type_line": "Instant"},
        ]
        cuts = [{"name": "Bad Card", "quantity": 1}]
        adds = [{"name": "Good Card", "quantity": 1}]
        new_deck, _new_hydrated = build_deck(deck, hydrated, cuts, adds)
        card_names = [c["name"] for c in new_deck["cards"]]
        assert "Bad Card" not in card_names
        assert "Good Card" in card_names
        assert len(new_deck["cards"]) == 2

    def test_quantity_adjustment(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [
                {"name": "Mountain", "quantity": 2},
                {"name": "Island", "quantity": 2},
            ],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Mountain", "cmc": 0, "type_line": "Basic Land — Mountain"},
            {"name": "Island", "cmc": 0, "type_line": "Basic Land — Island"},
        ]
        cuts = [{"name": "Mountain", "quantity": 1}]
        adds = [{"name": "Island", "quantity": 1}]
        new_deck, _ = build_deck(deck, hydrated, cuts, adds)
        by_name = {c["name"]: c for c in new_deck["cards"]}
        assert by_name["Mountain"]["quantity"] == 1
        assert by_name["Island"]["quantity"] == 3

    def test_removes_entry_when_quantity_zero(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [{"name": "Bad Card", "quantity": 1}],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Bad Card", "cmc": 3, "type_line": "Creature"},
        ]
        cuts = [{"name": "Bad Card", "quantity": 1}]
        new_deck, _ = build_deck(deck, hydrated, cuts, [])
        assert len(new_deck["cards"]) == 0

    def test_does_not_modify_original(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Sol Ring", "cmc": 1, "type_line": "Artifact"},
        ]
        build_deck(deck, hydrated, [], [{"name": "New Card", "quantity": 1}])
        assert len(deck["cards"]) == 1

    def test_merges_new_card_into_hydrated(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [],
        }
        hydrated = [{"name": "Korvold", "cmc": 5, "type_line": "Creature"}]
        new_card_data = {"name": "New Card", "cmc": 2, "type_line": "Instant"}
        adds = [{"name": "New Card", "quantity": 1}]
        _, new_hydrated = build_deck(
            deck, hydrated, [], adds, extra_hydrated=[new_card_data]
        )
        names = [c["name"] for c in new_hydrated if c]
        assert "New Card" in names


class TestCLI:
    def test_cli_writes_output_files(self, tmp_path):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [{"name": "Bad Card", "quantity": 1}],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Bad Card", "cmc": 3, "type_line": "Creature"},
        ]
        cuts = [{"name": "Bad Card", "quantity": 1}]
        adds = [{"name": "Good Card", "quantity": 1}]

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(cuts))
        adds_path = tmp_path / "adds.json"
        adds_path.write_text(json.dumps(adds))
        output_dir = tmp_path / "output"

        good_card_data = {
            "name": "Good Card",
            "cmc": 2,
            "type_line": "Instant",
            "oracle_text": "Draw a card.",
            "mana_cost": "{1}{U}",
            "keywords": [],
            "colors": ["U"],
            "color_identity": ["U"],
            "prices": {"usd": "0.50"},
            "legalities": {"commander": "legal"},
        }

        with patch(
            "commander_utils.build_deck.lookup_single", return_value=good_card_data
        ):
            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    str(deck_path),
                    str(hydrated_path),
                    "--cuts",
                    str(cuts_path),
                    "--adds",
                    str(adds_path),
                    "--output-dir",
                    str(output_dir),
                ],
            )

        assert result.exit_code == 0
        new_deck = json.loads((output_dir / "new-deck.json").read_text())
        card_names = [c["name"] for c in new_deck["cards"]]
        assert "Good Card" in card_names
        assert "Bad Card" not in card_names

        new_hydrated = json.loads((output_dir / "new-hydrated.json").read_text())
        hydrated_names = [c["name"] for c in new_hydrated if c]
        assert "Good Card" in hydrated_names
