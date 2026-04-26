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
