"""Tests for stated_archetypes resolver."""

from __future__ import annotations

import pytest

from mtg_utils._archetype_resolver import (
    ArchetypeGroup,  # noqa: F401  # used in Tasks 2-3
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
