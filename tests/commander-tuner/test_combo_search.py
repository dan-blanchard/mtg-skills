"""Tests for Commander Spellbook combo search."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from commander_utils.combo_search import (
    combo_search,
    discover_main,
    main,
    search_combos,
)

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


class TestFormatAwareLegality:
    def test_filters_by_deck_format(self, sample_combo_response):
        """When deck has format='brawl', check standardbrawl legality key."""
        sample_combo_response["results"]["included"][0]["legalities"][
            "standardbrawl"
        ] = True
        sample_combo_response["results"]["included"][0]["legalities"]["commander"] = (
            False
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        brawl_deck = {
            "format": "brawl",
            "deck_size": 60,
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [
                {"name": "Viscera Seer", "quantity": 1},
                {"name": "Blood Artist", "quantity": 1},
                {"name": "Reassembling Skeleton", "quantity": 1},
                {"name": "Ashnod's Altar", "quantity": 1},
            ],
        }

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(brawl_deck)

        assert len(result["combos"]) == 1

    def test_defaults_to_commander_legality(self, sample_combo_response):
        """Deck without format field uses commander legality."""
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

    def test_near_misses_use_format_legality(self, sample_combo_response):
        """Near-misses also filter by format legality."""
        for nm in sample_combo_response["results"]["almostIncluded"]:
            nm["legalities"]["commander"] = False
            nm["legalities"]["standardbrawl"] = True

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        brawl_deck = {
            "format": "brawl",
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [
                {"name": "Viscera Seer", "quantity": 1},
                {"name": "Blood Artist", "quantity": 1},
                {"name": "Reassembling Skeleton", "quantity": 1},
                {"name": "Ashnod's Altar", "quantity": 1},
                {"name": "Sol Ring", "quantity": 1},
                {"name": "Isochron Scepter", "quantity": 1},
            ],
        }

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = combo_search(brawl_deck)

        assert len(result["near_misses"]) == 2


class TestCLI:
    def test_text_report_and_json_file(self, tmp_path, sample_combo_response):
        from conftest import json_from_cli_output

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(SAMPLE_DECK))
        output_path = tmp_path / "out.json"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(main, [str(deck_path), "--output", str(output_path)])

        assert result.exit_code == 0, result.output
        assert "combo-search:" in result.output
        assert "Full JSON:" in result.output

        data = json_from_cli_output(result)
        assert "combos" in data
        assert "near_misses" in data

    def test_max_near_misses_flag(self, tmp_path, sample_combo_response):
        from conftest import json_from_cli_output

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(SAMPLE_DECK))
        output_path = tmp_path / "out.json"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_combo_response
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    str(deck_path),
                    "--max-near-misses",
                    "1",
                    "--output",
                    str(output_path),
                ],
            )

        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        assert len(data["near_misses"]) == 1


SAMPLE_VARIANTS_RESPONSE = {
    "results": [
        {
            "uses": [
                {"card": {"name": "Scurry Oak"}, "quantity": 1, "zoneLocations": "B"},
                {
                    "card": {"name": "Ivy Lane Denizen"},
                    "quantity": 1,
                    "zoneLocations": "B",
                },
            ],
            "produces": [
                {"name": "Infinite creature tokens"},
            ],
            "description": "1. Scurry Oak + Ivy Lane Denizen = infinite tokens.",
            "identity": "G",
            "manaNeeded": "",
            "bracketTag": "B3",
            "popularity": 24384,
            "legalities": {"commander": True, "standardbrawl": False, "brawl": True},
        },
    ],
}


class TestSearchCombos:
    def _mock_get(self, response_data, status_code=200, *, raise_error=False):
        """Create a mock session whose .get() returns the given response."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = response_data
        if raise_error:
            mock_resp.raise_for_status.side_effect = Exception("Server Error")
        else:
            mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_builds_query_from_result(self):
        mock_resp = self._mock_get(SAMPLE_VARIANTS_RESPONSE)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            search_combos(result="Infinite creature tokens")

        call_kwargs = mock_session.get.call_args
        q = (
            call_kwargs[1]["params"]["q"]
            if "params" in call_kwargs[1]
            else call_kwargs[0][1]["q"]
        )
        assert 'result:"Infinite creature tokens"' in q

    def test_builds_query_from_card(self):
        mock_resp = self._mock_get(SAMPLE_VARIANTS_RESPONSE)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            search_combos(cards=["Scurry Oak"])

        call_kwargs = mock_session.get.call_args
        q = call_kwargs[1]["params"]["q"]
        assert 'card:"Scurry Oak"' in q

    def test_builds_query_from_multiple_cards(self):
        mock_resp = self._mock_get(SAMPLE_VARIANTS_RESPONSE)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            search_combos(cards=["Scurry Oak", "Ivy Lane Denizen"])

        call_kwargs = mock_session.get.call_args
        q = call_kwargs[1]["params"]["q"]
        assert 'card:"Scurry Oak"' in q
        assert 'card:"Ivy Lane Denizen"' in q

    def test_builds_query_with_color_identity(self):
        mock_resp = self._mock_get(SAMPLE_VARIANTS_RESPONSE)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            search_combos(color_identity="BG")

        call_kwargs = mock_session.get.call_args
        q = call_kwargs[1]["params"]["q"]
        assert "ci:BG" in q

    def test_combines_all_query_parts(self):
        mock_resp = self._mock_get(SAMPLE_VARIANTS_RESPONSE)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            search_combos(
                result="Infinite creature tokens",
                cards=["Scurry Oak"],
                color_identity="G",
            )

        call_kwargs = mock_session.get.call_args
        q = call_kwargs[1]["params"]["q"]
        assert 'result:"Infinite creature tokens"' in q
        assert 'card:"Scurry Oak"' in q
        assert "ci:G" in q

    def test_normalizes_response(self):
        mock_resp = self._mock_get(SAMPLE_VARIANTS_RESPONSE)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            combos = search_combos(result="Infinite creature tokens")

        assert len(combos) == 1
        combo = combos[0]
        assert combo["cards"] == ["Scurry Oak", "Ivy Lane Denizen"]
        assert combo["result"] == ["Infinite creature tokens"]
        assert combo["identity"] == "G"
        assert combo["mana_needed"] == ""
        assert combo["bracket_tag"] == "B3"
        assert combo["popularity"] == 24384

    def test_returns_empty_on_api_error(self):
        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.side_effect = Exception("Connection refused")
            mock_requests.Session.return_value = mock_session

            result = search_combos(result="Infinite creature tokens")

        assert result == []

    def test_returns_empty_on_http_error(self):
        mock_resp = self._mock_get({}, status_code=500, raise_error=True)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = search_combos(result="Infinite creature tokens")

        assert result == []

    def test_respects_ordering_param(self):
        mock_resp = self._mock_get(SAMPLE_VARIANTS_RESPONSE)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            search_combos(result="Infinite creature tokens", ordering="-popularity")

        call_kwargs = mock_session.get.call_args
        assert call_kwargs[1]["params"]["ordering"] == "-popularity"

    def test_respects_limit_param(self):
        mock_resp = self._mock_get(SAMPLE_VARIANTS_RESPONSE)

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            search_combos(result="Infinite creature tokens", limit=25)

        call_kwargs = mock_session.get.call_args
        assert call_kwargs[1]["params"]["limit"] == 25


