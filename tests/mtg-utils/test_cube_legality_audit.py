"""Tests for cube-legality-audit CLI."""

import json
from pathlib import Path

from click.testing import CliRunner

from mtg_utils.cube_legality_audit import cube_legality_audit, main


class TestRarityFilter:
    def test_pauper_flags_rare_card(self, cube_hydrated):
        cube = {
            "cube_format": "pauper",
            "target_size": 2,
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},  # common
                {"name": "Wildfire", "quantity": 1},  # rare
            ],
            "total_cards": 2,
        }
        result = cube_legality_audit(cube, cube_hydrated)
        # Pauper uses Scryfall's `legalities.pauper`; fixture cards don't have
        # pauper legality populated, so they get warns (not errors).
        assert result["warn_count"] >= 1
        names = {v["card"] for v in result["violations"]}
        assert "Wildfire" in names or "Lightning Bolt" in names

    def test_pauper_uses_scryfall_legality_when_available(self, cube_hydrated):
        """When a card has `legalities.pauper == 'legal'`, no violation."""
        # Inject pauper legality onto Lightning Bolt for this test.
        patched = [
            {**c, "legalities": {**(c.get("legalities") or {}), "pauper": "legal"}}
            if c["name"] == "Lightning Bolt"
            else c
            for c in cube_hydrated
        ]
        cube = {
            "cube_format": "pauper",
            "target_size": 1,
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
            "total_cards": 1,
        }
        result = cube_legality_audit(cube, patched)
        bolt_violations = [
            v for v in result["violations"] if v["card"] == "Lightning Bolt"
        ]
        assert bolt_violations == []

    def test_peasant_warns_on_rare_default_printing(self, cube_hydrated):
        """Peasant has no Scryfall legality; falls back to default-rarity warn."""
        cube = {
            "cube_format": "peasant",
            "target_size": 2,
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},  # common — OK
                {"name": "Wildfire", "quantity": 1},  # rare — warn
            ],
            "total_cards": 2,
        }
        result = cube_legality_audit(cube, cube_hydrated)
        wildfire_issues = [v for v in result["violations"] if v["card"] == "Wildfire"]
        assert len(wildfire_issues) == 1
        assert wildfire_issues[0]["severity"] == "warn"

    def test_vintage_no_rarity_filter(self, cube_hydrated):
        cube = {
            "cube_format": "vintage",
            "target_size": 2,
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},
                {"name": "Wildfire", "quantity": 1},
            ],
            "total_cards": 2,
        }
        result = cube_legality_audit(cube, cube_hydrated)
        # No rarity filter → no rarity violations
        rarity_issues = [
            v
            for v in result["violations"]
            if "rarity" in v["reason"].lower() or "printing" in v["reason"].lower()
        ]
        assert rarity_issues == []


class TestBanList:
    def test_unpowered_flags_power_nine(self, cube_hydrated):
        # Inject Black Lotus onto hydrated data so the name resolves.
        lotus = {
            "name": "Black Lotus",
            "cmc": 0.0,
            "type_line": "Artifact",
            "oracle_text": "{T}, Sacrifice this artifact: Add three mana of any one color.",
            "colors": [],
            "color_identity": [],
            "rarity": "special",
            "legalities": {"vintage": "restricted"},
        }
        cube = {
            "cube_format": "unpowered",
            "target_size": 1,
            "cards": [{"name": "Black Lotus", "quantity": 1}],
            "total_cards": 1,
        }
        result = cube_legality_audit(cube, [*cube_hydrated, lotus])
        errors = [v for v in result["violations"] if v["severity"] == "error"]
        assert any(v["card"] == "Black Lotus" for v in errors)

    def test_vintage_allows_power_nine(self, cube_hydrated):
        lotus = {
            "name": "Black Lotus",
            "cmc": 0.0,
            "type_line": "Artifact",
            "oracle_text": "{T}, Sacrifice this artifact: Add three mana of any one color.",
            "colors": [],
            "color_identity": [],
            "rarity": "special",
            "legalities": {"vintage": "restricted"},
        }
        cube = {
            "cube_format": "vintage",
            "target_size": 1,
            "cards": [{"name": "Black Lotus", "quantity": 1}],
            "total_cards": 1,
        }
        result = cube_legality_audit(cube, [*cube_hydrated, lotus])
        errors = [v for v in result["violations"] if v["severity"] == "error"]
        assert not any(v["card"] == "Black Lotus" for v in errors)


class TestLegalityKey:
    def test_modern_flags_illegal_card(self, cube_hydrated):
        """A card with legalities.modern != 'legal' gets an error."""
        # Inject a "Mana Drain" style legacy-legal but modern-illegal card.
        illegal_card = {
            "name": "Mana Drain",
            "cmc": 2.0,
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
            "colors": ["U"],
            "color_identity": ["U"],
            "rarity": "rare",
            "legalities": {"modern": "not_legal", "legacy": "legal"},
        }
        cube = {
            "cube_format": "modern",
            "target_size": 1,
            "cards": [{"name": "Mana Drain", "quantity": 1}],
            "total_cards": 1,
        }
        result = cube_legality_audit(cube, [*cube_hydrated, illegal_card])
        errors = [v for v in result["violations"] if v["severity"] == "error"]
        assert any("not modern-legal" in v["reason"] for v in errors)

    def test_missing_legality_is_warn_not_error(self, cube_hydrated):
        """If hydrated data lacks the legality key, emit warn not error."""
        no_legality = {
            "name": "Mystery Card",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Do something.",
            "colors": ["U"],
            "color_identity": ["U"],
            "rarity": "rare",
            # No "legalities" field at all
        }
        cube = {
            "cube_format": "modern",
            "target_size": 1,
            "cards": [{"name": "Mystery Card", "quantity": 1}],
            "total_cards": 1,
        }
        result = cube_legality_audit(cube, [*cube_hydrated, no_legality])
        # Warn, not error (ambiguous — we don't know)
        mystery = [v for v in result["violations"] if v["card"] == "Mystery Card"]
        assert all(v["severity"] == "warn" for v in mystery)


class TestPDHCommanderPool:
    def test_pdh_flags_rare_commander(self, cube_hydrated):
        # Atraxa is mythic, should violate PDH's commander_pool_rarity_filter (uncommon)
        cube = {
            "cube_format": "pdh",
            "target_size": 2,
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
            "commander_pool": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
            "total_cards": 2,
        }
        result = cube_legality_audit(cube, cube_hydrated)
        cmd_issues = [
            v for v in result["violations"] if v["section"] == "commander_pool"
        ]
        assert any(v["card"] == "Atraxa, Praetors' Voice" for v in cmd_issues)


class TestNoCubeViolations:
    def test_clean_vintage_cube(self, sample_cube_json, cube_hydrated):
        result = cube_legality_audit(sample_cube_json, cube_hydrated)
        # Vintage has no legality_key, no rarity_filter, no ban_list —
        # only possible violations are "not found in hydrated data."
        errors = [v for v in result["violations"] if v["severity"] == "error"]
        assert errors == []


class TestCLIInterface:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "legality" in result.output.lower() or "rarity" in result.output.lower()

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
        assert "violations" in data

    def test_unknown_cube_format_errors(self, cube_hydrated, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        cube_path.write_text(
            json.dumps({"cube_format": "bogus", "cards": [], "target_size": 0})
        )
        hyd_path.write_text(json.dumps(cube_hydrated))
        result = runner.invoke(main, [str(cube_path), str(hyd_path)])
        assert result.exit_code != 0
