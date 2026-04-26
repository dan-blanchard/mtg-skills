"""Tests for archetype-audit CLI."""

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from mtg_utils.archetype_audit import (
    _build_kindred_preset,
    _parse_rewrite_flag,
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


class TestIncludeCommanders:
    """--include-commanders pulls entries from 'commanders' (parse-deck) and
    'commander_pool' (parse-cube) into the match loop."""

    def test_commanders_excluded_by_default(self, cube_hydrated):
        deck = {
            "cube_format": "commander",
            "cards": [{"name": "Viscera Seer", "quantity": 1}],
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
        }
        # Both Korvold and Viscera Seer have "sacrifice" in their oracle.
        themes = {
            "sac": _adhoc_preset("sac", re.compile(r"sacrifice", re.IGNORECASE)),
        }
        result = archetype_audit(deck, cube_hydrated, themes)
        assert result["themes"]["sac"]["total"] == 1
        assert "Korvold, Fae-Cursed King" not in result["themes"]["sac"]["cards"]

    def test_commanders_included_when_flag_set(self, cube_hydrated):
        deck = {
            "cube_format": "commander",
            "cards": [{"name": "Viscera Seer", "quantity": 1}],
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
        }
        themes = {
            "sac": _adhoc_preset("sac", re.compile(r"sacrifice", re.IGNORECASE)),
        }
        result = archetype_audit(deck, cube_hydrated, themes, include_commanders=True)
        assert result["themes"]["sac"]["total"] == 2
        assert "Korvold, Fae-Cursed King" in result["themes"]["sac"]["cards"]

    def test_overlap_between_commanders_and_cards_is_not_double_counted(
        self, cube_hydrated
    ):
        # Hand-edited / malformed deck JSON: the commander appears in BOTH
        # 'commanders' and 'cards'. With --include-commanders, this should
        # still count the commander once, not twice.
        deck = {
            "cube_format": "commander",
            "cards": [
                {"name": "Korvold, Fae-Cursed King", "quantity": 1},
                {"name": "Viscera Seer", "quantity": 1},
            ],
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
        }
        themes = {
            "sac": _adhoc_preset("sac", re.compile(r"sacrifice", re.IGNORECASE)),
        }
        result = archetype_audit(deck, cube_hydrated, themes, include_commanders=True)
        # Korvold + Viscera Seer = 2 unique cards, both match "sacrifice".
        # Without dedup, Korvold would be counted twice → total=3.
        assert result["themes"]["sac"]["total"] == 2
        assert result["themes"]["sac"]["cards"].count("Korvold, Fae-Cursed King") == 1

    def test_commander_pool_included_for_pdh_cubes(
        self, sample_commander_cube_json, cube_hydrated
    ):
        # Atraxa and Korvold live in commander_pool and both have "Flying"
        # in their oracle; the main cards list has neither.
        themes = {
            "fly": _adhoc_preset("fly", re.compile(r"\bflying\b", re.IGNORECASE)),
        }
        default = archetype_audit(sample_commander_cube_json, cube_hydrated, themes)
        with_flag = archetype_audit(
            sample_commander_cube_json,
            cube_hydrated,
            themes,
            include_commanders=True,
        )
        assert with_flag["themes"]["fly"]["total"] > default["themes"]["fly"]["total"]


class TestKindredFactory:
    """--kindred <type> builds a parametric preset matching creatures of that
    type plus oracle-text payoffs."""

    def test_matches_creature_via_type_line(self):
        _, preset = _build_kindred_preset("Elf")
        # Type line match fires even if oracle doesn't mention "Elf"
        card = {
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
            "keywords": [],
        }
        assert preset.matches(card)

    def test_matches_payoff_via_oracle(self):
        _, preset = _build_kindred_preset("Elf")
        # Non-Elf card whose oracle references Elves (tribal payoff).
        card = {
            "type_line": "Creature — Human Warrior",
            "oracle_text": "Other Elves you control get +1/+1.",
            "keywords": [],
        }
        assert preset.matches(card)

    def test_irregular_plural_matches(self):
        _, preset = _build_kindred_preset("Elf")
        # "Elves" — the irregular plural — must match
        card = {
            "type_line": "Instant",
            "oracle_text": "Until end of turn, Elves you control gain flying.",
            "keywords": [],
        }
        assert preset.matches(card)

    def test_regular_plural_matches(self):
        _, preset = _build_kindred_preset("Goblin")
        card = {
            "type_line": "Instant",
            "oracle_text": "Create three 1/1 red Goblin creature tokens.",
            "keywords": [],
        }
        assert preset.matches(card)

    def test_non_matching_card_rejected(self):
        _, preset = _build_kindred_preset("Elf")
        card = {
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
            "keywords": [],
        }
        assert not preset.matches(card)

    def test_changeling_counts_as_every_type(self):
        # Changeling cards (Mistform Ultimus, Universal Automaton, etc.)
        # count as every creature type per CR 702.73, so they should
        # match every kindred preset regardless of the type line or oracle.
        _, elf = _build_kindred_preset("Elf")
        _, goblin = _build_kindred_preset("Goblin")
        mistform = {
            "type_line": "Creature — Shapeshifter",
            "oracle_text": ("Changeling (This card is every creature type.)"),
            "keywords": ["Changeling"],
        }
        assert elf.matches(mistform)
        assert goblin.matches(mistform)

    def test_empty_string_rejected(self):
        with pytest.raises(Exception, match="cannot be empty"):
            _build_kindred_preset("   ")

    def test_preset_name_is_lowercase(self):
        name, _ = _build_kindred_preset("Goblin")
        assert name == "kindred-goblin"

    def test_cli_kindred_flag(self, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        out_path = tmp_path / "out.json"
        # Llanowar Elves has type_line "Creature — Elf Druid" in the
        # cube_hydrated fixture — it should match via type_patterns.
        cube = {
            "cube_format": "vintage",
            "cards": [
                {"name": "Llanowar Elves", "quantity": 1},
                {"name": "Lightning Bolt", "quantity": 1},
            ],
        }
        hydrated = [
            {
                "name": "Llanowar Elves",
                "type_line": "Creature — Elf Druid",
                "oracle_text": "{T}: Add {G}.",
                "keywords": [],
                "color_identity": ["G"],
            },
            {
                "name": "Lightning Bolt",
                "type_line": "Instant",
                "oracle_text": "Lightning Bolt deals 3 damage to any target.",
                "keywords": [],
                "color_identity": ["R"],
            },
        ]
        cube_path.write_text(json.dumps(cube))
        hyd_path.write_text(json.dumps(hydrated))
        result = runner.invoke(
            main,
            [
                str(cube_path),
                str(hyd_path),
                "--kindred",
                "Elf",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text())
        assert "kindred-elf" in data["themes"]
        assert data["themes"]["kindred-elf"]["total"] == 1
        assert "Llanowar Elves" in data["themes"]["kindred-elf"]["cards"]


class TestRewriteRule:
    """--rewrite "source -> dest" widens dest's matcher with an OR against
    source's preset. Captures commander-induced archetype shifts."""

    def test_parse_valid(self):
        source, dest = _parse_rewrite_flag("kindred-elf -> drain")
        assert source == "kindred-elf"
        assert dest == "drain"

    def test_parse_missing_arrow_rejected(self):
        with pytest.raises(Exception, match="source -> dest"):
            _parse_rewrite_flag("justone")

    def test_parse_empty_side_rejected(self):
        with pytest.raises(Exception, match="empty"):
            _parse_rewrite_flag(" -> dest")
        with pytest.raises(Exception, match="empty"):
            _parse_rewrite_flag("source ->")

    def test_rewrite_adds_source_matches_to_dest(self):
        # Synthetic "elf -> drain" rewrite:
        #   - drain theme: matches cards with "drain" in oracle (nothing
        #     in our test pool)
        #   - elf theme: matches creatures of type Elf
        # With the rewrite, elves should count toward drain.
        cube = {
            "cube_format": "vintage",
            "cards": [
                {"name": "Llanowar Elves", "quantity": 1},
                {"name": "Lightning Bolt", "quantity": 1},
            ],
        }
        hydrated = [
            {
                "name": "Llanowar Elves",
                "type_line": "Creature — Elf Druid",
                "oracle_text": "{T}: Add {G}.",
                "keywords": [],
                "color_identity": ["G"],
            },
            {
                "name": "Lightning Bolt",
                "type_line": "Instant",
                "oracle_text": "Lightning Bolt deals 3 damage to any target.",
                "keywords": [],
                "color_identity": ["R"],
            },
        ]
        elf_name, elf_preset = _build_kindred_preset("Elf")
        drain_preset = _adhoc_preset(
            "drain", re.compile(r"loses? \d+ life", re.IGNORECASE)
        )
        themes = {elf_name: elf_preset, "drain": drain_preset}

        without_rewrite = archetype_audit(cube, hydrated, themes)
        assert without_rewrite["themes"]["drain"]["total"] == 0

        with_rewrite = archetype_audit(
            cube, hydrated, themes, rewrites=(("kindred-elf", "drain"),)
        )
        assert with_rewrite["themes"]["drain"]["total"] == 1
        assert "Llanowar Elves" in with_rewrite["themes"]["drain"]["cards"]
        # Source theme is unaffected
        assert with_rewrite["themes"]["kindred-elf"]["total"] == 1

    def test_rewrite_unknown_source_raises(self):
        cube = {"cube_format": "vintage", "cards": []}
        themes = {
            "drain": _adhoc_preset("drain", re.compile(r"drain", re.IGNORECASE)),
        }
        with pytest.raises(KeyError, match="source"):
            archetype_audit(cube, [], themes, rewrites=(("not-a-theme", "drain"),))

    def test_cli_rewrite_flag(self, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        out_path = tmp_path / "out.json"
        cube = {
            "cube_format": "vintage",
            "cards": [{"name": "Llanowar Elves", "quantity": 1}],
        }
        hydrated = [
            {
                "name": "Llanowar Elves",
                "type_line": "Creature — Elf Druid",
                "oracle_text": "{T}: Add {G}.",
                "keywords": [],
                "color_identity": ["G"],
            },
        ]
        cube_path.write_text(json.dumps(cube))
        hyd_path.write_text(json.dumps(hydrated))
        result = runner.invoke(
            main,
            [
                str(cube_path),
                str(hyd_path),
                "--kindred",
                "Elf",
                "--theme",
                "drain=loses? \\d+ life",
                "--rewrite",
                "kindred-elf -> drain",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text())
        assert data["themes"]["drain"]["total"] == 1
        assert "Llanowar Elves" in data["themes"]["drain"]["cards"]

    def test_cli_rewrite_unknown_source_rejected(self, tmp_path: Path):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        cube_path.write_text(json.dumps({"cube_format": "vintage", "cards": []}))
        hyd_path.write_text(json.dumps([]))
        result = runner.invoke(
            main,
            [
                str(cube_path),
                str(hyd_path),
                "--preset",
                "flying",
                "--rewrite",
                "nope -> flying",
            ],
        )
        assert result.exit_code != 0
        assert "not a declared theme" in result.output.lower()


class TestWarnDensityOverride:
    """--warn-density lets deck-scale callers tune the warn threshold."""

    def test_warn_density_override_surfaces_in_result(self, cube_hydrated):
        cube = {
            "cube_format": "vintage",
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
        }
        themes = {"burn": _adhoc_preset("burn", re.compile(r"damage", re.IGNORECASE))}
        result = archetype_audit(
            cube, cube_hydrated, themes, min_density=1, warn_density=99
        )
        assert result["warn_density_threshold"] == 99

    def test_warn_density_default_falls_back_to_balance_target(self, cube_hydrated):
        cube = {
            "cube_format": "vintage",
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
        }
        themes = {"burn": _adhoc_preset("burn", re.compile(r"damage", re.IGNORECASE))}
        result = archetype_audit(cube, cube_hydrated, themes)
        # BALANCE_TARGETS default for vintage is 5.
        assert result["warn_density_threshold"] == 5

    def test_zero_threshold_suppresses_notes(self, cube_hydrated):
        # min_density=0 and warn_density=0 mean "no threshold" — no total
        # can fall below zero, so neither the LP-minimum nor the warn
        # note should fire. Pins the semantic that 0 is a valid,
        # explicit "suppress this warning" signal (distinct from None
        # which still falls back to the balance-target default).
        cube = {
            "cube_format": "vintage",
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
        }
        themes = {"burn": _adhoc_preset("burn", re.compile(r"damage", re.IGNORECASE))}
        result = archetype_audit(
            cube, cube_hydrated, themes, min_density=0, warn_density=0
        )
        assert result["min_density_threshold"] == 0
        assert result["warn_density_threshold"] == 0
        notes = result["themes"]["burn"]["notes"]
        assert not any("below" in n.lower() for n in notes)
        assert not any("thin" in n.lower() for n in notes)


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

    def test_warn_density_flag_routed_to_result(
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
                "--warn-density",
                "42",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text())
        assert data["warn_density_threshold"] == 42

    def test_include_commanders_flag_counts_commander_pool(
        self, sample_commander_cube_json, cube_hydrated, tmp_path: Path
    ):
        runner = CliRunner()
        cube_path = tmp_path / "cube.json"
        hyd_path = tmp_path / "hyd.json"
        cube_path.write_text(json.dumps(sample_commander_cube_json))
        hyd_path.write_text(json.dumps(cube_hydrated))

        out_default = tmp_path / "default.json"
        out_with_flag = tmp_path / "with_flag.json"

        default = runner.invoke(
            main,
            [
                str(cube_path),
                str(hyd_path),
                "--theme",
                "fly=\\bflying\\b",
                "--output",
                str(out_default),
            ],
        )
        assert default.exit_code == 0, default.output
        data_default = json.loads(out_default.read_text())

        flagged = runner.invoke(
            main,
            [
                str(cube_path),
                str(hyd_path),
                "--theme",
                "fly=\\bflying\\b",
                "--include-commanders",
                "--output",
                str(out_with_flag),
            ],
        )
        assert flagged.exit_code == 0, flagged.output
        data_flagged = json.loads(out_with_flag.read_text())

        # commander_pool contains Atraxa + Korvold (both have "flying");
        # main cards list has neither. Flag should raise the total.
        assert (
            data_flagged["themes"]["fly"]["total"]
            > (data_default["themes"]["fly"]["total"])
        )


class TestFromCubeViaResolver:
    def test_from_cube_consumes_preset_references(self, tmp_path):
        import json as _json

        from click.testing import CliRunner

        cube = {
            "format": "test_cube",
            "designer_intent": {
                "stated_archetypes": [
                    {"name": "removal"},
                ],
            },
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
        }
        hydrated = [
            {
                "name": "Lightning Bolt",
                "type_line": "Instant",
                "oracle_text": "~ deals 3 damage to any target.",
                "color_identity": ["R"],
                "mana_cost": "{R}",
                "cmc": 1,
                "produced_mana": [],
            }
        ]
        cube_path = tmp_path / "cube.json"
        hydrated_path = tmp_path / "hydrated.json"
        cube_path.write_text(_json.dumps(cube))
        hydrated_path.write_text(_json.dumps(hydrated))

        runner = CliRunner()
        from mtg_utils.archetype_audit import main

        result = runner.invoke(
            main,
            [
                str(cube_path),
                str(hydrated_path),
                "--from-cube",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "removal" in result.output

    def test_from_cube_consumes_groups(self, tmp_path):
        import json as _json

        from click.testing import CliRunner

        cube = {
            "format": "test_cube",
            "designer_intent": {
                "stated_archetypes": [
                    {"name": "graveyard", "members": ["reanimate", "self-mill"]},
                ],
            },
            "cards": [{"name": "Reanimate", "quantity": 1}],
        }
        hydrated = [
            {
                "name": "Reanimate",
                "type_line": "Sorcery",
                "oracle_text": "Put target creature card from a graveyard onto the battlefield under your control.",
                "color_identity": ["B"],
                "mana_cost": "{B}",
                "cmc": 1,
                "produced_mana": [],
            }
        ]
        cube_path = tmp_path / "cube.json"
        hydrated_path = tmp_path / "hydrated.json"
        cube_path.write_text(_json.dumps(cube))
        hydrated_path.write_text(_json.dumps(hydrated))

        runner = CliRunner()
        from mtg_utils.archetype_audit import main

        result = runner.invoke(
            main,
            [
                str(cube_path),
                str(hydrated_path),
                "--from-cube",
            ],
        )
        assert result.exit_code == 0, result.output
        # The group name appears as a theme in the output.
        assert "graveyard" in result.output
