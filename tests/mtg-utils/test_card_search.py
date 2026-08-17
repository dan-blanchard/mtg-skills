"""Tests for card_search module."""

import json
from datetime import UTC, datetime, timedelta

import click
import pytest
from click.testing import CliRunner

from mtg_utils.card_classify import color_identity_subset, is_commander
from mtg_utils.card_search import (
    _extract_price,
    _matches_filters,
    format_results,
    main,
    search_cards,
    unreleased_oracle_ids,
)
from mtg_utils.testkit import test_card


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

    def test_name_substr_matches_case_insensitive(self):
        card = _make_card(name="Llanowar Elves")
        assert _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            name_substr="llanowar",
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
        )

    def test_name_substr_rejects_non_match(self):
        card = _make_card(name="Llanowar Elves")
        assert not _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            name_substr="goblin",
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
        )

    def test_name_substr_matches_across_split_card_separator(self):
        # Players type "odds ends" for the split card "Odds // Ends" — the " // "
        # face separator must not block a multi-word substring (issue: find misses).
        card = _make_card(name="Odds // Ends")
        assert _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            name_substr="odds ends",
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
        )

    def test_name_substr_matches_single_face_of_split_card(self):
        # A single face still matches (regression guard for the normalization).
        card = _make_card(name="Fire // Ice")
        assert _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=None,
            name_substr="ice",
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


class TestTypeTokenFilter:
    """The type filter matches whole type-line TOKENS, never substrings of
    another type (CR 205.3 — each subtype is its own word). The substring
    behavior served Pirates on a 'rat' filter ("pi[rat]e"), every Sorcery on
    'orc' ("s[orc]ery"), and every Mountain on 'mount' (the Bloomburrow Mount
    type) — user-reported via the deck-forge Rat tribal lane."""

    def _matches_type(self, card, type_lower):
        return _matches_filters(
            card,
            allowed_colors=None,
            oracle_re=None,
            type_lower=type_lower,
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
        )

    def test_subtype_token_matches_its_tribe(self):
        assert self._matches_type(test_card("Marrow-Gnawer"), "rat")  # Rat Rogue

    @pytest.mark.parametrize(
        ("name", "wanted"),
        [
            ("Daring Saboteur", "rat"),  # Creature — Human Pirate
            ("Angrath, the Flame-Chained", "rat"),  # Planeswalker — Angrath
            ("Divination", "orc"),  # Sorcery
            ("Mountain", "mount"),  # Basic Land — Mountain (Mount is a real type)
            ("Invasion of Gobakhan // Lightshield Array", "bat"),  # Battle — Siege
        ],
    )
    def test_subtype_never_matches_as_substring_of_another_type(self, name, wanted):
        # The snapshot scanner traces the `name` parametrize column into the
        # test_card(name) call below, so each row's card joins the snapshot.
        assert not self._matches_type(test_card(name), wanted)

    def test_multiword_type_phrase_still_matches(self):
        assert self._matches_type(test_card("Mountain"), "basic land")

    def test_or_tuple_matches_any_token(self):
        ox = test_card("Bulwark Ox")  # Creature — Ox Mount
        assert self._matches_type(ox, ("fox", "mount"))
        assert not self._matches_type(ox, ("fox", "goat"))

    def test_rejects_reversible_card_layout(self):
        # Secret Lair "reversible" novelty reprints (e.g. Krark, the Thumbless //
        # Krark, the Thumbless) are legally single-faced cosmetic dupes with a null
        # top-level cmc/type_line; the canonical printing always exists, so skip them.
        card = _make_card(layout="reversible_card")
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

    def _color_match(self, card_ci, allowed, *, exact):
        return _matches_filters(
            _make_card(color_identity=card_ci),
            allowed_colors=allowed,
            oracle_re=None,
            type_lower=None,
            cmc_min=None,
            cmc_max=None,
            price_min=None,
            price_max=None,
            exact_colors=exact,
        )

    def test_exact_colors_requires_equality(self):
        # exact WU matches only a WU card — not mono-W, not WUB.
        assert self._color_match(["W", "U"], {"W", "U"}, exact=True)
        assert not self._color_match(["W"], {"W", "U"}, exact=True)
        assert not self._color_match(["W", "U", "B"], {"W", "U"}, exact=True)
        # subset still includes the mono and colorless cards.
        assert self._color_match(["W"], {"W", "U"}, exact=False)
        assert self._color_match([], {"W", "U"}, exact=False)

    def test_colorless_pip_subset_only_matches_colorless(self):
        # Selecting only the C pip (subset) → colorless cards only.
        assert self._color_match([], {"C"}, exact=False)
        assert not self._color_match(["G"], {"C"}, exact=False)

    def test_exact_colorless_matches_empty_identity(self):
        assert self._color_match([], {"C"}, exact=True)
        assert not self._color_match(["U"], {"C"}, exact=True)

    def test_colorless_included_in_colored_subset(self):
        # WU + C (subset) includes colorless and the WU spread.
        assert self._color_match([], {"W", "U", "C"}, exact=False)
        assert self._color_match(["W"], {"W", "U", "C"}, exact=False)

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

    def test_offset_paginates_contiguously(self, tmp_path):
        # distinct prices -> deterministic price-desc order
        cards = [
            _make_card(name=f"Card {i}", price_usd=f"{10 - i}.00") for i in range(10)
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))

        full = search_cards(bulk_path, limit=100, sort="price-desc")
        page1 = search_cards(bulk_path, limit=3, offset=0, sort="price-desc")
        page2 = search_cards(bulk_path, limit=3, offset=3, sort="price-desc")
        assert [c["name"] for c in page1] == [c["name"] for c in full[:3]]
        assert [c["name"] for c in page2] == [c["name"] for c in full[3:6]]
        # offset past the end yields nothing
        assert search_cards(bulk_path, limit=3, offset=100) == []

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


