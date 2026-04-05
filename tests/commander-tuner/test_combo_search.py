"""Tests for Commander Spellbook combo search."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from commander_utils.combo_search import combo_search, main

SAMPLE_DECK = {
    "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
    "cards": [
        {"name": "Viscera Seer", "quantity": 1},
        {"name": "Blood Artist", "quantity": 1},
        {"name": "Reassembling Skeleton", "quantity": 1},
        {"name": "Ashnod's Altar", "quantity": 1},
        {"name": "Sol Ring", "quantity": 1},
        {"name": "Isochron Scepter", "quantity": 1},
        {"name": "Command Tower", "quantity": 1},
    ],
}


class TestComboSearch:
    def test_extracts_full_combos(self, sample_combo_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(SAMPLE_DECK)

        assert len(result["combos"]) == 1
        combo = result["combos"][0]
        assert combo["cards"] == [
            "Viscera Seer",
            "Blood Artist",
            "Reassembling Skeleton",
            "Ashnod's Altar",
        ]
        assert "Infinite colorless mana" in combo["result"]
        assert combo["bracket_tag"] == "B3"

    def test_extracts_near_misses_with_missing_card(self, sample_combo_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(SAMPLE_DECK)

        assert len(result["near_misses"]) == 2
        # First near-miss (by popularity): combo-3 with Dramatic Reversal or Isochron Scepter missing
        # Second: combo-2 with Gravecrawler missing
        nm_last = result["near_misses"][-1]
        assert nm_last["missing_card"] == "Gravecrawler"
        assert "Infinite death triggers" in nm_last["result"]

    def test_near_misses_sorted_by_popularity(self, sample_combo_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(SAMPLE_DECK)

        # combo-3 (popularity 12000) should come before combo-2 (popularity 8000)
        assert (
            result["near_misses"][0]["popularity"]
            > result["near_misses"][1]["popularity"]
        )

    def test_respects_max_near_misses(self, sample_combo_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(SAMPLE_DECK, max_near_misses=1)

        assert len(result["near_misses"]) == 1

    def test_returns_empty_on_api_error(self):
        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.side_effect = Exception("Connection refused")
            mock_requests.Session.return_value = mock_session

            result = combo_search(SAMPLE_DECK)

        assert result == {"combos": [], "near_misses": []}

    def test_returns_empty_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("Server Error")

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(SAMPLE_DECK)

        assert result == {"combos": [], "near_misses": []}

    def test_returns_empty_for_empty_deck(self, sample_combo_empty_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_empty_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search({"commanders": [], "cards": []})

        assert result == {"combos": [], "near_misses": []}

    def test_filters_to_commander_legal_only(self, sample_combo_response):
        sample_combo_response["results"]["included"][0]["legalities"]["commander"] = (
            False
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(SAMPLE_DECK)

        assert len(result["combos"]) == 0

    def test_handles_feature_dict_in_produces(self):
        """Test that produces entries with feature dict format are handled."""
        response = {
            "results": {
                "included": [
                    {
                        "uses": [
                            {"card": {"name": "Card A"}, "zoneLocations": "B"},
                            {"card": {"name": "Card B"}, "zoneLocations": "B"},
                        ],
                        "produces": [
                            {"feature": {"name": "Infinite mana"}},
                            {"feature": {"name": "Infinite damage"}},
                        ],
                        "description": "Combo desc",
                        "identity": "BR",
                        "manaNeeded": "{B}{R}",
                        "bracketTag": "B3",
                        "popularity": 5000,
                        "legalities": {"commander": True},
                    }
                ],
                "almostIncluded": [],
            }
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response
        mock_resp.raise_for_status = MagicMock()

        deck = {
            "commanders": [],
            "cards": [
                {"name": "Card A", "quantity": 1},
                {"name": "Card B", "quantity": 1},
            ],
        }

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(deck)

        assert len(result["combos"]) == 1
        assert "Infinite mana" in result["combos"][0]["result"]
        assert "Infinite damage" in result["combos"][0]["result"]

    def test_sends_correct_post_body(self, sample_combo_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            combo_search(SAMPLE_DECK)

        call_kwargs = mock_session.post.call_args
        body = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert "Korvold, Fae-Cursed King" in str(body["commanders"])
        assert "Viscera Seer" in str(body["main"])


class TestCLI:
    def test_outputs_json(self, tmp_path, sample_combo_response):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(SAMPLE_DECK))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(main, [str(deck_path)])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "combos" in data
        assert "near_misses" in data

    def test_max_near_misses_flag(self, tmp_path, sample_combo_response):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(SAMPLE_DECK))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(main, [str(deck_path), "--max-near-misses", "1"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["near_misses"]) == 1
