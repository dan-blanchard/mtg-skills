"""Smoke tests: verify the cube-wizard package installs and key modules resolve."""

from click.testing import CliRunner


class TestEntryPointsImport:
    def test_parse_cube_main(self):
        from mtg_utils.parse_cube import main
        assert callable(main)

    def test_cube_stats_main(self):
        from mtg_utils.cube_stats import main
        assert callable(main)

    def test_cube_balance_main(self):
        from mtg_utils.cube_balance import main
        assert callable(main)

    def test_archetype_audit_main(self):
        from mtg_utils.archetype_audit import main
        assert callable(main)

    def test_cubecobra_fetch_main(self):
        from mtg_utils.cubecobra_fetch import main
        assert callable(main)

    def test_cube_diff_main(self):
        from mtg_utils.cube_diff import main
        assert callable(main)

    def test_cube_legality_audit_main(self):
        from mtg_utils.cube_legality_audit import main
        assert callable(main)

    def test_pack_simulate_main(self):
        from mtg_utils.pack_simulate import main
        assert callable(main)

    def test_export_cube_main(self):
        from mtg_utils.export_cube import main
        assert callable(main)


class TestCLIHelpSmoke:
    """Each cube CLI's --help should exit 0 and mention cube concepts."""

    def _run_help(self, main_fn) -> str:
        runner = CliRunner()
        result = runner.invoke(main_fn, ["--help"])
        assert result.exit_code == 0, result.output
        return result.output

    def test_parse_cube_help(self):
        from mtg_utils.parse_cube import main
        output = self._run_help(main)
        assert "cube" in output.lower()

    def test_cube_stats_help(self):
        from mtg_utils.cube_stats import main
        output = self._run_help(main)
        assert "cube" in output.lower()

    def test_cube_balance_help(self):
        from mtg_utils.cube_balance import main
        output = self._run_help(main)
        assert "cube" in output.lower() or "balance" in output.lower()

    def test_archetype_audit_help(self):
        from mtg_utils.archetype_audit import main
        output = self._run_help(main)
        assert "theme" in output.lower() or "archetype" in output.lower()

    def test_cubecobra_fetch_help(self):
        from mtg_utils.cubecobra_fetch import main
        output = self._run_help(main)
        assert "cube" in output.lower()

    def test_cube_diff_help(self):
        from mtg_utils.cube_diff import main
        output = self._run_help(main)
        assert "cube" in output.lower() or "compare" in output.lower()

    def test_cube_legality_audit_help(self):
        from mtg_utils.cube_legality_audit import main
        output = self._run_help(main)
        assert "legality" in output.lower() or "rarity" in output.lower() or "cube" in output.lower()

    def test_pack_simulate_help(self):
        from mtg_utils.pack_simulate import main
        output = self._run_help(main)
        assert "pack" in output.lower()

    def test_export_cube_help(self):
        from mtg_utils.export_cube import main
        output = self._run_help(main)
        assert "cube" in output.lower() or "export" in output.lower()


class TestCubeConfigBasics:
    def test_formats_cover_supported_list(self):
        from mtg_utils.cube_config import CUBE_FORMAT_CONFIGS

        required = {
            "vintage", "unpowered", "legacy", "modern", "pauper",
            "peasant", "set", "commander", "pdh",
        }
        assert required.issubset(set(CUBE_FORMAT_CONFIGS))

    def test_reference_cubes_non_empty_per_format(self):
        from mtg_utils.cube_config import CUBE_FORMAT_CONFIGS, REFERENCE_CUBES

        for fmt in CUBE_FORMAT_CONFIGS:
            assert len(REFERENCE_CUBES.get(fmt, [])) >= 1, (
                f"{fmt} has no reference cubes"
            )

    def test_pack_templates_default_sizes(self):
        from mtg_utils.cube_config import PACK_TEMPLATES

        for size in (9, 11, 15):
            assert size in PACK_TEMPLATES
            template = PACK_TEMPLATES[size]
            assert sum(template.values()) == size


class TestCardClassifyCubeAddition:
    def test_classify_cube_category_exposed(self):
        from mtg_utils.card_classify import classify_cube_category
        assert callable(classify_cube_category)

    def test_categorizes_basic_cases(self):
        from mtg_utils.card_classify import classify_cube_category

        # Multicolor non-fixing creature
        assert classify_cube_category(
            {
                "type_line": "Creature",
                "color_identity": ["W", "U"],
                "oracle_text": "Flying",
            }
        ) == "M"
        # Dual land that taps for mana → L (mana-producing land)
        assert classify_cube_category(
            {
                "type_line": "Land — Swamp Forest",
                "color_identity": ["B", "G"],
                "oracle_text": "{T}: Add {B} or {G}.",
            }
        ) == "L"
        # Fetch land that doesn't tap for mana → F (fixing)
        assert classify_cube_category(
            {
                "type_line": "Land",
                "color_identity": [],
                "oracle_text": "{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
            }
        ) == "F"
        # Mono-color non-fixing instant
        assert classify_cube_category(
            {
                "type_line": "Instant",
                "color_identity": ["R"],
                "oracle_text": "Deal 3 damage to any target.",
            }
        ) == "R"
        # Colorless non-fixing artifact
        assert classify_cube_category(
            {"type_line": "Artifact", "color_identity": [], "oracle_text": ""}
        ) == "C"
        # Mana rock → F
        assert classify_cube_category(
            {
                "type_line": "Artifact",
                "color_identity": [],
                "oracle_text": "{T}: Add {C}{C}.",
            }
        ) == "F"
