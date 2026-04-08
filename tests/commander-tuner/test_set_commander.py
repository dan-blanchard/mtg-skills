"""Tests for set_commander — moving cards to commander zone."""

import json

import pytest
from click.testing import CliRunner

from commander_utils.set_commander import main, set_commander


@pytest.fixture
def sample_deck() -> dict:
    """A minimal parsed deck with a few cards."""
    return {
        "commanders": [],
        "cards": [
            {"name": "Korvold, Fae-Cursed King", "quantity": 1},
            {"name": "Viscera Seer", "quantity": 1},
            {"name": "Sol Ring", "quantity": 1},
        ],
    }


@pytest.fixture
def partner_deck() -> dict:
    """A deck with two potential partner commanders in the cards list."""
    return {
        "commanders": [],
        "cards": [
            {"name": "Thrasios, Triton Hero", "quantity": 1},
            {"name": "Tymna the Weaver", "quantity": 1},
            {"name": "Sol Ring", "quantity": 1},
        ],
    }


class TestSetCommander:
    def test_moves_card_to_commanders(self, sample_deck):
        result = set_commander(sample_deck, ["Korvold, Fae-Cursed King"])
        commander_names = [c["name"] for c in result["commanders"]]
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in commander_names
        assert "Korvold, Fae-Cursed King" not in card_names

    def test_partner_commanders(self, partner_deck):
        result = set_commander(
            partner_deck, ["Thrasios, Triton Hero", "Tymna the Weaver"]
        )
        commander_names = [c["name"] for c in result["commanders"]]
        card_names = [c["name"] for c in result["cards"]]
        assert "Thrasios, Triton Hero" in commander_names
        assert "Tymna the Weaver" in commander_names
        assert "Thrasios, Triton Hero" not in card_names
        assert "Tymna the Weaver" not in card_names

    def test_card_not_found_raises(self, sample_deck):
        with pytest.raises(ValueError, match="not found"):
            set_commander(sample_deck, ["Nonexistent Card"])

    def test_does_not_modify_original(self, sample_deck):
        original_commanders = list(sample_deck["commanders"])
        original_cards = list(sample_deck["cards"])
        set_commander(sample_deck, ["Korvold, Fae-Cursed King"])
        assert sample_deck["commanders"] == original_commanders
        assert sample_deck["cards"] == original_cards

    def test_already_commander_is_noop(self):
        """Calling set-commander on a card already in the commander zone is a
        no-op, not an error. This makes ``parse-deck | set-commander`` safe to
        chain when parse-deck already honored a Moxfield ``Commander`` header.
        """
        deck = {
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        result = set_commander(deck, ["Korvold, Fae-Cursed King"])
        commander_names = [c["name"] for c in result["commanders"]]
        assert commander_names == ["Korvold, Fae-Cursed King"]
        assert [c["name"] for c in result["cards"]] == ["Sol Ring"]

    def test_mixed_idempotent_and_move(self):
        """Partner pair where one commander is already set and the other is in
        cards — the already-set one is untouched, the other is moved.
        """
        deck = {
            "commanders": [{"name": "Thrasios, Triton Hero", "quantity": 1}],
            "cards": [
                {"name": "Tymna the Weaver", "quantity": 1},
                {"name": "Sol Ring", "quantity": 1},
            ],
        }
        result = set_commander(deck, ["Thrasios, Triton Hero", "Tymna the Weaver"])
        commander_names = {c["name"] for c in result["commanders"]}
        card_names = {c["name"] for c in result["cards"]}
        assert commander_names == {"Thrasios, Triton Hero", "Tymna the Weaver"}
        assert card_names == {"Sol Ring"}


class TestCLI:
    def test_outputs_modified_json(self, sample_deck, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(sample_deck))

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), "Korvold, Fae-Cursed King"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        commander_names = [c["name"] for c in data["commanders"]]
        assert "Korvold, Fae-Cursed King" in commander_names

    def test_error_for_missing_card(self, sample_deck, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(sample_deck))

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), "Nonexistent Card"])

        assert result.exit_code != 0
