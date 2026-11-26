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
        # Drawn 26-14, not drawn 8-12, one win and one loss added to each.
        drawn, undrawn = 27 / 42, 9 / 22
        expected = (
            100 * (drawn * (1 - drawn) / 42 + undrawn * (1 - undrawn) / 22) ** 0.5
        )
        assert row["iwd_se"] == pytest.approx(expected, abs=0.01)

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
        # The error reads the counted not-drawn games: 22 of 45 won.
        assert row["iwd_se"] == pytest.approx(
            ls.iwd_standard_error(54, 37, 45, 22), abs=0.01
        )
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
                [
                    "--set",
                    "tst",
                    "--event",
                    "premier_draft",
                    "--premium-json",
                    str(premium_file),
                    "--json",
                ],
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
            ls.main,
            ["--set", "TST", "--event", "SEALED", "--premium-json", str(premium_file)],
        )
        assert result.exit_code == 0, result.output
        assert result.output.startswith("# TST SEALED")
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
            first = CliRunner().invoke(
                ls.main, ["--set", "tst", "--event", "PREMIER_DRAFT", "--json"]
            )
            second = CliRunner().invoke(
                ls.main, ["--set", "TST", "--event", "PREMIER_DRAFT", "--json"]
            )
        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        get.assert_called_once()
        args, kwargs = get.call_args
        assert args[0] == f"{ls.API_URL}/free"
        assert args[0].endswith("/card_stats_limited_by_set_v2/free")
        assert kwargs["params"] == {
            "CardSetFilter": "TST",
            "LimitedEventTypeFilter": "PREMIER_DRAFT",
            "LimitedEventTimeIntervalFilter": "LATEST_EVENT",
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

    def test_empty_204_names_the_query(self, cache):
        """A 204 says which query answered empty, so a moved path is spotted."""
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(None, status=204),
        ):
            result = CliRunner().invoke(
                ls.main, ["--set", "TST", "--event", "PREMIER_DRAFT"]
            )
        assert result.exit_code == 1
        assert "no Untapped data yet for TST/PREMIER_DRAFT" in result.output
        assert "HTTP 204" in result.output
        assert ls.API_URL in result.output
        assert not (cache / "card_stats_TST_PREMIER_DRAFT.json").exists()


# --- The pooled view ---------------------------------------------------------------


def _pair(colors, games, win_rate):
    return {"colors": colors, "games": games, "win_rate": win_rate}


def _card(title_id, gih, iwd, *, rarity="common", colors="W", card_set="TST", se=0.0):
    """A format's card row; ``se`` is its IWD's standard error (0: exact)."""
    return {
        "title_id": title_id,
        "name": f"Card {title_id}",
        "rarity": rarity,
        "colors": colors,
        "set": card_set,
        "gih": gih,
        "iwd": iwd,
        "iwd_se": se,
    }


def _report(pairs=(), cards=()):
    return {
        "summary": {"source": "free", "fetched_at": "t", "games": {"total": 9}},
        "color_pairs": {"two_color": list(pairs)},
        "cards": list(cards),
    }