class TestPresetSeedsSignalIndex:
    """A ``--preset`` with a non-empty ``signal_keys`` arm seeds the persisted
    whole-pool signals index (task #90) before the pool scan runs; a preset
    that only reads ``keywords``/``patterns`` never triggers a build it has
    no use for."""

    def _bulk(self, tmp_path):
        cards = [_make_card(name="Serra Angel", oracle_text="Flying")]
        cards[0]["keywords"] = ["Flying"]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        return bulk_path

    def test_seeds_when_a_structural_preset_is_requested(self, tmp_path, monkeypatch):
        bulk_path = self._bulk(tmp_path)
        calls = []
        monkeypatch.setattr(
            "mtg_utils.theme_presets.seed_signal_key_index",
            lambda path: calls.append(path) or True,
        )
        # "landfall" carries signal_keys=("landfall",) — a structural view.
        search_cards(bulk_path, preset_names=("landfall",))
        assert calls == [bulk_path]

    def test_skips_seeding_for_keyword_only_preset(self, tmp_path, monkeypatch):
        bulk_path = self._bulk(tmp_path)
        calls = []
        monkeypatch.setattr(
            "mtg_utils.theme_presets.seed_signal_key_index",
            lambda path: calls.append(path) or True,
        )
        # "flying" is keywords-only (no signal_keys) — nothing to seed for it.
        search_cards(bulk_path, preset_names=("flying",))
        assert calls == []


# The blanket not_legal a pre-release card carries is provisional data, not a verdict —
# these pin the line between "isn't out yet" and "will never be legal".
_ALL_ILLEGAL = {"commander": "not_legal", "legacy": "not_legal", "vintage": "not_legal"}
_LEGAL = {"commander": "legal", "legacy": "legal", "vintage": "legal"}


# Release dates are RELATIVE to the run date so these fixtures cannot expire.
# They previously hardcoded 2026-08-14 as "the future". Once that day passed, every
# test routing through search_cards() / is_commander() broke: those read the real
# clock rather than an injected ``today``, so the card was no longer unreleased and
# the "spoiled but not out yet" path stopped being exercised at all. The classes
# that DO inject ``today=`` were unaffected — hence a half-failing suite.
_TODAY = datetime.now(tz=UTC).date()  # matches card_search's own clock
_TODAY_ISO = _TODAY.isoformat()
_FUTURE = (_TODAY + timedelta(days=30)).isoformat()  # a pending set
_FAR_FUTURE = (_TODAY + timedelta(days=120)).isoformat()  # a later pending set


def _rec(name, oracle_id, released_at, legalities, **kw):
    """A bulk record carrying the two fields the release test reads."""
    card = _make_card(name=name, legalities=legalities, **kw)
    card["oracle_id"] = oracle_id
    card["released_at"] = released_at
    return card


