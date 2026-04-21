"""Tests for archetype-audit CLI."""

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from mtg_utils.archetype_audit import (
    _parse_theme_flag,
    archetype_audit,
    main,
)
from mtg_utils.theme_presets import Preset


def _adhoc_preset(name: str, pattern: re.Pattern) -> Preset:
    """Wrap a raw pattern in a Preset for the tests below."""
    return Preset(name=name, description="test", patterns=(pattern,))


class TestParseThemeFlag:
    def test_valid_spec(self):
        name, preset = _parse_theme_flag("tokens=create .* creature token")
        assert name == "tokens"
        assert preset.matches(
            {"oracle_text": "Create 2 1/1 white Soldier creature tokens."}
        )

    def test_case_insensitive(self):
        _, preset = _parse_theme_flag("burn=deals? \\d+ damage")
        assert preset.matches({"oracle_text": "Deals 3 damage to any target."})

    def test_missing_equals_rejected(self):
        with pytest.raises(Exception, match="name=regex"):
            _parse_theme_flag("just-a-name")

    def test_invalid_regex_rejected(self):
        with pytest.raises(Exception, match="Invalid regex"):
            _parse_theme_flag("bad=[unclosed")


class TestArchetypeAudit:
    def test_counts_matching_cards(self, sample_cube_json, cube_hydrated):
        themes = {
            "burn": _adhoc_preset(
                "burn", re.compile(r"deals?\s+\d+\s+damage", re.IGNORECASE)
            ),
        }
        result = archetype_audit(sample_cube_json, cube_hydrated, themes)
        # Lightning Bolt matches "deals 3 damage"; Fire // Ice matches "deals 2 damage"
        assert result["themes"]["burn"]["total"] >= 1

    def test_counter_spell_theme(self, sample_cube_json, cube_hydrated):
        themes = {
            "control": _adhoc_preset(
                "control", re.compile(r"counter target", re.IGNORECASE)
            ),
        }
        result = archetype_audit(sample_cube_json, cube_hydrated, themes)
        assert result["themes"]["control"]["total"] >= 1

    def test_empty_theme_produces_orphan_note(self, cube_hydrated):
        cube = {
            "cube_format": "vintage",
            "target_size": 2,
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
            "total_cards": 1,
        }
        themes = {
            "burn": _adhoc_preset("burn", re.compile(r"damage", re.IGNORECASE)),
        }
        result = archetype_audit(cube, cube_hydrated, themes, min_density=5)
        notes = result["themes"]["burn"]["notes"]
        # Total is 1, below threshold of 5 → should emit a note
        assert any("below" in n.lower() for n in notes)

    def test_bridge_cards_identified(self, sample_cube_json, cube_hydrated):
        # STP matches both "removal" (target creature) and "exile" (exile target).
        themes = {
            "removal": _adhoc_preset(
                "removal", re.compile(r"target\s+(?:creature|spell)", re.IGNORECASE)
            ),
            "exile": _adhoc_preset("exile", re.compile(r"\bexile\b", re.IGNORECASE)),
        }
        result = archetype_audit(sample_cube_json, cube_hydrated, themes)
        bridges = result["bridge_cards"]
        bridge_names = {b["name"] for b in bridges}
        assert "Swords to Plowshares" in bridge_names

    def test_by_guild_distribution(self, sample_cube_json, cube_hydrated):
        themes = {
            "burn": _adhoc_preset("burn", re.compile(r"damage", re.IGNORECASE)),
        }
        result = archetype_audit(sample_cube_json, cube_hydrated, themes)
        # Cards without color identity (colorless) count toward every guild;
        # Lightning Bolt is R so supports RW, RG, BR, UR.
        by_guild = result["themes"]["burn"]["by_guild"]
        assert any("R" in label for label in by_guild)

    def test_min_density_override(self, cube_hydrated):
        cube = {
            "cube_format": "vintage",
            "target_size": 3,
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},
                {"name": "Wildfire", "quantity": 1},
            ],
            "total_cards": 2,
        }
        themes = {
            "burn": _adhoc_preset("burn", re.compile(r"damage", re.IGNORECASE)),
        }
        # With default threshold 3, 2 is below
        default = archetype_audit(cube, cube_hydrated, themes)
        assert any("below" in n.lower() for n in default["themes"]["burn"]["notes"])
        # With override 1, 2 is above
        relaxed = archetype_audit(cube, cube_hydrated, themes, min_density=1)
        assert not any(
            "below LP minimum" in n.lower() for n in relaxed["themes"]["burn"]["notes"]
        )


class TestCLIInterface:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_requires_themes(self, sample_cube_json, cube_hydrated, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        cube_path.write_text(json.dumps(sample_cube_json))
        hyd_path.write_text(json.dumps(cube_hydrated))
        result = runner.invoke(main, [str(cube_path), str(hyd_path)])
        assert result.exit_code != 0
        assert "theme" in result.output.lower()

    def test_theme_flag_runs(self, sample_cube_json, cube_hydrated, tmp_path: Path):
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
                "--theme",
                "burn=deals? \\d+ damage",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text())
        assert "burn" in data["themes"]

    def test_multiple_themes(self, sample_cube_json, cube_hydrated, tmp_path: Path):
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
                "--theme",
                "burn=damage",
                "--theme",
                "control=counter target",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(out_path.read_text())
        assert "burn" in data["themes"]
        assert "control" in data["themes"]

    def test_list_presets_works_without_cube_args(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--list-presets"])
        assert result.exit_code == 0, result.output
        assert "flying" in result.output
        assert "self-mill" in result.output
        assert "removal" in result.output

    def test_preset_flag_loads_named_preset(
        self, sample_cube_json, cube_hydrated, tmp_path: Path
    ):
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
                "--preset",
                "removal",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text())
        assert "removal" in data["themes"]
        # Sample cube has Lightning Bolt, Swords to Plowshares, Counterspell —
        # all match removal.
        assert data["themes"]["removal"]["total"] >= 3

    def test_preset_flag_unknown_name_rejected(
        self, sample_cube_json, cube_hydrated, tmp_path: Path
    ):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        cube_path.write_text(json.dumps(sample_cube_json))
        hyd_path.write_text(json.dumps(cube_hydrated))
        result = runner.invoke(
            main,
            [
                str(cube_path),
                str(hyd_path),
                "--preset",
                "not-a-real-preset",
            ],
        )
        assert result.exit_code != 0
        assert "unknown preset" in result.output.lower()

    def test_preset_and_theme_combine(
        self, sample_cube_json, cube_hydrated, tmp_path: Path
    ):
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
                "--preset",
                "removal",
                "--theme",
                "custom=damage",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text())
        assert "removal" in data["themes"]
        assert "custom" in data["themes"]

    def test_show_matches_emits_card_names(
        self, sample_cube_json, cube_hydrated, tmp_path: Path
    ):
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
                "--preset",
                "removal",
                "--show-matches",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        # --show-matches adds a "matches:" line to the text report.
        assert "matches:" in result.output
