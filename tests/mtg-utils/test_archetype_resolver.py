"""Tests for stated_archetypes resolver."""

from __future__ import annotations

import pytest  # noqa: F401  # used in Tasks 2-5 parametrize/raises

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