class TestUnreleasedOracleIds:
    TODAY = _TODAY_ISO

    def _ids(self, cards):
        return unreleased_oracle_ids(cards, today=self.TODAY)

    def test_future_only_printing_is_unreleased(self):
        cards = [_rec("Belladonna Took", "oid-new", _FUTURE, _ALL_ILLEGAL)]
        assert self._ids(cards) == {"oid-new"}

    def test_past_printing_is_not_unreleased(self):
        # An Un-card: illegal everywhere, but it came out years ago.
        cards = [_rec("Standard Procedure", "oid-un", "2022-10-07", _ALL_ILLEGAL)]
        assert self._ids(cards) == set()

    def test_legal_card_never_qualifies(self):
        cards = [_rec("Sol Ring", "oid-legal", _FUTURE, _LEGAL)]
        assert self._ids(cards) == set()

    def test_banned_card_never_qualifies(self):
        # Banned is a real status, so the card is not "legal nowhere" in this sense.
        legalities = {**_ALL_ILLEGAL, "vintage": "banned"}
        cards = [_rec("Chaos Orb", "oid-ban", _FUTURE, legalities)]
        assert self._ids(cards) == set()

    def test_one_released_printing_disqualifies_the_oracle_card(self):
        # THE reason this is oracle-level and uses min(): an always-illegal card
        # reprinted into a future set must not read as merely-unreleased.
        cards = [
            _rec("Un Thing", "oid-mixed", "2022-10-07", _ALL_ILLEGAL),
            _rec("Un Thing", "oid-mixed", _FAR_FUTURE, _ALL_ILLEGAL),
        ]
        assert self._ids(cards) == set()

    def test_empty_legalities_is_not_evidence(self):
        # all() over an empty dict is vacuously True — guard against that reading as
        # "illegal everywhere" for a record that simply carries no legality data.
        cards = [_rec("No Data", "oid-empty", _FUTURE, {})]
        assert self._ids(cards) == set()

    def test_missing_release_date_is_not_unreleased(self):
        cards = [_rec("Undated", "oid-nodate", None, _ALL_ILLEGAL)]
        assert self._ids(cards) == set()

    def test_release_day_itself_counts_as_released(self):
        cards = [_rec("Out Today", "oid-today", self.TODAY, _ALL_ILLEGAL)]
        assert self._ids(cards) == set()


