"""Smoke test: playtest-goldfish CLI is registered and prints --help."""

import random

from click.testing import CliRunner

from mtg_utils.playtest import (
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
    """Build a synthetic hand: list of dicts with cmc and is_land flag."""
    hand = []
    for _ in range(land):
        hand.append({"cmc": 0, "is_land": True})
    for cmc, n in [(1, one), (2, two), (3, three), (4, four), (5, five_plus)]:
        for _ in range(n):
            hand.append({"cmc": cmc, "is_land": False})
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