class TestPairTiers:
    def test_each_format_against_its_own_average(self):
        # Sealed averages 60% (two pairs, equal games), draft 50%: the same
        # +5 in each pools to +5, whatever the raw rates.
        reports = {
            "SEALED": _report([_pair("WR", 10, 65.0), _pair("UB", 10, 55.0)]),
            "PREMIER_DRAFT": _report([_pair("WR", 30, 55.0), _pair("UB", 30, 45.0)]),
        }
        tiers = {
            e["colors"]: e for e in ls.pair_tiers(reports, tier_gap=5.0, confidence=0)
        }
        assert tiers["WR"]["vs_average"] == 5.0
        assert tiers["WR"]["tier"] == "top"
        assert tiers["UB"]["tier"] == "bottom"
        assert tiers["WR"]["games"] == 40
        assert tiers["WR"]["error"] == pytest.approx(50 / 40**0.5, abs=0.05)
        assert tiers["WR"]["events"]["SEALED"]["vs_average"] == 5.0

    def test_pooled_by_games_and_clash(self):
        # WR is +10 in Sealed (10 games) and -2 in draft (40): pooled
        # (10*10 + 40*-2) / 50 = +0.4, a middle pair whose formats clash.
        reports = {
            "SEALED": _report([_pair("WR", 10, 70.0), _pair("UB", 10, 50.0)]),
            "PREMIER_DRAFT": _report([_pair("WR", 40, 48.0), _pair("UB", 40, 52.0)]),
        }
        wr = next(e for e in ls.pair_tiers(reports, clash=10.0) if e["colors"] == "WR")
        assert wr["vs_average"] == pytest.approx(0.4)
        assert wr["tier"] == "middle"
        assert wr["clash"] is True

    def test_a_tier_needs_the_cautious_end(self):
        # 10,000 games: sigma 0.5, so 0.8 at 90%. WR at +7 clears the 5-point
        # gap at its cautious end (+6.2); UB at -7 likewise. With 400 games
        # (sigma 2.5, 4.1 at 90%) the same +7 only leans.
        def tiers(games):
            report = _report([_pair("WR", games, 57.0), _pair("UB", games, 43.0)])
            return {e["colors"]: e for e in ls.pair_tiers({"SEALED": report})}

        sure = tiers(10_000)
        assert (sure["WR"]["tier"], sure["WR"]["lean"]) == ("top", None)
        assert (sure["UB"]["tier"], sure["UB"]["lean"]) == ("bottom", None)
        assert sure["WR"]["plus_minus"] == pytest.approx(0.8, abs=0.05)
        thin = tiers(400)
        assert (thin["WR"]["tier"], thin["WR"]["lean"]) == ("middle", "top")
        assert (thin["UB"]["tier"], thin["UB"]["lean"]) == ("middle", "bottom")
        assert thin["WR"]["plus_minus"] == pytest.approx(4.1, abs=0.05)

    def test_a_middle_pair_leans_nowhere(self):
        report = _report([_pair("WR", 400, 52.0), _pair("UB", 400, 48.0)])
        assert [e["lean"] for e in ls.pair_tiers({"SEALED": report})] == [None, None]

    def test_text_names_a_leaning_pair(self):
        report = _report(
            [_pair("WR", 400, 57.0), _pair("UB", 400, 43.0)],
            [_card("a", 100, 5.0), _card("b", 100, 5.0)],
        )
        text = ls.render_pooled(ls.build_pooled({"SEALED": report}), "TST")
        pairs = text[text.index("## Colour pairs") :].split("\n\n")[0]
        assert "leaning top     WR    +7.0 (±4.1, 400 games)" in pairs
        assert "leaning bottom  UB    -7.0 (±4.1, 400 games)" in pairs
        plain = ls.render_pooled(
            ls.build_pooled({"SEALED": report}, confidence=0), "TST"
        )
        assert "  top     WR    +7.0 (±2.5, 400 games)" in plain
        assert "leaning" not in plain

    def test_one_format_alone(self):
        tiers = ls.pair_tiers({"SEALED": _report([_pair("WR", 10, 60.0)])})
        assert tiers[0]["vs_average"] == 0.0
        assert tiers[0]["clash"] is False


