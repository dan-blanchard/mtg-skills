"""Tests for card_search module."""

import json

from click.testing import CliRunner

from commander_utils.card_search import (
    _color_identity_subset,
    _extract_price,
    _matches_filters,
    format_results,
    main,
    search_cards,
)


def _make_card(
    name="Test Card",
    oracle_text="Some text",
    type_line="Creature",
    cmc=3.0,
    color_identity=None,
    price_usd="5.00",
    layout="normal",
    set_type="expansion",
    legalities=None,
):
    return {
        "name": name,
        "oracle_text": oracle_text,
        "type_line": type_line,
        "cmc": cmc,
        "color_identity": color_identity or [],
        "prices": {"usd": price_usd, "usd_foil": None, "usd_etched": None},
        "layout": layout,
        "set_type": set_type,
        "legalities": legalities or {"commander": "legal"},
    }


class TestColorIdentitySubset:
    def test_empty_is_subset_of_any(self):
        assert _color_identity_subset([], {"B", "R"})

    def test_mono_is_subset_of_pair(self):
        assert _color_identity_subset(["B"], {"B", "R"})

    def test_exact_match(self):
        assert _color_identity_subset(["B", "R"], {"B", "R"})

    def test_superset_rejected(self):
        assert not _color_identity_subset(["B", "R", "G"], {"B", "R"})


class TestExtractPrice:
    def test_usd_preferred(self):
        card = {"prices": {"usd": "10.00", "usd_foil": "15.00"}}
        assert _extract_price(card) == 10.0

    def test_foil_fallback(self):
        card = {"prices": {"usd": None, "usd_foil": "15.00"}}
        assert _extract_price(card) == 15.0

    def test_none_when_no_price(self):
        card = {"prices": {"usd": None, "usd_foil": None}}
        assert _extract_price(card) is None


class TestMatchesFilters:
    def test_matches_all_defaults(self):
        card = _make_card()
        assert _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
        )

    def test_rejects_token_layout(self):
        card = _make_card(layout="token")
        assert not _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
        )

    def test_rejects_non_commander_legal(self):
        card = _make_card(legalities={"commander": "not_legal"})
        assert not _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
        )

    def test_color_identity_filter(self):
        card = _make_card(color_identity=["B", "R", "G"])
        assert not _matches_filters(
            card,
            allowed_colors={"B", "R"},
            oracle_re=None,
            type_lower=None,
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
        )

    def test_cmc_range(self):
        card = _make_card(cmc=5.0)
        assert not _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            cmc_min=None,
            cmc_max=4.0,
            price_min=None,
            price_max=None,
        )

    def test_price_range(self):
        card = _make_card(price_usd="20.00")
        assert not _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=10.0,
        )


class TestSearchCards:
    def test_returns_matching_cards(self, tmp_path):
        cards = [
            _make_card(name="Good Card", oracle_text="Create a Treasure token"),
            _make_card(name="Bad Card", oracle_text="Draw a card"),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, oracle="Treasure")
        assert len(results) == 1
        assert results[0]["name"] == "Good Card"

    def test_deduplicates_by_name(self, tmp_path):
        cards = [
            _make_card(name="Sol Ring", price_usd="1.00"),
            _make_card(name="Sol Ring", price_usd="2.00"),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path)
        assert len(results) == 1

    def test_respects_limit(self, tmp_path):
        cards = [_make_card(name=f"Card {i}") for i in range(10)]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, limit=3)
        assert len(results) == 3

    def test_sort_price_desc(self, tmp_path):
        cards = [
            _make_card(name="Cheap", price_usd="1.00"),
            _make_card(name="Expensive", price_usd="50.00"),
            _make_card(name="Mid", price_usd="10.00"),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, sort="price-desc")
        assert results[0]["name"] == "Expensive"
        assert results[-1]["name"] == "Cheap"


class TestFormatResults:
    def test_empty_returns_message(self):
        assert format_results([]) == "No results found."

    def test_includes_headers(self):
        cards = [_make_card()]
        result = format_results(cards)
        assert "Name" in result
        assert "Price" in result
        assert "Oracle Text" in result

    def test_includes_card_name(self):
        cards = [_make_card(name="Sol Ring")]
        result = format_results(cards)
        assert "Sol Ring" in result


class TestCLI:
    def test_json_output(self, tmp_path):
        cards = [_make_card(name="Test")]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "Test"

    def test_table_output(self, tmp_path):
        cards = [_make_card(name="Test")]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
            ],
        )
        assert result.exit_code == 0
        assert "Test" in result.output
        assert "---" in result.output
