"""Tests for cube_config module."""

import pytest

from mtg_utils.cube_config import (
    BALANCE_TARGETS,
    CUBE_FORMAT_CONFIGS,
    PACK_TEMPLATES,
    REFERENCE_CUBES,
    SIZE_TO_DRAFTERS,
    drafters_for_size,
    get_balance_targets,
    get_cube_config,
    get_pack_templates,
)


class TestFormatConfigs:
    def test_all_formats_present(self):
        for fmt in (
            "vintage",
            "unpowered",
            "legacy",
            "modern",
            "pauper",
            "peasant",
            "set",
            "commander",
            "pdh",
        ):
            assert fmt in CUBE_FORMAT_CONFIGS

    def test_powered_format_dropped(self):
        """`powered` is a descriptor (Power 9 allowed), not a format distinct
        from vintage. Use `vintage` with `--target-size` for smaller variants."""
        assert "powered" not in CUBE_FORMAT_CONFIGS

    def test_unpowered_bans_power_nine(self):
        bans = set(CUBE_FORMAT_CONFIGS["unpowered"]["ban_list"])
        assert "Black Lotus" in bans
        assert "Ancestral Recall" in bans
        assert "Time Walk" in bans
        assert "Timetwister" in bans
        assert "Mox Sapphire" in bans

    def test_pauper_commons_only(self):
        cfg = CUBE_FORMAT_CONFIGS["pauper"]
        assert cfg["rarity_filter"] == frozenset({"common"})

    def test_peasant_commons_and_uncommons(self):
        cfg = CUBE_FORMAT_CONFIGS["peasant"]
        assert cfg["rarity_filter"] == frozenset({"common", "uncommon"})

    def test_commander_has_commander_pool(self):
        assert CUBE_FORMAT_CONFIGS["commander"]["has_commander_pool"] is True

    def test_pdh_has_commander_pool_with_uncommon_filter(self):
        cfg = CUBE_FORMAT_CONFIGS["pdh"]
        assert cfg["has_commander_pool"] is True
        assert cfg["rarity_filter"] == frozenset({"common"})
        assert cfg["commander_pool_rarity_filter"] == frozenset({"uncommon"})

    def test_legality_keys(self):
        assert CUBE_FORMAT_CONFIGS["modern"]["legality_key"] == "modern"
        assert CUBE_FORMAT_CONFIGS["legacy"]["legality_key"] == "legacy"
        assert CUBE_FORMAT_CONFIGS["vintage"]["legality_key"] is None

    def test_default_sizes(self):
        assert CUBE_FORMAT_CONFIGS["vintage"]["default_size"] == 540
        assert CUBE_FORMAT_CONFIGS["set"]["default_size"] == 360
        assert CUBE_FORMAT_CONFIGS["unpowered"]["default_size"] == 540


class TestGetCubeConfig:
    def test_defaults_to_vintage(self):
        cfg = get_cube_config({})
        assert cfg["default_size"] == 540

    def test_explicit_format(self):
        cfg = get_cube_config({"cube_format": "pauper"})
        assert cfg["rarity_filter"] == frozenset({"common"})

    def test_target_size_override(self):
        cfg = get_cube_config({"cube_format": "vintage", "target_size": 720})
        assert cfg["default_size"] == 720

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown cube format"):
            get_cube_config({"cube_format": "bogus"})


class TestSizeToDrafters:
    def test_canonical_sizes(self):
        assert SIZE_TO_DRAFTERS[360] == 8
        assert SIZE_TO_DRAFTERS[540] == 12
        assert SIZE_TO_DRAFTERS[720] == 16

    def test_drafters_for_size_canonical(self):
        assert drafters_for_size(360) == 8
        assert drafters_for_size(540) == 12

    def test_drafters_for_size_non_canonical_below(self):
        """Below 360 always returns 8."""
        assert drafters_for_size(300) == 8

    def test_drafters_for_size_non_canonical_above(self):
        """Above 360, extrapolate at 45 cards per seat."""
        # 360 + 90 = 450 → 8 + 2 = 10
        assert drafters_for_size(450) == 10
        # 360 + 100 = 460 → 8 + (100 // 45) = 10
        assert drafters_for_size(460) == 10


