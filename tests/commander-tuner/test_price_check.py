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
            "owned_cards": [{"name": "Owned Card", "quantity": 1}],
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
            "owned_cards": [{"name": "sol ring", "quantity": 1}],
        }
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(deck)

        assert result["cards"][0]["owned"] is True
        assert result["total_cost"] == 0.0
        assert result["total_value"] == 2.00

    def test_owned_cards_zero_quantity_not_owned(self):
        """A zero-quantity ``owned_cards`` entry (e.g. a Moxfield wishlist
        row) is not treated as owned — price-check charges full price.
        This pins the ``_normalize_owned_cards`` qty<1 skip behavior so a
        future refactor can't silently let wishlist rows zero out budgets.
        """
        cards_data = [
            {"name": "Sol Ring", "prices": {"usd": "2.00", "usd_foil": None}},
        ]
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
            "owned_cards": [{"name": "Sol Ring", "quantity": 0}],
        }
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(deck)

        assert result["total_cost"] == 2.00
        assert result["owned_cards_count"] == 0
        assert result["cards"][0]["owned"] is False

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

    def test_paper_playset_shortfall(self):
        """Paper mode charges for the shortfall between deck quantity and
        owned quantity. A Commander deck running 17 Hare Apparent with
        only 4 in the collection is charged for 13 copies, not 1.
        """
        cards_data = [
            {"name": "Hare Apparent", "prices": {"usd": "1.00", "usd_foil": None}},
        ]
        deck = {
            "commanders": [],
            "cards": [{"name": "Hare Apparent", "quantity": 17}],
            "owned_cards": [{"name": "Hare Apparent", "quantity": 4}],
        }
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(deck)

        # Charge for the 13 we don't own, not 1.
        assert result["total_cost"] == 13.00
        assert result["total_value"] == 17.00
        assert result["cards"][0]["copies_needed"] == 13
        assert result["cards"][0]["deck_quantity"] == 17
        assert result["cards"][0]["owned_quantity"] == 4
        assert result["cards"][0]["owned"] is False

    def test_paper_playset_fully_owned(self):
        """Owning ``>= deck_qty`` copies in paper mode marks the card fully
        owned and charges zero, even with quantity > 1."""
        cards_data = [
            {"name": "Hare Apparent", "prices": {"usd": "1.00", "usd_foil": None}},
        ]
        deck = {
            "commanders": [],
            "cards": [{"name": "Hare Apparent", "quantity": 5}],
            "owned_cards": [{"name": "Hare Apparent", "quantity": 8}],
        }
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(deck)

        assert result["total_cost"] == 0.00
        assert result["cards"][0]["copies_needed"] == 0
        assert result["cards"][0]["owned"] is True

    def test_echoed_commander_not_double_counted(self):
        """A legendary creature listed in both ``commanders`` and ``cards``
        describes the same physical copy, not two copies. ``_extract_deck_entries``
        must reconcile via ``max`` (not ``sum``) so the deck is charged for
        one copy, matching ``mark_owned._collect_entries(sum_duplicates=False)``.
        """
        cards_data = [
            {
                "name": "Atraxa, Praetors' Voice",
                "prices": {"usd": "30.00", "usd_foil": None},
            },
        ]
        deck = {
            "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
            "cards": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
        }
        with patch("commander_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(deck)

        # Charged once, not twice.
        assert result["total_cost"] == 30.00
        assert result["cards"][0]["deck_quantity"] == 1

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

    def test_arena_4cap_owning_4_of_normal_card_is_infinite(self, tmp_path):
        """Arena treats ownership of 4 copies of a standard playset-capped
        card as infinite supply (no legal deck can need a 5th). A deck
        running 1 copy with 4 owned = 0 wildcards."""
        cards = [
            {
                "name": "Normal Rare",
                "rarity": "rare",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
                "oracle_text": "Draw a card.",
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Normal Rare", "quantity": 1}],
            "owned_cards": [{"name": "Normal Rare", "quantity": 4}],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["rare"] == 0
        assert result["cards"][0]["owned"] is True
        assert result["cards"][0]["wildcards_needed"] == 0

    def test_arena_4cap_exempt_card_charges_literal_shortfall(self, tmp_path):
        """For cards with oracle exemption (any-number / up-to-N), owning
        4 does NOT grant infinite supply — a deck running 17 Hare
        Apparent with 4 owned needs 13 wildcards."""
        cards = [
            {
                "name": "Hare Apparent",
                "rarity": "common",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
                "oracle_text": (
                    "When Hare Apparent enters, create X 1/1 white Rabbit "
                    "creature tokens...\n"
                    "A deck can have any number of cards named Hare Apparent."
                ),
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Hare Apparent", "quantity": 17}],
            "owned_cards": [{"name": "Hare Apparent", "quantity": 4}],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["common"] == 13
        assert result["cards"][0]["owned"] is False
        assert result["cards"][0]["wildcards_needed"] == 13

    def test_arena_4cap_exempt_card_fully_owned(self, tmp_path):
        """Exempt card where owned >= deck_qty: 0 wildcards."""
        cards = [
            {
                "name": "Hare Apparent",
                "rarity": "common",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
                "oracle_text": (
                    "A deck can have any number of cards named Hare Apparent."
                ),
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Hare Apparent", "quantity": 7}],
            "owned_cards": [{"name": "Hare Apparent", "quantity": 10}],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["common"] == 0
        assert result["cards"][0]["owned"] is True

    def test_arena_4cap_exempt_up_to_n_card(self, tmp_path):
        """The "up to N" exemption variant (Seven Dwarves, Nazgul) must
        also suppress the Arena 4-cap substitution: owning 4 Seven
        Dwarves when the deck wants 7 should charge 3 wildcards, not 0.

        The ``exempt_from_4cap`` flag on ``build_rarity_index`` is
        already unit-tested for the up-to-N oracle pattern; this test
        closes the end-to-end loop through ``_check_arena_wildcards``.
        """
        cards = [
            {
                "name": "Seven Dwarves",
                "rarity": "rare",
                "legalities": {"historicbrawl": "legal", "brawl": "legal"},
                "games": ["arena"],
                "prices": {},
                "oracle_text": (
                    "Seven Dwarves gets +1/+1 for each other creature "
                    "named Seven Dwarves you control.\n"
                    "A deck can have up to seven cards named Seven Dwarves."
                ),
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Seven Dwarves", "quantity": 7}],
            "owned_cards": [{"name": "Seven Dwarves", "quantity": 4}],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["rare"] == 3
        assert result["cards"][0]["wildcards_needed"] == 3
        assert result["cards"][0]["owned"] is False

    def test_arena_partial_ownership_under_4cap(self, tmp_path):
        """Owning 1-3 copies of a normal card does NOT trigger the 4-cap
        substitution; the deck still needs wildcards for the shortfall.
        (In singleton Historic Brawl with owned=1, this is the no-op
        "fully owned" case, so construct a non-singleton deck.)"""
        cards = [
            {
                "name": "Persistent Petitioners",
                "rarity": "common",
                "legalities": {"brawl": "legal"},
                "games": ["arena"],
                "prices": {},
                "oracle_text": (
                    "A deck can have any number of cards named Persistent Petitioners."
                ),
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Persistent Petitioners", "quantity": 10}],
            "owned_cards": [{"name": "Persistent Petitioners", "quantity": 2}],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["common"] == 8
        assert result["cards"][0]["wildcards_needed"] == 8

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
            "owned_cards": [{"name": "My Rare", "quantity": 1}],
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
