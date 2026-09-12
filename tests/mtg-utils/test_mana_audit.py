"""Tests for mana_audit module: land count and color balance analysis."""

from __future__ import annotations

import json

from click.testing import CliRunner

from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.mana_audit import (
    allocate_basic_lands,
    burgess_formula,
    color_balance,
    constructed_land_target,
    karsten_adjustment,
    land_band,
    land_band_readout,
    main,
    mana_audit,
    pip_demand,
    render_text_report,
)
from mtg_utils.parse_deck import parse_deck


def _hd(deck, hydrated):
    return HydratedDeck.from_parsed(deck, records=hydrated)


class TestPipDemandFaces:
    def test_counts_mdfc_face_pips(self):
        # Modal DFCs carry no top-level mana_cost; pips live on card_faces and must
        # not be silently dropped.
        mdfc = {
            "name": "Malakir Rebirth // Malakir Mire",
            "mana_cost": None,
            "card_faces": [{"mana_cost": "{2}{B}"}, {"mana_cost": ""}],
        }
        assert pip_demand([mdfc]) == {"B": 1}

    def test_normal_card_still_uses_top_level_cost(self):
        card = {"name": "Lightning Helix", "mana_cost": "{R}{W}"}
        assert pip_demand([card]) == {"R": 1, "W": 1}


class TestAllocateBasicLands:
    """Pure allocator: distribute the land shortfall across basics by color demand,
    water-filling toward balance against what existing lands already produce."""

    def test_no_shortfall_adds_nothing(self):
        assert allocate_basic_lands(0, 35, {"W": 10}, {}) == {}
        assert allocate_basic_lands(-3, 35, {"W": 10}, {}) == {}

    def test_mono_color_all_one_basic(self):
        assert allocate_basic_lands(10, 35, {"W": 20}, {}) == {"Plains": 10}

    def test_two_color_splits_by_pip_demand(self):
        # 60/40 pips, no existing production → allocate the shortfall 60/40.
        out = allocate_basic_lands(10, 35, {"W": 12, "U": 8}, {})
        assert out == {"Plains": 6, "Island": 4}

    def test_allocation_sums_to_shortfall(self):
        out = allocate_basic_lands(7, 35, {"W": 1, "U": 1, "B": 1}, {})
        assert sum(out.values()) == 7

    def test_water_fills_toward_underserved_color(self):
        # equal pips but W already over-produced → all new basics go to U.
        out = allocate_basic_lands(10, 35, {"W": 10, "U": 10}, {"W": 25})
        assert out == {"Island": 10}

    def test_colorless_falls_back_to_wastes(self):
        assert allocate_basic_lands(8, 35, {}, {}, fallback_colors=[]) == {"Wastes": 8}

    def test_no_pips_uses_fallback_color_identity(self):
        assert allocate_basic_lands(8, 35, {}, {}, fallback_colors=["W"]) == {
            "Plains": 8
        }


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


def _constructed(land_count, *, floor, top):
    return land_band_readout(
        land_count=land_count, floor=floor, top=top, warn_below_top=True
    )["status"]


class TestConstructedReadoutStatus:
    """The 60-card gate: FAIL below the floor, WARN between floor and the target,
    PASS at or above it, FLOOD above top + 2."""

    def test_pass_at_recommended(self):
        assert _constructed(38, floor=36, top=38) == "PASS"

    def test_warn_below_recommended(self):
        assert _constructed(37, floor=36, top=38) == "WARN"

    def test_fail_below_floor(self):
        assert _constructed(35, floor=36, top=38) == "FAIL"

    def test_warn_at_floor_below_recommended(self):
        assert _constructed(35, floor=35, top=38) == "WARN"

    def test_flood_above_top_plus_two(self):
        assert _constructed(40, floor=36, top=38) == "PASS"
        assert _constructed(41, floor=36, top=38) == "FLOOD"