class TestPooledCards:
    def test_iwd_against_each_format_average(self):
        # Sealed's average card is +5 (cards 1 and 2 at 30+ drawn), draft's +0.
        reports = {
            "SEALED": _report(cards=[_card("1", 30, 15.0), _card("2", 30, -5.0)]),
            "PREMIER_DRAFT": _report(
                cards=[_card("1", 90, 10.0), _card("2", 90, -10.0)]
            ),
        }
        cards = {c["title_id"]: c for c in ls.pooled_cards(reports, min_games=30)}
        one = cards["1"]
        assert one["gih"] == 120
        # IWD (30*15 + 90*10) / 120; vs average (30*10 + 90*10) / 120.
        assert one["iwd"] == pytest.approx(11.2, abs=0.05)
        assert one["vs_average"] == 10.0
        assert one["events"]["SEALED"] == {
            "gih": 30,
            "iwd": 15.0,
            "vs_average": 10.0,
            "se": 0.0,
            "plus_minus": 0.0,
        }

    def test_card_without_iwd_skipped(self):
        reports = {"SEALED": _report(cards=[_card("1", 0, None), _card("2", 40, 5.0)])}
        assert [c["title_id"] for c in ls.pooled_cards(reports)] == ["2"]

    def test_error_pools_as_a_weighted_mean(self):
        # Sealed: 30 drawn, se 6; draft: 90 drawn, se 2. The pooled lift is
        # (30 x + 90 y) / 120, so its se is sqrt((30*6)^2 + (90*2)^2) / 120.
        reports = {
            "SEALED": _report(cards=[_card("1", 30, 15.0, se=6.0)]),
            "PREMIER_DRAFT": _report(cards=[_card("1", 90, 10.0, se=2.0)]),
        }
        card = ls.pooled_cards(reports, confidence=90)[0]
        se = (180**2 + 180**2) ** 0.5 / 120
        assert card["se"] == pytest.approx(se, abs=0.005)
        assert card["plus_minus"] == pytest.approx(1.645 * se, abs=0.05)
        assert card["events"]["SEALED"]["plus_minus"] == pytest.approx(9.9)


class TestStandardError:
    def test_hand_checkable_counts(self):
        # Drawn 59-39 -> (59+1)/(98+2) = 0.6; not drawn 199-199 -> 200/400 = 0.5.
        # 0.6*0.4/100 + 0.5*0.5/400 = 0.003025, whose root is 0.055.
        assert ls.iwd_standard_error(98, 59, 398, 199) == pytest.approx(5.5)

    def test_a_perfect_record_still_has_a_width(self):
        assert ls.iwd_standard_error(10, 10, 10, 0) > 0

    def test_no_games_on_either_side_has_no_error(self):
        assert ls.iwd_standard_error(0, 0, 50, 25) is None
        assert ls.iwd_standard_error(50, 25, 0, 0) is None

    @pytest.mark.parametrize(
        ("confidence", "z"), [(0, 0.0), (80, 1.2816), (90, 1.6449), (95, 1.9600)]
    )
    def test_z_score(self, confidence, z):
        assert ls.z_score(confidence) == pytest.approx(z, abs=1e-4)