class TestPackTemplates:
    def test_pack_sizes_present(self):
        for size in (9, 11, 15):
            assert size in PACK_TEMPLATES

    def test_pack_15_slots_sum_to_size(self):
        template = PACK_TEMPLATES[15]
        total = sum(template.values())
        assert total == 15

    def test_pack_11_slots_sum_to_size(self):
        template = PACK_TEMPLATES[11]
        total = sum(template.values())
        assert total == 11

    def test_pack_9_slots_sum_to_size(self):
        template = PACK_TEMPLATES[9]
        total = sum(template.values())
        assert total == 9

    def test_every_template_includes_all_mono_colors(self):
        for size, template in PACK_TEMPLATES.items():
            for color in "WUBRG":
                assert color in template, f"pack size {size} missing color {color}"

    def test_get_pack_templates_default(self):
        assert get_pack_templates({}) == PACK_TEMPLATES

    def test_get_pack_templates_override(self):
        custom = {
            "15": {"W": 2, "U": 2, "B": 2, "R": 2, "G": 2, "M": 3, "L": 1, "F": 1}
        }
        templates = get_pack_templates({"pack_templates": custom})
        assert templates[15]["M"] == 3
        # Non-overridden sizes remain.
        assert templates[9] == PACK_TEMPLATES[9]


class TestBalanceTargets:
    def test_has_removal_band(self):
        assert BALANCE_TARGETS["removal_density_pct"] == (22.0, 28.0)

    def test_has_fixing_band(self):
        assert BALANCE_TARGETS["fixing_density_pct"] == (17.0, 28.0)

    def test_has_min_archetype_density(self):
        assert BALANCE_TARGETS["min_archetype_signal_density"] == 3

    def test_has_maindeck_efficiency_curve(self):
        curve = BALANCE_TARGETS["fixing_maindeck_efficiency"]
        assert 5.0 in curve
        assert 10.0 in curve
        assert 13.0 in curve

    def test_unused_constants_not_declared(self):
        """Dropped targets (nonbasic_land_pct, creature_pct_*) were declared but
        never checked by any `cube-balance --check`. Keep the BALANCE_TARGETS
        surface minimal so future wiring-up doesn't silently miss them."""
        assert "nonbasic_land_pct" not in BALANCE_TARGETS
        assert "creature_pct_per_color" not in BALANCE_TARGETS
        assert "creature_pct_tolerance" not in BALANCE_TARGETS

    def test_get_balance_targets_default(self):
        targets = get_balance_targets({})
        assert targets["removal_density_pct"] == (22.0, 28.0)

    def test_get_balance_targets_override(self):
        targets = get_balance_targets(
            {"balance_targets_override": {"removal_density_pct": (20.0, 30.0)}}
        )
        assert targets["removal_density_pct"] == (20.0, 30.0)
        # Non-overridden targets remain.
        assert targets["fixing_density_pct"] == (17.0, 28.0)


class TestReferenceCubes:
    def test_every_format_has_entries(self):
        """Each format in CUBE_FORMAT_CONFIGS should have at least one ref cube."""
        for fmt in CUBE_FORMAT_CONFIGS:
            assert fmt in REFERENCE_CUBES
            assert len(REFERENCE_CUBES[fmt]) >= 1, f"{fmt} has no reference cubes"

    def test_reference_entry_shape(self):
        for fmt, entries in REFERENCE_CUBES.items():
            for entry in entries:
                assert "id" in entry, f"{fmt} entry missing 'id'"
                assert "name" in entry, f"{fmt} entry missing 'name'"
                assert "description" in entry, f"{fmt} entry missing 'description'"
                assert "size" in entry, f"{fmt} entry missing 'size'"
                assert isinstance(entry["id"], str)
                assert isinstance(entry["size"], int)

    def test_vintage_has_mtgo(self):
        vintage_ids = {e["id"] for e in REFERENCE_CUBES["vintage"]}
        assert "modovintage" in vintage_ids

    def test_vintage_absorbed_powered_reference_cubes(self):
        """When `powered` was dropped, its reference cubes merged into vintage."""
        vintage_ids = {e["id"] for e in REFERENCE_CUBES["vintage"]}
        assert "MaxPower360" in vintage_ids
        assert "hp360" in vintage_ids

    def test_pauper_has_canonical(self):
        pauper_ids = {e["id"] for e in REFERENCE_CUBES["pauper"]}
        assert "thepaupercube" in pauper_ids
