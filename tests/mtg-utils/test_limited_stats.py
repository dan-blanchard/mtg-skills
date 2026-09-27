"""Tests for limited-stats (Untapped.gg limited card stats).

Synthetic payloads with fictional card names: this is machinery over
Untapped's payload shape, not real-card behaviour (ADR-0056).
"""

import json
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from mtg_utils import limited_stats as ls

FREE_FIELDS = [
    [
        "games",
        "wins",
        "in_main_games",
        "in_main_games_dist",
        "in_side_games",
        "in_side_games_dist",
    ],
    ["available_games", "available_wins"],
    ["in_opening_hands", "in_opening_hand_wins"],
]

# The free tier's shape: short rows (trailing values dropped), no diamond /
# mythic buckets, no not_available_* fields.
FREE_PAYLOAD = {
    "data": {
        "100": {
            "ALL": {"b": [[40, 24], [30, 20], [5, 3]], "s": [[20, 10], [10, 6]]},
            "3": {"b": [[10, 7]], "s": [[10, 5]]},
            "1": {"b": [[4, 1]]},
        },
        "200": {"ALL": {"p": [[50, 35], [40, 32], [10, 8]]}, "24": {"p": [[30, 15]]}},
        "300": {"ALL": {"b": [[15, 10], [12, 9]]}, "24": {"b": [[10, 6]]}},
        "400": {"ALL": {"b": [[30, 12], [20, 6]]}, "7": {"b": [[10, 4]]}},
        "500": {"ALL": {"b": [[60, 50], [50, 45]]}},
        "600": {"ALL": {"b": [[60, 30], [40, 20]]}},
        "700": {"ALL": {"g": [[40, 22], [35, 21]]}},
        "800": {"ALL": {"s": [[40, 22], [32, 18]]}, "3": {"b": [[20, 12]]}},
        "900": {"ALL": {"b": [[8, 8], [5, 5]]}},
    },
    "metadata": {
        "games": {
            "3": {"bronze": 10, "silver": 5},
            "24": {"platinum": 8},
            "7": {"bronze": 2},
            "1": {"bronze": 1},
            "ALL": {"bronze": 30, "silver": 12, "platinum": 20},
        },
        "fields": FREE_FIELDS,
    },
}

# mtgajson shapes: cards.json records and loc_en.json entries.
CARDS = [
    {"grpid": 1, "titleId": 100, "set": "TST", "rarity": 2, "colors": [1]},
    {"grpid": 2, "titleId": 200, "set": "TST", "rarity": 5, "colors": [4]},
    {"grpid": 3, "titleId": 300, "set": "TST", "rarity": 4, "colors": [5]},
    {"grpid": 4, "titleId": 400, "set": "TST", "rarity": 4, "colors": [2]},
    {"grpid": 5, "titleId": 500, "set": "TST", "rarity": 3, "colors": [4]},
    {"grpid": 6, "titleId": 600, "set": "TST", "rarity": 3, "colors": [3]},
    # A reprint seen first in another set, then in this one: the TST printing wins.
    {"grpid": 7, "titleId": 700, "set": "OLD", "rarity": 4, "colors": [3]},
    {"grpid": 8, "titleId": 700, "set": "TST", "rarity": 2, "colors": [3]},
    {"grpid": 9, "titleId": 800, "set": "TST", "rarity": 2, "colors": [2, 1]},
    # A special guest with no printing in this set keeps its own set.
    {"grpid": 10, "titleId": 900, "set": "GST", "rarity": 4, "colors": []},
]
LOC = [
    {"id": 100, "text": "Glimmerwing Test Angel"},
    {"id": 200, "text": "Fictional Bomb Dragon"},
    {"id": 300, "text": "Tiny Sample Wurm"},
    {"id": 400, "text": "Overhyped Sphinx"},
    {"id": 500, "text": "Standout Goblin"},
    {"id": 600, "text": "Mediocre Shade"},
    {"id": 700, "text": "Returning Guest Rat"},
    {"id": 800, "text": "Hybrid Test Sprite"},
    {"id": 900, "text": "Visiting Relic"},
    {"id": 999, "text": "Unrelated Card"},
]


@pytest.fixture
def index():
    return ls.build_card_index(CARDS, LOC, "TST", set(FREE_PAYLOAD["data"]))


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    return tmp_path / "untapped"


@pytest.fixture
def premium_file(tmp_path):
    """A saved stats payload for ``--premium-json`` (the free shape serves)."""
    path = tmp_path / "premium.json"
    path.write_text(json.dumps(FREE_PAYLOAD))
    return path


def _seed_card_files(cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "cards.json").write_text(json.dumps(CARDS))
    (cache_dir / "loc_en.json").write_text(json.dumps(LOC))


def _response(body, status=200):
    resp = MagicMock()
    resp.status_code = status
    text = "" if body is None else json.dumps(body)
    resp.text = text
    resp.content = text.encode()
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


def _row(rows, name):
    return next(r for r in rows if r["name"] == name)


