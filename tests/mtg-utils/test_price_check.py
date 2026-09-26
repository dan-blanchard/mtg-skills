"""Tests for price_check module."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mtg_utils.price_check import check_prices, main
from mtg_utils.testkit import printing_row, test_card, test_printing


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
        with (
            patch("mtg_utils.price_check.lookup_single") as mock_lookup,
            patch("mtg_utils.price_check._api_price_lookup", return_value=None),
        ):
            mock_lookup.side_effect = lambda name, **_kw: next(
                (c for c in cards_data if c["name"] == name), None
            )
            result = check_prices(["Cheap Card", "No Price Card"])

        assert result["total_cost"] == 1.50
        assert result["cards"][1]["price_usd"] is None

    def test_falls_back_to_usd_foil(self):
        card = {"name": "Foil Only", "prices": {"usd": None, "usd_foil": "5.00"}}
        with patch("mtg_utils.price_check.lookup_single", return_value=card):
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
        with patch("mtg_utils.price_check.lookup_single") as mock_lookup:
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
        with patch("mtg_utils.price_check.lookup_single") as mock_lookup:
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
        with patch("mtg_utils.price_check.lookup_single") as mock_lookup:
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
        with patch("mtg_utils.price_check.lookup_single") as mock_lookup:
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
        with patch("mtg_utils.price_check.lookup_single") as mock_lookup:
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
        with patch("mtg_utils.price_check.lookup_single") as mock_lookup:
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
        with patch("mtg_utils.price_check.lookup_single") as mock_lookup:
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
            patch("mtg_utils.price_check.lookup_single", return_value=bulk_card),
            patch("mtg_utils.price_check.requests") as mock_requests,
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

    def test_arena_4cap_covers_any_number_cards(self, tmp_path):
        """Arena's 4-copies-means-unlimited rule covers "any number" cards too:
        owning 4 Hare Apparent lets a deck run 17 of them for 0 wildcards."""
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps([_arena_printing("Hare Apparent", "common")]))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Hare Apparent", "quantity": 17}],
            "owned_cards": [{"name": "Hare Apparent", "quantity": 4}],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["common"] == 0
        assert result["cards"][0]["owned"] is True
        assert result["cards"][0]["wildcards_needed"] == 0

    def test_arena_4cap_covers_up_to_n_cards(self, tmp_path):
        """The "up to N" variant (Seven Dwarves, Nazgul) is covered the same way:
        owning 4 Seven Dwarves fills all 7 slots."""
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps([_arena_printing("Seven Dwarves", "common")]))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Seven Dwarves", "quantity": 7}],
            "owned_cards": [{"name": "Seven Dwarves", "quantity": 4}],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["common"] == 0
        assert result["cards"][0]["wildcards_needed"] == 0

    def test_arena_basic_lands_are_free(self, tmp_path):
        """Arena gives every player unlimited basic lands: 32 unowned Forests
        cost no wildcards and count as owned."""
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps([_arena_printing("Forest", "common")]))

        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Forest", "quantity": 32}],
            "owned_cards": [],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["common"] == 0
        assert result["cards"][0]["owned"] is True
        assert result["cards"][0]["wildcards_needed"] == 0
        assert result["owned_cards_count"] == 1

    def test_arena_snow_basics_are_collected_not_free(self, tmp_path):
        """Only the six basic land types are free on Arena: Snow-Covered basics are
        collected like any card, so unowned ones cost wildcards."""
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(
            json.dumps([_arena_printing("Snow-Covered Forest", "common")])
        )
        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Snow-Covered Forest", "quantity": 2}],
            "owned_cards": [],
        }
        result = check_prices(deck, bulk_path=bulk_path)
        assert result["wildcard_cost"]["common"] == 2

    def test_arena_partial_ownership_under_4cap(self, tmp_path):
        """Owning 1-3 copies does NOT trigger the 4-cap substitution; the deck
        still needs wildcards for the shortfall. (An "any number" card, since
        a singleton deck with owned=1 is the no-op "fully owned" case.)"""
        cards = [_arena_printing("Persistent Petitioners", "common")]
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
        # Sol Ring is only Commander-legal (brawl: not_legal); not in the Brawl
        # rarity index.
        bulk = [
            _arena_printing("Sol Ring", "uncommon"),
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
            _arena_printing("Sol Ring", "uncommon"),
            _arena_printing("Cultivate", "common"),
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
            _arena_printing("Sol Ring", "uncommon"),
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
        from mtg_utils.price_check import render_text_report

        bulk = [
            _arena_printing("Sol Ring", "uncommon"),
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


class TestCompetitiveBrawlBanOverrides:
    """``competitive_brawl`` shares the ``brawl`` legality key but not its ban
    list (``Format.ignores_legality_key_bans`` + ``banned_cards``).
    ``price-check`` must cost a brawl-banned staple as a normal craft, not
    report it under ``illegal_or_missing`` — and must still reject the
    format's own by-name bans."""

    def _bulk(self, tmp_path):
        # Both are banned under the ``brawl`` key and printed on Arena; only Oko
        # is on Competitive Brawl's own by-name list.
        cards = [
            _arena_printing("Tainted Pact", "mythic"),
            _arena_printing("Oko, Thief of Crowns", "mythic"),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        return bulk_path

    def test_key_banned_card_is_costed_in_competitive_brawl(self, tmp_path):
        deck = {
            "format": "competitive_brawl",
            "commanders": [],
            "cards": [{"name": "Tainted Pact", "quantity": 1}],
            "owned_cards": [],
        }
        result = check_prices(deck, bulk_path=self._bulk(tmp_path))
        assert result["illegal_or_missing"] == []
        assert result["wildcard_cost"]["mythic"] == 1
        assert result["cards"][0]["legal"] is True

    def test_key_banned_card_still_illegal_in_historic_brawl(self, tmp_path):
        deck = {
            "format": "historic_brawl",
            "commanders": [],
            "cards": [{"name": "Tainted Pact", "quantity": 1}],
            "owned_cards": [],
        }
        result = check_prices(deck, bulk_path=self._bulk(tmp_path))
        assert [e["name"] for e in result["illegal_or_missing"]] == ["Tainted Pact"]

    def test_format_own_ban_list_still_enforced(self, tmp_path):
        deck = {
            "format": "competitive_brawl",
            "commanders": [],
            "cards": [{"name": "Oko, Thief of Crowns", "quantity": 1}],
            "owned_cards": [],
        }
        result = check_prices(deck, bulk_path=self._bulk(tmp_path))
        assert [e["name"] for e in result["illegal_or_missing"]] == [
            "Oko, Thief of Crowns"
        ]
        assert result["wildcard_cost"]["mythic"] == 0


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


def test_cli_auto_discovers_the_bulk_and_stays_offline(
    sample_bulk_data, tmp_path, monkeypatch
):
    # ADR-0046: the shared --bulk-data option defaults to the auto-discovered bulk,
    # so a bare `price-check deck.json` prices from disk, never one Scryfall request
    # per name.
    from mtg_utils import card_pool, price_check, scryfall_lookup

    monkeypatch.setattr(card_pool, "default_bulk_path", lambda: sample_bulk_data)
    monkeypatch.setattr(
        scryfall_lookup, "fetch_card", lambda name: pytest.fail(f"fetched {name}")
    )
    names = tmp_path / "names.json"
    names.write_text(json.dumps(["Sol Ring"]))
    result = CliRunner().invoke(
        price_check.main, [str(names), "--output", str(tmp_path / "out.json")]
    )
    assert result.exit_code == 0, result.output
    assert "WARNING" not in result.output
    assert json.loads((tmp_path / "out.json").read_text())["cards"]


def test_cli_arena_format_without_a_bulk_is_an_error(tmp_path, monkeypatch):
    # Wildcard costing has no per-card fallback: a USD report would read as
    # wildcards to an agent following SKILL.md's "price-check --format <fmt>".
    from mtg_utils import card_pool, price_check

    monkeypatch.setattr(card_pool, "default_bulk_path", lambda: None)
    names = tmp_path / "names.json"
    names.write_text(json.dumps(["Sol Ring"]))
    result = CliRunner().invoke(price_check.main, [str(names), "--format", "brawl"])
    assert result.exit_code != 0
    assert "Arena wildcard pricing" in result.output
    assert "download-mtgjson" in result.output
    # The deck JSON's own format counts too (check_prices reads it when no flag).
    deck = tmp_path / "deck.json"
    deck.write_text(
        json.dumps({"format": "historic_brawl", "commanders": [], "cards": []})
    )
    result = CliRunner().invoke(price_check.main, [str(deck)])
    assert result.exit_code != 0
    assert "historic_brawl needs the local bulk" in result.output


def test_cli_without_any_bulk_warns_and_prices_from_scryfall(tmp_path, monkeypatch):
    from mtg_utils import card_pool, price_check, scryfall_lookup

    monkeypatch.setattr(card_pool, "default_bulk_path", lambda: None)
    monkeypatch.setattr(
        scryfall_lookup,
        "fetch_card",
        lambda name: {"name": name, "prices": {"usd": "1.00"}},
    )
    names = tmp_path / "names.json"
    names.write_text(json.dumps(["Sol Ring"]))
    result = CliRunner().invoke(
        price_check.main, [str(names), "--output", str(tmp_path / "out.json")]
    )
    assert result.exit_code == 0, result.output
    assert "no card-data bulk found" in result.output


def test_cube_json_prices_the_commander_pool_too(sample_bulk_data):
    # cube-wizard's "Cube budget check" runs price-check on the cube JSON; the
    # commander / PDH cube's commanders sit in ``commander_pool``, not ``cards``.
    cube = {
        "cards": [{"name": "Sol Ring", "quantity": 1}],
        "commander_pool": [{"name": "Thrasios, Triton Hero", "quantity": 1}],
    }
    result = check_prices(cube, bulk_path=sample_bulk_data)
    assert {c["name"] for c in result["cards"]} == {"Sol Ring", "Thrasios, Triton Hero"}


def _arena_printing(name: str, rarity: str) -> dict:
    """The real card *name* (its record from the snapshot) as one Arena printing at
    *rarity* — rarity and availability are per-printing facts the snapshot omits."""
    return {**test_card(name), "rarity": rarity, "games": ["arena"], "prices": {}}


# ── Basic lands: owned in any medium; a SPECIAL printing is owned in paper only if
# the collection holds that exact printing ──

_M21 = test_printing("Forest", "m21", "274", prices={"usd": "0.10", "usd_foil": "0.75"})
_ZNR_FULL_ART = test_printing(
    "Forest",
    "znr",
    "278",
    full_art=True,
    frame_effects=["fullart"],
    prices={"usd": "0.90", "usd_foil": "3.00"},
)
# A special printing with no listed price.
_UNPRICED_SHOWCASE = test_printing(
    "Forest", "m21", "313", frame_effects=["showcase"], prices={}
)
_LTR = test_printing(
    "Forest", "ltr", "270", promo_types=["universesbeyond"], prices={"usd": "0.10"}
)
# The collection holds thirty plain Forests of another printing.
_OTHER = printing_row("dmu", "277", quantity=30)


def _paper(tmp_path, entry, owned):
    """Copies of ``entry`` a paper check says to buy, with bulk printing records."""
    bulk_path = tmp_path / "bulk.json"
    bulk_path.write_text(json.dumps([_M21, _ZNR_FULL_ART, _LTR, _UNPRICED_SHOWCASE]))
    deck = {"cards": [entry], "owned_cards": owned}
    return check_prices(deck, bulk_path=bulk_path)["cards"][0]["copies_needed"]


def _paper_row(tmp_path, entry):
    bulk_path = tmp_path / "bulk.json"
    bulk_path.write_text(json.dumps([_M21, _ZNR_FULL_ART, _LTR, _UNPRICED_SHOWCASE]))
    return check_prices({"cards": [entry], "owned_cards": []}, bulk_path=bulk_path)


def _forests(*rows):
    return [{"name": "Forest", "quantity": 30, "printings": list(rows)}]


def _pin(set_code, number, **extra):
    return {
        "name": "Forest",
        "quantity": 2,
        "set": set_code,
        "collector_number": number,
        **extra,
    }


class TestBasicLandOwnership:
    def test_unlisted_basics_are_owned_in_paper(self, tmp_path):
        assert _paper(tmp_path, {"name": "Forest", "quantity": 20}, []) == 0

    def test_plain_printing_pins_stay_owned_in_paper(self, tmp_path):
        # "Forest (M21) 274" from an export, and a Universes Beyond basic: neither is
        # special, so the collection lacking that exact printing doesn't matter.
        assert _paper(tmp_path, _pin("M21", "274"), _forests(_OTHER)) == 0
        assert _paper(tmp_path, _pin("LTR", "270"), _forests(_OTHER)) == 0

    def test_a_special_pin_is_short_unless_that_printing_is_held(self, tmp_path):
        full_art = _pin("ZNR", "278")
        assert _paper(tmp_path, full_art, []) == 2  # no collection rows at all
        name_only = [{"name": "Forest", "quantity": 20}]
        assert _paper(tmp_path, full_art, name_only) == 2  # no printing detail
        assert _paper(tmp_path, full_art, _forests(_OTHER)) == 2  # another printing
        held = printing_row("znr", "278", quantity=2)
        assert _paper(tmp_path, full_art, _forests(_OTHER, held)) == 0

    def test_a_foil_pin_is_covered_only_by_foil_copies(self, tmp_path):
        foil = _pin("M21", "274", finish="foil")
        assert _paper(tmp_path, foil, []) == 2
        nonfoil_held = printing_row("m21", "274", quantity=2)
        assert _paper(tmp_path, foil, _forests(nonfoil_held)) == 2
        foil_held = printing_row("m21", "274", foil_quantity=2)
        assert _paper(tmp_path, foil, _forests(foil_held)) == 0

    def test_a_special_request_is_priced_at_that_printing(self, tmp_path):
        # Twenty unowned full-art ZNR Forests cost the ZNR price, not the cheapest
        # Forest's; a foil request costs the foil price.
        full_art = {**_pin("ZNR", "278"), "quantity": 20}
        assert _paper_row(tmp_path, full_art)["total_cost"] == 18.0
        foil = {**_pin("M21", "274", finish="foil"), "quantity": 20}
        assert _paper_row(tmp_path, foil)["total_cost"] == 15.0

    def test_an_unpriced_special_printing_falls_back_and_says_so(self, tmp_path):
        result = _paper_row(tmp_path, _pin("M21", "313"))
        row = result["cards"][0]
        assert row["copies_needed"] == 2
        assert row["price_usd"] == 0.10  # the cheapest printing's
        assert "no listed price" in row["price_note"]

    def test_any_forest_style_is_free_on_arena(self, tmp_path):
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps([_arena_printing("Forest", "common")]))
        for entry in (
            {"name": "Forest", "quantity": 2},
            _pin("ZNR", "278", finish="foil"),
        ):
            deck = {"format": "historic_brawl", "cards": [entry], "owned_cards": []}
            result = check_prices(deck, bulk_path=bulk_path)
            assert result["cards"][0]["wildcards_needed"] == 0

    def test_snow_covered_basics_are_ordinary_cards(self, tmp_path):
        snow = {"name": "Snow-Covered Forest", "quantity": 2}
        # A price is a per-printing fact the snapshot omits; without one, paper
        # pricing would fall back to Scryfall's API.
        records = {
            "Snow-Covered Forest": {
                **test_card("Snow-Covered Forest"),
                "prices": {"usd": "0.25"},
            }
        }
        with patch("mtg_utils.price_check.lookup_single") as mock_lookup:
            mock_lookup.side_effect = lambda name, **_kw: records.get(name)
            paper = check_prices({"cards": [snow], "owned_cards": []})
        assert paper["cards"][0]["copies_needed"] == 2
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(
            json.dumps([_arena_printing("Snow-Covered Forest", "common")])
        )
        arena = check_prices(
            {"format": "historic_brawl", "cards": [snow], "owned_cards": []},
            bulk_path=bulk_path,
        )
        assert arena["cards"][0]["wildcards_needed"] == 2


