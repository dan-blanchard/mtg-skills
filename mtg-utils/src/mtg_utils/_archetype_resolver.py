"""Resolver for cube.designer_intent.stated_archetypes.

Each entry in ``stated_archetypes`` has one of three shapes:

- ``{"name": NAME}`` — preset reference; ``NAME`` must be in
  :data:`mtg_utils.theme_presets.PRESETS`.
- ``{"name": NAME, "members": [PRESET, ...]}`` — archetype group; ``name``
  is the umbrella label and each ``members`` entry must be a known preset.
- ``{"name": NAME, "regex": PATTERN}`` — legacy / custom matcher; used
  when ``NAME`` is not a preset and the cube author has a hand-rolled
  pattern.

Validation: unknown preset names, unknown group members, malformed regex,
duplicate ``name`` values, and missing ``name`` keys all raise ``ValueError``
listing every violation found.
"""

from __future__ import annotations

import re  # noqa: F401  # used in Task 4 regex validation
from dataclasses import dataclass


@dataclass(frozen=True)
class ArchetypeGroup:
    """An umbrella archetype that unions multiple preset matchers."""

    name: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class CustomRegexArchetype:
    """A legacy stated_archetype with a user-supplied oracle regex."""

    name: str
    regex: str


@dataclass(frozen=True)
class ResolvedArchetypes:
    """Three-bucket resolution of a cube's ``stated_archetypes`` list.

    ``preset_names`` is the *flattened* tuple of preset references — all
    ``{name}`` entries plus every member of every group. Use this when
    you only need a list of presets to feed into ``precompute_metadata``.

    ``groups`` carries each group's name + members so callers that care
    about umbrella reporting (e.g., the simulator's archetype tracking)
    can compute group-level assembly.

    ``custom`` carries legacy regex entries for tools that still consume
    them (e.g., archetype-audit's ``--theme NAME=REGEX`` plumbing).
    """

    preset_names: tuple[str, ...]
    groups: tuple[ArchetypeGroup, ...]
    custom: tuple[CustomRegexArchetype, ...]


def resolve_stated_archetypes(cube: dict) -> ResolvedArchetypes:
    """Resolve a cube's ``stated_archetypes`` list into typed buckets.

    Reads ``cube.designer_intent.stated_archetypes`` (with
    ``cube.stated_archetypes`` as a deprecated fallback). Returns an
    empty ``ResolvedArchetypes`` when the cube has no stated archetypes.
    """
    stated = (cube.get("designer_intent") or {}).get("stated_archetypes")
    if stated is None:
        stated = cube.get("stated_archetypes") or []
    if not stated:
        return ResolvedArchetypes(
            preset_names=(),
            groups=(),
            custom=(),
        )

    # Validation + classification happens in subsequent tasks.
    return ResolvedArchetypes(preset_names=(), groups=(), custom=())
