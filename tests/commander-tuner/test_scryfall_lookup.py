"""Tests for Scryfall card lookup."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from commander_utils.scryfall_lookup import (
    build_rarity_index,
    lookup_cards,
    lookup_single,
    main,
)


class TestLookupSingle:
    def test_finds_card_by_exact_name(self, sample_bulk_data):
        result = lookup_single("Viscera Seer", bulk_path=sample_bulk_data)
        assert result is not None
        assert result["name"] == "Viscera Seer"
        assert result["oracle_text"] == "Sacrifice a creature: Scry 1."
        assert result["mana_cost"] == "{B}"
        assert result["cmc"] == 1.0
        assert result["game_changer"] is False

    def test_finds_split_card_by_full_name(self, sample_bulk_data):
        result = lookup_single("Fire // Ice", bulk_path=sample_bulk_data)
        assert result is not None
        assert result["name"] == "Fire // Ice"

    def test_finds_split_card_by_front_face(self, sample_bulk_data):
        result = lookup_single("Fire", bulk_path=sample_bulk_data)
        assert result is not None
        assert result["name"] == "Fire // Ice"

    def test_identifies_game_changer(self, sample_bulk_data):
        result = lookup_single("Rhystic Study", bulk_path=sample_bulk_data)
        assert result is not None
        assert result["game_changer"] is True

    def test_api_fallback_when_not_in_bulk(self, sample_bulk_data):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "Newly Printed Card",
            "oracle_text": "Does something new.",
            "mana_cost": "{2}{W}",
            "cmc": 3.0,
            "type_line": "Creature — Human",
            "keywords": [],
            "colors": ["W"],
            "color_identity": ["W"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "1.00", "usd_foil": "3.00"},
            "game_changer": False,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.scryfall_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = lookup_single("Newly Printed Card", bulk_path=sample_bulk_data)

        assert result is not None
        assert result["name"] == "Newly Printed Card"

    def test_returns_none_when_not_found(self, sample_bulk_data):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("commander_utils.scryfall_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = lookup_single("Totally Fake Card", bulk_path=sample_bulk_data)

        assert result is None


class TestLookupBatch:
    def test_looks_up_multiple_cards(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Sol Ring", "Blood Artist"]))

        results = lookup_cards(names_path, bulk_path=sample_bulk_data)
        assert len(results) == 3
        result_names = {r["name"] for r in results}
        assert result_names == {"Viscera Seer", "Sol Ring", "Blood Artist"}

    def test_caches_results(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Sol Ring"]))
        cache_dir = tmp_path / "cache"

        # First call — populates cache
        results1 = lookup_cards(
            names_path, bulk_path=sample_bulk_data, cache_dir=cache_dir
        )
        assert len(results1) == 2

        # Second call — reads from cache (bulk_path=None would fail without cache)
        results2 = lookup_cards(names_path, bulk_path=None, cache_dir=cache_dir)
        assert results2 == results1

    def test_includes_not_found_as_none(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Totally Fake Card"]))

        with patch("commander_utils.scryfall_lookup.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            results = lookup_cards(names_path, bulk_path=sample_bulk_data)

        found = [r for r in results if r is not None]
        assert len(found) == 1


class TestLookupBatchDeckJSON:
    def test_accepts_deck_json(self, sample_bulk_data, tmp_path):
        deck_json = {
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [
                {"name": "Viscera Seer", "quantity": 1},
                {"name": "Sol Ring", "quantity": 1},
            ],
        }
        batch_path = tmp_path / "deck.json"
        batch_path.write_text(json.dumps(deck_json))

        results = lookup_cards(batch_path, bulk_path=sample_bulk_data)
        result_names = {r["name"] for r in results if r}
        assert "Korvold, Fae-Cursed King" in result_names
        assert "Viscera Seer" in result_names
        assert "Sol Ring" in result_names

    def test_deduplicates_names(self, sample_bulk_data, tmp_path):
        deck_json = {
            "commanders": [{"name": "Sol Ring", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        batch_path = tmp_path / "deck.json"
        batch_path.write_text(json.dumps(deck_json))

        results = lookup_cards(batch_path, bulk_path=sample_bulk_data)
        assert len(results) == 1

    def test_handles_empty_commanders(self, sample_bulk_data, tmp_path):
        deck_json = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        batch_path = tmp_path / "deck.json"
        batch_path.write_text(json.dumps(deck_json))

        results = lookup_cards(batch_path, bulk_path=sample_bulk_data)
        assert len(results) == 1
        assert results[0]["name"] == "Sol Ring"

    def test_still_accepts_name_list(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Sol Ring"]))

        results = lookup_cards(names_path, bulk_path=sample_bulk_data)
        assert len(results) == 2


class TestRarityField:
    def test_lookup_includes_rarity(self, sample_bulk_data):
        result = lookup_single("Sol Ring", bulk_path=sample_bulk_data)
        assert "rarity" in result


class TestBuildRarityIndex:
    def test_finds_lowest_rarity(self, tmp_path):
        cards = [
            {
                "name": "Dual Card",
                "rarity": "rare",
                "legalities": {"commander": "legal"},
            },
            {
                "name": "Dual Card",
                "rarity": "uncommon",
                "legalities": {"commander": "legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = build_rarity_index(bulk_path, "commander")
        assert index["dual card"] == "uncommon"

    def test_filters_by_legality(self, tmp_path):
        cards = [
            {
                "name": "Arena Card",
                "rarity": "common",
                "legalities": {"brawl": "legal", "commander": "not_legal"},
            },
            {
                "name": "Arena Card",
                "rarity": "rare",
                "legalities": {"brawl": "legal", "commander": "not_legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        # Legal in brawl — should find common
        index = build_rarity_index(bulk_path, "brawl")
        assert index["arena card"] == "common"
        # Not legal in commander — should be absent
        index = build_rarity_index(bulk_path, "commander")
        assert "arena card" not in index

    def test_treats_special_as_rare(self, tmp_path):
        cards = [
            {
                "name": "Special Card",
                "rarity": "special",
                "legalities": {"commander": "legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = build_rarity_index(bulk_path, "commander")
        assert index["special card"] == "rare"

    def test_indexes_front_face_of_split_cards(self, tmp_path):
        cards = [
            {
                "name": "Fire // Ice",
                "rarity": "uncommon",
                "legalities": {"commander": "legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = build_rarity_index(bulk_path, "commander")
        assert index["fire // ice"] == "uncommon"
        assert index["fire"] == "uncommon"


class TestCLI:
    def test_single_card_output(self, sample_bulk_data):
        runner = CliRunner()
        result = runner.invoke(
            main, ["Viscera Seer", "--bulk-data", str(sample_bulk_data)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "Viscera Seer"