class TestIncludeUnreleasedSearch:
    def _bulk(self, tmp_path):
        cards = [
            _rec("Belladonna Took", "oid-new", _FUTURE, _ALL_ILLEGAL),
            _rec("Standard Procedure", "oid-un", "2022-10-07", _ALL_ILLEGAL),
            _rec("Sol Ring", "oid-legal", "2015-01-01", _LEGAL),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        return bulk_path

    def _names(self, bulk_path, **kw):
        return {c["name"] for c in search_cards(bulk_path, limit=100, **kw)}

    def test_default_hides_unreleased(self, tmp_path):
        assert self._names(self._bulk(tmp_path)) == {"Sol Ring"}

    def test_flag_admits_unreleased_only(self, tmp_path):
        # The Un-card stays out — the flag widens for release date, nothing else.
        assert self._names(self._bulk(tmp_path), include_unreleased=True) == {
            "Sol Ring",
            "Belladonna Took",
        }

    def test_pool_cache_does_not_leak_between_modes(self, tmp_path):
        # _POOL_CACHE is keyed on include_unreleased; without that, whichever mode ran
        # first would win for both. Assert in BOTH orders against one bulk file.
        bulk_path = self._bulk(tmp_path)
        assert "Belladonna Took" not in self._names(bulk_path)
        assert "Belladonna Took" in self._names(bulk_path, include_unreleased=True)
        assert "Belladonna Took" not in self._names(bulk_path)

    def test_cli_flag_round_trips(self, tmp_path):
        bulk_path = self._bulk(tmp_path)
        runner = CliRunner()
        args = ["--bulk-data", str(bulk_path), "--name", "Belladonna"]
        assert "No results found." in runner.invoke(main, args).output
        out = runner.invoke(main, [*args, "--include-unreleased"]).output
        assert "Belladonna Took" in out


class TestNeverLegalSetTypeGuard:
    """`funny` sets are illegal by design, so a future release date must not read as
    "merely pending" — the one case the date test alone gets wrong."""

    TODAY = _TODAY_ISO

    def _ids(self, cards):
        return unreleased_oracle_ids(cards, today=self.TODAY)

    def test_future_funny_set_is_not_unreleased(self):
        # A spoiled-but-unreleased Un-set: passes every date/legality check, and is
        # still never going to be legal. This is what the guard exists for.
        cards = [
            _rec(
                "Silly Card",
                "oid-funny",
                _FAR_FUTURE,
                _ALL_ILLEGAL,
                set_type="funny",
            )
        ]
        assert self._ids(cards) == set()

    def test_normal_future_set_still_qualifies(self):
        # The guard must not over-reach: an ordinary expansion is unaffected.
        cards = [
            _rec(
                "Belladonna Took",
                "oid-new",
                _FUTURE,
                _ALL_ILLEGAL,
                set_type="expansion",
            )
        ]
        assert self._ids(cards) == {"oid-new"}

    def test_any_funny_printing_disqualifies_the_oracle_card(self):
        # Checked per PRINTING: a funny printing anywhere in the card's history is
        # enough, even when the other printing is an ordinary future expansion.
        cards = [
            _rec("Two Faced", "oid-mixed", _FAR_FUTURE, _ALL_ILLEGAL, set_type="funny"),
            _rec(
                "Two Faced",
                "oid-mixed",
                _FUTURE,
                _ALL_ILLEGAL,
                set_type="expansion",
            ),
        ]
        assert self._ids(cards) == set()

    def test_funny_cards_stay_out_of_search_results(self, tmp_path):
        cards = [
            _rec(
                "Silly Card", "oid-funny", _FAR_FUTURE, _ALL_ILLEGAL, set_type="funny"
            ),
            _rec("Belladonna Took", "oid-new", _FUTURE, _ALL_ILLEGAL),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        found = {
            c["name"]
            for c in search_cards(bulk_path, limit=100, include_unreleased=True)
        }
        assert found == {"Belladonna Took"}


class TestUnreleasedCommanderEligibility:
    """A pre-release legend must be nominatable as a commander, or "findable but
    un-buildable" makes pre-release brewing pointless. The bypass is scoped to cards
    proven merely-unreleased — never to Un-cards or banned ones."""

    LEGEND = {
        "type_line": "Legendary Creature — Dwarf Noble",
        "oracle_text": "Whenever Thorin enters, create a Treasure token.",
    }

    def test_is_commander_gates_on_legality_by_default(self):
        card = _rec("Thorin", "oid-pre", _FUTURE, _ALL_ILLEGAL, **self.LEGEND)
        assert is_commander(card, "commander")["eligible"] is False

    def test_ignore_legality_admits_the_pre_release_legend(self):
        card = _rec("Thorin", "oid-pre", _FUTURE, _ALL_ILLEGAL, **self.LEGEND)
        assert is_commander(card, "commander", ignore_legality=True)["eligible"] is True

    def test_ignore_legality_still_requires_a_legendary_type_line(self):
        # The bypass drops the legality gate ONLY — type-line rules still apply.
        card = _rec(
            "Sol Ring",
            "oid-pre",
            _FUTURE,
            _ALL_ILLEGAL,
            type_line="Artifact",
            oracle_text="{T}: Add {C}{C}.",
        )
        assert (
            is_commander(card, "commander", ignore_legality=True)["eligible"] is False
        )

    def _bulk(self, tmp_path):
        cards = [
            _rec("Thorin", "oid-pre", _FUTURE, _ALL_ILLEGAL, **self.LEGEND),
            # An Un-card legend: illegal by design, already released.
            _rec(
                "Urza Headmaster",
                "oid-un",
                "2018-12-07",
                _ALL_ILLEGAL,
                set_type="funny",
                **self.LEGEND,
            ),
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        return bulk_path

    def test_commanders_only_plus_unreleased_finds_the_legend(self, tmp_path):
        found = search_cards(
            self._bulk(tmp_path),
            limit=100,
            is_commander_filter=True,
            include_unreleased=True,
        )
        assert [c["name"] for c in found] == ["Thorin"]

    def test_commanders_only_alone_still_excludes_it(self, tmp_path):
        found = search_cards(self._bulk(tmp_path), limit=100, is_commander_filter=True)
        assert found == []
