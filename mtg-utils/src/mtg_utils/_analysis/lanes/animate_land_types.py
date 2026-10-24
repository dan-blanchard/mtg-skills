"""Two subject-carrying lanes the 25-precon audit found missing:
animation (``animate_makers``) and land-subtype payoffs (``land_type_matters``).

* ``animate_makers|you|<Type>`` — a continuous effect that makes noncreature
  permanents of a card type creatures (CR 613.1d: a type-changing effect, layer
  4; CR 205.1b: "in addition to its other types" / "an artifact creature" keep
  the permanent's prior types). Bello, Bard of the Brambles, March of the
  Machines, Ensoul Artifact, Opalescence, Tezzeret, Agent of Bolas's -1. The
  subject is the animated card type, spelled as ``cheat_into_play``'s is, plus
  the animated set's mana-value floor when it has one (Bello: ``Artifact>=4`` —
  ``signal_keys.animate_subject``).
* ``land_type_matters|you|<Subtype>`` — a card that counts, watches or grants
  to lands of one land type (CR 205.3i): Yuma, Proud Protector's Desert
  trigger, Gatebreaker Ram's Gate count, Maze's End's ten-Gates win. The
  subject is the land type, spelled as the card's own filter spells it.
"""

from __future__ import annotations

from collections.abc import Iterator

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis._subtypes import subtype_card_type
from mtg_utils._analysis.signal_base import Signal
from mtg_utils._analysis.tree_synthesis.types_tribal import structural_type_subjects
from mtg_utils._card_ir.crosswalk import (
    LAND_SUBTYPE_WORDS,
    AbilityUnit,
    ConceptTree,
    adds_creature_type,
    affected_tag,
    filter_controller,
    filter_core_types,
    filter_mana_value_floor,
    filter_subtypes,
    iter_nested_trigger_defs,
    iter_static_defs,
    iter_threaded_target_statics,
    or_arms,
    static_affected,
    tag_of,
)

# ── animate_makers ────────────────────────────────────────────────────────────

# The card types an animation can name as its SUBJECT are
# ``signal_keys.ANIMATE_SUBJECT_TYPES`` (the spec layer reads the same tuple). A
# land made a creature is the land-creatures lane (``land_creatures_matter`` /
# ``land_protection``), never this one; a filter that already names Creature
# ("target creature becomes an artifact creature") animates nothing.


def _animated_filters(unit: AbilityUnit) -> Iterator[object]:
    """The filter of each set of permanents one ability makes creatures.

    Two shapes, both off the shared static-def walks: a continuous effect whose
    own ``affected`` names the set — a static ability (March of the Machines,
    Bello; an Aura's "enchanted artifact" — Ensoul Artifact) or a one-shot
    ``GenericEffect`` over a mass filter (Tezzeret the Seeker's -5) — and a
    targeted one whose ``affected`` is ``ParentTarget``, read through the
    threaded target (Karn, Silver Golem; Tezzeret, Agent of Bolas's -1), or a
    trigger's ``TriggeringSource`` read through its watched object. A
    ``SelfRef`` animation (a manland, a Vehicle's crew, a creature-planeswalker)
    is the card making only itself a creature and is never read. ``affected``
    is read through the overlay corrections: an Aura's "enchanted artifact"
    and Alacrian Armory's "that permanent" phase stamps ``SelfRef``
    (``animated_object``), and the Hidden / Opal / Veiled cycles' "if ~ is an
    enchantment, it becomes …" phase stamps ``TriggeringSource``
    (``self_animation``: the card itself)."""
    for sdef in iter_static_defs(unit.node):
        if not adds_creature_type(sdef):
            continue
        aff = static_affected(sdef, unit)
        atag = affected_tag(sdef, unit)
        if atag in ("Typed", "Or", "And"):
            yield aff
        elif atag == "TriggeringSource" and unit.trigger_event == "enters":
            # "Whenever a Vehicle you control enters, it becomes an artifact
            # creature" (Kolodin, Triumph Caster): the trigger's watched
            # object, the permanent that entered. Only an enters trigger's
            # triggering source is a permanent ``valid_card`` describes; under
            # a cast trigger it is the spell, so an uncorrected cast-trigger
            # animation stays out (the corrected Hidden cycle reads SelfRef).
            yield getattr(unit.node, "valid_card", None)
    # The ability's own chain, then each trigger it grants or puts on an emblem
    # (Tezzeret the Schemer's -7: "At the beginning of combat on your turn,
    # target artifact you control becomes an artifact creature").
    for root in (unit.node, *iter_nested_trigger_defs(unit.node)):
        for resolved, sdef in iter_threaded_target_statics(root):
            if adds_creature_type(sdef):
                yield resolved


def _filter_arms(filt: object) -> Iterator[object]:
    """An ``Or`` filter's arms one by one (Bello's "non-Equipment artifact and
    non-Aura enchantment" is two), any other filter whole."""
    for arm in or_arms(filt):
        yield from _filter_arms(arm) if tag_of(arm) == "Or" else (arm,)


