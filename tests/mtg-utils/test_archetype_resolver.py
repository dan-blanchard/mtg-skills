"""Tests for stated_archetypes resolver."""

from __future__ import annotations

import pytest

from mtg_utils._archetype_resolver import (
    ArchetypeGroup,
    CustomRegexArchetype,  # noqa: F401  # used in Task 4
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