class TestLandBand:
    """ADR-0041: ONE deck-specific band [Karsten-adjusted floor, raw Burgess]."""

    def test_benchmark_band_burgess_above_karsten(self):
        # 5 colors, commander CMC 5, 12 ramp: Burgess = 31+5+5 = 41,
        # Karsten = 42 - floor(12/2.5) = 42-4 = 38. Burgess exceeds the
        # static template's ceiling (38) — the bug ADR-0041 fixes.
        floor, top = land_band(colors=5, commander_cmc=5, ramp_count=12)
        assert (floor, top) == (38, 41)

    def test_band_floor_is_burgess_when_karsten_is_higher(self):
        # Light ramp, mono-color low-CMC commander: Burgess = 31+1+3 = 35,
        # Karsten (0 ramp) = 42. Burgess is the smaller number either way,
        # so it lands as the floor regardless of which formula it came from.
        floor, top = land_band(colors=1, commander_cmc=3, ramp_count=0)
        assert (floor, top) == (35, 42)

    def test_scales_to_60(self):
        # Same benchmark inputs at deck_size=60: Burgess round(41*.6)=25,
        # Karsten round(38*.6)=23.
        floor, top = land_band(colors=5, commander_cmc=5, ramp_count=12, deck_size=60)
        assert (floor, top) == (23, 25)


def _commander(land_count, *, floor=38, top=41):
    return land_band_readout(
        land_count=land_count, floor=floor, top=top, warn_below_top=False
    )


