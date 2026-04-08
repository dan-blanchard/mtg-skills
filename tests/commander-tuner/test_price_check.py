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
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(["Cheap Card", "No Price Card"])

        assert result["total_cost"] == 1.50
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

    def test_owned_cards_excluded_from_cost(self):
        cards_data = [
            {"name": "Sol Ring", "prices": {"usd": "2.00", "usd_foil": None}},
            {"name": "Owned Card", "prices": {"usd": "10.00", "usd_foil": None}},
        ]
        deck = {
            "commanders": [],
            "cards": [
                {"name": "Sol Ring", "quantity": 1},
                {"name": "Owned Card", "quantity": 1},
            ],
            "owned_cards": ["Owned Card"],
        }
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(deck)

        assert result["total_cost"] == 2.00
        assert result["total_value"] == 12.00
        assert result["owned_cards_count"] == 1
        assert result["cards"][1]["owned"] is True
        assert result["cards"][0]["owned"] is False

    def test_owned_cards_case_insensitive(self):
        cards_data = [
            {"name": "Sol Ring", "prices": {"usd": "2.00", "usd_foil": None}},
        ]
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
            "owned_cards": ["sol ring"],
        }
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(deck)

        assert result["cards"][0]["owned"] is True
        assert result["total_cost"] == 0.0
        assert result["total_value"] == 2.00

    def test_no_owned_cards_field_works(self):
        cards_data = [
            {"name": "Sol Ring", "prices": {"usd": "2.00", "usd_foil": None}},
        ]
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(["Sol Ring"])

        assert result["total_cost"] == 2.00
        assert result["total_value"] == 2.00
        assert result["owned_cards_count"] == 0

    def test_api_fallback_for_null_prices(self):
        bulk_card = {
            "name": "Priceless Card",
            "prices": {"usd": None, "usd_foil": None},
        }
        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = {
            "name": "Priceless Card",
            "prices": {"usd": "42.00", "usd_foil": "80.00"},
        }
        api_resp.raise_for_status = MagicMock()

        with (
            patch("commander_utils.price_check.lookup_single", return_value=bulk_card),
            patch("commander_utils.price_check.requests") as mock_requests,
        ):
            mock_session = MagicMock()
            mock_session.get.return_value = api_resp
            mock_requests.Session.return_value = mock_session

            result = check_prices(["Priceless Card"])

        assert result["cards"][0]["price_usd"] == 42.00
        assert result["total_cost"] == 42.00


