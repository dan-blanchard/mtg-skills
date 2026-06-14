"""Smoke test: playtest-goldfish CLI is registered and prints --help."""

import json
import random

import pytest
from click.testing import CliRunner

from mtg_utils._playtest_common import render_goldfish_markdown
from mtg_utils.playtest import (
    _aggregate_goldfish,
    _build_indexed_deck,
    _is_color_screwed,
    _keep_hand,
    _mana_ability_profile,
    _pay,
    _pips_coverable,
    _run_goldfish,
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


class TestColorScrewMetric:
    def test_pips_coverable_basic(self):
        assert _pips_coverable({"B": 2}, [{"B"}, {"B"}]) is True
        assert _pips_coverable({"B": 2}, [{"B"}, {"R"}]) is False

    def test_pips_coverable_with_duals(self):
        # Two B/R duals can pay {B}{R}; one dual cannot pay two pips.
        assert _pips_coverable({"B": 1, "R": 1}, [{"B", "R"}, {"B", "R"}]) is True
        assert _pips_coverable({"B": 1, "R": 1}, [{"B", "R"}]) is False

    def test_pips_coverable_no_pips(self):
        assert _pips_coverable({}, []) is True

    def test_too_expensive_is_not_color_screw(self):
        # 5-drop with only 2 lands: a curve issue, not color screw (the bug).
        card = {"mana_cost": "{B}{B}{1}{1}{1}", "cmc": 5}
        assert _is_color_screwed(card, [{"B"}, {"B"}]) is False

    def test_wrong_colors_is_color_screw(self):
        # Enough total mana (3 >= cmc 2) but nothing produces the U pip.
        card = {"mana_cost": "{U}{1}", "cmc": 2}
        assert _is_color_screwed(card, [{"R"}, {"R"}, {"R"}]) is True

    def test_right_colors_is_not_color_screw(self):
        card = {"mana_cost": "{B}{B}{1}", "cmc": 3}
        assert _is_color_screwed(card, [{"B"}, {"B"}, {"R"}]) is False

    def test_any_color_source_covers_off_color_pip(self):
        # A Birds/Signet-style any-color source pays an off-color pip.
        card = {"mana_cost": "{U}{1}", "cmc": 2}
        assert _is_color_screwed(card, [{"R"}, {"W", "U", "B", "R", "G"}]) is False

    def test_float_cmc_does_not_crash(self):
        # Scryfall stores cmc as a float (2.0); _pay's slice index and the
        # color-screw mana check must coerce it to int rather than crash.
        payable = {"mana_cost": "{B}{B}", "cmc": 2.0}
        sources = [{"B"}, {"B"}, {"R"}]
        assert _pay(payable, sources) is True
        assert len(sources) == 1  # the two B sources were consumed
        screwed = {"mana_cost": "{U}{1}", "cmc": 2.0}
        assert _is_color_screwed(screwed, [{"R"}, {"R"}, {"R"}]) is True


class TestManaAbilityProfile:
    def test_sol_ring_makes_two_colorless(self):
        sol_ring = {
            "produced_mana": ["C"],
            "oracle_text": "{T}: Add {C}{C}.",
            "type_line": "Artifact",
        }
        assert _mana_ability_profile(sol_ring) == (2, frozenset())

    def test_any_color_dork(self):
        birds = {
            "produced_mana": ["W", "U", "B", "R", "G"],
            "oracle_text": "Flying\n{T}: Add one mana of any color.",
            "type_line": "Creature — Bird",
        }
        assert _mana_ability_profile(birds) == (1, frozenset("WUBRG"))

    def test_restricted_dork(self):
        ignoble = {
            "produced_mana": ["B", "R", "G"],
            "oracle_text": "Exalted\n{T}: Add {B}, {R}, or {G}.",
            "type_line": "Creature — Goblin Shaman",
        }
        assert _mana_ability_profile(ignoble) == (1, frozenset("BRG"))

    def test_non_source_returns_none(self):
        bear = {"produced_mana": [], "oracle_text": "", "type_line": "Creature — Bear"}
        assert _mana_ability_profile(bear) is None

    def test_token_maker_counted_as_one_per_turn(self):
        # Scryfall populates produced_mana on Treasure/token MAKERS (from the
        # token's ability), so we count them as a rough 1-mana/turn source. The
        # five-color list must yield ONE mana of any color per turn, NOT five.
        plunderer = {
            "produced_mana": ["B", "G", "R", "U", "W"],
            "oracle_text": (
                "Whenever another creature you control dies, create a Treasure "
                "token. (It's an artifact with \"{T}, Sacrifice this token: Add "
                'one mana of any color.")'
            ),
            "type_line": "Creature — Human Pirate",
        }
        amount, colors = _mana_ability_profile(plunderer)
        assert amount == 1  # one per turn, not five
        assert colors == frozenset("BGRUW")


class TestManaRocksCountTowardCasting:
    def test_sol_ring_accelerates_a_four_drop(self):
        # Opening hand: 2 Mountains + Sol Ring + a 4-cmc spell. With Sol Ring's
        # +2, the 4-drop is castable on turn 2 (2 lands + Sol Ring = 4 mana) —
        # impossible from two lands alone. Proves rocks count as mana producers.
        mountain = _hydrated_card("Mountain", type_line="Basic Land — Mountain")
        mountain["produced_mana"] = ["R"]
        sol_ring = _hydrated_card(
            "Sol Ring",
            mana_cost="{1}",
            cmc=1,
            type_line="Artifact",
            oracle_text="{T}: Add {C}{C}.",
        )
        sol_ring["produced_mana"] = ["C"]
        four_drop = _hydrated_card(
            "Hill Giant", mana_cost="{3}{R}", cmc=4, type_line="Creature — Giant"
        )
        # hydrated[0,1]=Mountains, [2]=Sol Ring, [3]=four-drop, rest filler lands.
        deck = [
            dict(mountain),
            dict(mountain),
            sol_ring,
            four_drop,
            *[dict(mountain) for _ in range(20)],
        ]
        result = _simulate_game(
            deck, max_turns=2, rng=random.Random(0), starting_hand=[0, 1, 2, 3]
        )
        # Only 2 lands by turn 2, so a turn-2 cast of a 4-drop requires the rock.
        assert result["lands_in_play_by_turn"][2] == 2
        assert result["casts_by_turn"].get(2, 0) >= 1


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


class TestMulliganThreading:
    def test_forced_mulligan_to_4_tracked_and_threaded(self):
        """Deck of all 5-CMC cards fails _keep_hand at 7/6/5, force-keeps at 4.

        Verifies that:
        - mulligan_rate["4"] == 1.0 (the force-keep is counted)
        - mulligan_rate["7"] == 0.0 (never kept a 7-card hand)
        - _simulate_game does not crash (the kept indices thread through correctly)
        """
        # 60 cards: 30 forests + 30 five-drops — _keep_hand returns False for 7/6/5
        # because there are no nonland cards with cmc <= 3.
        deck = []
        for _ in range(30):
            c = _hydrated_card("Forest", type_line="Basic Land — Forest")
            c["produced_mana"] = ["G"]
            deck.append(c)
        for i in range(30):
            deck.append(
                _hydrated_card(
                    f"FiveDrop{i}",
                    mana_cost="{5}",
                    cmc=5,
                    type_line="Creature — Elemental",
                )
            )

        result = _run_goldfish(deck, games=1, max_turns=4, base_seed=42)
        assert result["mulligan_rate"]["7"] == 0.0
        assert result["mulligan_rate"]["4"] == 1.0
        # Simulation completed without error — kept_indices threaded through correctly.
        assert result["games"] == 1


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
                    "oracle_text": "({T}: Add {R}.)",
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


class TestGoldfishMarkdown:
    def test_renders_summary(self):
        env = {
            "schema_version": 1,
            "mode": "goldfish",
            "engine": "goldfish",
            "engine_version": "goldfish v1",
            "seed": 0,
            "format": "modern",
            "card_coverage": {"requested": 60, "supported": 60, "missing": []},
            "results": {
                "games": 1000,
                "mean_lands_by_turn": {"4": 3.5},
                "mean_casts_by_turn": {"1": 0.9, "2": 0.8},
                "color_screw_rate": 0.05,
                "mulligan_rate": {"7": 0.85, "6": 0.10, "5": 0.04, "4": 0.01},
            },
            "warnings": [],
            "duration_s": 4.2,
        }
        md = render_goldfish_markdown(env)
        assert "# Goldfish report" in md
        assert "1000 games" in md
        assert "Color-screw rate" in md
        assert "5.0%" in md  # color screw
        assert "Kept on 7: 85.0%" in md
