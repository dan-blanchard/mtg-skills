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

import re
import warnings
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

    Raises ``ValueError`` listing every violation found if any entry is
    malformed.
    """
    from mtg_utils.theme_presets import PRESETS

    stated = (cube.get("designer_intent") or {}).get("stated_archetypes")
    if stated is None:
        legacy = cube.get("stated_archetypes")
        if legacy:
            warnings.warn(
                "Reading stated_archetypes from cube top level is deprecated; "
                "move entries under cube.designer_intent.stated_archetypes.",
                DeprecationWarning,
                stacklevel=2,
            )
            stated = legacy
        else:
            stated = []
    if not stated:
        return ResolvedArchetypes(preset_names=(), groups=(), custom=())

    preset_refs: list[str] = []
    groups: list[ArchetypeGroup] = []
    custom: list[CustomRegexArchetype] = []
    errors: list[str] = []
    seen_names: set[str] = set()

    for idx, entry in enumerate(stated):
        if not isinstance(entry, dict):
            errors.append(f"entry {idx}: must be an object, got {type(entry).__name__}")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"entry {idx}: missing or empty 'name'")
            continue
        if name in seen_names:
            errors.append(
                f"entry {idx}: duplicate 'name' {name!r} (each name must be unique)",
            )
            continue
        seen_names.add(name)

        if "members" in entry:
            members = entry["members"]
            if not isinstance(members, list) or not members:
                errors.append(
                    f"entry {idx} ({name!r}): 'members' must be a non-empty list",
                )
                continue
            bad_members = [m for m in members if m not in PRESETS]
            if bad_members:
                errors.append(
                    f"entry {idx} ({name!r}): unknown preset(s) in members: "
                    f"{', '.join(repr(m) for m in bad_members)}",
                )
                continue
            groups.append(ArchetypeGroup(name=name, members=tuple(members)))
            for member in members:
                if member not in preset_refs:
                    preset_refs.append(member)
            continue
        if "regex" in entry:
            pattern = entry["regex"]
            if not isinstance(pattern, str) or not pattern:
                errors.append(
                    f"entry {idx} ({name!r}): 'regex' must be a non-empty string",
                )
                continue
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(
                    f"entry {idx} ({name!r}): regex {pattern!r} does not "
                    f"compile: {exc}",
                )
                continue
            custom.append(CustomRegexArchetype(name=name, regex=pattern))
            continue

        # Preset-reference shape: {name} only.
        if name not in PRESETS:
            errors.append(
                f"entry {idx} ({name!r}): not a known preset; "
                f"either fix the name or add a 'regex' field",
            )
            continue
        preset_refs.append(name)

    if errors:
        raise ValueError("\n".join(["stated_archetypes: invalid", *errors]))

    return ResolvedArchetypes(
        preset_names=tuple(preset_refs),
        groups=tuple(groups),
        custom=tuple(custom),
    )


def merge_member_presets(name: str, members: tuple[str, ...] | list[str]):
    """Synthesize a single :class:`Preset` whose matcher ORs each member's.

    The :class:`Preset` class's :meth:`matches` method is already an OR
    over its keywords/patterns/type_patterns/layouts. So combining the
    constituent presets' tuples preserves OR semantics — a card matches
    iff at least one member's matchers fire.

    Raises ``KeyError`` if any member is not a known preset.
    """
    from mtg_utils.theme_presets import PRESETS, Preset

    member_presets = [PRESETS[m] for m in members]
    keywords = tuple(dict.fromkeys(kw for p in member_presets for kw in p.keywords))
    patterns = tuple(p_ for p in member_presets for p_ in p.patterns)
    type_patterns = tuple(p_ for p in member_presets for p_ in p.type_patterns)
    layouts = tuple(
        dict.fromkeys(layout for p in member_presets for layout in p.layouts)
    )
    desc = f"Group: {' + '.join(members)}"
    return Preset(
        name=name,
        description=desc,
        keywords=keywords,
        patterns=patterns,
        type_patterns=type_patterns,
        layouts=layouts,
    )
