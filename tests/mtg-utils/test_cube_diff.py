"""Tests for cube-diff CLI."""

import copy
import json
from pathlib import Path

from click.testing import CliRunner

from mtg_utils.cube_diff import cube_diff, main


class TestCubeDiff:
    def test_no_changes(self, sample_cube_json):
        result = cube_diff(sample_cube_json, sample_cube_json)
        assert result["added"] == []
        assert result["removed"] == []
        assert result["changed"] == []
        assert result["size_delta"] == 0

    def test_detect_additions(self, sample_cube_json):
        new = copy.deepcopy(sample_cube_json)
        new["cards"].append({"name": "Dark Ritual", "quantity": 1})
        # Note: Dark Ritual is already in sample_cube_json; picking one that isn't.
        # Use Wildfire instead.
        new["cards"] = [c for c in new["cards"] if c["name"] != "Dark Ritual"] + [
            *[c for c in sample_cube_json["cards"] if c["name"] == "Dark Ritual"],
            {"name": "Wildfire", "quantity": 1},
        ]
        result = cube_diff(sample_cube_json, new)
        added_names = {a["name"] for a in result["added"]}
        assert "Wildfire" in added_names

    def test_detect_removals(self, sample_cube_json):
        new = copy.deepcopy(sample_cube_json)
        new["cards"] = [c for c in new["cards"] if c["name"] != "Lightning Bolt"]
        result = cube_diff(sample_cube_json, new)
        removed_names = {r["name"] for r in result["removed"]}
        assert "Lightning Bolt" in removed_names
        assert result["size_delta"] == -1

    def test_detect_quantity_changes(self, sample_cube_json):
        new = copy.deepcopy(sample_cube_json)
        for c in new["cards"]:
            if c["name"] == "Lightning Bolt":
                c["quantity"] = 3
        result = cube_diff(sample_cube_json, new)
        assert len(result["changed"]) == 1
        ch = result["changed"][0]
        assert ch["name"] == "Lightning Bolt"
        assert ch["old_quantity"] == 1
        assert ch["new_quantity"] == 3

    def test_metrics_section(self, sample_cube_json, cube_hydrated):
        new = copy.deepcopy(sample_cube_json)
        new["cards"] = [c for c in new["cards"] if c["name"] != "Lightning Bolt"]
        result = cube_diff(
            sample_cube_json,
            new,
            old_hydrated=cube_hydrated,
            new_hydrated=cube_hydrated,
            include_metrics=True,
        )
        assert "metrics" in result
        assert "color_counts_delta" in result["metrics"]
        # Removing Lightning Bolt should decrement R by 1
        assert result["metrics"]["color_counts_delta"].get("R") == -1

    def test_commander_pool_diff(self, sample_commander_cube_json):
        new = copy.deepcopy(sample_commander_cube_json)
        new["commander_pool"] = [
            c for c in new["commander_pool"] if c["name"] != "Atraxa, Praetors' Voice"
        ]
        result = cube_diff(sample_commander_cube_json, new)
        removed_names = {r["name"] for r in result["removed"]}
        assert "Atraxa, Praetors' Voice" in removed_names


class TestCLIInterface:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_runs_without_metrics(self, sample_cube_json, tmp_path: Path):
        runner = CliRunner()
        old_path = tmp_path / "old.json"
        new_path = tmp_path / "new.json"
        old_path.write_text(json.dumps(sample_cube_json))
        new_path.write_text(json.dumps(sample_cube_json))
        result = runner.invoke(main, [str(old_path), str(new_path)])
        assert result.exit_code == 0, result.output
        assert "Full JSON:" in result.output

    def test_metrics_requires_hydrated(self, sample_cube_json, tmp_path: Path):
        runner = CliRunner()
        old_path = tmp_path / "old.json"
        new_path = tmp_path / "new.json"
        old_path.write_text(json.dumps(sample_cube_json))
        new_path.write_text(json.dumps(sample_cube_json))
        result = runner.invoke(main, [str(old_path), str(new_path), "--metrics"])
        assert result.exit_code != 0
        assert "metrics" in result.output.lower()
