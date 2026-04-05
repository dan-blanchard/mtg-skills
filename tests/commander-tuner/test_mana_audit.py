"""Tests for mana_audit module: land count and color balance analysis."""

from __future__ import annotations

import json

from click.testing import CliRunner

from commander_utils.mana_audit import (
    burgess_formula,
    color_balance,
    karsten_adjustment,
    land_count_status,
    main,
    mana_audit,
    pip_demand,
)
from commander_utils.parse_deck import parse_deck


class TestBurgessFormula:
    def test_three_color_cmc_4(self):
        assert burgess_formula(colors=3, commander_cmc=4) == 38

    def test_mono_color_cmc_3(self):
        assert burgess_formula(colors=1, commander_cmc=3) == 35

    def test_five_color_cmc_5(self):
        assert burgess_formula(colors=5, commander_cmc=5) == 41


class TestKarstenAdjustment:
    def test_no_ramp(self):
        assert karsten_adjustment(ramp_count=0) == 42

    def test_four_rocks(self):
        # 42 - floor(4 / 2.5) = 42 - 1 = 41
        assert karsten_adjustment(ramp_count=4) == 41

    def test_ten_rocks(self):
        # 42 - floor(10 / 2.5) = 42 - 4 = 38
        assert karsten_adjustment(ramp_count=10) == 38

    def test_never_below_36(self):
        assert karsten_adjustment(ramp_count=100) == 36


class TestLandCountStatus:
    def test_pass_at_recommended(self):
        assert land_count_status(land_count=38, recommended=38) == "PASS"

    def test_warn_below_recommended(self):
        assert land_count_status(land_count=37, recommended=38) == "WARN"

    def test_fail_below_36(self):
        assert land_count_status(land_count=35, recommended=38) == "FAIL"


class TestPipDemand:
    def test_counts_colored_pips(self):
        cards = [
            {"mana_cost": "{U}{U}"},  # Counterspell
            {"mana_cost": "{2}{B}{B}"},  # No Mercy
        ]
        result = pip_demand(cards)
        assert result == {"B": 2, "U": 2}

    def test_ignores_generic(self):
        cards = [{"mana_cost": "{5}{R}"}]
        result = pip_demand(cards)
        assert result == {"R": 1}

    def test_empty(self):
        assert pip_demand([]) == {}

    def test_sorted_output(self):
        cards = [{"mana_cost": "{R}{U}{G}{W}{B}"}]
        result = pip_demand(cards)
        assert list(result.keys()) == sorted(result.keys())

    def test_skips_none_mana_cost(self):
        cards = [{"mana_cost": None}, {"mana_cost": "{G}"}]
        result = pip_demand(cards)
        assert result == {"G": 1}


class TestColorBalance:
    def test_pass_when_balanced(self):
        # 50% blue pips, 50% blue land production, 4 total lands
        pips = {"U": 5, "B": 5}
        land_colors = {"U": 2, "B": 2}
        result = color_balance(pips, land_colors, total_lands=4)
        assert result["status"] == "PASS"
        assert result["flags"] == []

    def test_fail_when_severely_off(self):
        # 100% blue pip demand, but no blue lands at all
        pips = {"U": 10}
        land_colors = {"R": 4}
        result = color_balance(pips, land_colors, total_lands=4)
        assert result["status"] == "FAIL"
        assert len(result["flags"]) > 0

    def test_warn_when_slightly_off(self):
        # U is 60% of pips but only 50% of lands => exactly 10pp deficit => WARN (not > 10)
        pips = {"U": 6, "B": 4}
        land_colors = {"U": 5, "B": 5}
        # U demand: 60%, U supply: 50% => deficit exactly 10 pts => WARN (threshold is > 10 for FAIL)
        result = color_balance(pips, land_colors, total_lands=10)
        assert result["status"] == "WARN"

    def test_warn_threshold(self):
        # U: 55% demand, 50% supply => 5pt deficit => WARN (not > 5)
        pips = {"U": 11, "B": 9}
        land_colors = {"U": 10, "B": 10}
        result = color_balance(pips, land_colors, total_lands=20)
        assert result["status"] == "WARN"

    def test_empty_pips(self):
        result = color_balance({}, {}, total_lands=0)
        assert result["status"] == "PASS"
        assert result["flags"] == []