def _animate_subjects(filt: object) -> set[tuple[str, int | None]]:
    """The ``(card type, mana-value floor)`` pairs one animated filter names: each
    arm's noncreature, nonland permanent card type — a core type, or the card
    type a subtype belongs to (CR 205.3g/h: Vehicle → Artifact, Saga →
    Enchantment) — with the arm's own floor (``filter_mana_value_floor``:
    Bello's "mana value 4 or greater"), and ``("", None)`` for an arm naming
    only "permanent" (no one type). An arm that names Creature or Land, or
    another player's permanents, adds nothing."""
    out: set[tuple[str, int | None]] = set()
    for arm in _filter_arms(filt):
        if filter_controller(arm) == "Opponent":
            continue
        cores = set(filter_core_types(arm))
        if cores & {"Creature", "Land"}:
            continue
        sub_types = {subtype_card_type(s) for s in filter_subtypes(arm)}
        if sub_types & {"Creature", None} and not cores:
            continue  # a creature or land subtype ("Forests") — not this lane
        named = cores | {t for t in sub_types if t}
        typed = [t for t in signal_keys.ANIMATE_SUBJECT_TYPES if t in named]
        floor = filter_mana_value_floor(arm)
        if typed:
            out.update((t, floor) for t in typed)
        elif "Permanent" in cores:
            out.add(("", None))
    return out


def _animate_makers(tree: ConceptTree) -> list[Signal]:
    """animate_makers — one Signal per card type the card's effects animate
    (module docstring; the read is :func:`_animated_filters`).

    The subject is the type plus the animated set's mana-value floor when it
    has one (``signal_keys.animate_subject``: Bello's ``Artifact>=4``). Out of
    scope:
    a type conferral that adds no Creature (Liquimetal Coating), a land
    animation (the land-creatures lanes)."""
    # Cheap presence gate before the per-unit threaded walk: no type-changing
    # modification anywhere, no animation.
    if not tree.has_typed("AddType", "SetCardTypes"):
        return []
    found: set[tuple[str, int | None]] = set()
    raw = ""
    for unit in tree.units:
        for filt in _animated_filters(unit):
            subjects = _animate_subjects(filt)
            if subjects - found and not raw:
                raw = getattr(unit.node, "description", "") or ""
            found |= subjects
    order = (*signal_keys.ANIMATE_SUBJECT_TYPES, "")
    return [
        Signal(
            signal_keys.ANIMATE_MAKERS,
            "you",
            signal_keys.animate_subject(card_type, floor),
            raw,
            tree.name,
            "high",
        )
        for card_type, floor in sorted(
            found, key=lambda tf: (order.index(tf[0]), tf[1] or 0)
        )
    ]


# ── land_type_matters ─────────────────────────────────────────────────────────

# The basic land types (CR 305.6) are left out: "for each Forest you control" /
# "as long as you control an Island" is a colour's mana base read (Kird Ape,
# Gaea's Liege), and a basic land type's population is the deck's basics, not a
# package it builds toward.
_BASIC_LAND_TYPES = frozenset({"plains", "island", "swamp", "mountain", "forest"})
_NONBASIC_LAND_TYPES = LAND_SUBTYPE_WORDS - _BASIC_LAND_TYPES


def _land_type_subject(subtype: str) -> str:
    """A filter subtype as a ``land_type_matters`` subject: a nonbasic land type
    (CR 205.3i) in the filter's own spelling ("Desert", "Urza's"), else ""."""
    return subtype if subtype.lower() in _NONBASIC_LAND_TYPES else ""


def _land_type_matters(tree: ConceptTree) -> list[Signal]:
    """land_type_matters — a card that cares about lands of one land type
    (CR 205.3i), one Signal per type.

    The kindred Arm-B walk (``structural_type_subjects``) over land types: a
    land type named at a count operand (Gatebreaker Ram's "+1/+1 for each Gate
    you control"), a trigger's watched object (Yuma, Proud Protector's
    "Whenever a Desert card is put into your graveyard"; Hazezon's "Whenever a
    Desert you control enters"), a static's affected set (Hazezon's "You may
    play Desert lands from your graveyard") or a condition (Maze's End's "ten or
    more Gates with different names"; Hour of Promise's "three or more
    Deserts"). The sites where a land type names what an effect or cost acts on
    are left out (``population_only``): "search your library for a Gate
    card" or a fetch land's "Forest or Plains card" fetches the land, and a
    landfall trigger names no type at all (Rampaging Baloths). Another player's
    lands (a landwalk-style "defending player controls an Island") never count.
    Basic land types are out (:data:`_BASIC_LAND_TYPES`)."""
    subjects = structural_type_subjects(
        tree, resolve=_land_type_subject, population_only=True
    )
    return [
        Signal(signal_keys.LAND_TYPE_MATTERS, "you", subject, "", tree.name, "high")
        for subject in sorted(subjects)
    ]


LANES = (_animate_makers, _land_type_matters)
