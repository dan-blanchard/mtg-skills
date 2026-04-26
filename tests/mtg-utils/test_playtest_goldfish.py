"""Smoke test: playtest-goldfish CLI is registered and prints --help."""

import json
import random

import pytest
from click.testing import CliRunner

from mtg_utils.playtest import (
    _aggregate_goldfish,
    _build_indexed_deck,
    _keep_hand,
    _simulate_game,
    goldfish_main,
)


def test_goldfish_help():
    runner = CliRunner()
    result = runner.invoke(goldfish_main, ["--help"])
    assert result.exit_code == 0
    assert "simulator" in result.output.lower()


def _h(land=0, one=0, two=0, three=0, four=0, five_plus=0):
    """Build a synthetic hand: list of dicts with cmc and type_line.

    Lands carry a Land type_line so :func:`mtg_utils.card_classify.is_land`
    classifies them correctly; nonlands use a Creature type_line.
    """
    hand = []
    for _ in range(land):
        hand.append({"cmc": 0, "type_line": "Basic Land — Mountain"})
    for cmc, n in [(1, one), (2, two), (3, three), (4, four), (5, five_plus)]:
        for _ in range(n):
            hand.append({"cmc": cmc, "type_line": "Creature — Goblin"})
    return hand


class TestKeepHand:
    def test_keeps_2_lands_with_early_plays(self):
        hand = _h(land=2, one=2, two=2, three=1)
        assert _keep_hand(hand) is True

    def test_mulligans_zero_lands(self):
        hand = _h(land=0, one=3, two=3, three=1)
        assert _keep_hand(hand) is False

    def test_mulligans_six_lands(self):
        hand = _h(land=6, one=1)
        assert _keep_hand(hand) is False

    def test_mulligans_no_early_plays(self):
        hand = _h(land=3, four=2, five_plus=2)
        assert _keep_hand(hand) is False

    def test_keeps_three_lands_with_curve(self):
        hand = _h(land=3, one=1, two=1, three=1, four=1)
        assert _keep_hand(hand) is True


def _hydrated_card(name, mana_cost="", cmc=0, type_line="", oracle_text=""):
    """Minimal hydrated-card stub the goldfish uses."""
    return {
        "name": name,
        "mana_cost": mana_cost,
        "cmc": cmc,
        "type_line": type_line,
        "oracle_text": oracle_text,
        "produced_mana": [],
    }


def _simple_mono_red_deck():
    """20 Mountains + 40 cmc-1 red one-drops."""
    cards = []
    for _ in range(20):
        cards.append(_hydrated_card("Mountain", type_line="Basic Land — Mountain"))
    for i in range(40):
        cards.append(
            _hydrated_card(
                f"OneDrop{i}", mana_cost="{R}", cmc=1, type_line="Creature — Goblin"
            )
        )
    # Patch: produced_mana for Mountains
    for c in cards:
        if c["name"] == "Mountain":
            c["produced_mana"] = ["R"]
    return cards


class TestSimulateGame:
    def test_runs_to_target_turn(self):
        deck = _simple_mono_red_deck()
        rng = random.Random(0)
        result = _simulate_game(deck, max_turns=4, rng=rng)
        assert result["turns_played"] == 4
        # Turn 4: should have 4 lands in play if no mulligan
        assert result["lands_in_play_by_turn"][4] >= 1

    def test_records_casts_by_turn(self):
        deck = _simple_mono_red_deck()
        rng = random.Random(0)
        result = _simulate_game(deck, max_turns=4, rng=rng)
        # Mono-red one-drops should cast every turn we have R available
        assert sum(result["casts_by_turn"].values()) >= 1

    def test_color_screw_in_off_color_hand(self):
        # 20 Mountains + 40 blue one-drops — every turn is "color screwed"
        deck = []
        for _ in range(20):
            deck.append(_hydrated_card("Mountain", type_line="Basic Land — Mountain"))
        for c in deck:
            if c["name"] == "Mountain":
                c["produced_mana"] = ["R"]
        for i in range(40):
            deck.append(
                _hydrated_card(
                    f"BlueOne{i}", mana_cost="{U}", cmc=1, type_line="Creature — Bird"
                )
            )
        rng = random.Random(0)
        result = _simulate_game(deck, max_turns=4, rng=rng)
        # Color-screw flag should be true (we have lands but cannot cast a held card)
        assert result["color_screwed"] is True


class TestBuildIndexedDeck:
    def test_indexes_60_cards(self):
        deck = _simple_mono_red_deck()
        idx = _build_indexed_deck(deck)
        assert len(idx) == 60


class TestAggregate:
    def test_aggregates_metrics_across_games(self):
        # Three game results with synthetic data.
        games = [
            {
                "turns_played": 4,
                "lands_in_play_by_turn": {1: 1, 2: 2, 3: 3, 4: 4},
                "casts_by_turn": {1: 1, 2: 1},
                "color_screwed": False,
            },
            {
                "turns_played": 4,
                "lands_in_play_by_turn": {1: 1, 2: 2, 3: 2, 4: 3},
                "casts_by_turn": {1: 1, 2: 0},
                "color_screwed": True,
            },
            {
                "turns_played": 4,
                "lands_in_play_by_turn": {1: 1, 2: 2, 3: 3, 4: 4},
                "casts_by_turn": {1: 1, 2: 1, 3: 1},
                "color_screwed": False,
            },
        ]
        agg = _aggregate_goldfish(games, mulligans={"7": 3, "6": 0, "5": 0, "4": 0})
        assert agg["games"] == 3
        assert agg["color_screw_rate"] == pytest.approx(1 / 3)
        # Avg lands at turn 4 = (4 + 3 + 4) / 3 = 3.67
        assert agg["mean_lands_by_turn"]["4"] == pytest.approx(11 / 3)
        assert agg["mulligan_rate"]["7"] == 1.0


class TestGoldfishCLI:
    def test_runs_against_minimal_deck(self, tmp_path):
        # Prepare a minimal hydrated input: 20 Mountain + 40 cmc-1 spell.
        hydrated = []
        for _ in range(20):
            hydrated.append(
                {
                    "name": "Mountain",
                    "type_line": "Basic Land — Mountain",
                    "cmc": 0,
                    "mana_cost": "",
                    "oracle_text": "",
                    "produced_mana": ["R"],
                }
            )
        for i in range(40):
            hydrated.append(
                {
                    "name": f"Goblin{i}",
                    "type_line": "Creature — Goblin",
                    "cmc": 1,
                    "mana_cost": "{R}",
                    "oracle_text": "",
                    "produced_mana": [],
                }
            )
        deck = {
            "format": "modern",
            "cards": (
                [{"name": "Mountain", "quantity": 20}]
                + [{"name": f"Goblin{i}", "quantity": 1} for i in range(40)]
            ),
            "commanders": [],
            "sideboard": [],
        }
        deck_path = tmp_path / "deck.json"
        hydrated_path = tmp_path / "hydrated.json"
        out_path = tmp_path / "out.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(
            goldfish_main,
            [
                str(deck_path),
                "--hydrated",
                str(hydrated_path),
                "--games",
                "10",
                "--turns",
                "4",
                "--seed",
                "0",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output

        envelope = json.loads(out_path.read_text())
        assert envelope["schema_version"] == 1
        assert envelope["mode"] == "goldfish"
        assert envelope["engine"] == "goldfish"
        assert envelope["seed"] == 0
        assert envelope["results"]["games"] == 10
        assert "mean_lands_by_turn" in envelope["results"]