class TestArenaWildcardMode:
    def test_arena_format_returns_wildcard_cost(self, sample_bulk_data):
        names = ["Sol Ring", "Viscera Seer"]
        result = check_prices(
            names,
            bulk_path=sample_bulk_data,
            format="historic_brawl",
        )
        assert "wildcard_cost" in result
        assert "total_cost" not in result
        for card in result["cards"]:
            assert "rarity" in card
            assert "price_usd" not in card

    def test_arena_format_tallies_wildcards(self, tmp_path):
        """Build bulk data with cards at known rarities."""
        cards = [
            {
                "name": "Common Card",
                "rarity": "common",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
            },
            {
                "name": "Rare Card",
                "rarity": "rare",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        result = check_prices(
            ["Common Card", "Rare Card"],
            bulk_path=bulk_path,
            format="historic_brawl",
        )
        assert result["wildcard_cost"]["common"] == 1
        assert result["wildcard_cost"]["rare"] == 1
        assert result["wildcard_cost"]["uncommon"] == 0

    def test_arena_uses_lowest_rarity_across_printings(self, tmp_path):
        """A card printed at rare and uncommon should cost an uncommon WC."""
        cards = [
            {
                "name": "Dual Print Card",
                "rarity": "rare",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
            },
            {
                "name": "Dual Print Card",
                "rarity": "uncommon",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        result = check_prices(
            ["Dual Print Card"],
            bulk_path=bulk_path,
            format="historic_brawl",
        )
        assert result["cards"][0]["rarity"] == "uncommon"
        assert result["wildcard_cost"]["uncommon"] == 1
        assert result["wildcard_cost"]["rare"] == 0

    def test_owned_cards_not_counted_in_wildcards(self, tmp_path):
        cards = [
            {
                "name": "My Rare",
                "rarity": "rare",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "My Rare", "quantity": 1}],
            "owned_cards": ["My Rare"],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["rare"] == 0
        assert result["cards"][0]["owned"] is True

    def test_commander_format_still_uses_usd(self, sample_bulk_data):
        names = ["Sol Ring"]
        result = check_prices(names, bulk_path=sample_bulk_data, format="commander")
        assert "total_cost" in result
        assert "wildcard_cost" not in result
        assert "price_usd" in result["cards"][0]


class TestArenaIllegalOrMissing:
    """Cards absent from the Arena rarity index must surface explicitly.

    The previous behavior silently defaulted them to "rare" wildcards,
    which masked banned cards (Sol Ring, Skullclamp, etc.) in Brawl /
    Historic Brawl budget checks.
    """

    def _bulk_with(self, tmp_path, cards):
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        return bulk_path

    def test_illegal_card_goes_to_illegal_or_missing(self, tmp_path):
        # Sol Ring is only Commander-legal; not in the Brawl rarity index.
        bulk = [
            {
                "name": "Sol Ring",
                "rarity": "uncommon",
                "legalities": {"commander": "legal", "brawl": "not_legal"},
                "games": ["arena"],
                "prices": {},
            },
        ]
        bulk_path = self._bulk_with(tmp_path, bulk)

        result = check_prices(
            ["Sol Ring"],
            bulk_path=bulk_path,
            format="historic_brawl",
        )
        assert "illegal_or_missing" in result
        names = [c["name"] for c in result["illegal_or_missing"]]
        assert "Sol Ring" in names

    def test_illegal_card_not_counted_in_wildcards(self, tmp_path):
        """A banned card must not inflate the rare wildcard count."""
        bulk = [
            {
                "name": "Sol Ring",
                "rarity": "uncommon",
                "legalities": {"commander": "legal", "brawl": "not_legal"},
                "games": ["arena"],
                "prices": {},
            },
            {
                "name": "Cultivate",
                "rarity": "common",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
            },
        ]
        bulk_path = self._bulk_with(tmp_path, bulk)

        result = check_prices(
            ["Sol Ring", "Cultivate"],
            bulk_path=bulk_path,
            format="historic_brawl",
        )
        # Sol Ring is illegal: 0 contribution. Cultivate is a legal common.
        assert result["wildcard_cost"]["rare"] == 0
        assert result["wildcard_cost"]["common"] == 1
        assert len(result["illegal_or_missing"]) == 1

    def test_illegal_card_entry_marked_not_legal(self, tmp_path):
        bulk = [
            {
                "name": "Sol Ring",
                "rarity": "uncommon",
                "legalities": {"commander": "legal", "brawl": "not_legal"},
                "games": ["arena"],
                "prices": {},
            },
        ]
        bulk_path = self._bulk_with(tmp_path, bulk)

        result = check_prices(
            ["Sol Ring"],
            bulk_path=bulk_path,
            format="historic_brawl",
        )
        entry = next(c for c in result["cards"] if c["name"] == "Sol Ring")
        assert entry["legal"] is False
        assert entry["rarity"] is None

    def test_text_report_warns_about_illegal_cards(self, tmp_path):
        from commander_utils.price_check import render_text_report

        bulk = [
            {
                "name": "Sol Ring",
                "rarity": "uncommon",
                "legalities": {"brawl": "not_legal"},
                "games": ["arena"],
                "prices": {},
            },
        ]
        bulk_path = self._bulk_with(tmp_path, bulk)

        result = check_prices(
            ["Sol Ring"],
            bulk_path=bulk_path,
            format="historic_brawl",
        )
        text = render_text_report(result)
        assert "WARNING" in text
        assert "Sol Ring" in text
        assert "illegal or not on Arena" in text


class TestCLI:
    def test_cli_with_name_list(self, sample_bulk_data, tmp_path):
        from conftest import json_from_cli_output

        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Sol Ring"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(names_path),
                "--bulk-data",
                str(sample_bulk_data),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0
        assert "price-check:" in result.output
        assert "Sol Ring" in result.output
        assert "Full JSON:" in result.output
        data = json_from_cli_output(result)
        assert len(data["cards"]) == 1

    def test_cli_with_budget(self, sample_bulk_data, tmp_path):
        from conftest import json_from_cli_output

        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Sol Ring"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(names_path),
                "--budget",
                "100",
                "--bulk-data",
                str(sample_bulk_data),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0
        assert "of $100.00 budget" in result.output
        data = json_from_cli_output(result)
        assert data["over_budget"] is False
