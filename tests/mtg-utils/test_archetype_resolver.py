"""Tests for stated_archetypes resolver."""

from __future__ import annotations

import pytest

from mtg_utils._archetype_resolver import (
    ArchetypeGroup,
    CustomRegexArchetype,
    ResolvedArchetypes,
    resolve_stated_archetypes,
)


def _cube(stated_archetypes):
    return {"designer_intent": {"stated_archetypes": stated_archetypes}}


class TestEmptyAndShape:
    def test_empty_stated_archetypes(self):
        out = resolve_stated_archetypes(_cube([]))
        assert out == ResolvedArchetypes(
            preset_names=(),
            groups=(),
            custom=(),
        )

    def test_missing_designer_intent_returns_empty(self):
        out = resolve_stated_archetypes({})
        assert out.preset_names == ()
        assert out.groups == ()
        assert out.custom == ()


class TestPresetReferenceShape:
    def test_single_preset_reference(self):
        cube = _cube([{"name": "removal"}])
        out = resolve_stated_archetypes(cube)
        assert out.preset_names == ("removal",)
        assert out.groups == ()
        assert out.custom == ()

    def test_multiple_preset_references_dedupe_preserved(self):
        cube = _cube(
            [
                {"name": "top-manipulation"},
                {"name": "removal"},
                {"name": "counterspell"},
            ]
        )
        out = resolve_stated_archetypes(cube)
        assert out.preset_names == ("top-manipulation", "removal", "counterspell")

    def test_unknown_preset_raises(self):
        cube = _cube([{"name": "no-such-preset"}])
        with pytest.raises(ValueError, match="no-such-preset"):
            resolve_stated_archetypes(cube)


class TestGroupShape:
    def test_single_group_resolves(self):
        cube = _cube(
            [
                {
                    "name": "graveyard",
                    "members": ["reanimate", "self-mill", "graveyard-cast"],
                },
            ]
        )
        out = resolve_stated_archetypes(cube)
        assert out.groups == (
            ArchetypeGroup("graveyard", ("reanimate", "self-mill", "graveyard-cast")),
        )
        # preset_names is the flattened union of members.
        assert set(out.preset_names) == {"reanimate", "self-mill", "graveyard-cast"}

    def test_group_plus_preset_reference_combine(self):
        cube = _cube(
            [
                {"name": "removal"},
                {"name": "graveyard", "members": ["reanimate", "self-mill"]},
            ]
        )
        out = resolve_stated_archetypes(cube)
        assert "removal" in out.preset_names
        assert "reanimate" in out.preset_names
        assert "self-mill" in out.preset_names
        assert len(out.groups) == 1
        assert out.groups[0].name == "graveyard"

    def test_group_dedupes_preset_names_with_other_entries(self):
        cube = _cube(
            [
                {"name": "reanimate"},
                {"name": "graveyard", "members": ["reanimate", "self-mill"]},
            ]
        )
        out = resolve_stated_archetypes(cube)
        # 'reanimate' should appear once even though it's both a top-level
        # entry and a member of the group.
        assert out.preset_names.count("reanimate") == 1

    def test_group_with_unknown_member_raises(self):
        cube = _cube(
            [
                {"name": "graveyard", "members": ["reanimate", "no-such", "self-mill"]},
            ]
        )
        with pytest.raises(ValueError, match="no-such") as excinfo:
            resolve_stated_archetypes(cube)
        assert "graveyard" in str(excinfo.value)

    def test_group_with_empty_members_raises(self):
        cube = _cube([{"name": "empty-group", "members": []}])
        with pytest.raises(ValueError, match="empty-group") as excinfo:
            resolve_stated_archetypes(cube)
        assert "members" in str(excinfo.value).lower()


class TestRegexShape:
    def test_legacy_regex_resolves_to_custom_bucket(self):
        cube = _cube(
            [
                {"name": "kindred-cats", "regex": "(?i)cats? you control"},
            ]
        )
        out = resolve_stated_archetypes(cube)
        assert out.preset_names == ()
        assert out.groups == ()
        assert out.custom == (
            CustomRegexArchetype("kindred-cats", "(?i)cats? you control"),
        )

    def test_invalid_regex_raises(self):
        cube = _cube(
            [
                {"name": "broken", "regex": "(?i)[unclosed"},
            ]
        )
        with pytest.raises(ValueError, match="broken") as excinfo:
            resolve_stated_archetypes(cube)
        assert "regex" in str(excinfo.value).lower()

    def test_regex_when_name_is_also_a_preset_keeps_regex_behavior(self):
        # If the author wrote {name: 'removal', regex: '...custom...'}
        # they explicitly want the custom matcher, not the preset.
        cube = _cube(
            [
                {"name": "removal", "regex": "(?i)destroy target nonland"},
            ]
        )
        out = resolve_stated_archetypes(cube)
        # Goes to custom, not preset_names.
        assert out.preset_names == ()
        assert out.custom == (
            CustomRegexArchetype("removal", "(?i)destroy target nonland"),
        )