class TestGameWinningClassifier:
    """Pin the _is_game_winning heuristic.

    The classifier is deliberately narrow (matches 'infinite' and
    'win the game'). Synonyms like 'game-ending' or 'lethal damage'
    currently label as VALUE — this is a known limitation, not a bug.
    If the heuristic is ever broadened, update these tests too.
    """

    def test_infinite_is_game_winning(self):
        from commander_utils.combo_search import _is_game_winning

        assert _is_game_winning({"result": ["Infinite damage"]})
        assert _is_game_winning({"result": ["Infinite creature tokens"]})
        assert _is_game_winning({"result": ["Infinite mana", "Draw the deck"]})

    def test_win_the_game_is_game_winning(self):
        from commander_utils.combo_search import _is_game_winning

        assert _is_game_winning({"result": ["Win the game"]})

    def test_non_infinite_value_interactions_are_not_game_winning(self):
        from commander_utils.combo_search import _is_game_winning

        assert not _is_game_winning({"result": ["Extra mana of any color"]})
        assert not _is_game_winning({"result": ["Untap all lands"]})
        assert not _is_game_winning({"result": []})

    def test_narrow_heuristic_misses_synonyms(self):
        """Document that the narrow heuristic intentionally misses synonyms
        like 'game-ending' and 'lethal damage to each opponent'. A future
        broadening of _is_game_winning should delete this test and replace
        it with expanded positive cases."""
        from commander_utils.combo_search import _is_game_winning

        assert not _is_game_winning({"result": ["Game-ending pressure"]})
        assert not _is_game_winning({"result": ["Lethal damage to each opponent"]})


class TestDiscoverCLI:
    def test_text_report_and_json_file(self, tmp_path):
        from conftest import json_from_cli_output

        output_path = tmp_path / "out.json"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_VARIANTS_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.combo_search.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(
                discover_main,
                [
                    "--result",
                    "Infinite creature tokens",
                    "--output",
                    str(output_path),
                ],
            )

        assert result.exit_code == 0, result.output
        assert "combo-discover:" in result.output
        assert "Scurry Oak" in result.output
        assert "Full JSON:" in result.output

        data = json_from_cli_output(result)
        assert len(data) == 1
        assert data[0]["cards"] == ["Scurry Oak", "Ivy Lane Denizen"]
