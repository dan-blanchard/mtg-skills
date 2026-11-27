"""Tests for playtest-draft (heuristic draft + per-deck goldfish)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

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


def _draft_in_a_process(cube_path, hydrated_path, out_path, hash_seed: str) -> dict:
    """``playtest-draft`` in a fresh interpreter under ``PYTHONHASHSEED=hash_seed``."""
    argv = [
        str(cube_path),
        "--hydrated",
        str(hydrated_path),
        "--pods",
        "2",
        "--players",
        "8",
        "--goldfish-games",
        "50",
        "--seed",
        "1",
        "--output",
        str(out_path),
    ]
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from mtg_utils.playtest import draft_main; draft_main(sys.argv[1:])",
            *argv,
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
    )
    return json.loads(out_path.read_text())["results"]


class TestDraftDeterminism:
    def test_a_colour_tie_breaks_the_same_way_in_every_process(
        self, tmp_path, small_cube
    ):
        # Pod 1 player 6 of this draft ties on two colours (W31 / B7 / G7): before
        # the WUBRG tie-break its colour-screw rate was 0.30 under PYTHONHASHSEED=0
        # and 0.34 under 7.
        cube_path, hydrated_path = small_cube
        first = _draft_in_a_process(cube_path, hydrated_path, tmp_path / "a.json", "0")
        second = _draft_in_a_process(cube_path, hydrated_path, tmp_path / "b.json", "7")
        assert first == second


#: The full ``results`` of a seeded two-pod draft over ``small_cube``. The draft is
#: reproducible across processes since colour ties break in WUBRG order.
_GOLDEN_DRAFT = {
    0: {
        "pods": 2,
        "players": 3,
        "decks": [
            {
                "pod": 0,
                "player": 0,
                "archetype": "Aggro",
                "build_status": "insufficient",
                "reason": "Only 21 on-color nonland cards available; need 23.",
            },
            {
                "pod": 0,
                "player": 1,
                "archetype": "Midrange",
                "build_status": "ok",
                "color_screw_rate": 0.5,
                "mean_lands_at_t4": 4.0,
                "mulligan_rate": {"7": 0.875, "6": 0.125, "5": 0.0, "4": 0.0},
            },
            {
                "pod": 0,
                "player": 2,
                "archetype": "Aggro",
                "build_status": "ok",
                "color_screw_rate": 0.375,
                "mean_lands_at_t4": 3.625,
                "mulligan_rate": {"7": 0.875, "6": 0.0, "5": 0.125, "4": 0.0},
            },
            {
                "pod": 1,
                "player": 0,
                "archetype": "Midrange",
                "build_status": "insufficient",
                "reason": "Only 22 on-color nonland cards available; need 23.",
            },
            {
                "pod": 1,
                "player": 1,
                "archetype": "Aggro",
                "build_status": "ok",
                "color_screw_rate": 0.25,
                "mean_lands_at_t4": 3.625,
                "mulligan_rate": {"7": 0.75, "6": 0.125, "5": 0.125, "4": 0.0},
            },
            {
                "pod": 1,
                "player": 2,
                "archetype": "Midrange",
                "build_status": "ok",
                "color_screw_rate": 0.5,
                "mean_lands_at_t4": 3.875,
                "mulligan_rate": {"7": 1.0, "6": 0.0, "5": 0.0, "4": 0.0},
            },
        ],
        "archetype_distribution": {"Aggro": 3, "Midrange": 3, "Control": 0, "Combo": 0},
    },
    5: {
        "pods": 2,
        "players": 3,
        "decks": [
            {
                "pod": 0,
                "player": 0,
                "archetype": "Aggro",
                "build_status": "ok",
                "color_screw_rate": 0.25,
                "mean_lands_at_t4": 3.875,
                "mulligan_rate": {"7": 0.75, "6": 0.25, "5": 0.0, "4": 0.0},
            },
            {
                "pod": 0,
                "player": 1,
                "archetype": "Midrange",
                "build_status": "ok",
                "color_screw_rate": 0.375,
                "mean_lands_at_t4": 3.75,
                "mulligan_rate": {"7": 0.875, "6": 0.125, "5": 0.0, "4": 0.0},
            },
            {
                "pod": 0,
                "player": 2,
                "archetype": "Midrange",
                "build_status": "ok",
                "color_screw_rate": 0.375,
                "mean_lands_at_t4": 3.875,
                "mulligan_rate": {"7": 0.875, "6": 0.125, "5": 0.0, "4": 0.0},
            },
            {
                "pod": 1,
                "player": 0,
                "archetype": "Midrange",
                "build_status": "insufficient",
                "reason": "Only 21 on-color nonland cards available; need 23.",
            },
            {
                "pod": 1,
                "player": 1,
                "archetype": "Aggro",
                "build_status": "ok",
                "color_screw_rate": 0.5,
                "mean_lands_at_t4": 3.875,
                "mulligan_rate": {"7": 0.875, "6": 0.125, "5": 0.0, "4": 0.0},
            },
            {
                "pod": 1,
                "player": 2,
                "archetype": "Midrange",
                "build_status": "ok",
                "color_screw_rate": 0.125,
                "mean_lands_at_t4": 3.75,
                "mulligan_rate": {"7": 0.875, "6": 0.125, "5": 0.0, "4": 0.0},
            },
        ],
        "archetype_distribution": {"Aggro": 2, "Midrange": 4, "Control": 0, "Combo": 0},
    },
}


class TestDraftGolden:
    @pytest.mark.parametrize("seed", sorted(_GOLDEN_DRAFT))
    def test_seeded_draft_is_pinned(self, tmp_path, small_cube, seed):
        cube_path, hydrated_path = small_cube
        out_path = tmp_path / "draft.json"
        result = CliRunner().invoke(
            draft_main,
            [
                str(cube_path),
                "--hydrated",
                str(hydrated_path),
                "--pods",
                "2",
                "--players",
                "3",
                "--packs",
                "2",
                "--pack-size",
                "15",
                "--goldfish-games",
                "8",
                "--goldfish-turns",
                "4",
                "--seed",
                str(seed),
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(out_path.read_text())["results"] == _GOLDEN_DRAFT[seed]