class TestNameValidation:
    def test_duplicate_name_raises(self):
        cube = _cube(
            [
                {"name": "removal"},
                {"name": "removal"},
            ]
        )
        with pytest.raises(ValueError, match="duplicate") as excinfo:
            resolve_stated_archetypes(cube)
        assert "removal" in str(excinfo.value)

    def test_missing_name_raises(self):
        cube = _cube([{"members": ["reanimate"]}])
        with pytest.raises(ValueError, match="name") as excinfo:
            resolve_stated_archetypes(cube)
        assert "name" in str(excinfo.value).lower()

    def test_non_dict_entry_raises(self):
        cube = _cube(["just-a-string"])
        with pytest.raises(ValueError, match=r"object|dict") as excinfo:
            resolve_stated_archetypes(cube)
        msg = str(excinfo.value).lower()
        assert "object" in msg or "dict" in msg

    def test_multiple_violations_all_reported(self):
        cube = _cube(
            [
                {"name": "no-such-preset"},
                {"name": "broken", "regex": "(?i)[unclosed"},
                {"members": ["reanimate"]},  # missing name
            ]
        )
        with pytest.raises(ValueError, match=r"no-such-preset|broken|name") as excinfo:
            resolve_stated_archetypes(cube)
        msg = str(excinfo.value)
        # Multi-line message with one entry per violation.
        assert "no-such-preset" in msg
        assert "broken" in msg
        assert "name" in msg.lower()


class TestLegacyTopLevelLocation:
    def test_top_level_stated_archetypes_resolves_with_warning(self):
        # No `designer_intent` key; entries at top level instead.
        cube = {"stated_archetypes": [{"name": "removal"}]}
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = resolve_stated_archetypes(cube)
        assert out.preset_names == ("removal",)
        assert any(
            "deprecat" in str(w.message).lower()
            and "stated_archetypes" in str(w.message)
            for w in caught
        )

    def test_designer_intent_takes_precedence_over_top_level(self):
        # If both are present, designer_intent wins; top-level is ignored.
        cube = {
            "designer_intent": {"stated_archetypes": [{"name": "removal"}]},
            "stated_archetypes": [{"name": "counterspell"}],
        }
        out = resolve_stated_archetypes(cube)
        assert out.preset_names == ("removal",)


class TestMergeMemberPresets:
    def test_merged_preset_or_matches_any_member(self):
        # ``reanimate`` moved to a structural view (task #83) so it needs a
        # real oracle_id to resolve — ``graveyard-return`` (still regex)
        # exercises the SAME "merge ORs across two regex members" behavior
        # with a synthetic card, so this test stays decoupled from the
        # structural-view snapshot fixtures.
        from mtg_utils._archetype_resolver import merge_member_presets
        from mtg_utils.theme_presets import PRESETS

        merged = merge_member_presets(
            "graveyard",
            ("graveyard-return", "self-mill"),
        )

        # The merged preset's `matches` returns True if EITHER constituent
        # preset's matchers fire on a card.
        # graveyard-return match: a generic grave-to-hand recursion spell.
        graveyard_return_card = {
            "name": "Regrowth",
            "type_line": "Sorcery",
            "oracle_text": "Return target card from your graveyard to your hand.",
        }
        # Self-mill match: a self-mill card (oracle uses the preset's pattern).
        self_mill_card = {
            "name": "Stitcher's Supplier",
            "type_line": "Creature — Zombie",
            "oracle_text": (
                "When this creature enters or dies, mill three cards. (Put the top three cards of your library into your graveyard.)"
            ),
        }
        # Neither — should NOT match the union.
        bystander = {
            "name": "Llanowar Elves",
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
        }

        # Sanity-check the constituents match individually.
        assert PRESETS["graveyard-return"].matches(graveyard_return_card)
        assert PRESETS["self-mill"].matches(self_mill_card)
        assert not PRESETS["graveyard-return"].matches(bystander)
        assert not PRESETS["self-mill"].matches(bystander)

        # Merged preset matches both kinds, doesn't match the bystander.
        assert merged.matches(graveyard_return_card)
        assert merged.matches(self_mill_card)
        assert not merged.matches(bystander)

    def test_merged_preset_name_matches_group_name(self):
        from mtg_utils._archetype_resolver import merge_member_presets

        merged = merge_member_presets("graveyard", ("graveyard-return", "self-mill"))
        assert merged.name == "graveyard"

    def test_unknown_member_raises(self):
        from mtg_utils._archetype_resolver import merge_member_presets

        with pytest.raises(KeyError):
            merge_member_presets("bad-group", ("does-not-exist",))

    def test_merged_preset_unions_a_structural_view_with_a_regex_member(self):
        """Task #83: merge_member_presets ORs a converted (signal_keys) member
        with an unconverted (regex) member — a mixed group during the
        transition still merges to a coherent single Preset."""
        from mtg_utils import testkit
        from mtg_utils._archetype_resolver import merge_member_presets

        merged = merge_member_presets("value-engines", ("landfall", "extra-turns"))
        assert merged.signal_keys == ("landfall",)
        assert merged.patterns  # extra-turns' regex arm survives the merge

        # landfall member matches ONLY via the structural signal_keys arm.
        testkit.test_card_ir("Courser of Kruphix")
        landfall_card = testkit.test_card("Courser of Kruphix")
        assert merged.matches(landfall_card)

        # extra-turns member matches ONLY via the regex arm (no oracle_id
        # needed — extra-turns is still an unconverted regex preset).
        extra_turn_card = {
            "name": "Time Walk",
            "type_line": "Sorcery",
            "oracle_text": "Take an extra turn after this one.",
        }
        assert merged.matches(extra_turn_card)

        # Neither arm fires on a bystander.
        bystander = {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        }
        assert not merged.matches(bystander)
