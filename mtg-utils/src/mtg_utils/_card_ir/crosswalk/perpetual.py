"""A perpetual power/toughness change read as the pump it is.

Phase types "~ perpetually gets +1/+1" (Accident-Prone Apprentice) and "target
creature an opponent controls perpetually gets -1/-2" (Davriel's Withering) as
``ApplyPerpetual{target, modification: ModifyPowerToughness{power, toughness}}``.
"Perpetually" is an Arena-only (Alchemy) mechanic outside the Comprehensive
Rules; the repo's digital supplement, DD1.1: "A perpetual effect modifies a
specific card permanently for the rest of the game, regardless of zone
changes". Every lane that reads a
pump reads ``concept == "pump"`` and the ``Pump`` / ``PumpAll`` node's
``power`` / ``toughness`` / ``target``, so the change is decorated here, once,
as that concept carrying a ``Pump`` / ``PumpAll`` view of the same fields — and
no lane is taught a special case.

**Only a creature on the battlefield is pumped** (the lane's own decision,
2026-11-25): a creature card in a hand, a library or a graveyard, a spell on the
stack, a card sought, conjured or drafted, is changed but not pumped. The
recipient is read off the structure (:func:`perpetual_changes`):

* ``SelfRef`` / ``Any`` (phase writes ``Any`` for "~ perpetually gets") is the
  card itself: on the battlefield when the card is a creature and its ability
  works from the battlefield (``reads.ability_zones``) or an earlier effect of
  the chain put it there — not from a graveyard-only activation (Diminished
  Returner), a trigger granted to another card (Tawnos Endures), or after it
  died (Tomakul Phoenix).
* A ``Typed`` filter is a targeted creature, unless its zone is elsewhere.
* ``ParentTarget`` is what the earlier effect of the chain acted on: a card put
  onto the battlefield (Vladimir and Godfrey), a target an effect left there; not
  a card chosen from a hand (Veteran Charger), sought (Hardened Bonds) or
  returned to a hand (Candela, Aegis of Adagia). With no earlier effect
  it is the trigger's object (as is ``TriggeringSource``): a creature entering
  the battlefield, blocking or crewing; not a spell cast (Rothga) or a card
  that died.
* ``CostPaidObject`` of a behold ("If a Dragon creature was beheld, it
  perpetually gets +2/+2" — Territorial Strike) is a card revealed from your
  hand or a permanent you control (CR 701.4a): pumped on the battlefield, and a
  ``card_boost`` of your hand.
* ``TrackedSet`` ("those creatures") is the population the earlier mass effect
  acted on; the view is a ``PumpAll`` over that effect's filter, so it keeps
  whose creatures they are ("each creature target player controls" — Chaos
  Balor, whose player can be you), and a raise on creatures only your opponents
  control is no pump of yours.

The rules themselves live in ``_card_ir.perpetual_rules``, which the parked-
change rewrite (``misparsed_shapes``) asks too. The view is marked
``ConceptNode.perpetual``: the change lasts, timed or better, so
``effect_boost`` reads it as a pump with a duration of its own — except one on
the card itself, which is the card growing (Dan's call, 2026-11-25).

A change that lands on cards of yours off the battlefield is the ``card_boost``
read's (:func:`card_boost_zones`, at the end of this module), never a pump.

Anything else — an earlier effect phase left a residue, a trigger mode phase
couldn't type — is left unread. ``ApplyPerpetual`` stays in the typed tree, so
the reads of its other parts (the keyword grant, the perpetual graveyard
return) walk it as before; only the unit's effect decoration changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields, replace
from typing import NamedTuple

from mtg_utils._card_ir.crosswalk.core import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    decorate_effect,
)
from mtg_utils._card_ir.crosswalk.reads import (
    ability_zones,
    beholds,
    filter_controller,
    filter_inzone_zones,
    pump_raises,
    tag_of,
)
from mtg_utils._card_ir.mirror.generated import GENERATED_BY_KEY
from mtg_utils._card_ir.mirror.runtime import MISSING, MirrorVariant, TypedMirrorNode
from mtg_utils._card_ir.perpetual_rules import (
    EARLIER,
    OFF_BATTLEFIELD_TAGS,
    Recipient,
    card_by_zones,
    earlier_object,
    earlier_zone,
    later_zone,
    names_another_zone,
    one_other_zone,
    population_pump_is_yours,
    tracked_population,
    trigger_object,
    trigger_zone,
)

#: Fields under which an ability is granted to another object: a ``SelfRef``
#: there names that object, not this card.
_GRANT_FIELDS = frozenset({"static_abilities", "modifications", "definition"})


class _Body(NamedTuple):
    """An ability body in its chain: the bodies before it, the trigger it runs
    for (``None`` in an ability), whether it sits in a granted ability, and the
    bodies after it."""

    body: TypedMirrorNode
    earlier: tuple[TypedMirrorNode, ...]
    trigger: TypedMirrorNode | None
    granted: bool
    later: tuple[TypedMirrorNode, ...] = ()


def _is_trigger_def(node: TypedMirrorNode) -> bool:
    return getattr(node, "trigger_zones", MISSING) is not MISSING and isinstance(
        getattr(node, "execute", None), TypedMirrorNode
    )


def _children(node: TypedMirrorNode, skip: str = "") -> Iterator[tuple[str, object]]:
    for f in fields(node):
        if f.name != skip:
            yield f.name, getattr(node, f.name)


def _bodies(
    node: object, trigger: TypedMirrorNode | None, *, granted: bool
) -> Iterator[_Body]:
    """Every ability body under ``node``, with its chain context."""
    if isinstance(node, MirrorVariant):
        yield from _bodies(node.inner, trigger, granted=granted)
        return
    if isinstance(node, list):
        for item in node:
            yield from _bodies(item, trigger, granted=granted)
        return
    if not isinstance(node, TypedMirrorNode):
        return
    if _is_trigger_def(node):
        trigger = node
    if tag_of(node) is None and isinstance(
        getattr(node, "effect", None), TypedMirrorNode
    ):
        chain: list[TypedMirrorNode] = []
        body: object = node
        while isinstance(body, TypedMirrorNode):
            chain.append(body)
            body = getattr(body, "sub_ability", None)
        for i, body in enumerate(chain):
            yield _Body(body, tuple(chain[:i]), trigger, granted, tuple(chain[i + 1 :]))
            for name, value in _children(body, skip="sub_ability"):
                yield from _bodies(
                    value, trigger, granted=granted or name in _GRANT_FIELDS
                )
        return
    for name, value in _children(node):
        yield from _bodies(value, trigger, granted=granted or name in _GRANT_FIELDS)


def _pt_change(effect: object) -> TypedMirrorNode | None:
    """The ``ModifyPowerToughness`` modification of an ``ApplyPerpetual``."""
    if tag_of(effect) != "ApplyPerpetual":
        return None
    mod = getattr(effect, "modification", None)
    if (
        isinstance(mod, TypedMirrorNode)
        and getattr(mod, "kind", None) == "ModifyPowerToughness"
    ):
        return mod
    return None


def _zones(filt: object) -> tuple[str, ...]:
    return filter_inzone_zones(filt) if tag_of(filt) == "Typed" else ()


def _returns_self(effect: object, decorations: dict[int, list[ConceptNode]]) -> bool:
    """An effect putting the card itself onto the battlefield: phase's typed
    return, or a residue the recovery grammar reads as returning it."""
    if tag_of(effect) in ("ChangeZone", "ChangeZoneAll"):
        return (
            getattr(effect, "destination", None) == "Battlefield"
            and tag_of(getattr(effect, "target", None)) == "SelfRef"
        )
    return any(
        c.concept == "change_zone"
        and c.recovered_by == "reanimate"
        and "Self" in c.reading
        for c in decorations.get(id(effect), ())
    )


def _moves_self_away(effect: object) -> bool:
    if tag_of(getattr(effect, "target", None)) != "SelfRef":
        return False
    tag = tag_of(effect)
    if tag in ("ChangeZone", "ChangeZoneAll"):
        return getattr(effect, "destination", None) != "Battlefield"
    return tag in OFF_BATTLEFIELD_TAGS


def _the_card(
    at: _Body, unit: AbilityUnit, tree: ConceptTree, decorations: dict
) -> Recipient:
    """Where the card itself is when the body resolves."""
    if at.granted:
        return "unknown"
    if not tree.is_type("Creature"):
        return "off"
    for body in reversed(at.earlier):
        effect = getattr(body, "effect", None)
        if _returns_self(effect, decorations):
            return "returned"
        if _moves_self_away(effect):
            return "off"
    return card_by_zones(
        ability_zones(at.trigger if at.trigger is not None else unit.node)
    )


def _trigger_object(trigger: TypedMirrorNode | None) -> Recipient:
    if trigger is None:
        return "unknown"
    return trigger_object(
        getattr(trigger, "mode", None),
        getattr(trigger, "destination", None),
        watches_self=tag_of(getattr(trigger, "valid_card", None)) == "SelfRef",
    )


def _earlier_effect(at: _Body) -> object:
    return getattr(at.earlier[-1], "effect", None) if at.earlier else None


def _parent(at: _Body, decorations: dict) -> Recipient:
    """What ``ParentTarget`` names: the object the earlier effect acted on."""
    if not at.earlier:
        return _trigger_object(at.trigger)
    effect = _earlier_effect(at)
    if _returns_self(effect, decorations):
        return "self"
    target = getattr(effect, "target", None)
    extra = getattr(effect, "additional_zones", None)
    return earlier_object(
        tag_of(effect),
        destination=getattr(effect, "destination", None),
        choice_zone=getattr(effect, "zone", None),
        target_typed=tag_of(target) == "Typed",
        target_zones=_zones(target),
        choice_zones=[z for z in extra if isinstance(z, str)]
        if isinstance(extra, list)
        else (),
    )


def _population(at: _Body) -> object:
    """The filter of the population the earlier effect acted on."""
    return getattr(_earlier_effect(at), "target", None)


def _tracked(at: _Body) -> Recipient:
    """What ``TrackedSet`` names: the population the earlier effect acted on
    (``perpetual_rules.tracked_population``)."""
    target = _population(at)
    return tracked_population(
        tag_of(_earlier_effect(at)),
        target_typed=tag_of(target) == "Typed",
        target_zones=_zones(target),
    )


def _recipient(
    at: _Body,
    unit: AbilityUnit,
    tree: ConceptTree,
    decorations: dict[int, list[ConceptNode]],
) -> Recipient:
    """Where the ``ApplyPerpetual`` heading ``at`` lands (the module docstring's
    rules)."""
    target = getattr(getattr(at.body, "effect", None), "target", None)
    tag = tag_of(target)
    if tag in ("SelfRef", "Any"):
        return _the_card(at, unit, tree, decorations)
    if tag == "Typed":
        return "off" if names_another_zone(_zones(target)) else "battlefield"
    if tag in ("ParentTarget", "TriggeringSource"):
        found = (
            _parent(at, decorations)
            if tag == "ParentTarget"
            else _trigger_object(at.trigger)
        )
        return _the_card(at, unit, tree, decorations) if found == "self" else found
    if tag == "TrackedSet":
        return _tracked(at)
    if tag == "CostPaidObject" and beholds(unit):
        # "Behold a [quality]" means "Reveal a [quality] card from your hand or
        # choose a [quality] permanent you control on the battlefield" (CR
        # 701.4a): the beheld object can be a creature you control.
        return "battlefield"
    return "unknown"


def _as_pump_amount(amount: object) -> object | None:
    """``amount`` in a ``Pump``'s form: a ``Fixed`` as is, any other quantity
    wrapped in the ``Quantity`` phase writes for a dynamic pump (Ral's
    Staticaster's "+1/+0 for each …")."""
    tag = tag_of(amount)
    if tag == "Fixed":
        return amount
    if (
        not isinstance(amount, TypedMirrorNode)
        or ("value", tag) not in GENERATED_BY_KEY
    ):
        return None
    inner = _built(
        "value", tag or "", **{f.name: getattr(amount, f.name) for f in fields(amount)}
    )
    return _built("power", "Quantity", value=inner)


def pump_view(
    effect: TypedMirrorNode, recipient: Recipient, population: object = None
) -> TypedMirrorNode | None:
    """The ``Pump`` (one object) or ``PumpAll`` (a population) phase types for
    the same power/toughness change on the same recipient — ``SelfRef`` for the
    card itself, the earlier effect's filter (``population``) for a
    ``TrackedSet``, so the view keeps whose creatures they are ("each creature
    target player controls": ``TargetPlayer`` — Chaos Balor) — and no
    duration: the change is perpetual. ``None`` off the battlefield, for an
    amount a ``Pump`` can't hold, or for a raise on a population only your
    opponents control (``perpetual_rules.population_pump_is_yours``)."""
    mod = _pt_change(effect)
    if mod is None or recipient in ("off", "unknown"):
        return None
    power = _as_pump_amount(getattr(mod, "power", None))
    toughness = _as_pump_amount(getattr(mod, "toughness", None))
    if power is None or toughness is None:
        return None
    target = getattr(effect, "target", None)
    if recipient in ("self", "returned"):
        target = _built("target", "SelfRef")
    if tag_of(target) != "TrackedSet":
        return _built("effect", "Pump", power=power, toughness=toughness, target=target)
    if tag_of(population) != "Typed":
        return None
    view = _built(
        "effect", "PumpAll", power=power, toughness=toughness, target=population
    )
    controller = getattr(population, "controller", None)
    yours = population_pump_is_yours(
        controller if isinstance(controller, str) else None, raises=pump_raises(view)
    )
    return view if yours else None


def _built(field: str, tag: str, **values: object) -> TypedMirrorNode:
    """The mirror node phase's loader builds for ``tag`` in ``field`` (the
    strict loader's own dispatch, ``loader._walk_tagged``)."""
    return GENERATED_BY_KEY[(field, tag)](**values)


def perpetual_changes(
    unit: AbilityUnit, tree: ConceptTree
) -> Iterator[tuple[TypedMirrorNode, Recipient, object]]:
    """Each perpetual power/toughness change of ``unit`` with its recipient and
    the population an earlier effect acted on (for a ``TrackedSet``)."""
    if not any(_pt_change(c.node) is not None for c in unit.effects):
        return
    decorations: dict[int, list[ConceptNode]] = {}
    for c in unit.effects:
        decorations.setdefault(id(c.node), []).append(c)
    for at in _bodies(unit.node, None, granted=False):
        effect = getattr(at.body, "effect", None)
        if _pt_change(effect) is not None:
            assert isinstance(effect, TypedMirrorNode)
            yield effect, _recipient(at, unit, tree, decorations), _population(at)


def apply_perpetual_pumps(tree: ConceptTree) -> ConceptTree:
    """``tree`` with each perpetual power/toughness change of a creature on the
    battlefield decorated as a ``pump`` (:func:`pump_view`)."""
    units = []
    changed = False
    for unit in tree.units:
        views = {
            id(effect): (view, recipient == "returned")
            for effect, recipient, population in perpetual_changes(unit, tree)
            if (view := pump_view(effect, recipient, population)) is not None
        }
        if views:
            changed = True
            unit = replace(  # noqa: PLW2901
                unit,
                effects=tuple(
                    replace(_pumped(*views[id(c.node)]), raw=c.raw)
                    if id(c.node) in views
                    else c
                    for c in unit.effects
                ),
            )
        units.append(unit)
    return replace(tree, units=tuple(units)) if changed else tree


def _pumped(view: TypedMirrorNode, returned: bool) -> ConceptNode:  # noqa: FBT001
    node = decorate_effect(view)
    assert node is not None
    return replace(node, perpetual=True, returned_self=returned)


# ── A perpetual boost to your cards outside the battlefield ─────────────────────
# The ``card_boost`` lane's read (Dan's ruling, 2026-11-25): where a perpetual
# power/toughness raise lands on cards of yours that are not on the battlefield
# ("A perpetual effect modifies a specific card permanently for the rest of the
# game, regardless of zone changes" — the repo's digital supplement, DD1.1). Two
# sources: phase's typed change (Veteran Charger's "choose a creature card in
# your hand. It perpetually gets +2/+2"; Rothga, Bonded Engulfer's delayed "When
# you cast a creature spell, it perpetually gets +X/+X", which no unit
# decorates), and a parked one the recovery stage decorated with what it lands
# on (``ConceptNode.perpetual_cards``, ``recovery.mark_perpetual_cards``: Feed
# the Bog's "Creature cards in your graveyard perpetually get +1/+1"). The
# residue stays parked: phase's typed form for cards in a zone covers only a
# plain population of one zone (Fountainport Charmer's ``InZone`` filter), not a
# random or topmost card, every card you own, or a duplicate a parked conjure
# made. A card an earlier instruction named is filed where it ENDS UP in the
# ability — the last zone move of that object, before or after the change
# (Richlau, Headmaster's "Put it into your library second from the top"). A
# change to the card itself is the card growing (Tomakul Phoenix), and a shrink
# no boost.

#: Effects that take a permanent off the battlefield to a zone of its owner's.
_TAKES_A_PERMANENT = frozenset({"Destroy", "Bounce"})


def _trigger_card_zone(trigger: TypedMirrorNode | None) -> str | None:
    """The zone of the card a trigger watched, outside the battlefield; ``None``
    for the card itself (a trigger that watches only it — Tomakul Phoenix)."""
    if trigger is None or tag_of(getattr(trigger, "valid_card", None)) == "SelfRef":
        return None
    if _trigger_object(trigger) != "off":
        return None
    return trigger_zone(
        getattr(trigger, "mode", None), getattr(trigger, "destination", None)
    )


def _moved_to(effect: object, decorations: dict) -> str | None:
    """The zone a parked instruction moves its cards into, as the recovery stage
    decorated it (``ConceptNode.moves_to``)."""
    return next(
        (c.moves_to for c in decorations.get(id(effect), ()) if c.moves_to), None
    )


def _earlier_card_zone(at: _Body, decorations: dict) -> str | None:
    """The zone outside the battlefield of the card the earlier effect of the
    chain acted on (``perpetual_rules.earlier_zone``), or of the cards a parked
    conjure made ("conjure X duplicates of it into exile" — Gyox, Brutal
    Carnivora); the trigger's card with no earlier effect."""
    if not at.earlier:
        return _trigger_card_zone(at.trigger)
    effect = _earlier_effect(at)
    if _returns_self(effect, decorations):
        return None
    if tag_of(effect) == "Unimplemented":
        return _moved_to(effect, decorations)
    target = getattr(effect, "target", None)
    if (
        tag_of(effect) in _TAKES_A_PERMANENT
        and tag_of(target) == "Typed"
        and filter_controller(target) != "You"
    ):
        # a permanent anyone controls, destroyed or returned to its owner's
        # hand: no card of yours
        return None
    return earlier_zone(
        tag_of(effect),
        destination=getattr(effect, "destination", None),
        choice_zone=getattr(effect, "zone", None),
        target_zones=_zones(target),
    )


def _object_zone(at: _Body, decorations: dict) -> str | None:
    """Where the card an earlier instruction named (:func:`_earlier_card_zone`)
    ends up in the ability: the last later effect of the chain that moves it
    (one on ``ParentTarget``, ``perpetual_rules.later_zone``, or a parked move
    of it — "Then shuffle those duplicates into your library"), else where the
    earlier one left it."""
    zone = _earlier_card_zone(at, decorations)
    if zone is None:
        return None
    for body in at.later:
        effect = getattr(body, "effect", None)
        if tag_of(effect) == "Unimplemented":
            zone = _moved_to(effect, decorations) or zone
        elif tag_of(getattr(effect, "target", None)) == "ParentTarget":
            zone = later_zone(tag_of(effect), getattr(effect, "destination", None)) or (
                zone
            )
    return zone


def _typed_card_zones(
    at: _Body, decorations: dict, unit: AbilityUnit
) -> tuple[str, ...]:
    """Where the typed ``ApplyPerpetual`` heading ``at`` lands on a card of yours
    outside the battlefield (the rules :func:`_recipient` reads it by): a target
    in another zone, the earlier effect's object where it ends up, the
    trigger's card, the population an earlier mass effect acted on, a card a
    behold revealed from your hand (phase's ``CostPaidObject``). A change in
    a granted ability lands on the object it was granted to, whose owner the
    structure doesn't tell (Tawnos Endures's "Exile target creature" — anyone's),
    so it is none."""
    target = getattr(getattr(at.body, "effect", None), "target", None)
    tag = tag_of(target)
    if tag == "Typed":
        if filter_controller(target) == "Opponent":
            return ()
        zone = one_other_zone(_zones(target))
    elif tag == "ParentTarget":
        zone = _object_zone(at, decorations)
    elif tag == "TriggeringSource":
        zone = _trigger_card_zone(at.trigger)
    elif tag == "TrackedSet" and _tracked(at) == "off":
        zone = _object_zone(at, decorations)
    elif tag == "CostPaidObject" and beholds(unit):
        zone = "Hand"  # a beheld card revealed from your hand (CR 701.4a)
    else:
        zone = None
    return (zone,) if zone else ()


def _parked_card_zones(at: _Body, decorations: dict) -> tuple[str, ...]:
    """Where the parked perpetual raise heading ``at`` lands on cards of yours
    outside the battlefield: the recovery stage's ``perpetual_cards``, a card an
    earlier instruction named located where it ends up (:func:`_object_zone`)."""
    effect = getattr(at.body, "effect", None)
    zones: list[str] = []
    for c in decorations.get(id(effect), ()):
        for entry in c.perpetual_cards:
            zone = _object_zone(at, decorations) if entry == EARLIER else entry
            if zone:
                zones.append(zone)
    return tuple(zones)


def card_boost_zones(unit: AbilityUnit) -> frozenset[str]:
    """The zones outside the battlefield where ``unit``'s perpetual power or
    toughness raises land on cards of yours (``Hand``, ``Graveyard``,
    ``Library``, ``Stack``, or ``EVERYWHERE``), typed or parked,
    in its own chain and in every trigger nested under it."""
    decorations: dict[int, list[ConceptNode]] = {}
    for c in unit.effects:
        decorations.setdefault(id(c.node), []).append(c)
    zones: set[str] = set()
    for at in _bodies(unit.node, None, granted=False):
        effect = getattr(at.body, "effect", None)
        mod = _pt_change(effect)
        if mod is not None:
            if pump_raises(mod) and not at.granted:
                zones.update(_typed_card_zones(at, decorations, unit))
        elif tag_of(effect) == "Unimplemented":
            zones.update(_parked_card_zones(at, decorations))
    return frozenset(zones)