class TestCautiousEnd:
    """A label needs the cautious end of the range past the margin."""

    def _reports(self):
        # Average card: 0 (the six 30+ cards' IWDs sum to 0). At 90%, se 2 is
        # ±3.3, se 4 ±6.6, se 6 ±9.9.
        cards = [
            _card("sure", 100, 15.0, rarity="rare", se=2.0),
            _card("maybe", 100, 15.0, rarity="rare", se=4.0),
            _card("sure-flop", 100, -15.0, se=2.0),
            _card("maybe-flop", 100, -15.0, se=4.0),
            _card("big-up", 100, 18.0, rarity="uncommon", se=6.0),
            _card("big-flop", 100, -18.0, se=6.0),
            # Under the 60-game floor (and the 30-game average): never a
            # label, never leaning, however narrow its range.
            _card("thin-big", 20, 40.0, se=1.0),
        ]
        return {"SEALED": _report([_pair("WR", 10, 50.0)], cards)}

    def _ids(self, pooled, key):
        return [c["title_id"] for c in pooled[key]]

    def test_only_the_cautious_end_labels(self):
        pooled = ls.build_pooled(self._reports(), margin=10.0, confidence=90)
        assert self._ids(pooled, "standouts") == ["sure"]
        assert self._ids(pooled, "data_bombs") == ["sure"]
        assert self._ids(pooled, "underperformers") == ["sure-flop"]
        # Leaning standouts first, then leaning underperformers, furthest first.
        assert [(c["title_id"], c["lean"]) for c in pooled["leaning"]] == [
            ("big-up", "standout"),
            ("maybe", "standout"),
            ("big-flop", "underperformer"),
            ("maybe-flop", "underperformer"),
        ]
        maybe = next(c for c in pooled["cards"] if c["title_id"] == "maybe")
        assert maybe["vs_average"] - maybe["plus_minus"] < 10.0 <= maybe["vs_average"]
        assert pooled["thresholds"]["confidence"] == 90
        assert pooled["thresholds"]["z"] == pytest.approx(1.645)

    def test_confidence_zero_is_the_point_estimate(self):
        pooled = ls.build_pooled(self._reports(), margin=10.0, confidence=0)
        assert self._ids(pooled, "standouts") == ["big-up", "sure", "maybe"]
        assert pooled["leaning"] == []

    def test_confidence_zero_text_is_the_point_estimates(self):
        text = ls.render_pooled(ls.build_pooled(self._reports(), confidence=0), "tst")
        assert "% range" not in text
        assert "±0.0" not in text
        assert "## Leaning" not in text
        assert "Card sure [rare W]  vs avg +15.0, 100 drawn  (SEALED +15.0 (100))" in (
            text
        )

    def test_under_the_floor_never_leans(self):
        pooled = ls.build_pooled(self._reports(), confidence=90)
        assert "thin-big" not in self._ids(pooled, "leaning")
        assert "thin-big" not in self._ids(pooled, "standouts")

    def test_leaning_rares_carry_the_reviewers_grade(self):
        reviews = ls.parse_reviews(
            "window.TST_DATA = "
            + json.dumps(
                {
                    "cards": [
                        {
                            "name": n,
                            "rarity": "Rare",
                            "consensus": {"mean": 93.0, "sourceCount": 6},
                        }
                        for n in ("Card maybe", "Card big-up")
                    ]
                }
            )
        )
        pooled = ls.build_pooled(self._reports(), confidence=90, reviews=reviews)
        leaning = {c["title_id"]: c for c in pooled["leaning"]}
        assert leaning["maybe"]["review_mean"] == 93.0
        assert leaning["maybe"]["review_sources"] == 6
        # Only a rare or mythic: the data can't call it, so the reviewers do.
        assert "review_mean" not in leaning["big-up"]
        text = ls.render_pooled(pooled, "tst")
        assert "reviewers 93.0 (6)" in text[text.index("## Leaning") :]

    def test_colour_depth_carries_the_mean_s_range(self):
        # Two white commons with se 3 and 4: the mean's se is sqrt(9 + 16) / 2
        # = 2.5, so ±4.1 at 90%. A colour with no commons carries no range.
        report = _report(
            cards=[
                _card("a", 100, 12.0, se=3.0),
                _card("b", 100, 8.0, se=4.0),
                _card("c", 100, 4.0, colors="U", rarity="rare"),
            ]
        )
        pooled = ls.build_pooled({"SEALED": report}, confidence=90)
        assert pooled["color_depth"]["W"]["plus_minus"] == pytest.approx(4.1, abs=0.05)
        assert "plus_minus" not in pooled["color_depth"]["U"]
        text = ls.render_pooled(pooled, "tst")
        depth = text[text.index("## Colour depth") :].split("\n\n")[0]
        assert "W +2.0 ±4.1 (2)" in depth
        plain = ls.render_pooled(ls.build_pooled({"SEALED": report}, confidence=0), "t")
        assert "W +2.0 (2)" in plain

    def test_text_shows_the_range_and_the_leaning_list(self):
        text = ls.render_pooled(ls.build_pooled(self._reports(), confidence=90), "tst")
        assert "A card's ± is a two-sided 90% range" in text
        assert "a one-sided 95% call" in text
        leaning = text[text.index("## Leaning") :].split("\n\n")[0]
        assert "*" + " " * 3 + "+15.0 ±6.6  standout?  Card maybe [rare W]" in leaning
        assert "underperformer?  Card maybe-flop" in leaning
        assert "Card sure " not in leaning
        assert leaning.index("leaning standouts") < leaning.index("Card big-up")
        assert leaning.index("Card maybe ") < leaning.index("leaning underperformers")
        assert leaning.index("leaning underperformers") < leaning.index("Card big-flop")
        standouts = text[text.index("## Standouts") :].split("\n\n")[0]
        assert "Card sure [rare W]  vs avg +15.0 ±3.3, 100 drawn" in standouts
        assert "SEALED +15.0 ±3.3 (100)" in standouts


