"""Tests for cube-balance CLI."""

import json
from pathlib import Path

from click.testing import CliRunner

from mtg_utils.cube_balance import _is_removal, cube_balance, main


class TestRemovalDetection:
    def test_destroy_target(self):
        card = {
            "type_line": "Sorcery",
            "oracle_text": "Destroy target creature.",
        }
        assert _is_removal(card) is True

    def test_exile_target(self):
        card = {
            "type_line": "Instant",
            "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
        }
        assert _is_removal(card) is True

    def test_counterspell(self):
        card = {
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
        }
        assert _is_removal(card) is True

    def test_lightning_bolt(self):
        card = {
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        }
        assert _is_removal(card) is True

    def test_damage_to_target_creature(self):
        card = {
            "type_line": "Instant",
            "oracle_text": "Flame Slash deals 4 damage to target creature.",
        }
        assert _is_removal(card) is True

    def test_wrath_of_god(self):
        card = {
            "type_line": "Sorcery",
            "oracle_text": "Destroy all creatures. They can't be regenerated.",
        }
        assert _is_removal(card) is True

    def test_creature_not_removal(self):
        card = {
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
        }
        assert _is_removal(card) is False

    def test_land_not_removal(self):
        card = {
            "type_line": "Land",
            "oracle_text": "Destroy target land. (rider text)",
        }
        # Lands are explicitly excluded from removal classification.
        assert _is_removal(card) is False


class TestCubeBalance:
    def test_runs_all_checks_by_default(self, sample_cube_json, cube_hydrated):
        result = cube_balance(sample_cube_json, cube_hydrated)
        for check in ("colors", "curve", "removal", "fixing", "commander_pool"):
            assert check in result

    def test_restricts_checks(self, sample_cube_json, cube_hydrated):
        result = cube_balance(sample_cube_json, cube_hydrated, checks=["removal"])
        assert "removal" in result
        assert "colors" not in result

    def test_color_balance_reports_observed(self, sample_cube_json, cube_hydrated):
        result = cube_balance(sample_cube_json, cube_hydrated, checks=["colors"])
        observed = result["colors"]["observed"]
        # Cube contains cards in W, U, B, R, G
        for c in ("W", "U", "B", "R", "G"):
            assert c in observed

    def test_color_balance_skips_absent_colors(self, cube_hydrated):
        cube = {
            "cube_format": "vintage",
            "target_size": 2,
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},
                {"name": "Wildfire", "quantity": 1},
            ],
            "total_cards": 2,
        }
        result = cube_balance(cube, cube_hydrated, checks=["colors"])
        observed = result["colors"]["observed"]
        assert observed == {"R": 2}

    def test_removal_density(self, sample_cube_json, cube_hydrated):
        result = cube_balance(sample_cube_json, cube_hydrated, checks=["removal"])
        r = result["removal"]
        # Lightning Bolt + Swords to Plowshares + Counterspell + Deadly Rollick
        # + Fire // Ice are all removal. Nonland total = 10.
        assert r["removal_count"] >= 4
        assert r["nonland_total"] == 10

    def test_fixing_density_includes_duals(self, sample_cube_json, cube_hydrated):
        result = cube_balance(sample_cube_json, cube_hydrated, checks=["fixing"])
        f = result["fixing"]
        # Overgrown Tomb + Command Tower = 2 fixing lands
        assert f["fixing_count"] == 2

    def test_fixing_maindeck_curve_emits_estimate(
        self, sample_cube_json, cube_hydrated
    ):
        result = cube_balance(sample_cube_json, cube_hydrated, checks=["fixing"])
        assert result["fixing"]["expected_maindeck_rate_pct"] is not None

    def test_fixing_high_density_emits_note(self, cube_hydrated):
        """A cube over-saturated with fixing should get a symmetric warn."""
        # Cube with 2 nonland cards + 2 fixing lands = 50% fixing density.
        cube = {
            "cube_format": "vintage",
            "target_size": 4,
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},
                {"name": "Counterspell", "quantity": 1},
                {"name": "Overgrown Tomb", "quantity": 1},
                {"name": "Command Tower", "quantity": 1},
            ],
            "total_cards": 4,
        }
        result = cube_balance(cube, cube_hydrated, checks=["fixing"])
        notes = result["fixing"]["notes"]
        assert any("above" in n.lower() for n in notes), (
            f"expected 'above' warning in {notes}"
        )

    def test_commander_pool_check_present(
        self, sample_commander_cube_json, cube_hydrated
    ):
        result = cube_balance(
            sample_commander_cube_json, cube_hydrated, checks=["commander_pool"]
        )
        cp = result["commander_pool"]
        assert cp["present"] is True
        assert cp["total"] == 4

    def test_commander_pool_check_absent_without_pool(
        self, sample_cube_json, cube_hydrated
    ):
        result = cube_balance(
            sample_cube_json, cube_hydrated, checks=["commander_pool"]
        )
        assert result["commander_pool"]["present"] is False

    def test_informational_notes_roll_up(self, sample_cube_json, cube_hydrated):
        result = cube_balance(sample_cube_json, cube_hydrated)
        assert "summary_notes" in result
        assert isinstance(result["summary_notes"], list)


class TestCLIInterface:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_writes_output_file(self, sample_cube_json, cube_hydrated, tmp_path: Path):
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
        data = json.loads(out_path.read_text())
        assert "removal" in data
        assert "colors" in data

    def test_check_filter(self, sample_cube_json, cube_hydrated, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        out_path = tmp_path / "out.json"
        cube_path.write_text(json.dumps(sample_cube_json))
        hyd_path.write_text(json.dumps(cube_hydrated))
        result = runner.invoke(
            main,
            [
                str(cube_path),
                str(hyd_path),
                "--check",
                "removal",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(out_path.read_text())
        assert "removal" in data
        assert "colors" not in data
