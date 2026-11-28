"""Untapped's per-card results per commander: the pure reads, the cached fetch and
the ``arena-meta`` section. Synthetic names and counts (machinery only)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from test_arena_meta import _brawl_raw

from mtg_utils import arena_meta
from mtg_utils._arena_meta import card_stats as cs
from mtg_utils._arena_meta import untapped

FIELDS = [
    ["games", "wins", "in_main_games"],
    [
        "available_games",
        "available_wins",
        "played_games",
        "played_wins",
        "not_available_games",
        "not_available_wins",
    ],
    ["in_opening_hands", "in_opening_hand_wins"],
]


def _rows(deck, hand, played, unseen, opening=(0, 0)):
    return [[*deck, deck[0]], [*hand, *played, *unseen], list(opening)]


def _bundle():
    """Spell One is good in hand, Spell Two bad, Spell Three too thin to say."""
    return {
        "event": "Brawl_Ladder",
        "period": 787,
        "partition": 2,
        "scope": cs.SCOPE,
        "fields": FIELDS,
        "games": {
            "gold": {"ALL": 500},
            "platinum": {"ALL": 3000},
            "mythic": {"ALL": 0},
        },
        "names": {"11": "Spell One", "12": "Spell Two", "13": "Spell Three"},
        "data": {
            "11": {
                "ALL": {
                    "g": _rows((500, 250), (100, 90), (80, 75), (400, 160)),
                    "p": _rows((2000, 1100), (400, 260), (300, 200), (1600, 840)),
                    # a short row: Untapped drops trailing zeros
                    "m": [[1000, 560, 1000], [200, 130]],
                }
            },
            "12": {
                "ALL": {"p": _rows((2000, 1000), (500, 200), (400, 150), (1500, 800))}
            },
            "13": {"ALL": {"p": _rows((40, 20), (10, 5), (8, 4), (30, 15))}},
            "99": {"ALL": {"p": _rows((40, 20), (10, 5), (8, 4), (30, 15))}},
        },
    }


def test_card_results_sum_the_asked_ranks_and_pad_short_rows():
    results = cs.card_results(_bundle())  # platinum and up
    one = results["Spell One"]
    assert (one.deck.matches, one.deck.wins) == (3000, 1660)
    assert (one.in_hand.matches, one.in_hand.wins) == (600, 390)
    # mythic's short row has no not-in-hand counts: they read as zero
    assert (one.not_in_hand.matches, one.not_in_hand.wins) == (1600, 840)
    assert "99" not in results  # a titleId with no name is dropped
    every = cs.card_results(_bundle(), ranks=("gold", "platinum", "mythic"))
    assert every["Spell One"].in_hand.matches == 700


def test_lift_is_in_hand_minus_not_in_hand_with_its_error():
    one = cs.card_results(_bundle())["Spell One"]
    assert one.lift == pytest.approx(390 / 600 - 840 / 1600)
    seen, unseen = 390 / 600, 840 / 1600
    assert one.lift_se == pytest.approx(
        (seen * (1 - seen) / 600 + unseen * (1 - unseen) / 1600) ** 0.5
    )
    assert cs.CardResult("Nothing").lift is None
    assert cs.CardResult("Nothing").lift_se is None


def test_partition_games_sums_the_asked_ranks():
    assert cs.partition_games(_bundle()) == 3000
    assert cs.partition_games(_bundle(), ranks=("gold",)) == 500


def test_the_deck_section_is_relative_to_the_average_card():
    section = cs.deck_card_results(
        _bundle(),
        ["Island", "Spell Two", "Spell One", "Spell Three", "Spell Nine"],
        skip=["Island"],
    )
    assert [r["name"] for r in section["cards"]] == [
        "Spell One",
        "Spell Three",
        "Spell Two",
    ]
    assert section["missing"] == ["Spell Nine"]
    results = cs.card_results(_bundle())
    weights = {n: r.in_hand.matches for n, r in results.items()}
    average = sum(weights[n] * results[n].lift for n in weights) / sum(weights.values())
    assert section["average_lift"] == pytest.approx(average, abs=1e-4)
    by_name = {r["name"]: r for r in section["cards"]}
    assert by_name["Spell One"]["relative"] == pytest.approx(
        results["Spell One"].lift - average, abs=1e-4
    )
    assert by_name["Spell Three"]["thin"]
    assert not by_name["Spell One"]["thin"]


class _FakeSession:
    """Stands in for the signed-in browser session: counts its requests."""

    calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def get(self, path, **_params):
        type(self).calls.append(path)
        if path == "meta-periods/active":
            return [{"id": 787, "event_name": "Brawl_Ladder", "start_ts": "2026-11-10"}]
        bundle = _bundle()
        return {
            "data": bundle["data"],
            "metadata": {
                "fields": FIELDS,
                "games": bundle["games"],
                "games_by_partition_and_rank": {"2": {"platinum": 3000}},
            },
        }


@pytest.fixture
def fake_untapped(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(untapped, "_Session", _FakeSession)
    monkeypatch.setattr(cs, "_names", lambda _data, _pool: dict(_bundle()["names"]))
    _FakeSession.calls = []
    return _FakeSession


def test_load_fetches_once_and_then_reads_the_cache(fake_untapped):
    first = cs.load_card_stats("Brawl_Ladder", [cs.EVERY_COMMANDER, 2])
    assert set(first) == {cs.EVERY_COMMANDER, 2}
    assert first[2]["period"] == 787
    assert first[2]["names"]["11"] == "Spell One"
    # only the every-commander bundle keeps the per-commander game counts
    assert first[cs.EVERY_COMMANDER]["games_by_partition"] == {"2": {"platinum": 3000}}
    assert "games_by_partition" not in first[2]
    fetched = len(fake_untapped.calls)
    again = cs.load_card_stats("Brawl_Ladder", [2], period_id=787)
    assert again[2]["data"] == first[2]["data"]
    assert len(fake_untapped.calls) == fetched  # the cache answered


def test_load_refuses_an_answer_with_no_card_data(fake_untapped, monkeypatch):
    monkeypatch.setattr(fake_untapped, "get", lambda _self, _path, **_p: {})
    with pytest.raises(untapped.MetaError, match="no card results"):
        cs.load_card_stats("Brawl_Ladder", [2], period_id=787)


def test_cli_prints_the_decks_card_results(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(_brawl_raw()))
    results = tmp_path / "results.json"
    results.write_text(json.dumps(_bundle()))
    deck = tmp_path / "deck.json"
    deck.write_text(
        json.dumps(
            {
                "format": "competitive_brawl",
                "commanders": [{"name": "Commander Beta", "quantity": 1}],
                "cards": [
                    {"name": "Spell One", "quantity": 1},
                    {"name": "Spell Two", "quantity": 1},
                ],
            }
        )
    )
    args = ["--deck", str(deck), "--from-json", str(raw)]
    result = CliRunner().invoke(
        arena_meta.main, [*args, "--card-results-json", str(results)]
    )
    assert result.exit_code == 0, result.output
    assert (
        "## Card results under Mono-Blue / Commander Beta (3000 games" in result.output
    )
    assert result.output.index("Spell One") < result.output.rindex("Spell Two")
    assert "no results: Commander Beta" in result.output
    # a saved meta bundle with no saved card results never fetches them
    offline = CliRunner().invoke(arena_meta.main, [*args, "--json"])
    assert offline.exit_code == 0, offline.output
    assert json.loads(offline.output)["card_results"] is None
