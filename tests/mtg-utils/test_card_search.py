"""Tests for card_search module."""

import json

import click
import pytest
from click.testing import CliRunner

from mtg_utils.card_classify import color_identity_subset
from mtg_utils.card_search import (
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
    games=None,
    rarity="uncommon",
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
        "games": games if games is not None else ["arena", "paper"],
        "rarity": rarity,
    }


class TestColorIdentitySubset:
    def test_empty_is_subset_of_any(self):
        assert color_identity_subset([], {"B", "R"})

    def test_mono_is_subset_of_pair(self):
        assert color_identity_subset(["B"], {"B", "R"})

    def test_exact_match(self):
        assert color_identity_subset(["B", "R"], {"B", "R"})

    def test_superset_rejected(self):
        assert not color_identity_subset(["B", "R", "G"], {"B", "R"})


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

    def test_deduplicates_keeps_cheapest(self, tmp_path):
        cards = [
            _make_card(name="Sol Ring", price_usd="5.00"),
            _make_card(name="Sol Ring", price_usd="1.00"),
            _make_card(name="Sol Ring", price_usd="3.00"),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path)
        assert len(results) == 1
        assert _extract_price(results[0]) == 1.0

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

    def test_invalid_regex_raises_bad_parameter(self, tmp_path):
        cards = [_make_card()]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        with pytest.raises(click.BadParameter, match="Invalid oracle regex"):
            search_cards(bulk_path, oracle="[invalid")

    def test_sort_name_defaults_ascending(self, tmp_path):
        cards = [
            _make_card(name="Zebra"),
            _make_card(name="Alpha"),
            _make_card(name="Middle"),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, sort="name")
        assert results[0]["name"] == "Alpha"
        assert results[-1]["name"] == "Zebra"


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