class TestDecodeArchetype:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("1", "W"),
            ("2", "U"),
            ("3", "WU"),
            ("5", "WB"),
            ("6", "UB"),
            ("9", "WR"),
            ("10", "UR"),
            ("12", "BR"),
            ("17", "WG"),
            ("18", "UG"),
            ("20", "BG"),
            ("24", "RG"),
            ("7", "WUB"),
            ("31", "WUBRG"),
            ("0", "C"),
            ("ALL", "ALL"),
        ],
    )
    def test_bitmask(self, key, expected):
        assert ls.decode_archetype(key) == expected


class TestCardIndex:
    def test_join_names_rarity_colors(self, index):
        assert index["100"] == {
            "name": "Glimmerwing Test Angel",
            "rarity": "common",
            "colors": "W",
            "set": "TST",
        }
        # Colours come out in WUBRG order whatever order the record lists them.
        assert index["800"]["colors"] == "WU"

    def test_prefers_printing_in_set(self, index):
        assert index["700"]["set"] == "TST"
        assert index["700"]["rarity"] == "common"

    def test_guest_keeps_its_own_set(self, index):
        assert index["900"]["set"] == "GST"
        assert index["900"]["colors"] == ""

    def test_restricted_to_title_ids(self):
        index = ls.build_card_index(CARDS, LOC, "TST", {"100", "999"})
        assert set(index) == {"100", "999"}
        assert index["999"]["rarity"] == "unknown"

    def test_split_card_name_uses_two_slashes(self):
        loc = [{"id": 1, "text": "Fictional /// Testcard"}]
        index = ls.build_card_index([], loc, "TST", {"1"})
        assert index["1"]["name"] == "Fictional // Testcard"


class TestCardRows:
    def test_gih_gns_iwd_from_truncated_rows(self, index):
        row = _row(ls.card_rows(FREE_PAYLOAD, index), "Glimmerwing Test Angel")
        # games 40+20, wins 24+10; GIH 30+10 won 20+6; the silver row has no
        # opening-hand section at all.
        assert row["gp"] == 60
        assert row["gp_wr"] == pytest.approx(56.7)
        assert row["gih"] == 40
        assert row["gih_wr"] == 65.0
        # Free tier: not drawn = 60 - 40 games, 34 - 26 wins.
        assert row["gns"] == 20
        assert row["gns_wr"] == 40.0
        assert row["iwd"] == 25.0
        assert row["oh"] == 5
        assert row["oh_wr"] == 60.0

    def test_missing_title_id_gets_placeholder_name(self):
        rows = ls.card_rows(FREE_PAYLOAD, {})
        assert _row(rows, "titleId 100")["rarity"] == "unknown"

    def test_premium_uses_explicit_not_available_counts(self, index):
        payload = {
            "data": {
                "100": {
                    "ALL": {
                        "d": [
                            [100, 60, 100, [100], 0, [0]],
                            [50, 35, 45, 32, 40, 20],
                            [10, 7, 0, 0, 0, 0],
                        ],
                        "m": [[10, 5], [4, 2, 4, 2, 5, 2]],
                    }
                }
            },
            "metadata": {"fields": ls.DEFAULT_FIELDS, "games": {}},
        }
        row = ls.card_rows(payload, index)[0]
        assert row["gih"] == 54
        assert row["gns"] == 45  # explicit 40 + 5, not derived 110 - 54
        assert row["gns_wr"] == pytest.approx(48.9)
        assert ls.payload_source(payload) == "premium"
        assert ls.payload_source(FREE_PAYLOAD) == "file"


class TestColorPairs:
    def test_card_weighted_rates(self):
        pairs = ls.color_pair_rates(FREE_PAYLOAD)
        two = pairs["two_color"]
        # WU: (7 + 5 + 12) / (10 + 10 + 20); RG: (15 + 6) / (30 + 10).
        assert [(e["colors"], e["win_rate"]) for e in two] == [
            ("WU", 60.0),
            ("RG", 52.5),
        ]
        assert two[0]["games"] == 15  # metadata games summed over ranks
        assert two[0]["card_games"] == 40
        assert [e["colors"] for e in pairs["multicolor"]] == ["WUB"]
        assert pairs["mono"] == [
            {"key": "1", "colors": "W", "games": 1, "card_games": 4, "win_rate": 25.0}
        ]

    def test_games_by_rank(self):
        assert ls.games_by_rank(FREE_PAYLOAD) == {
            "bronze": 30,
            "silver": 12,
            "platinum": 20,
            "total": 62,
        }


