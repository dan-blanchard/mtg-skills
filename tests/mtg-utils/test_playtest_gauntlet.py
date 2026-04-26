"""Tests for playtest-gauntlet (cube round-robin)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from mtg_utils.playtest import gauntlet_main


def _build_cube(tmp_path):
    cube = {
        "format": "modern_cube",
        "cards": [],
    }
    hydrated = []
    # 40 red 1-drops, 40 blue 2-drops, 40 black 3-drops, 40 red 4-drops + basics.
    for color, type_line, cmc in [
        ("R", "Creature — Goblin", 1),
        ("U", "Instant", 2),
        ("B", "Creature — Zombie", 3),
        ("R", "Sorcery", 4),
    ]:
        for i in range(40):
            name = f"{color}_{cmc}_{i}"
            cube["cards"].append({"name": name, "quantity": 1})
            hydrated.append(
                {
                    "name": name,
                    "type_line": type_line,
                    "oracle_text": "",
                    "mana_cost": f"{{{color}}}",
                    "cmc": cmc,
                    "power": "2",
                    "toughness": "2",
                    "color_identity": [color],
                    "produced_mana": [],
                }
            )
    for basic, color in [
        ("Plains", "W"),
        ("Island", "U"),
        ("Swamp", "B"),
        ("Mountain", "R"),
        ("Forest", "G"),
    ]:
        cube["cards"].append({"name": basic, "quantity": 30})
        hydrated.append(
            {
                "name": basic,
                "type_line": f"Basic Land — {basic}",
                "oracle_text": "",
                "mana_cost": "",
                "cmc": 0,
                "color_identity": [color],
                "produced_mana": [color],
            }
        )

    cube_path = tmp_path / "cube.json"
    hydrated_path = tmp_path / "hydrated.json"
    cube_path.write_text(json.dumps(cube))
    hydrated_path.write_text(json.dumps(hydrated))
    return cube_path, hydrated_path


class TestGauntletCLI:
    def test_runs_round_robin_with_4_archetypes(self, tmp_path, monkeypatch):
        cube_path, hydrated_path = _build_cube(tmp_path)

        # Mock phase to return canned win counts.
        def fake_run_duel(*_a, **_kw):
            return {
                "status": "ok",
                "wins_p0": 12,
                "wins_p1": 8,
                "draws": 0,
                "games": 20,
                "avg_turns": 6.5,
                "avg_duration_ms": 1200,
            }

        monkeypatch.setattr("mtg_utils._phase.run_duel", fake_run_duel)
        monkeypatch.setattr(
            "mtg_utils._phase.coverage_report",
            lambda names, **_kw: {
                "status": "full",
                "supported_pct": 1.0,
                "missing": [],
                "requested": len(names),
                "supported": len(names),
            },
        )

        out_path = tmp_path / "gauntlet.json"
        runner = CliRunner()
        result = runner.invoke(
            gauntlet_main,
            [
                str(cube_path),
                "--hydrated",
                str(hydrated_path),
                "--games-per-pair",
                "20",
                "--seed",
                "1",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output

        env = json.loads(out_path.read_text())
        assert env["mode"] == "gauntlet"
        # 4 archetypes => 6 pairs scheduled
        assert len(env["results"]["pairs"]) == 6
        # Each cell has wins_a, wins_b, draws.
        for pair in env["results"]["pairs"]:
            assert {"a", "b", "wins_a", "wins_b", "draws"}.issubset(pair.keys())
