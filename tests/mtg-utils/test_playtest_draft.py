"""Tests for playtest-draft (heuristic draft + per-deck goldfish)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from mtg_utils.playtest import draft_main


@pytest.fixture
def small_cube(tmp_path):
    cube = {"format": "modern_cube", "cards": []}
    hydrated = []
    for color in ["W", "U", "B", "R", "G"]:
        for i in range(72):
            name = f"{color}{i}"
            cube["cards"].append({"name": name, "quantity": 1})
            hydrated.append(
                {
                    "name": name,
                    "type_line": "Creature — Beast",
                    "oracle_text": "",
                    "mana_cost": f"{{{color}}}",
                    "cmc": (i % 5) + 1,
                    "power": "2",
                    "toughness": "2",
                    "color_identity": [color],
                    "produced_mana": [],
                }
            )
    cube_path = tmp_path / "cube.json"
    hydrated_path = tmp_path / "hydrated.json"
    cube_path.write_text(json.dumps(cube))
    hydrated_path.write_text(json.dumps(hydrated))
    return cube_path, hydrated_path


class TestDraftCLI:
    def test_runs_one_pod_8_players(self, tmp_path, small_cube):
        cube_path, hydrated_path = small_cube
        out_path = tmp_path / "draft.json"
        runner = CliRunner()
        result = runner.invoke(
            draft_main,
            [
                str(cube_path),
                "--hydrated",
                str(hydrated_path),
                "--pods",
                "1",
                "--players",
                "8",
                "--seed",
                "0",
                "--goldfish-games",
                "5",
                "--goldfish-turns",
                "4",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        env = json.loads(out_path.read_text())
        assert env["mode"] == "draft"
        assert env["engine"] == "goldfish"
        # 1 pod * 8 players = 8 deck reports.
        assert len(env["results"]["decks"]) == 8