class TestMediumDecidesCostMode:
    """The medium, not the format's Arena flag, picks wildcards vs USD (ADR-0052):
    Standard and Pioneer run on both media and default to paper, so an Arena build
    says so with ``--medium digital`` or a deck ``medium``."""

    def test_standard_defaults_to_paper_usd(self, sample_bulk_data):
        result = check_prices(
            ["Viscera Seer"], bulk_path=sample_bulk_data, format="standard"
        )
        assert "total_cost" in result
        assert "wildcard_cost" not in result

    def test_medium_override_prices_standard_in_wildcards(self, sample_bulk_data):
        result = check_prices(
            ["Viscera Seer"],
            bulk_path=sample_bulk_data,
            format="standard",
            medium="digital",
        )
        assert "wildcard_cost" in result
        assert "total_cost" not in result

    def test_deck_medium_prices_standard_in_wildcards(self, sample_bulk_data):
        deck = {
            "format": "standard",
            "medium": "digital",
            "cards": [{"name": "Viscera Seer", "quantity": 1}],
        }
        result = check_prices(deck, bulk_path=sample_bulk_data)
        assert "wildcard_cost" in result

    def test_override_a_format_cannot_honour_falls_back(self, sample_bulk_data):
        # Commander is paper-only: a digital override is ignored, not raised.
        result = check_prices(
            ["Sol Ring"],
            bulk_path=sample_bulk_data,
            format="commander",
            medium="digital",
        )
        assert "total_cost" in result

    def test_cli_medium_flag(self, sample_bulk_data, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(
            json.dumps(
                {
                    "format": "standard",
                    "cards": [{"name": "Viscera Seer", "quantity": 1}],
                }
            )
        )
        out = tmp_path / "out.json"
        args = [
            str(deck_path),
            "--bulk-data",
            str(sample_bulk_data),
            "--output",
            str(out),
        ]
        runner = CliRunner()
        paper = runner.invoke(main, args)
        assert paper.exit_code == 0, paper.output
        assert "total_cost" in json.loads(out.read_text())
        digital = runner.invoke(main, [*args, "--medium", "digital"])
        assert digital.exit_code == 0, digital.output
        assert "wildcard_cost" in json.loads(out.read_text())
