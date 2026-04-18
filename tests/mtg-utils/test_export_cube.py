"""Tests for export-cube CLI."""

import csv
import io
import json
from pathlib import Path

from click.testing import CliRunner

from mtg_utils.export_cube import CUBECOBRA_COLUMNS, export_csv, export_text, main


class TestExportCSV:
    def test_header_matches_cubecobra(self, sample_cube_json):
        output = export_csv(sample_cube_json)
        reader = csv.reader(io.StringIO(output))
        header = next(reader)
        assert header == CUBECOBRA_COLUMNS

    def test_one_row_per_copy(self, sample_cube_json):
        output = export_csv(sample_cube_json)
        rows = list(csv.DictReader(io.StringIO(output)))
        total = sum(int(c.get("quantity", 1)) for c in sample_cube_json["cards"])
        assert len(rows) == total

    def test_tags_preserved(self):
        cube = {
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1, "tags": ["aggro", "burn"]}
            ]
        }
        output = export_csv(cube)
        rows = list(csv.DictReader(io.StringIO(output)))
        assert "aggro" in rows[0]["Tags"]
        assert "burn" in rows[0]["Tags"]

    def test_color_category_preserved(self):
        cube = {"cards": [{"name": "Lightning Bolt", "quantity": 1, "cube_color": "R"}]}
        output = export_csv(cube)
        rows = list(csv.DictReader(io.StringIO(output)))
        assert rows[0]["Color Category"] == "R"
        assert rows[0]["Color"] == "R"


class TestExportText:
    def test_basic_list(self, sample_cube_json):
        output = export_text(sample_cube_json)
        assert "1 Lightning Bolt" in output
        assert "1 Swords to Plowshares" in output

    def test_commander_section(self, sample_commander_cube_json):
        output = export_text(sample_commander_cube_json)
        assert "//Commander" in output
        assert "//Mainboard" in output
        assert "1 Atraxa, Praetors' Voice" in output


class TestCLIInterface:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_csv_to_file(self, sample_cube_json, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        out_path = tmp_path / "cube.csv"
        cube_path.write_text(json.dumps(sample_cube_json))
        result = runner.invoke(
            main, [str(cube_path), "--format", "csv", "--output", str(out_path)]
        )
        assert result.exit_code == 0, result.output
        text = out_path.read_text()
        assert "name,CMC" in text

    def test_text_to_stdout(self, sample_cube_json, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        cube_path.write_text(json.dumps(sample_cube_json))
        result = runner.invoke(main, [str(cube_path), "--format", "text"])
        assert result.exit_code == 0
        assert "1 Lightning Bolt" in result.output

    def test_refuses_overwrite(self, sample_cube_json, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        cube_path.write_text(json.dumps(sample_cube_json))
        result = runner.invoke(main, [str(cube_path), "--output", str(cube_path)])
        assert result.exit_code != 0

    def test_csv_warns_when_commander_pool_present(
        self, sample_commander_cube_json, tmp_path: Path
    ):
        """CSV export can't round-trip the commander pool — warn the user."""
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        out_path = tmp_path / "cube.csv"
        cube_path.write_text(json.dumps(sample_commander_cube_json))
        result = runner.invoke(
            main, [str(cube_path), "--format", "csv", "--output", str(out_path)]
        )
        assert result.exit_code == 0, result.output
        # Warning goes to stderr (mix_stderr default True merges them).
        assert "commander pool" in result.output.lower()

    def test_csv_silent_when_no_commander_pool(self, sample_cube_json, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        out_path = tmp_path / "cube.csv"
        cube_path.write_text(json.dumps(sample_cube_json))
        result = runner.invoke(
            main, [str(cube_path), "--format", "csv", "--output", str(out_path)]
        )
        assert result.exit_code == 0
        assert "commander pool" not in result.output.lower()
