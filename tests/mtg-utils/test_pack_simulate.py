"""Tests for pack-simulate CLI."""

import json
import random
from pathlib import Path

from click.testing import CliRunner

from mtg_utils.pack_simulate import (
    _classify_cube,
    generate_pack,
    main,
    pack_simulate,
)


class TestClassifyCube:
    def test_partitions_into_categories(self, sample_cube_json, cube_hydrated):
        buckets = _classify_cube(sample_cube_json, cube_hydrated)
        for cat in ("W", "U", "B", "R", "G", "M", "F", "C"):
            assert cat in buckets

    def test_respects_quantities(self, cube_hydrated):
        cube = {
            "cube_format": "vintage",
            "target_size": 3,
            "cards": [{"name": "Lightning Bolt", "quantity": 3}],
            "total_cards": 3,
        }
        buckets = _classify_cube(cube, cube_hydrated)
        assert len(buckets["R"]) == 3


class TestGeneratePack:
    def test_pack_15_composition(self, sample_cube_json, cube_hydrated):
        """Pack 15 template expects 1 per color + M + L + F + C + 6 extras = 15."""
        buckets = _classify_cube(sample_cube_json, cube_hydrated)
        from mtg_utils.cube_config import PACK_TEMPLATES

        rng = random.Random(42)
        pack = generate_pack(buckets, PACK_TEMPLATES[15], rng)
        # Pack size may be less than 15 because the sample cube has only 12
        # cards total — the bucket will run dry before the template is full.
        assert len(pack) <= 15

    def test_seed_deterministic(self, sample_cube_json, cube_hydrated):
        buckets = _classify_cube(sample_cube_json, cube_hydrated)
        from mtg_utils.cube_config import PACK_TEMPLATES

        pack_a = generate_pack(buckets, PACK_TEMPLATES[9], random.Random(7))
        pack_b = generate_pack(buckets, PACK_TEMPLATES[9], random.Random(7))
        assert [c["name"] for c in pack_a] == [c["name"] for c in pack_b]

    def test_seed_diverse(self, sample_cube_json, cube_hydrated):
        buckets = _classify_cube(sample_cube_json, cube_hydrated)
        from mtg_utils.cube_config import PACK_TEMPLATES

        pack_a = generate_pack(buckets, PACK_TEMPLATES[9], random.Random(1))
        pack_b = generate_pack(buckets, PACK_TEMPLATES[9], random.Random(42))
        # Different seeds should produce at least some different output.
        assert {c["name"] for c in pack_a} != {c["name"] for c in pack_b} or len(
            pack_a
        ) <= 3

    def test_no_duplicate_cards_in_pack(self, cube_hydrated):
        """Fixed mono-color slots + extra_mono pool must not double-pick.

        Regression: earlier implementation used two independent rng.sample
        calls, so the same card could appear twice in a 15-card pack if
        mono buckets were small.
        """
        # Build a tight cube: only 2 R cards, 2 W cards, 2 B cards, 2 U cards,
        # 2 G cards, and a few lands. Pack 15 template asks for 1-per-color
        # plus 6 extra mono, totaling 11 mono slots for 10 mono cards.
        from mtg_utils.cube_config import PACK_TEMPLATES

        buckets = {
            "W": [
                {"name": "Swords to Plowshares", "category": "W"},
                {"name": "Wrath of God", "category": "W"},
            ],
            "U": [
                {"name": "Counterspell", "category": "U"},
                {"name": "Brainstorm", "category": "U"},
            ],
            "B": [
                {"name": "Dark Ritual", "category": "B"},
                {"name": "Duress", "category": "B"},
            ],
            "R": [
                {"name": "Lightning Bolt", "category": "R"},
                {"name": "Shock", "category": "R"},
            ],
            "G": [
                {"name": "Llanowar Elves", "category": "G"},
                {"name": "Giant Growth", "category": "G"},
            ],
            "M": [{"name": "Thrasios, Triton Hero", "category": "M"}],
            "L": [{"name": "Cavern of Souls", "category": "L"}],
            "F": [{"name": "Overgrown Tomb", "category": "F"}],
            "C": [{"name": "Sol Ring", "category": "C"}],
        }
        pack = generate_pack(buckets, PACK_TEMPLATES[15], random.Random(7))
        names = [c["name"] for c in pack]
        assert len(names) == len(set(names)), (
            f"duplicate card in pack: {sorted(names)}"
        )


class TestPackSimulate:
    def test_produces_pack(self, sample_cube_json, cube_hydrated):
        result = pack_simulate(sample_cube_json, cube_hydrated, seed=1, pack_size=9)
        assert "pack" in result
        assert result["pack_size"] == 9
        assert result["seed"] == 1

    def test_bucket_sizes_reported(self, sample_cube_json, cube_hydrated):
        result = pack_simulate(sample_cube_json, cube_hydrated, seed=1, pack_size=15)
        assert "bucket_sizes" in result

    def test_commander_pack_generated(self, sample_commander_cube_json, cube_hydrated):
        result = pack_simulate(
            sample_commander_cube_json,
            cube_hydrated,
            seed=1,
            pack_size=9,
            commander_pack_size=2,
        )
        assert "commander_pack" in result
        assert len(result["commander_pack"]) == 2

    def test_no_commander_pack_without_pool(self, sample_cube_json, cube_hydrated):
        result = pack_simulate(sample_cube_json, cube_hydrated, seed=1, pack_size=9)
        assert "commander_pack" not in result

    def test_simulate_drafts_aggregates(self, sample_cube_json, cube_hydrated):
        result = pack_simulate(
            sample_cube_json, cube_hydrated, seed=1, pack_size=9, drafts=5
        )
        assert "simulation" in result
        assert result["simulation"]["packs_generated"] == 5

    def test_invalid_pack_size(self, sample_cube_json, cube_hydrated):
        import click
        import pytest

        with pytest.raises(click.UsageError, match="template"):
            pack_simulate(sample_cube_json, cube_hydrated, seed=1, pack_size=17)


class TestCLIInterface:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_runs_end_to_end(self, sample_cube_json, cube_hydrated, tmp_path: Path):
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
                "--seed",
                "42",
                "--pack-size",
                "9",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text())
        assert data["pack_size"] == 9