class TestSelections:
    def test_best_commons(self, index):
        rows = ls.card_rows(FREE_PAYLOAD, index)
        commons = ls.best_commons(rows, min_games=30)
        assert [r["name"] for r in commons["W"]] == ["Glimmerwing Test Angel"]
        assert [r["name"] for r in commons["B"]] == ["Returning Guest Rat"]
        assert [r["name"] for r in commons["multicolor"]] == ["Hybrid Test Sprite"]
        # The floor drops a common under it.
        assert ls.best_commons(rows, min_games=36)["B"] == []

    def test_bombs_threshold_and_small_samples(self, index):
        rows = ls.card_rows(FREE_PAYLOAD, index)
        bombs = ls.bomb_candidates(rows, min_games=30)
        by_name = {b["name"]: b for b in bombs}
        # Standout Goblin (uncommon, 90%) beats the rare median; Mediocre Shade
        # (uncommon, 50%) doesn't; Visiting Relic has under 10 GIH.
        assert [b["name"] for b in bombs] == [
            "Standout Goblin",
            "Fictional Bomb Dragon",
            "Tiny Sample Wurm",
            "Overhyped Sphinx",
        ]
        assert by_name["Standout Goblin"]["standout_uncommon"] is True
        assert by_name["Fictional Bomb Dragon"]["sample"] == "ok"
        assert by_name["Tiny Sample Wurm"]["sample"] == "small"
        assert ls._gih(by_name["Tiny Sample Wurm"]) == "[75.0%]"
        assert ls._gih(by_name["Fictional Bomb Dragon"]) == "80.0%"

    def test_underperformers(self, index):
        rows = ls.card_rows(FREE_PAYLOAD, index)
        assert [r["name"] for r in ls.underperformers(rows)] == ["Overhyped Sphinx"]


class TestCli:
    def test_premium_json_file(self, premium_file, cache):
        _seed_card_files(cache)
        with (
            patch("mtg_utils.limited_stats.requests.get") as get,
            patch("requests.Session.get") as session_get,
        ):
            result = CliRunner().invoke(
                ls.main,
                ["--set", "tst", "--premium-json", str(premium_file), "--json"],
            )
        assert result.exit_code == 0, result.output
        get.assert_not_called()
        session_get.assert_not_called()  # the seeded mtgajson files are fresh
        report = json.loads(result.output)
        assert report["summary"]["set"] == "TST"
        assert report["summary"]["source"] == "file"
        assert report["color_pairs"]["method"] == "card-weighted"
        assert report["bomb_candidates"][0]["name"] == "Standout Goblin"

    def test_human_output_sections(self, premium_file, cache):
        _seed_card_files(cache)
        result = CliRunner().invoke(
            ls.main, ["--set", "TST", "--premium-json", str(premium_file)]
        )
        assert result.exit_code == 0, result.output
        for heading in (
            "## Summary",
            "## Colour pairs",
            "## Best commons",
            "## Bomb candidates",
            "## Underperformers",
        ):
            assert heading in result.output
        assert "[75.0%]" in result.output
        assert "Visiting Relic" not in result.output

    def test_free_fetch_and_cache_reuse(self, cache):
        _seed_card_files(cache)
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(FREE_PAYLOAD),
        ) as get:
            first = CliRunner().invoke(ls.main, ["--set", "tst", "--json"])
            second = CliRunner().invoke(ls.main, ["--set", "TST", "--json"])
        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        get.assert_called_once()
        args, kwargs = get.call_args
        assert args[0] == f"{ls.API_URL}/free"
        assert kwargs["params"] == {
            "CardSetFilter": "TST",
            "LimitedEventTypeFilter": "PREMIER_DRAFT",
        }
        assert kwargs["headers"]["User-Agent"].startswith("Mozilla/")
        assert json.loads(first.output)["summary"]["source"] == "free"
        assert (cache / "card_stats_TST_PREMIER_DRAFT.json").exists()

    def test_mtgajson_files_cached(self, cache):
        responses = {ls.CARDS_URL: _response(CARDS), ls.LOC_URL: _response(LOC)}
        with patch(
            "requests.Session.get", side_effect=lambda url, **_: responses[url]
        ) as get:
            first = ls.fetch_card_index("TST", {"100"})
            second = ls.fetch_card_index("TST", {"100"})
        assert first == second
        assert first["100"]["name"] == "Glimmerwing Test Angel"
        assert get.call_count == 2  # cards + loc once each

    def test_unsupported_event_surfaces_server_message(self, cache):
        message = "Unsupported filter LimitedEventTypeFilter=TRADITIONAL_DRAFT"
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(message, status=400),
        ):
            result = CliRunner().invoke(
                ls.main, ["--set", "TST", "--event", "TRADITIONAL_DRAFT"]
            )
        assert result.exit_code == 1
        assert message in result.output
        assert "SEALED" in result.output

    @pytest.mark.parametrize(
        ("body", "status"), [(None, 204), ({"data": {}, "metadata": {}}, 200)]
    )
    def test_empty_data(self, cache, body, status):
        with (
            patch(
                "mtg_utils.limited_stats.requests.get",
                return_value=_response(body, status=status),
            ),
            pytest.raises(click.ClickException, match="no Untapped data yet"),
        ):
            ls.fetch_card_stats("tst", "sealed")
        assert not (cache / "card_stats_TST_SEALED.json").exists()