class TestFormatLegalityFilter:
    def test_format_filters_by_legality(self, tmp_path):
        cards = [
            _make_card(
                name="Standard Legal",
                legalities={"commander": "legal", "standardbrawl": "legal"},
            ),
            _make_card(
                name="Commander Only",
                legalities={"commander": "legal", "standardbrawl": "not_legal"},
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, format="brawl")
        names = [c["name"] for c in results]
        assert "Standard Legal" in names
        assert "Commander Only" not in names

    def test_no_format_keeps_commander_default(self, tmp_path):
        cards = [
            _make_card(
                name="Commander Legal",
                legalities={"commander": "legal", "standardbrawl": "not_legal"},
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path)
        assert len(results) == 1

    def test_historic_brawl_format(self, tmp_path):
        cards = [
            _make_card(
                name="Historic Card",
                legalities={"commander": "legal", "brawl": "legal"},
            ),
            _make_card(
                name="Not In Brawl",
                legalities={"commander": "legal", "brawl": "not_legal"},
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, format="historic_brawl")
        names = [c["name"] for c in results]
        assert "Historic Card" in names
        assert "Not In Brawl" not in names

    def test_cli_format_flag(self, tmp_path):
        cards = [
            _make_card(
                name="Brawl Legal",
                legalities={"commander": "legal", "standardbrawl": "legal"},
            ),
            _make_card(
                name="Not Brawl Legal",
                legalities={"commander": "legal", "standardbrawl": "not_legal"},
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--bulk-data", str(bulk_path), "--format", "brawl", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [c["name"] for c in data]
        assert "Brawl Legal" in names
        assert "Not Brawl Legal" not in names


class TestArenaFormatImpliesArenaOnly:
    """Brawl and Historic Brawl are Arena-native formats.

    Without the implication, `search_cards(format="historic_brawl")` would
    happily return paper-only printings, and the dedup-by-cheapest-printing
    step would pick the paper rarity — misreporting a Historic Anthology
    rare as a Modern Horizons common.
    """

    def test_brawl_filters_out_paper_only_printings(self, tmp_path):
        cards = [
            _make_card(
                name="Paper Only",
                legalities={"standardbrawl": "legal"},
                games=["paper"],
            ),
            _make_card(
                name="Arena Legal",
                legalities={"standardbrawl": "legal"},
                games=["arena", "paper"],
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        names = [c["name"] for c in search_cards(bulk_path, format="brawl")]
        assert "Arena Legal" in names
        assert "Paper Only" not in names

    def test_historic_brawl_filters_out_paper_only_printings(self, tmp_path):
        cards = [
            _make_card(
                name="Paper Only",
                legalities={"brawl": "legal"},
                games=["paper"],
            ),
            _make_card(
                name="Arena Legal",
                legalities={"brawl": "legal"},
                games=["arena"],
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        names = [c["name"] for c in search_cards(bulk_path, format="historic_brawl")]
        assert "Arena Legal" in names
        assert "Paper Only" not in names

    def test_paper_only_flag_overrides_format_implication(self, tmp_path):
        cards = [
            _make_card(
                name="Paper Only",
                legalities={"brawl": "legal"},
                games=["paper"],
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        names = [
            c["name"]
            for c in search_cards(bulk_path, format="historic_brawl", paper_only=True)
        ]
        assert "Paper Only" in names

    def test_commander_format_does_not_imply_arena_only(self, tmp_path):
        cards = [
            _make_card(
                name="Paper Only",
                legalities={"commander": "legal"},
                games=["paper"],
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        names = [c["name"] for c in search_cards(bulk_path, format="commander")]
        assert "Paper Only" in names

    def test_dedup_prefers_arena_printing_for_historic_brawl(self, tmp_path):
        """Same card, two printings: paper common vs Arena rare.

        Before the fix, dedup picked the cheapest printing regardless of
        platform, so the rarity column reported "common" even though Arena
        players can only get the rare printing. Now the Arena-implied
        filter runs before dedup, so the Arena printing wins.
        """
        cards = [
            _make_card(
                name="Ephemerate",
                price_usd="0.25",
                rarity="common",
                legalities={"brawl": "legal"},
                games=["paper"],
            ),
            _make_card(
                name="Ephemerate",
                price_usd="3.00",
                rarity="rare",
                legalities={"brawl": "legal"},
                games=["arena"],
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, format="historic_brawl")
        assert len(results) == 1
        assert results[0]["rarity"] == "rare"


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


class TestIsCommanderFilter:
    def test_filters_to_commander_eligible(self, tmp_path):
        cards = [
            _make_card(
                name="Atraxa",
                type_line="Legendary Creature — Phyrexian Angel",
            ),
            _make_card(
                name="Lightning Bolt",
                type_line="Instant",
            ),
            _make_card(
                name="Goblin Guide",
                type_line="Creature — Goblin Scout",
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, is_commander_filter=True)
        names = [c["name"] for c in results]
        assert "Atraxa" in names
        assert "Lightning Bolt" not in names
        assert "Goblin Guide" not in names

    def test_brawl_includes_planeswalkers(self, tmp_path):
        cards = [
            _make_card(
                name="Teferi",
                type_line="Legendary Planeswalker — Teferi",
                legalities={"commander": "legal", "standardbrawl": "legal"},
            ),
            _make_card(
                name="Atraxa",
                type_line="Legendary Creature — Phyrexian Angel",
                legalities={"commander": "legal", "standardbrawl": "legal"},
            ),
            _make_card(
                name="Sol Ring",
                type_line="Artifact",
                legalities={"commander": "legal", "standardbrawl": "legal"},
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        results = search_cards(bulk_path, format="brawl", is_commander_filter=True)
        names = [c["name"] for c in results]
        assert "Teferi" in names
        assert "Atraxa" in names
        assert "Sol Ring" not in names

    def test_cli_is_commander_flag(self, tmp_path):
        cards = [
            _make_card(
                name="Atraxa",
                type_line="Legendary Creature — Phyrexian Angel",
            ),
            _make_card(
                name="Sol Ring",
                type_line="Artifact",
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--bulk-data", str(bulk_path), "--is-commander", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [c["name"] for c in data]
        assert "Atraxa" in names
        assert "Sol Ring" not in names

    def test_cli_is_commander_with_brawl_format(self, tmp_path):
        cards = [
            _make_card(
                name="Teferi",
                type_line="Legendary Planeswalker — Teferi",
                legalities={"commander": "legal", "standardbrawl": "legal"},
            ),
            _make_card(
                name="Sol Ring",
                type_line="Artifact",
                legalities={"commander": "legal", "standardbrawl": "legal"},
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--is-commander",
                "--format",
                "brawl",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [c["name"] for c in data]
        assert "Teferi" in names
        assert "Sol Ring" not in names

    def test_json_fields_projection(self, tmp_path):
        cards = [
            _make_card(
                name="Projected Card",
                oracle_text="A big oracle text block that takes up lots of bytes.",
                type_line="Creature",
                cmc=3.0,
                color_identity=["B"],
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--json",
                "--fields",
                "name,type_line,cmc,color_identity",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data) == 1
        card = data[0]
        # Only the requested fields survive projection
        assert set(card.keys()) == {"name", "type_line", "cmc", "color_identity"}
        assert card["name"] == "Projected Card"
        # oracle_text must be absent
        assert "oracle_text" not in card

    def test_json_without_fields_returns_full_dict(self, tmp_path):
        cards = [_make_card(name="Full Card")]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--bulk-data", str(bulk_path), "--json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        # Default full CARD_FIELDS projection includes oracle_text
        assert "oracle_text" in data[0]
        assert "type_line" in data[0]
        assert "color_identity" in data[0]


class TestPresetFilter:
    """--preset <name> restricts results to cards matching a theme_presets entry."""

    def _bulk(self, tmp_path):
        cards = [
            _make_card(
                name="Serra Angel",
                type_line="Creature — Angel",
                oracle_text="Flying, vigilance",
                price_usd="1.00",
            ),
            _make_card(
                name="Lightning Bolt",
                type_line="Instant",
                oracle_text="Lightning Bolt deals 3 damage to any target.",
                price_usd="0.50",
            ),
            _make_card(
                name="Goldvein Hydra",
                type_line="Creature — Hydra",
                oracle_text="Vigilance, trample, haste",
                price_usd="2.00",
            ),
            _make_card(
                name="Giant Spider",
                type_line="Creature — Spider",
                oracle_text="Reach",
                price_usd="0.25",
            ),
        ]
        # Attach keywords arrays so the preset's keyword matcher fires.
        cards[0]["keywords"] = ["Flying", "Vigilance"]
        cards[1]["keywords"] = []
        cards[2]["keywords"] = ["Vigilance", "Trample", "Haste"]
        cards[3]["keywords"] = ["Reach"]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        return bulk_path

    def test_single_preset_filters(self, tmp_path):
        bulk_path = self._bulk(tmp_path)
        results = search_cards(bulk_path, preset_names=("flying",))
        names = {c["name"] for c in results}
        assert names == {"Serra Angel"}

    def test_multiple_presets_combine_with_and(self, tmp_path):
        bulk_path = self._bulk(tmp_path)
        # Only Goldvein Hydra has both vigilance AND haste.
        results = search_cards(bulk_path, preset_names=("vigilance", "haste"))
        names = {c["name"] for c in results}
        assert names == {"Goldvein Hydra"}

    def test_unknown_preset_rejected(self, tmp_path):
        bulk_path = self._bulk(tmp_path)
        with pytest.raises(click.BadParameter, match="unknown preset"):
            search_cards(bulk_path, preset_names=("not-a-real-preset",))

    def test_cli_preset_flag(self, tmp_path):
        bulk_path = self._bulk(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--preset",
                "flying",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        names = [c["name"] for c in data]
        assert names == ["Serra Angel"]