class TestBuildPooled:
    def _reports(self):
        sealed = [
            _card("bomb", 40, 30.0, rarity="rare", colors="G"),
            _card("good", 40, 20.0),
            _card("flop", 40, -20.0, colors="B"),
            _card("avg", 40, 5.0),
            _card("thin", 20, 50.0, rarity="mythic"),
            _card("guest", 20, 50.0, rarity="rare", card_set="OLD"),
            _card("tiny", 3, 90.0, rarity="rare"),
            _card("swing", 25, -15.0, colors="W"),
        ]
        draft = [
            _card("bomb", 40, 30.0, rarity="rare", colors="G"),
            _card("good", 40, 20.0),
            _card("flop", 40, -20.0, colors="B"),
            _card("avg", 40, 5.0),
            _card("swing", 25, 25.0, colors="W"),
        ]
        return {
            "SEALED": _report([_pair("WR", 10, 60.0)], sealed),
            "PREMIER_DRAFT": _report([_pair("WR", 10, 50.0)], draft),
        }

    def test_selections(self):
        pooled = ls.build_pooled(self._reports(), pool_min_games=60, margin=10.0)
        names = {
            k: [c["title_id"] for c in pooled[k]]
            for k in pooled
            if k
            in {
                "standouts",
                "data_bombs",
                "underperformers",
                "thin_rares",
                "disagreements",
            }
        }
        # Average card: +8.75 in each format (bomb, good, flop, avg).
        assert names["standouts"] == ["bomb", "good"]
        assert names["data_bombs"] == ["bomb"]
        assert names["underperformers"] == ["flop"]
        # A special guest from another set is thin too; "tiny" is under the floor.
        assert names["thin_rares"] == ["thin", "guest"]
        assert names["disagreements"] == ["swing"]
        assert pooled["disagreements"][0]["gap"] == 40.0
        # W commons with 60+ drawn: good (+11.25) and avg (-3.75); swing has 50.
        assert pooled["color_depth"]["W"]["commons"] == 2
        assert pooled["color_depth"]["W"]["vs_average"] == pytest.approx(3.75, abs=0.06)
        assert pooled["color_depth"]["U"] == {"vs_average": None, "commons": 0}
        assert pooled["formats"]["SEALED"]["average_pair"] == 60.0
        assert pooled["formats"]["SEALED"]["average_iwd"] == 8.8
        assert pooled["thresholds"]["clash_floor"] == ls._CLASH_FLOOR

    def test_render_has_every_section(self):
        pooled = ls.build_pooled(self._reports(), missing={"X": "no data"})
        text = ls.render_pooled(pooled, "tst")
        for heading in (
            "# TST pooled — SEALED + PREMIER_DRAFT",
            "## Formats",
            "X: missing (no data)",
            "## Colour pairs",
            "## Colour depth at common",
            "## Standouts",
            "## Data bombs",
            "## Underperformers",
            "## Leaning",
            "## Thin rares",
            "## Formats disagree",
        ):
            assert heading in text