class TestCommanderReadout:
    """ADR-0041: FAIL only below the floor; the top is a reference, never a WARN
    line; above top + 2 the advisory FLOOD status (never a gate)."""

    def test_fail_below_floor(self):
        assert _commander(37)["status"] == "FAIL"

    def test_pass_at_floor(self):
        assert _commander(38)["status"] == "PASS"

    def test_pass_within_band(self):
        assert _commander(40)["status"] == "PASS"

    def test_pass_above_band_top_up_to_the_flood_line(self):
        assert _commander(43)["status"] == "PASS"

    def test_flood_above_the_flood_line(self):
        assert _commander(44) == {
            "floor": 38,
            "top": 41,
            "flood": 43,
            "count": 44,
            "status": "FLOOD",
        }


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
        result = mana_audit(_hd(deck, hydrated_cards))

        # Check all required keys are present
        expected_keys = [
            "land_count",
            "burgess_formula",
            "karsten_adjustment",
            "land_band",
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
        assert set(result["land_band"]) == {"floor", "top", "flood", "count", "status"}

        # Validate status values
        assert result["land_band"]["status"] in ("PASS", "WARN", "FAIL", "FLOOD")
        assert result["color_balance_status"] in ("PASS", "WARN", "FAIL")
        assert result["overall_status"] in ("PASS", "WARN", "FAIL")

        # Korvold (5 cmc, BRG = 3 colors) deck has 2 lands
        assert result["land_count"] == 2

    def test_korvold_commander_cmc(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        result = mana_audit(_hd(deck, hydrated_cards))
        # Korvold is CMC 5, 3 colors (B, R, G)
        assert result["burgess_formula"]["commander_cmc"] == 5
        assert result["burgess_formula"]["colors"] == 3
        assert result["burgess_formula"]["result"] == 39

    def test_ramp_count(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        result = mana_audit(_hd(deck, hydrated_cards))
        # Sakura-Tribe Elder, Cultivate, Sol Ring, Ashnod's Altar are ramp
        assert result["ramp_count"] >= 3

    def test_overall_status_fail_when_too_few_lands(
        self, moxfield_deck, hydrated_cards
    ):
        deck = parse_deck(moxfield_deck)
        result = mana_audit(_hd(deck, hydrated_cards))
        # 2 lands is well below 36, should FAIL
        assert result["overall_status"] == "FAIL"


def _benchmark_deck(*, land_count, ramp_count=12):
    """ADR-0041 benchmark shape: 5-color, CMC-5 commander, N ramp pieces,
    land_count copies of one land (a real deck would vary basics/nonbasics;
    land count is all this audit cares about)."""
    commander = {
        "name": "Bennie Bracks, Zoologist",
        "cmc": 5.0,
        "type_line": "Legendary Creature — Human Advisor",
        "mana_cost": "{W}{U}{B}{R}{G}",
        "keywords": [],
        "color_identity": ["W", "U", "B", "R", "G"],
    }
    ramp_cards = [
        {
            "name": f"Rock {i}",
            "cmc": 2.0,
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}.",
            "keywords": [],
        }
        for i in range(ramp_count)
    ]
    land = {
        "name": "Command Tower",
        "cmc": 0.0,
        "type_line": "Land",
        "oracle_text": (
            "({T}: Add one mana of any color in your commander's color identity.)"
        ),
        "keywords": [],
    }
    deck = {
        "format": "commander",
        "commanders": [{"name": commander["name"], "quantity": 1}],
        "cards": [{"name": c["name"], "quantity": 1} for c in ramp_cards]
        + [{"name": "Command Tower", "quantity": land_count}],
    }
    return _hd(deck, [commander, land, *ramp_cards])


class TestManaAuditBenchmarkLandBand:
    """ADR-0041 benchmark: 5 colors, commander CMC 5, 12 ramp → band [38, 41].
    Under the old raw-Burgess-floor gate, 40 lands FAILed (below 41); the
    deck-specific band FAILs only below the Karsten-adjusted floor (38)."""

    def test_pass_at_40_lands(self):
        result = mana_audit(_benchmark_deck(land_count=40))
        assert result["land_band"] == {
            "floor": 38,
            "top": 41,
            "flood": 43,
            "count": 40,
            "status": "PASS",
        }

    def test_pass_at_the_floor(self):
        result = mana_audit(_benchmark_deck(land_count=38))
        assert result["land_band"]["status"] == "PASS"

    def test_fail_just_below_the_floor(self):
        result = mana_audit(_benchmark_deck(land_count=37))
        assert result["land_band"]["status"] == "FAIL"
        assert result["overall_status"] == "FAIL"

    def test_flood_is_advisory_never_the_overall_gate(self):
        result = mana_audit(_benchmark_deck(land_count=44))
        assert result["land_band"]["status"] == "FLOOD"
        assert result["overall_status"] != "FAIL"


class TestCLI:
    def test_text_report_and_json_file(self, moxfield_deck, hydrated_cards, tmp_path):
        from conftest import json_from_cli_output

        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "mana-audit:" in result.output
        assert "Land count:" in result.output
        assert "Full JSON:" in result.output

        data = json_from_cli_output(result)
        assert "overall_status" in data

    def test_compare_mode(self, moxfield_deck, hydrated_cards, tmp_path):
        from conftest import json_from_cli_output

        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
                "--compare",
                str(deck_path),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "mana-audit --compare" in result.output
        assert "Delta:" in result.output

        data = json_from_cli_output(result)
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

    def test_constructed_readout_scaled_floor(self):
        # For a 60-card deck with floor 22 / target 23: below is FAIL, at is WARN
        assert _constructed(21, floor=22, top=23) == "FAIL"
        assert _constructed(22, floor=22, top=23) == "WARN"
        assert _constructed(23, floor=22, top=23) == "PASS"


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
        result = mana_audit(_hd(deck, hydrated))
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

        from conftest import json_from_cli_output

        output_path = tmp_path / "out.json"
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
                "--compare",
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0
        data = json_from_cli_output(result)
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

        from conftest import json_from_cli_output

        output_path = tmp_path / "out.json"
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
                "--compare",
                str(compare_path),
                "--output",
                str(output_path),
            ],
        )
        data = json_from_cli_output(result)
        assert data["primary"]["source"] == "primary.json"
        assert data["comparison"]["source"] == "comparison.json"


