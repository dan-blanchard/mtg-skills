"""Tests for deck comparison and impact metrics."""

import json

from click.testing import CliRunner

from commander_utils.deck_diff import deck_diff, main
from commander_utils.parse_deck import parse_deck


def _make_modified_deck(deck):
    """Swap Viscera Seer for Rhystic Study in a deck."""
    new_deck = {
        "commanders": list(deck["commanders"]),
        "cards": [c for c in deck["cards"] if c["name"] != "Viscera Seer"],
    }
    new_deck["cards"].append({"name": "Rhystic Study", "quantity": 1})
    return new_deck


class TestDeckDiff:
    def test_detects_added_card(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        new_deck = _make_modified_deck(deck)
        result = deck_diff(deck, new_deck, hydrated, hydrated)
        added_names = [a["name"] for a in result["added"]]
        assert "Rhystic Study" in added_names

    def test_detects_removed_card(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        new_deck = _make_modified_deck(deck)
        result = deck_diff(deck, new_deck, hydrated, hydrated)
        removed_names = [r["name"] for r in result["removed"]]
        assert "Viscera Seer" in removed_names

    def test_count_stays_same_for_swap(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        new_deck = _make_modified_deck(deck)
        result = deck_diff(deck, new_deck, hydrated, hydrated)
        assert result["count_before"] == result["count_after"]

    def test_cmc_impact(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        new_deck = _make_modified_deck(deck)
        result = deck_diff(deck, new_deck, hydrated, hydrated)
        # Swapping Viscera Seer (cmc 1) for Rhystic Study (cmc 3) increases avg CMC
        assert result["avg_cmc_delta"] > 0

    def test_land_count_unchanged_for_nonland_swap(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        new_deck = _make_modified_deck(deck)
        result = deck_diff(deck, new_deck, hydrated, hydrated)
        assert result["land_count_delta"] == 0

    def test_ramp_count_delta(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        new_deck = _make_modified_deck(deck)
        result = deck_diff(deck, new_deck, hydrated, hydrated)
        # Viscera Seer is not ramp, Rhystic Study is not ramp, so delta = 0
        assert result["ramp_count_delta"] == 0


class TestSideboardDiff:
    def test_sideboard_added(self):
        old_deck = {
            "commanders": [],
            "cards": [{"name": "Bolt", "quantity": 4}],
            "sideboard": [],
        }
        new_deck = {
            "commanders": [],
            "cards": [{"name": "Bolt", "quantity": 4}],
            "sideboard": [{"name": "Smash", "quantity": 3}],
        }
        hydrated = [
            {"name": "Bolt", "cmc": 1, "type_line": "Instant"},
            {"name": "Smash", "cmc": 2, "type_line": "Instant"},
        ]
        result = deck_diff(old_deck, new_deck, hydrated, hydrated)
        assert result["sideboard_added"] == [{"name": "Smash", "quantity": 3}]
        assert result["sideboard_removed"] == []

    def test_sideboard_removed(self):
        old_deck = {
            "commanders": [],
            "cards": [{"name": "Bolt", "quantity": 4}],
            "sideboard": [{"name": "Smash", "quantity": 2}],
        }
        new_deck = {
            "commanders": [],
            "cards": [{"name": "Bolt", "quantity": 4}],
            "sideboard": [],
        }
        hydrated = [
            {"name": "Bolt", "cmc": 1, "type_line": "Instant"},
            {"name": "Smash", "cmc": 2, "type_line": "Instant"},
        ]
        result = deck_diff(old_deck, new_deck, hydrated, hydrated)
        assert result["sideboard_removed"] == [{"name": "Smash", "quantity": 2}]

    def test_no_sideboard_keys_when_no_sideboard(self):
        old_deck = {
            "commanders": [],
            "cards": [{"name": "Bolt", "quantity": 4}],
        }
        new_deck = {
            "commanders": [],
            "cards": [{"name": "Bolt", "quantity": 4}],
        }
        hydrated = [{"name": "Bolt", "cmc": 1, "type_line": "Instant"}]
        result = deck_diff(old_deck, new_deck, hydrated, hydrated)
        assert "sideboard_added" not in result
        assert "sideboard_removed" not in result


class TestCLI:
    def test_outputs_valid_json(self, moxfield_deck, hydrated_cards, tmp_path):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        new_deck = _make_modified_deck(deck)

        old_deck_path = tmp_path / "old_deck.json"
        old_deck_path.write_text(json.dumps(deck))
        new_deck_path = tmp_path / "new_deck.json"
        new_deck_path.write_text(json.dumps(new_deck))
        old_hydrated_path = tmp_path / "old_hydrated.json"
        old_hydrated_path.write_text(json.dumps(hydrated))
        new_hydrated_path = tmp_path / "new_hydrated.json"
        new_hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(old_deck_path),
                str(new_deck_path),
                str(old_hydrated_path),
                str(new_hydrated_path),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "added" in data
        assert "removed" in data
        assert "avg_cmc_delta" in data
