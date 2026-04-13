"""Tests for Scryfall card lookup."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from mtg_utils.scryfall_lookup import (
    _load_bulk_index,
    build_digest,
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

        with patch("mtg_utils.scryfall_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = lookup_single("Newly Printed Card", bulk_path=sample_bulk_data)

        assert result is not None
        assert result["name"] == "Newly Printed Card"

    def test_returns_none_when_not_found(self, sample_bulk_data):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("mtg_utils.scryfall_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = lookup_single("Totally Fake Card", bulk_path=sample_bulk_data)

        assert result is None


class TestLookupBatch:
    def test_looks_up_multiple_cards(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Sol Ring", "Blood Artist"]))

        results, cache_path, _ = lookup_cards(
            names_path, bulk_path=sample_bulk_data, cache_dir=tmp_path / "cache"
        )
        assert len(results) == 3
        result_names = {r["name"] for r in results}
        assert result_names == {"Viscera Seer", "Sol Ring", "Blood Artist"}
        assert cache_path.exists()
        assert cache_path.is_absolute()

    def test_caches_results(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Sol Ring"]))
        cache_dir = tmp_path / "cache"

        # First call — populates cache
        results1, path1, _ = lookup_cards(
            names_path, bulk_path=sample_bulk_data, cache_dir=cache_dir
        )
        assert len(results1) == 2

        # Second call with the SAME bulk_path reads from cache. (Cache key
        # now includes bulk_path by mtime+size, so swapping bulk files
        # correctly busts the cache — verified separately below.)
        results2, path2, _ = lookup_cards(
            names_path, bulk_path=sample_bulk_data, cache_dir=cache_dir
        )
        assert results2 == results1
        assert path2 == path1

    def test_cache_key_busted_by_bulk_data_change(self, sample_bulk_data, tmp_path):
        """A different bulk data file must land at a different cache path."""
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer"]))
        cache_dir = tmp_path / "cache"

        _, path1, _ = lookup_cards(
            names_path, bulk_path=sample_bulk_data, cache_dir=cache_dir
        )

        # Duplicate the bulk data to a new file with a different path
        alt_bulk = tmp_path / "alt-bulk.json"
        alt_bulk.write_bytes(sample_bulk_data.read_bytes())

        _, path2, _ = lookup_cards(names_path, bulk_path=alt_bulk, cache_dir=cache_dir)

        # Different bulk_path → different mtime → different cache key
        assert path1 != path2

    def test_corrupt_cache_is_recomputed(self, sample_bulk_data, tmp_path):
        """A truncated/corrupt cache file is unlinked and recomputed."""
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer"]))
        cache_dir = tmp_path / "cache"

        # First call populates the cache
        _, path1, _ = lookup_cards(
            names_path, bulk_path=sample_bulk_data, cache_dir=cache_dir
        )
        assert path1.exists()

        # Corrupt it
        path1.write_text("not valid json")

        # Second call notices, unlinks, recomputes
        results, path2, _ = lookup_cards(
            names_path, bulk_path=sample_bulk_data, cache_dir=cache_dir
        )
        assert results[0]["name"] == "Viscera Seer"
        assert path2 == path1
        # File is now valid JSON again
        json.loads(path2.read_text())

    def test_empty_cache_dir_falls_back_to_default(self, sample_bulk_data, tmp_path):
        """An empty-string cache_dir is treated as unset, not as CWD."""
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer"]))

        # Simulate an empty-string --cache-dir coming from a misconfigured
        # shell variable. Click would construct Path("") which is a real
        # footgun the scryfall_lookup guard handles.
        empty = Path("")  # noqa: PTH201 — intentional test of the guard
        _, path, _ = lookup_cards(
            names_path,
            bulk_path=sample_bulk_data,
            cache_dir=empty,
        )
        assert "scryfall-cache" in str(path)

    def test_includes_not_found_as_none(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Totally Fake Card"]))

        with patch("mtg_utils.scryfall_lookup.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            results, _, _ = lookup_cards(
                names_path, bulk_path=sample_bulk_data, cache_dir=tmp_path / "cache"
            )

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

        results, _, _ = lookup_cards(
            batch_path, bulk_path=sample_bulk_data, cache_dir=tmp_path / "cache"
        )
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

        results, _, _ = lookup_cards(
            batch_path, bulk_path=sample_bulk_data, cache_dir=tmp_path / "cache"
        )
        assert len(results) == 1

    def test_handles_empty_commanders(self, sample_bulk_data, tmp_path):
        deck_json = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        batch_path = tmp_path / "deck.json"
        batch_path.write_text(json.dumps(deck_json))

        results, _, _ = lookup_cards(
            batch_path, bulk_path=sample_bulk_data, cache_dir=tmp_path / "cache"
        )
        assert len(results) == 1
        assert results[0]["name"] == "Sol Ring"

    def test_still_accepts_name_list(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Sol Ring"]))

        results, _, _ = lookup_cards(
            names_path, bulk_path=sample_bulk_data, cache_dir=tmp_path / "cache"
        )
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
        assert index["dual card"]["rarity"] == "uncommon"
        assert index["dual card"]["exempt_from_4cap"] is False

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
        assert index["arena card"]["rarity"] == "common"
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
        assert index["special card"]["rarity"] == "rare"

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
        assert index["fire // ice"]["rarity"] == "uncommon"
        assert index["fire"]["rarity"] == "uncommon"

    def test_exempt_from_4cap_for_any_number_cards(self, tmp_path):
        """Cards with 'A deck can have any number of cards named X' oracle
        text are flagged ``exempt_from_4cap=True`` so price-check can
        suppress the Arena 4-cap substitution for them."""
        cards = [
            {
                "name": "Hare Apparent",
                "rarity": "common",
                "legalities": {"commander": "legal"},
                "oracle_text": (
                    "When Hare Apparent enters, create X 1/1 white Rabbit "
                    "creature tokens, where X is the number of other "
                    "creatures named Hare Apparent you control.\n"
                    "A deck can have any number of cards named Hare Apparent."
                ),
            },
            {
                "name": "Regular Rare",
                "rarity": "rare",
                "legalities": {"commander": "legal"},
                "oracle_text": "Draw a card.",
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = build_rarity_index(bulk_path, "commander")
        assert index["hare apparent"]["exempt_from_4cap"] is True
        assert index["regular rare"]["exempt_from_4cap"] is False

    def test_exempt_from_4cap_for_up_to_n_cards(self, tmp_path):
        """Cards with 'A deck can have up to N cards named X' oracle text
        are also flagged exempt — a deck can legitimately want 7 Seven
        Dwarves, so owning 4 is not infinite supply."""
        cards = [
            {
                "name": "Seven Dwarves",
                "rarity": "rare",
                "legalities": {"commander": "legal"},
                "oracle_text": (
                    "Seven Dwarves gets +1/+1 for each other creature "
                    "named Seven Dwarves you control.\n"
                    "A deck can have up to seven cards named Seven Dwarves."
                ),
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = build_rarity_index(bulk_path, "commander")
        assert index["seven dwarves"]["exempt_from_4cap"] is True

    def test_skips_draft_set_reprints_for_arena(self, tmp_path):
        """J21/JMP/AJMP reprints have draft-format rarities that don't match
        Arena wildcard cost.  A J21 common reprint should be excluded so the
        real printing's uncommon rarity wins."""
        cards = [
            {
                "name": "Lightning Bolt",
                "rarity": "common",
                "set": "j21",
                "reprint": True,
                "games": ["arena"],
                "legalities": {"brawl": "legal"},
            },
            {
                "name": "Lightning Bolt",
                "rarity": "uncommon",
                "set": "sta",
                "reprint": True,
                "games": ["arena", "paper", "mtgo"],
                "legalities": {"brawl": "legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = build_rarity_index(bulk_path, "brawl", arena_only=True)
        assert index["lightning bolt"]["rarity"] == "uncommon"


class TestBulkIndexCheapestPrinting:
    def test_prefers_cheapest_printing(self, tmp_path):
        cards = [
            {
                "name": "Steam Vents",
                "legalities": {"commander": "legal"},
                "prices": {"usd": "1300.00", "usd_foil": None},
            },
            {
                "name": "Steam Vents",
                "legalities": {"commander": "legal"},
                "prices": {"usd": "13.00", "usd_foil": "20.00"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = _load_bulk_index(bulk_path)
        assert float(index["steam vents"]["prices"]["usd"]) == 13.00

    def test_prefers_priced_over_null(self, tmp_path):
        cards = [
            {
                "name": "Sol Ring",
                "legalities": {"commander": "legal"},
                "prices": {"usd": None, "usd_foil": None},
            },
            {
                "name": "Sol Ring",
                "legalities": {"commander": "legal"},
                "prices": {"usd": "1.50", "usd_foil": "5.00"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = _load_bulk_index(bulk_path)
        assert float(index["sol ring"]["prices"]["usd"]) == 1.50

    def test_skips_tokens(self, tmp_path):
        cards = [
            {
                "name": "Soldier",
                "layout": "token",
                "legalities": {},
                "prices": {"usd": None},
            },
            {
                "name": "Real Card",
                "legalities": {"commander": "legal"},
                "prices": {"usd": "1.00"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = _load_bulk_index(bulk_path)
        assert "soldier" not in index
        assert "real card" in index

    def test_standalone_wins_front_face_key_over_split(self, tmp_path):
        """Looking up 'Bind' should return the standalone card, not 'Bind // Liberate'."""
        cards = [
            {
                "name": "Bind // Liberate",
                "legalities": {"commander": "legal"},
                "prices": {"usd": "0.50"},
            },
            {
                "name": "Bind",
                "legalities": {"commander": "legal"},
                "prices": {"usd": "1.00"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = _load_bulk_index(bulk_path)
        assert index["bind"]["name"] == "Bind"
        assert index["bind // liberate"]["name"] == "Bind // Liberate"

    def test_split_front_face_alias_when_no_standalone(self, tmp_path):
        """Looking up 'Fire' should return 'Fire // Ice' when no standalone 'Fire' exists."""
        cards = [
            {
                "name": "Fire // Ice",
                "legalities": {"commander": "legal"},
                "prices": {"usd": "0.25"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = _load_bulk_index(bulk_path)
        assert index["fire"]["name"] == "Fire // Ice"
        assert index["fire // ice"]["name"] == "Fire // Ice"


class TestCLI:
    def test_single_card_output(self, sample_bulk_data):
        runner = CliRunner()
        result = runner.invoke(
            main, ["Viscera Seer", "--bulk-data", str(sample_bulk_data)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "Viscera Seer"

    def test_batch_output_is_envelope(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Viscera Seer", "Sol Ring", "Command Tower"]))
        cache_dir = tmp_path / "cache"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--batch",
                str(names_path),
                "--bulk-data",
                str(sample_bulk_data),
                "--cache-dir",
                str(cache_dir),
            ],
        )
        assert result.exit_code == 0, result.output

        envelope = json.loads(result.output)
        assert set(envelope.keys()) == {"cache_path", "card_count", "missing", "digest"}
        assert envelope["card_count"] == 3
        assert envelope["missing"] == []
        assert "categories" in envelope["digest"]
        assert "avg_cmc_nonland" in envelope["digest"]
        assert "curve" in envelope["digest"]

        # The envelope should be small — no per-card data, just aggregates.
        assert "oracle_text" not in result.output
        assert len(result.output) < 1500  # ~400 bytes typical, 1500 is generous

        # The cache file at cache_path must exist and contain the full
        # hydrated card list with all 12 CARD_FIELDS per card.
        cache_path = Path(envelope["cache_path"])
        assert cache_path.exists()
        assert cache_path.is_absolute()
        cached = json.loads(cache_path.read_text())
        assert len(cached) == 3
        viscera = next(c for c in cached if c["name"] == "Viscera Seer")
        assert viscera["oracle_text"] == "Sacrifice a creature: Scry 1."
        assert viscera["mana_cost"] == "{B}"

    def test_batch_envelope_lists_missing_cards(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(
            json.dumps(["Viscera Seer", "Totally Fake Card", "Sol Ring"])
        )
        cache_dir = tmp_path / "cache"

        with patch("mtg_utils.scryfall_lookup.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    "--batch",
                    str(names_path),
                    "--bulk-data",
                    str(sample_bulk_data),
                    "--cache-dir",
                    str(cache_dir),
                ],
            )

        assert result.exit_code == 0, result.output
        envelope = json.loads(result.output)
        assert envelope["missing"] == ["Totally Fake Card"]
        assert envelope["card_count"] == 3  # total, including the missing one

    def test_batch_envelope_categorizes_deck(self, sample_bulk_data, tmp_path):
        names_path = tmp_path / "names.json"
        # Mix of creature, artifact, land, instant, sorcery, enchantment
        names_path.write_text(
            json.dumps(
                [
                    "Viscera Seer",  # creature
                    "Sol Ring",  # artifact
                    "Command Tower",  # land
                    "Deadly Rollick",  # instant
                    "Cultivate",  # sorcery
                    "Dictate of Erebos",  # enchantment
                ]
            )
        )
        cache_dir = tmp_path / "cache"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--batch",
                str(names_path),
                "--bulk-data",
                str(sample_bulk_data),
                "--cache-dir",
                str(cache_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        envelope = json.loads(result.output)
        cats = envelope["digest"]["categories"]
        assert cats["creatures"] >= 1
        assert cats["artifacts"] >= 1
        assert cats["lands"] >= 1
        assert cats["instants"] >= 1
        assert cats["sorceries"] >= 1
        assert cats["enchantments"] >= 1


class TestBuildDigest:
    def test_classifies_types(self):
        results = [
            {"name": "Forest", "type_line": "Basic Land — Forest", "cmc": 0},
            {
                "name": "Llanowar Elves",
                "type_line": "Creature — Elf Druid",
                "cmc": 1,
            },
            {"name": "Counterspell", "type_line": "Instant", "cmc": 2},
        ]
        digest = build_digest(results, ["Forest", "Llanowar Elves", "Counterspell"])
        assert digest["categories"]["lands"] == 1
        assert digest["categories"]["creatures"] == 1
        assert digest["categories"]["instants"] == 1
        assert digest["missing"] == []

    def test_missing_cards_populate_missing_list(self):
        results = [{"name": "Forest", "type_line": "Basic Land", "cmc": 0}, None]
        digest = build_digest(results, ["Forest", "Bogus"])
        assert digest["missing"] == ["Bogus"]
        assert digest["categories"]["lands"] == 1

    def test_avg_cmc_excludes_lands(self):
        results = [
            {"name": "Forest", "type_line": "Basic Land", "cmc": 0},
            {"name": "Creature", "type_line": "Creature", "cmc": 4},
            {"name": "Instant", "type_line": "Instant", "cmc": 2},
        ]
        digest = build_digest(results, ["Forest", "Creature", "Instant"])
        assert digest["avg_cmc_nonland"] == 3.0  # (4+2)/2

    def test_curve_bucketing(self):
        results = [
            {"name": "A", "type_line": "Creature", "cmc": 1},
            {"name": "B", "type_line": "Creature", "cmc": 1},
            {"name": "C", "type_line": "Creature", "cmc": 9},
        ]
        digest = build_digest(results, ["A", "B", "C"])
        assert digest["curve"]["1"] == 2
        assert digest["curve"]["7+"] == 1
