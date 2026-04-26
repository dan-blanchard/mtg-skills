"""Tests for playtest-custom-format CLI."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from mtg_utils.playtest import custom_format_main


@pytest.fixture
def small_cube(tmp_path):
    cube = {"format": "shared_library_cube", "cards": []}
    hydrated = []
    for color in ["W", "U", "B", "R", "G"]:
        for i in range(16):
            name = f"{color}{i}"
            cube["cards"].append({"name": name, "quantity": 1})
            hydrated.append(
                {
                    "name": name,
                    "type_line": "Creature — Beast",
                    "oracle_text": "",
                    "mana_cost": f"{{{color}}}",
                    "cmc": (i % 5) + 1,
                    "color_identity": [color],
                    "produced_mana": [],
                }
            )
    cube_path = tmp_path / "cube.json"
    hydrated_path = tmp_path / "hydrated.json"
    cube_path.write_text(json.dumps(cube))
    hydrated_path.write_text(json.dumps(hydrated))
    return cube_path, hydrated_path


def test_custom_format_help():
    runner = CliRunner()
    result = runner.invoke(custom_format_main, ["--help"])
    assert result.exit_code == 0
    assert "format" in result.output.lower()


class TestCustomFormatCLI:
    def test_runs_shared_library_with_no_archetypes(self, small_cube, tmp_path):
        cube_path, hydrated_path = small_cube
        out = tmp_path / "report.json"
        runner = CliRunner()
        result = runner.invoke(
            custom_format_main,
            [
                str(cube_path),
                "--hydrated",
                str(hydrated_path),
                "--format-module",
                "shared_library",
                "--players",
                "4",
                "--turns",
                "3",
                "--games",
                "5",
                "--seed",
                "0",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        env = json.loads(out.read_text())
        assert env["mode"] == "custom_format"
        assert env["engine"] == "custom_format"
        assert env["seed"] == 0
        assert env["results"]["n_games"] == 5

    def test_unknown_format_module_errors(self, small_cube):
        cube_path, hydrated_path = small_cube
        runner = CliRunner()
        result = runner.invoke(
            custom_format_main,
            [
                str(cube_path),
                "--hydrated",
                str(hydrated_path),
                "--format-module",
                "no_such_format",
                "--turns",
                "3",
                "--games",
                "1",
            ],
        )
        assert result.exit_code != 0
        assert (
            "no_such_format" in result.output.lower()
            or "format" in result.output.lower()
        )

    def test_renders_markdown_to_stdout(self, small_cube, tmp_path):
        cube_path, hydrated_path = small_cube
        runner = CliRunner()
        result = runner.invoke(
            custom_format_main,
            [
                str(cube_path),
                "--hydrated",
                str(hydrated_path),
                "--format-module",
                "shared_library",
                "--turns",
                "3",
                "--games",
                "2",
                "--seed",
                "0",
            ],
        )
        assert result.exit_code == 0
        assert "# Custom-format playtest report" in result.output