class TestConstructedLandTarget:
    def test_baseline_24_at_avg_cmc_3(self):
        assert constructed_land_target(ramp_count=0, avg_cmc=3.0) == 24

    def test_ramp_reduces_count(self):
        assert constructed_land_target(ramp_count=4, avg_cmc=3.0) == 22

    def test_high_curve_increases(self):
        result = constructed_land_target(ramp_count=0, avg_cmc=4.5)
        assert result > 24

    def test_low_curve_decreases(self):
        result = constructed_land_target(ramp_count=0, avg_cmc=1.5)
        assert result < 24

    def test_clamped_low_at_20(self):
        result = constructed_land_target(ramp_count=20, avg_cmc=1.0)
        assert result >= 20

    def test_clamped_high_at_27(self):
        result = constructed_land_target(ramp_count=0, avg_cmc=6.0)
        assert result <= 27

    def test_scales_to_non_60(self):
        r60 = constructed_land_target(ramp_count=0, avg_cmc=3.0, deck_size=60)
        r80 = constructed_land_target(ramp_count=0, avg_cmc=3.0, deck_size=80)
        assert r80 > r60


class TestConstructedManaAudit:
    def test_constructed_uses_constructed_target(self):
        deck = {
            "format": "pioneer",
            "deck_size": 60,
            "commanders": [],
            "cards": [
                {"name": "Lightning Bolt", "quantity": 4},
                {"name": "Mountain", "quantity": 22},
            ],
        }
        hydrated = [
            {
                "name": "Lightning Bolt",
                "cmc": 1.0,
                "mana_cost": "{R}",
                "type_line": "Instant",
                "keywords": [],
                "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            },
            {
                "name": "Mountain",
                "cmc": 0.0,
                "mana_cost": "",
                "type_line": "Basic Land — Mountain",
                "keywords": [],
                "oracle_text": "({T}: Add {R}.)",
            },
        ]
        result = mana_audit(_hd(deck, hydrated))
        assert "constructed_land_target" in result
        assert "burgess_formula" not in result
        assert result["land_count"] == 22
        assert result["constructed_land_target"]["ramp_count"] == 0

    def test_constructed_excludes_sideboard(self):
        deck = {
            "format": "pioneer",
            "deck_size": 60,
            "commanders": [],
            "cards": [{"name": "Mountain", "quantity": 22}],
            "sideboard": [{"name": "Island", "quantity": 5}],
        }
        hydrated = [
            {
                "name": "Mountain",
                "cmc": 0.0,
                "mana_cost": "",
                "type_line": "Basic Land — Mountain",
                "keywords": [],
                "oracle_text": "({T}: Add {R}.)",
            },
            {
                "name": "Island",
                "cmc": 0.0,
                "mana_cost": "",
                "type_line": "Basic Land — Island",
                "keywords": [],
                "oracle_text": "({T}: Add {U}.)",
            },
        ]
        result = mana_audit(_hd(deck, hydrated))
        assert result["land_count"] == 22  # sideboard Island not counted


class TestEffectiveCommanderCost:
    """ADR-0044: the Burgess term is the effective commander cost."""

    def test_ordinary_commander_keeps_printed_value(
        self, moxfield_deck, hydrated_cards
    ):
        deck = parse_deck(moxfield_deck)
        result = mana_audit(_hd(deck, hydrated_cards))
        bf = result["burgess_formula"]
        assert bf["commander_cmc"] == bf["printed_cmc"] == 5  # Korvold, {2}{B}{R}{G}
        block = result["commander_cost"]
        assert block["used"] == block["printed"] == 5
        assert len(block["commanders"]) == 1
        # No self-discount clause (or no IR in CI) → a reported, non-silent status.
        assert block["commanders"][0]["status"] in ("none", "unmodelled (no IR)")

    def test_modelled_discount_moves_both_band_edges(self, hydrated_cards, monkeypatch):
        from mtg_utils import commander_cost as cc

        # Sixty cheap creatures + lands so the operand expectation is non-trivial
        # (the Moxfield fixture deck has only two creatures).
        deck = {
            "format": "commander",
            "deck_size": 100,
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [
                {"name": "Viscera Seer", "quantity": 30},
                {"name": "Blood Artist", "quantity": 30},
                {"name": "Command Tower", "quantity": 39},
            ],
            "total_cards": 100,
        }
        baseline = mana_audit(_hd(deck, hydrated_cards))
        # Pretend Korvold costs {1} less per creature you control (an ObjectCount
        # operand over Creature/You). Korvold is {2}{B}{R}{G}: printed 5, pips 3.
        discount = cc.SelfDiscount("count", None, 1, ("Creature",), (), ())
        monkeypatch.setattr(cc, "read_self_discount", lambda _rec: discount)
        result = mana_audit(_hd(deck, hydrated_cards))
        block = result["commander_cost"]["commanders"][0]
        assert block["status"] == "modelled"
        assert block["pips"] == 3
        # Turn 3: budget 3 mana — 30 Seers seen 9/99 each (2.73 copies, 2.73 mana)
        # fit whole, a sliver of Blood Artist fills the rest → floor 2 → residual
        # max(3, 5-2) = 3 ≤ 3. Turn 2 fails (budget 1 → floor 1 → residual 4 > 2).
        assert block["effective"] == 3
        assert block["residual"] == 3
        assert result["burgess_formula"]["commander_cmc"] == 3
        assert result["burgess_formula"]["printed_cmc"] == 5
        assert (
            result["burgess_formula"]["result"]
            == baseline["burgess_formula"]["result"] - 2
        )
        # The band is [min(Burgess, Karsten), max(Burgess, Karsten)]; with no ramp
        # Karsten (42) is the top in both runs, so the FLOOR is what moves.
        assert result["land_band"]["floor"] == baseline["land_band"]["floor"] - 2
        assert result["land_band"]["top"] == baseline["land_band"]["top"] == 42
        assert "Commander cost: Korvold, Fae-Cursed King printed 5, effective 3" in (
            render_text_report(result)
        )


def _limited_deck(land_count: int):
    """A 40-card constructed-shaped deck (Arena limited): 23 3-cmc
    creatures plus ``land_count`` Plains. Avg cmc 3.0 keeps the
    constructed target at its baseline (24 scaled to 16)."""
    spells = [
        {
            "name": f"Bear {i}",
            "cmc": 3.0,
            "type_line": "Creature — Bear",
            "mana_cost": "{2}{W}",
            "oracle_text": "",
            "keywords": [],
        }
        for i in range(23)
    ]
    plains = {
        "name": "Plains",
        "cmc": 0.0,
        "type_line": "Basic Land — Plains",
        "oracle_text": "({T}: Add {W}.)",
        "keywords": [],
    }
    deck = {
        "format": "timeless",
        "deck_size": 40,
        "commanders": [],
        "cards": [{"name": s["name"], "quantity": 1} for s in spells]
        + [{"name": "Plains", "quantity": land_count}],
    }
    return _hd(deck, [plains, *spells])


class TestConstructedFloorScalesWithDeckSize:
    """The constructed FAIL floor is ``max(20, target - 2)`` for a 60-card
    deck; the 20-land clamp must scale with deck size too, or every
    40-card limited deck FAILs regardless of its land count."""

    def test_40_card_deck_at_target_passes(self):
        result = mana_audit(_limited_deck(land_count=17))
        assert result["land_band"]["top"] == 16
        assert result["land_band"]["floor"] == 14
        assert result["land_band"]["status"] == "PASS"

    def test_40_card_deck_below_scaled_floor_fails(self):
        result = mana_audit(_limited_deck(land_count=13))
        assert result["land_band"]["floor"] == 14
        assert result["land_band"]["status"] == "FAIL"
