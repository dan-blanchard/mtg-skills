"""Tests for price_check module."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from commander_utils.price_check import check_prices, main


class TestCheckPrices:
    def test_returns_prices_from_bulk(self, sample_bulk_data):
        names = ["Sol Ring", "Viscera Seer"]
        result = check_prices(names, bulk_path=sample_bulk_data)
        assert len(result["cards"]) == 2
        assert result["cards"][0]["name"] == "Sol Ring"

    def test_null_prices_excluded_from_total(self):
        cards_data = [
            {"name": "Cheap Card", "prices": {"usd": "1.50", "usd_foil": "3.00"}},
            {"name": "No Price Card", "prices": {"usd": None, "usd_foil": None}},
        ]
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(["Cheap Card", "No Price Card"])

        assert result["total"] == 1.50
        assert result["cards"][1]["price_usd"] is None

    def test_falls_back_to_usd_foil(self):
        card = {"name": "Foil Only", "prices": {"usd": None, "usd_foil": "5.00"}}
        with patch("commander_utils.price_check.lookup_single", return_value=card):
            result = check_prices(["Foil Only"])

        assert result["cards"][0]["price_usd"] == 5.00

    def test_budget_tracking(self, sample_bulk_data):
        names = ["Sol Ring"]
        result = check_prices(names, bulk_path=sample_bulk_data, budget=10.0)
        assert "budget" in result
        assert "over_budget" in result

    def test_no_budget_omits_fields(self, sample_bulk_data):
        names = ["Sol Ring"]
        result = check_prices(names, bulk_path=sample_bulk_data)
        assert "budget" not in result
        assert "over_budget" not in result

    def test_accepts_deck_json(self, sample_bulk_data):
        deck = {
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        result = check_prices(deck, bulk_path=sample_bulk_data)
        names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in names
        assert "Sol Ring" in names

    def test_api_fallback_for_null_prices(self):
        bulk_card = {"name": "Priceless Card", "prices": {"usd": None, "usd_foil": None}}
        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = {"name": "Priceless Card", "prices": {"usd": "42.00", "usd_foil": "80.00"}}
        api_resp.raise_for_status = MagicMock()

        with patch("commander_utils.price_check.lookup_single", return_value=bulk_card), \
             patch("commander_utils.price_check.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = api_resp
            mock_requests.Session.return_value = mock_session

            result = check_prices(["Priceless Card"])

        assert result["cards"][0]["price_usd"] == 42.00
        assert result["total"] == 42.00


class TestCLI:
    def test_cli_with_name_list(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Sol Ring"]))

        runner = CliRunner()
        result = runner.invoke(
            main, [str(names_path), "--bulk-data", str(sample_bulk_data)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["cards"]) == 1

    def test_cli_with_budget(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Sol Ring"]))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(names_path), "--budget", "100", "--bulk-data", str(sample_bulk_data)],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["over_budget"] is False