class TestPooledCli:
    def test_fetches_both_formats_sealed_first(self, cache):
        _seed_card_files(cache)
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(FREE_PAYLOAD),
        ) as get:
            result = CliRunner().invoke(ls.main, ["--set", "TST", "--json"])
        assert result.exit_code == 0, result.output
        events = [
            c.kwargs["params"]["LimitedEventTypeFilter"] for c in get.call_args_list
        ]
        assert events == ["SEALED", "PREMIER_DRAFT"]
        out = json.loads(result.output)
        assert list(out["events"]) == ["SEALED", "PREMIER_DRAFT"]
        assert out["pooled"]["missing"] == {}

    def test_confidence_option_reaches_the_json(self, cache):
        _seed_card_files(cache)
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(FREE_PAYLOAD),
        ):
            default, wide = (
                json.loads(
                    CliRunner()
                    .invoke(ls.main, ["--set", "TST", "--json", *extra])
                    .output
                )["pooled"]
                for extra in ([], ["--confidence", "95"])
            )
        assert default["thresholds"]["confidence"] == ls.DEFAULT_CONFIDENCE
        assert wide["thresholds"]["confidence"] == 95
        assert "leaning" in wide
        assert default["formats"]["SEALED"]["not_drawn"] == "derived"
        for pooled, z in ((default, 1.645), (wide, 1.96)):
            for card in pooled["cards"]:
                assert card["plus_minus"] == pytest.approx(z * card["se"], abs=0.06)
        assert any(c["plus_minus"] for c in wide["cards"])

    @pytest.mark.parametrize("value", ["100", "-5"])
    def test_confidence_out_of_range(self, value):
        result = CliRunner().invoke(ls.main, ["--set", "TST", "--confidence", value])
        assert result.exit_code == 2
        assert "--confidence" in result.output

    def test_text_puts_pooled_view_first(self, cache):
        _seed_card_files(cache)
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(FREE_PAYLOAD),
        ):
            result = CliRunner().invoke(ls.main, ["--set", "TST"])
        assert result.exit_code == 0, result.output
        assert result.output.startswith("# TST pooled")
        assert result.output.index("# TST SEALED") < result.output.index(
            "# TST PREMIER_DRAFT"
        )

    def test_premium_counts_its_not_drawn_games(self, cache, tmp_path):
        # A Premium-layout Sealed payload (explicit not_available_* counts) for a
        # fictional card, the free payload for draft.
        premium = {
            "data": {
                "100": {
                    "ALL": {
                        "d": [
                            [100, 60, 100, [100], 0, [0]],
                            [50, 35, 45, 32, 40, 20],
                            [10, 7, 0, 0, 0, 0],
                        ]
                    }
                }
            },
            "metadata": {"fields": ls.DEFAULT_FIELDS, "games": {}},
        }
        path = tmp_path / "premium-sealed.json"
        path.write_text(json.dumps(premium))
        _seed_card_files(cache)
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(FREE_PAYLOAD),
        ):
            runs = [
                CliRunner().invoke(
                    ls.main, ["--set", "TST", "--premium-sealed", str(path), *extra]
                )
                for extra in (["--json"], [])
            ]
        assert all(r.exit_code == 0 for r in runs), runs[0].output
        pooled = json.loads(runs[0].output)["pooled"]
        assert pooled["formats"]["SEALED"]["not_drawn"] == "counted"
        assert pooled["formats"]["PREMIER_DRAFT"]["not_drawn"] == "derived"
        sealed = next(c for c in pooled["cards"] if c["title_id"] == "100")
        assert sealed["events"]["SEALED"]["se"] == pytest.approx(
            ls.iwd_standard_error(50, 35, 40, 20), abs=0.01
        )
        formats = runs[1].output.split("## Formats")[1].split("\n\n")[0]
        sealed_line, draft_line = formats.strip().split("\n")
        assert "not drawn =" not in sealed_line
        assert "not drawn = games - drawn" in draft_line

    def test_one_format_missing_still_pools(self, cache, premium_file):
        _seed_card_files(cache)
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(None, status=204),
        ):
            result = CliRunner().invoke(
                ls.main,
                ["--set", "TST", "--premium-draft", str(premium_file), "--json"],
            )
        assert result.exit_code == 0, result.output
        pooled = json.loads(result.output)["pooled"]
        assert pooled["events"] == ["PREMIER_DRAFT"]
        assert "no Untapped data yet for TST/SEALED" in pooled["missing"]["SEALED"]

    def test_both_missing_fails(self, cache):
        with patch(
            "mtg_utils.limited_stats.requests.get",
            return_value=_response(None, status=204),
        ):
            result = CliRunner().invoke(ls.main, ["--set", "TST"])
        assert result.exit_code == 1
        assert "TST/SEALED" in result.output
        assert "TST/PREMIER_DRAFT" in result.output

    @pytest.mark.parametrize(
        "args",
        [
            ["--premium-json", "{f}"],
            ["--event", "SEALED", "--premium-sealed", "{f}"],
        ],
    )
    def test_premium_flags_match_the_mode(self, premium_file, args):
        args = [a.format(f=premium_file) for a in args]
        result = CliRunner().invoke(ls.main, ["--set", "TST", *args])
        assert result.exit_code == 2
        assert "--premium" in result.output