class TestManaAudit:
    def test_full_audit_pass(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        result = mana_audit(deck, hydrated_cards)

        # Check all required keys are present
        expected_keys = [
            "land_count",
            "recommended_land_count",
            "burgess_formula",
            "karsten_adjustment",
            "land_count_status",
            "ramp_count",
            "avg_cmc",
            "pip_demand",
            "pip_demand_pct",
            "land_color_production",
            "land_color_pct",
            "rock_color_pct",
            "color_balance_status",
            "color_balance_flags",
            "overall_status",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

        # Validate nested keys
        assert "colors" in result["burgess_formula"]
        assert "commander_cmc" in result["burgess_formula"]
        assert "result" in result["burgess_formula"]
        assert "ramp_count" in result["karsten_adjustment"]
        assert "result" in result["karsten_adjustment"]

        # Validate status values
        assert result["land_count_status"] in ("PASS", "WARN", "FAIL")
        assert result["color_balance_status"] in ("PASS", "WARN", "FAIL")
        assert result["overall_status"] in ("PASS", "WARN", "FAIL")

        # Korvold (5 cmc, BRG = 3 colors) deck has 2 lands
        assert result["land_count"] == 2

    def test_korvold_commander_cmc(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        result = mana_audit(deck, hydrated_cards)
        # Korvold is CMC 5, 3 colors (B, R, G)
        assert result["burgess_formula"]["commander_cmc"] == 5
        assert result["burgess_formula"]["colors"] == 3
        assert result["burgess_formula"]["result"] == 39

    def test_ramp_count(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        result = mana_audit(deck, hydrated_cards)
        # Sakura-Tribe Elder, Cultivate, Sol Ring, Ashnod's Altar are ramp
        assert result["ramp_count"] >= 3

    def test_overall_status_fail_when_too_few_lands(
        self, moxfield_deck, hydrated_cards
    ):
        deck = parse_deck(moxfield_deck)
        result = mana_audit(deck, hydrated_cards)
        # 2 lands is well below 36, should FAIL
        assert result["overall_status"] == "FAIL"


class TestCLI:
    def test_outputs_valid_json(self, moxfield_deck, hydrated_cards, tmp_path):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), str(hydrated_path)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "overall_status" in data

    def test_compare_mode(self, moxfield_deck, hydrated_cards, tmp_path):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                str(hydrated_path),
                "--compare",
                str(deck_path),
                str(hydrated_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "primary" in data
        assert "comparison" in data
        assert "delta" in data
        assert "land_count" in data["delta"]
        assert "avg_cmc" in data["delta"]
        assert "ramp_count" in data["delta"]


class TestScaledFormulas:
    def test_burgess_scaled_to_60(self):
        # 3 colors, CMC 4: base = 31+3+4 = 38, scaled = round(38 * 60/100) = 23
        result = burgess_formula(colors=3, commander_cmc=4, deck_size=60)
        assert result == 23

    def test_burgess_unscaled_at_100(self):
        assert burgess_formula(colors=3, commander_cmc=4) == 38

    def test_karsten_scaled_to_60(self):
        # 0 ramp: base = max(36, 42) = 42, scaled = round(42 * 60/100) = 25
        result = karsten_adjustment(ramp_count=0, deck_size=60)
        assert result == 25

    def test_karsten_unscaled_at_100(self):
        assert karsten_adjustment(ramp_count=0) == 42

    def test_land_count_status_scaled_floor(self):
        # For 60-card: floor = round(36 * 60/100) = 22
        assert land_count_status(land_count=21, recommended=23, deck_size=60) == "FAIL"
        assert land_count_status(land_count=22, recommended=23, deck_size=60) == "WARN"
        assert land_count_status(land_count=23, recommended=23, deck_size=60) == "PASS"

    def test_land_count_status_default_100(self):
        assert land_count_status(land_count=35, recommended=38) == "FAIL"


class TestManaAuditWithFormat:
    def test_audit_reads_deck_size(self):
        """Mana audit on a 60-card Brawl deck uses scaled formulas."""
        deck = {
            "format": "brawl",
            "deck_size": 60,
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [{"name": "Mountain", "quantity": 22}],
        }
        hydrated = [
            {
                "name": "Korvold",
                "cmc": 5,
                "type_line": "Legendary Creature",
                "mana_cost": "{2}{B}{R}{G}",
                "keywords": [],
                "color_identity": ["B", "R", "G"],
            },
            {
                "name": "Mountain",
                "cmc": 0,
                "type_line": "Basic Land — Mountain",
                "oracle_text": "({T}: Add {R}.)",
                "keywords": [],
            },
        ]
        result = mana_audit(deck, hydrated)
        assert result["land_count"] == 22
        # Burgess for 60-card: round((31+3+5) * 60/100) = round(23.4) = 23
        assert result["burgess_formula"]["result"] == 23


class TestCompareLabels:
    def test_uses_primary_comparison_keys(self, tmp_path):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [{"name": "Mountain", "quantity": 37}],
        }
        hydrated = [
            {
                "name": "Korvold",
                "cmc": 5,
                "type_line": "Legendary Creature",
                "mana_cost": "{2}{B}{R}{G}",
                "keywords": [],
                "color_identity": ["B", "R", "G"],
            },
            {
                "name": "Mountain",
                "cmc": 0,
                "type_line": "Basic Land — Mountain",
                "oracle_text": "({T}: Add {R}.)",
                "keywords": [],
            },
        ]
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                str(hydrated_path),
                "--compare",
                str(deck_path),
                str(hydrated_path),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "primary" in data
        assert "comparison" in data
        assert "before" not in data
        assert "after" not in data

    def test_includes_source_filenames(self, tmp_path):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [{"name": "Mountain", "quantity": 37}],
        }
        hydrated = [
            {
                "name": "Korvold",
                "cmc": 5,
                "type_line": "Legendary Creature",
                "mana_cost": "{2}{B}{R}{G}",
                "keywords": [],
                "color_identity": ["B", "R", "G"],
            },
            {
                "name": "Mountain",
                "cmc": 0,
                "type_line": "Basic Land — Mountain",
                "oracle_text": "({T}: Add {R}.)",
                "keywords": [],
            },
        ]
        deck_path = tmp_path / "primary.json"
        deck_path.write_text(json.dumps(deck))
        compare_path = tmp_path / "comparison.json"
        compare_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                str(hydrated_path),
                "--compare",
                str(compare_path),
                str(hydrated_path),
            ],
        )
        data = json.loads(result.output)
        assert data["primary"]["source"] == "primary.json"
        assert data["comparison"]["source"] == "comparison.json"
