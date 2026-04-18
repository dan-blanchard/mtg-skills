"""Tests for cube-stats CLI."""

import json
from pathlib import Path

from click.testing import CliRunner

from mtg_utils.cube_stats import cube_stats, main, render_text_report


class TestCubeStatsCore:
    def test_total_cards_matches_cube(self, sample_cube_json, cube_hydrated):
        result = cube_stats(sample_cube_json, cube_hydrated)
        assert result["total_cards"] == 12

    def test_size_delta(self, sample_cube_json, cube_hydrated):
        result = cube_stats(sample_cube_json, cube_hydrated)
        assert result["size_delta"] == 0

    def test_land_count(self, sample_cube_json, cube_hydrated):
        # Overgrown Tomb + Command Tower
        result = cube_stats(sample_cube_json, cube_hydrated)
        assert result["land_count"] == 2

    def test_nonbasic_land_count(self, sample_cube_json, cube_hydrated):
        result = cube_stats(sample_cube_json, cube_hydrated)
        assert result["nonbasic_land_count"] == 2

    def test_creature_count(self, sample_cube_json, cube_hydrated):
        # Llanowar Elves, Viscera Seer, Thrasios
        result = cube_stats(sample_cube_json, cube_hydrated)
        assert result["creature_count"] == 3

    def test_gold_card_count(self, sample_cube_json, cube_hydrated):
        # Thrasios (GU), Fire // Ice (UR)
        result = cube_stats(sample_cube_json, cube_hydrated)
        assert result["gold_card_count"] == 2

    def test_categories_present(self, sample_cube_json, cube_hydrated):
        """The sample cube covers W/U/B/R (non-fixing mono cards), M
        (multicolor creatures), L (Overgrown Tomb, Command Tower), and F
        (Sol Ring, Dark Ritual, Llanowar Elves — all classify as fixing
        under cube-utils semantics because they produce mana). Green
        non-fixing creatures aren't in the sample, so "G" won't appear."""
        result = cube_stats(sample_cube_json, cube_hydrated)
        cats = result["by_category"]
        for c in ("W", "U", "B", "R", "M", "L", "F"):
            assert c in cats, f"expected {c} in {cats}"

    def test_by_color_includes_multicolor(self, sample_cube_json, cube_hydrated):
        """A multicolor card counts toward every color in its identity."""
        result = cube_stats(sample_cube_json, cube_hydrated)
        # Green: Llanowar Elves + Thrasios = 2
        # Blue: Counterspell + Rhystic + Thrasios + Fire//Ice = 4
        assert result["by_color"]["G"] >= 2
        assert result["by_color"]["U"] >= 4

    def test_auto_detects_present_colors(self, cube_hydrated):
        """A cube with only one color should only report that color."""
        cube = {
            "cube_format": "vintage",
            "target_size": 3,
            "name": "Mono Red Cube",
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},
                {"name": "Wildfire", "quantity": 1},
            ],
            "total_cards": 2,
        }
        result = cube_stats(cube, cube_hydrated)
        assert result["by_color"] == {"R": 2}
        assert "U" not in result["by_color"]

    def test_rarity_breakdown(self, sample_cube_json, cube_hydrated):
        result = cube_stats(sample_cube_json, cube_hydrated)
        rarities = result["by_rarity"]
        assert any(k in rarities for k in ("common", "uncommon", "rare", "mythic"))

    def test_type_breakdown(self, sample_cube_json, cube_hydrated):
        result = cube_stats(sample_cube_json, cube_hydrated)
        types = result["by_type"]
        assert "Land" in types
        assert "Creature" in types
        assert "Instant" in types

    def test_curve_excludes_lands(self, sample_cube_json, cube_hydrated):
        result = cube_stats(sample_cube_json, cube_hydrated)
        curve_total = sum(result["curve"].values())
        # Curve should equal nonland count = 12 - 2 lands = 10
        assert curve_total == 10

    def test_missing_card_reported(self, cube_hydrated):
        cube = {
            "cube_format": "vintage",
            "target_size": 1,
            "cards": [{"name": "Nonexistent Card", "quantity": 1}],
            "total_cards": 1,
        }
        result = cube_stats(cube, cube_hydrated)
        assert "Nonexistent Card" in result["missing"]


class TestCommanderPool:
    def test_commander_pool_tracked(self, sample_commander_cube_json, cube_hydrated):
        result = cube_stats(sample_commander_cube_json, cube_hydrated)
        assert "commander_pool" in result
        assert result["commander_pool"]["total"] == 4

    def test_commander_pool_grouped_by_color_identity(
        self, sample_commander_cube_json, cube_hydrated
    ):
        result = cube_stats(sample_commander_cube_json, cube_hydrated)
        breakdown = result["commander_pool"]["by_color_identity"]
        # Atraxa 4C, Tuvasa 3C (Bant), Thrasios Simic, Korvold Jund
        assert len(breakdown) == 4

    def test_no_commander_pool_field_when_empty(self, sample_cube_json, cube_hydrated):
        result = cube_stats(sample_cube_json, cube_hydrated)
        assert "commander_pool" not in result


class TestTextReport:
    def test_renders_basic(self, sample_cube_json, cube_hydrated):
        result = cube_stats(sample_cube_json, cube_hydrated)
        text = render_text_report(result)
        assert "cube-stats: 12 cards" in text
        assert "Colors" in text
        assert "Lands" in text

    def test_renders_commander_pool(self, sample_commander_cube_json, cube_hydrated):
        result = cube_stats(sample_commander_cube_json, cube_hydrated)
        text = render_text_report(result)
        assert "Commander pool: 4" in text


class TestCLIInterface:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "cube" in result.output.lower()

    def test_reads_and_writes(self, sample_cube_json, cube_hydrated, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        out_path = tmp_path / "out.json"
        cube_path.write_text(json.dumps(sample_cube_json))
        hyd_path.write_text(json.dumps(cube_hydrated))
        result = runner.invoke(
            main, [str(cube_path), str(hyd_path), "--output", str(out_path)]
        )
        assert result.exit_code == 0, result.output
        assert "Full JSON:" in result.output
        data = json.loads(out_path.read_text())
        assert data["total_cards"] == 12

    def test_json_flag(self, sample_cube_json, cube_hydrated, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        cube_path.write_text(json.dumps(sample_cube_json))
        hyd_path.write_text(json.dumps(cube_hydrated))
        result = runner.invoke(main, [str(cube_path), str(hyd_path), "--json"])
        assert result.exit_code == 0
        assert '"total_cards": 12' in result.output