# --- Reviewer consensus (chunk.science) ----------------------------------------------

# The set data script's shape, with fictional cards: a window assignment of one
# JSON object whose ``cards`` each carry ``consensus.mean`` / ``sourceCount``.
_REVIEWED = [
    {
        "name": "Card thin",
        "rarity": "Mythic",
        "consensus": {"mean": 93.5, "sourceCount": 7},
    },
    {
        "name": "Card guest",
        "rarity": "Rare",
        "consensus": {"mean": 71.0, "sourceCount": 8},
    },
    {
        "name": "Card bomb",
        "rarity": "Rare",
        "consensus": {"mean": 96.0, "sourceCount": 8},
    },
    {
        "name": "Undrawn Testwing // Its Other Face",
        "rarity": "Rare",
        "consensus": {"mean": 90.0, "sourceCount": 5},
    },
    {
        "name": "Card good",
        "rarity": "Common",
        "consensus": {"mean": 99.0, "sourceCount": 8},
    },
    {"name": "Ungraded Card", "rarity": "Rare", "consensus": {}},
]
REVIEWS_SCRIPT = (
    "window.TST_DATA = "
    + json.dumps({"set": {"code": "TST"}, "cards": _REVIEWED})
    + ";\n"
)

REVIEWS_PAGE = (
    '<script src="/mtga-test/data/tst_17lands.682e70c31ce1.js"></script>'
    '<script src="/mtga-test/data/tst.0ef434212333.js"></script>'
)


class TestReviews:
    def test_parse_reads_each_graded_card_by_its_names(self):
        reviews = ls.parse_reviews(REVIEWS_SCRIPT)
        assert reviews["cardthin"] == {
            "name": "Card thin",
            "rarity": "mythic",
            "mean": 93.5,
            "sources": 7,
        }
        # a double-faced card answers to its whole name and its front face
        assert reviews["undrawntestwing"] is reviews["undrawntestwingitsotherface"]
        assert "ungradedcard" not in reviews
        with pytest.raises(ValueError, match="not a chunk"):
            ls.parse_reviews("<html>not a script</html>")

    def test_a_name_the_two_sites_punctuate_differently_still_matches(self):
        """Arena writes an ellipsis spaced out and with other accents than the
        reviewers' page does; a miss here would list a well-drawn card as a
        bomb nobody has data for."""
        script = "window.TST_DATA = " + json.dumps(
            {
                "cards": [
                    {
                        "name": "All Good Tests...",
                        "rarity": "Rare",
                        "consensus": {"mean": 95.0, "sourceCount": 4},
                    }
                ]
            }
        )
        reviews = ls.parse_reviews(script)
        drawn = {"name": "All Good Tests . . .", "gih": 7000, "iwd": 4.0}
        assert ls._review_of(drawn, reviews)["mean"] == 95.0
        assert ls.reviewer_bombs([drawn], reviews, 60) == []

    def test_thin_rares_carry_the_grade_and_the_bombs_are_listed(self):
        reports = TestBuildPooled()._reports()
        plain = ls.build_pooled(reports, pool_min_games=60)
        assert "reviewer_bombs" not in plain
        assert all("review_mean" not in c for c in plain["thin_rares"])

        pooled = ls.build_pooled(
            reports, pool_min_games=60, reviews=ls.parse_reviews(REVIEWS_SCRIPT)
        )
        thin = {c["title_id"]: c for c in pooled["thin_rares"]}
        assert (thin["thin"]["review_mean"], thin["thin"]["review_sources"]) == (
            93.5,
            7,
        )
        assert thin["guest"]["review_mean"] == 71.0
        # A reviewer bomb: a rare or mythic the data is too thin for, graded 90
        # or better. "Card bomb" has 80 drawn (the data's to call), "Card guest"
        # is graded 71, "Card good" is a common, and the card nobody drew counts.
        bombs = pooled["reviewer_bombs"]
        assert [(b["name"], b["review_mean"], b["gih"]) for b in bombs] == [
            ("Card thin", 93.5, 20),
            ("Undrawn Testwing // Its Other Face", 90.0, 0),
        ]
        text = ls.render_pooled(pooled, "tst")
        assert "## Reviewer bombs" in text
        assert "reviewers 93.5 (7)" in text
        assert "5 reviewers  (no stats under this name)" in text
        assert "## Reviewer bombs" not in ls.render_pooled(plain, "tst")

    def test_fetch_finds_the_data_script_and_caches_it(self, cache):
        page = MagicMock(status_code=200, text=REVIEWS_PAGE)
        page.url = "https://chunk.science/mtga-test.html"
        # the bytes are read as UTF-8 whatever charset the server claims
        script = MagicMock(status_code=200, text="read as Latin-1")
        script.content = REVIEWS_SCRIPT.encode()
        with patch.object(ls.requests, "get", side_effect=[page, script]) as get:
            reviews, _fetched = ls.fetch_reviews("tst")
            assert get.call_args_list[0].args[0] == "https://chunk.science/TST"
            assert get.call_args_list[1].args[0] == (
                "https://chunk.science/mtga-test/data/tst.0ef434212333.js"
            )
            # the second read is the cache's
            again, _fetched = ls.fetch_reviews("TST")
            assert get.call_count == 2
        assert reviews == again
        assert (cache.parent / "reviews" / "TST.js").read_text() == REVIEWS_SCRIPT

    def test_fetch_says_when_the_page_has_no_data_script(self, cache):
        page = MagicMock(status_code=200, text="<html></html>")
        page.url = "https://chunk.science/mtga-test.html"
        with (
            patch.object(ls.requests, "get", return_value=page),
            pytest.raises(click.ClickException, match="loads no data/tst"),
        ):
            ls.fetch_reviews("TST")

    def test_fetch_says_when_the_data_script_fails(self, cache):
        page = MagicMock(status_code=200, text=REVIEWS_PAGE)
        page.url = "https://chunk.science/mtga-test.html"
        with (
            patch.object(
                ls.requests, "get", side_effect=[page, MagicMock(status_code=503)]
            ),
            pytest.raises(click.ClickException, match="HTTP 503"),
        ):
            ls.fetch_reviews("TST")
        assert not (cache.parent / "reviews" / "TST.js").exists()

    def test_cli_reviews_are_the_pooled_views(self, cache, tmp_path):
        saved = tmp_path / "tst.js"
        saved.write_text(REVIEWS_SCRIPT)
        res = CliRunner().invoke(
            ls.main, ["--set", "TST", "--event", "SEALED", "--reviews-json", str(saved)]
        )
        assert res.exit_code != 0
        assert "pooled view" in res.output


def test_cached_stat_names_reads_the_cache_alone(cache):
    """The cards a set's cached stats list, by name with their home set: what
    ``guide-card-hovers`` adds the bonus sheet's guests from. Nothing fetched,
    and nothing at all before ``limited-stats`` has run for the set."""
    with patch.object(ls.requests, "get", side_effect=AssertionError("no network")):
        assert ls.cached_stat_names("TST") == {}
        _seed_card_files(cache)
        assert ls.cached_stat_names("TST") == {}  # no stats payload yet
        (cache / "card_stats_TST_SEALED.json").write_text(json.dumps(FREE_PAYLOAD))
        names = ls.cached_stat_names("tst")
    assert names["Visiting Relic"] == "GST"  # the guest keeps its home set
    assert names["Glimmerwing Test Angel"] == "TST"
    assert "Unrelated Card" not in names
