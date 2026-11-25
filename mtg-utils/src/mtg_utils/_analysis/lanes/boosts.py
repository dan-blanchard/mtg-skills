"""The creature-boost lanes of ADR-0065.

``effect_boost`` (``removal_tutors``) is an effect that boosts ANOTHER creature
or a group. Beside it:

* ``self_boost`` — a creature raising its OWN power or toughness
  (:func:`_self_boost`), subject ``""`` (a triggered or perpetual effect on
  itself), ``activated`` (an activated ability), ``counters`` (+1/+1 counters
  it puts on itself) or ``static`` (its own static ability).
* ``boosts_others`` — the umbrella over everything that makes your OTHER
  creatures bigger, by delivery (:func:`boosts_others_signals`): ``effect``,
  ``counters``, ``anthem``, ``attached``, and ``target_spell`` /
  ``target_ability`` when the boost targets one creature that isn't an
  opponent's.

Every read asks the shared crosswalk walks who a boost lands on
(``crosswalk.boost_recipient``), whether it targets
(``crosswalk.chosen_target``) and how it gets there
(``crosswalk.boost_delivery``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis.lanes._shared import _GRANT_ABILITY_MOD_TAGS
from mtg_utils._analysis.lanes.counters_voltron import gear_pump_subjects
from mtg_utils._analysis.lanes.mana_and_wipes import anthem_defs
from mtg_utils._analysis.lanes.removal_tutors import puts_counters_on_itself
from mtg_utils._analysis.signal_base import Signal
from mtg_utils._analysis.tree_synthesis import animates_itself, effect_boost_units
from mtg_utils._card_ir.crosswalk import (
    OBJECT_FILTER_TAGS,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    boost_delivery,
    boost_recipient,
    chosen_target,
    controller_reach,
    counter_kind,
    counter_raises,
    effect_owner_rebinds_kind,
    filter_controller,
    filter_names_creatures,
    generic_effect_boosts,
    iter_static_defs,
    iter_typed_nodes,
    keyword_counter_placements,
    memo_on,
    names_attached_object,
    pt_mod_signs,
    pump_raises,
    raises_pt,
    raises_with_counters,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
from mtg_utils._card_ir.recovery import ON_SELF, OTHER_CHOOSER, SELF, is_theirs

_SELF_BOOST = signal_keys.SELF_BOOST
_BOOSTS_OTHERS = signal_keys.BOOSTS_OTHERS
#: The keyword actions that put +1/+1 counters on a creature other than the
#: one doing them: bolster (the creature with the least toughness among yours,
#: CR 701.39a), amass (an Army you control, 701.47a), and "each creature you
#: control explores" (``ExploreAll``; each puts the counter on itself, 701.44a).
_OTHERS_COUNTER_ACTIONS: frozenset[str] = frozenset({"Bolster", "Amass", "ExploreAll"})
#: The voltron gear subjects a boost of the creature an Aura or Equipment is
#: attached to emits (``counters_voltron.gear_pump_subjects``): ``pump``, and
#: ``power``, a +N/-M power-up (a raise of one number is a boost, ruling 6).
_ATTACHED_GEAR_SUBJECTS: frozenset[str] = frozenset({"pump", "power"})
#: The subtypes of a noncreature card that is a creature when it grows: a
#: Vehicle its crew makes an artifact creature (CR 301.7), a Spacecraft at its
#: station threshold.
_CREATURE_WHEN_USED: frozenset[str] = frozenset({"vehicle", "spacecraft"})


def is_creature_body(tree: ConceptTree) -> bool:
    """Whether the face is a creature when its boost lands on it: a creature
    card, a Vehicle or a Spacecraft, or a permanent that makes itself a creature
    (``tree_synthesis.animates_itself``: a manland). A noncreature permanent has
    no power or toughness (CR 208.3), so an artifact holding +1/+1 counters it
    will move (Weapon Rack) grows nothing."""
    return (
        tree.is_type("Creature")
        or bool({s.lower() for s in tree.card_subtypes} & _CREATURE_WHEN_USED)
        or animates_itself(tree)
    )


def _self_pump_subject(unit: AbilityUnit, c: ConceptNode) -> str | None:
    """The ``self_boost`` subject of an effect of ``unit`` that raises the card
    itself, or ``None``: ``activated`` for an activated ability's (Shivan
    Dragon), ``""`` for a trigger's or a perpetual change's (Glaze Fiend,
    bushido; Ichor Aberration). A perpetual pump of the card the ability
    returned to the battlefield is recursion that grows it, not an activated
    boost (Vladimir and Godfrey — Dan's call, 2026-11-25)."""
    if c.returned_self:
        return ""
    if unit.origin == "ability" and unit.kind == "Activated":
        return signal_keys.SELF_BOOST_ACTIVATED
    if unit.origin == "trigger" or c.perpetual:
        return ""
    return None


def static_self_boost(tree: ConceptTree) -> bool:
    """A creature's own static ability that raises its own power or toughness
    (CR 604.1, 613.4c): "This creature gets +1/+2 as long as you control a
    Forest" (Kird Ape), "~ gets +1/+1 for each other Elf you control". The line
    (the coordinator's, from Dan's "a creature grows itself by any means"): a
    static whose ``affected`` is the card and whose modification ADDS to power
    or toughness (``AddPower`` / ``AddToughness`` or their counted forms,
    :func:`reads.pt_mod_signs`); a characteristic-defining ability that SETS
    them (CR 604.3, layer 7a — Tarmogoyf's "*/1+*") is the card's size, not a
    boost."""
    for unit in tree.units:
        if unit.origin != "static":
            continue
        for sdef in iter_static_defs(unit.node):
            # The card itself, alone or beside a group ("~ and land creatures
            # you control get +2/+2" — Sylvan Advocate).
            if not any(
                tag_of(arm) == "SelfRef"
                for arm in _arms(getattr(sdef, "affected", None))
            ):
                continue
            if getattr(sdef, "characteristic_defining", None) is True:
                continue
            if max(pt_mod_signs(sdef)) > 0:
                return True
    return False


def _self_boost(tree: ConceptTree) -> list[Signal]:
    """self_boost — a creature raises its OWN power or toughness (ADR-0065).

    * ``""`` — a triggered or perpetual effect on itself: "Whenever another
      artifact you control enters, ~ gets +2/+2 until end of turn" (Glaze
      Fiend), bushido (CR 702.45a: "it gets +N/+N until end of turn"), prowess
      (702.108a: "this creature gets +1/+1 until end of turn" — the keyword
      phase keeps unexpanded, read off ``card_keywords``), a perpetual growth
      (Ichor Aberration), Vladimir and Godfrey's return that grows it.
    * ``activated`` — an activated ability that boosts itself: "{R}: ~ gets
      +1/+0 until end of turn" (Shivan Dragon), "{4}: Put a +1/+1 counter on ~"
      (Walking Ballista). The firebreather's subject: big mana and untap
      effects are its partners.
    * ``counters`` — +1/+1 counters it puts on itself, the ``self_counter_grow``
      population (:func:`removal_tutors.puts_counters_on_itself`).
    * ``static`` — its own static ability (:func:`static_self_boost`).

    Only a creature body grows (:func:`is_creature_body`): a noncreature that
    grants the growth to another creature is ``boosts_others``'. The card
    itself is ``crosswalk.boost_recipient``'s ``"self"``; a raise of one number
    is a boost ("+2/-2"). Scope "you", HIGH."""
    if not is_creature_body(tree):
        return []
    found: dict[str, str] = {}
    for unit in tree.units:
        for c in unit.effects:
            subject: str | None = None
            if c.concept == "pump" and raises_pt(c):
                if boost_recipient(unit, c) == "self":
                    subject = _self_pump_subject(unit, c)
            elif c.concept == "place_counter" and (
                unit.origin == "ability" and unit.kind == "Activated"
            ):
                # The card itself, named: an untargeted placement may be on
                # another object ("that creature enters with two additional
                # +1/+1 counters" — Yuna, Grand Summoner).
                on_self = (
                    ON_SELF in c.subject and "+1/+1 counter" in c.subject
                    if c.recovered_by
                    else raises_with_counters(c)
                    and tag_of(getattr(c.node, "target", None)) == "SelfRef"
                    and boost_recipient(unit, c) == "self"
                )
                if on_self:
                    subject = signal_keys.SELF_BOOST_ACTIVATED
            if subject is not None:
                found.setdefault(subject, c.raw)
        for recipient, _node, _static in generic_effect_boosts(unit):
            if recipient != "self":
                continue
            if unit.origin == "ability" and unit.kind == "Activated":
                found.setdefault(signal_keys.SELF_BOOST_ACTIVATED, "")
            elif unit.origin == "trigger":
                found.setdefault("", "")
    if any(k.lower() == "prowess" for k in tree.card_keywords):
        found.setdefault("", "")
    if puts_counters_on_itself(tree) or any(
        raises_with_counters(c) and boost_recipient(unit, c) == "self"
        for unit in tree.units
        for c in unit.effect_concepts("place_counter")
    ):
        # The self_counter_grow population, and a typed +1/+1 counter whose "it"
        # names the card ("put your choice of a +1/+1 … counter on Me" — Me,
        # the Immortal: the chain's own target, the card).
        found.setdefault(signal_keys.SELF_BOOST_COUNTERS, "")
    if static_self_boost(tree):
        found.setdefault(signal_keys.SELF_BOOST_STATIC, "")
    return [
        Signal(_SELF_BOOST, "you", subject, raw, tree.name, "high")
        for subject, raw in found.items()
    ]


def _counter_boosts(
    tree: ConceptTree,
) -> tuple[bool, tuple[tuple[AbilityUnit, object], ...]]:
    """Whether the card puts +1/+1 counters on, or moves them onto (CR 122.5;
    graft, 702.58a), a creature other than itself or a group that isn't only an
    opponent's — and each such typed placement or move on ONE creature it
    targets, as ``(unit, effect node)``. Memoized on the tree. A placement that
    rebinds its kind per counter on the object is no +1/+1 placement (Quarry
    Hauler)."""
    return memo_on(tree, "_xw_boost_counter_boosts", _read_counter_boosts)


def _read_counter_boosts(
    tree: ConceptTree,
) -> tuple[bool, tuple[tuple[AbilityUnit, object], ...]]:
    others = False
    targeted: list[tuple[AbilityUnit, object]] = []
    for unit in tree.units:
        for c in unit.effects:
            tag = tag_of(c.node)
            if c.concept == "place_counter" and c.recovered_by:
                if (
                    "+1/+1 counter" in c.subject
                    and not {ON_SELF, SELF, OTHER_CHOOSER} & set(c.subject)
                    and not is_theirs(c)
                ):
                    others = True
                continue
            if tag not in ("PutCounter", "PutCounterAll", "MoveCounters"):
                continue
            if tag != "MoveCounters" and effect_owner_rebinds_kind(unit.node, c.node):
                continue
            if not counter_raises(counter_kind(c.node)):
                continue
            if boost_recipient(unit, c) != "yours":
                continue
            others = True
            if tag != "PutCounterAll" and (
                chosen_target(unit, c.node, getattr(c.node, "target", None)) is not None
            ):
                targeted.append((unit, c.node))
    if any(
        keyword in _OTHERS_COUNTER_ACTIONS and kind == "P1P1"
        for keyword, kind in keyword_counter_placements(tree)
    ):
        others = True
    return others, tuple(targeted)


def _anthem_reaches_yours(tree: ConceptTree) -> bool:
    """A static boost of a creature group that reaches your creatures (CR
    604.1, 613.4c): "Creatures you control get +1/+1" (Glorious Anthem), a
    symmetric one ("Black creatures get +1/+1" — Bad Moon; "All creatures get
    +1/+1"), not one only your opponents' creatures get. The card itself, the
    one creature an Aura or Equipment is attached to, and a bestow creature's
    "This creature and enchanted creature" (``attached``) are no group."""
    for sdef in anthem_defs(tree):
        if max(pt_mod_signs(sdef)) <= 0:
            continue
        arms = _arms(getattr(sdef, "affected", None))
        if any(names_attached_object(arm) for arm in arms):
            continue
        if any(
            tag_of(arm) in OBJECT_FILTER_TAGS
            and filter_names_creatures(arm)
            and controller_reach(filter_controller(arm)) == "yours"
            for arm in arms
            if tag_of(arm) != "SelfRef"
        ):
            return True
    return False


def _arms(filt: object) -> tuple[object, ...]:
    """An ``Or`` filter's arms ("~ and other Vampire creatures you control" —
    Vampire Nocturnus), else the filter alone."""
    if tag_of(filt) == "Or":
        arms = getattr(filt, "filters", None)
        return tuple(arms) if isinstance(arms, list) else ()
    return (filt,)


def _granted_growth(tree: ConceptTree) -> Iterator[object]:
    """The ``affected`` filter of each static that grants other creatures an
    ability growing themselves: "Enchanted creature has 'Whenever you gain life,
    put that many +1/+1 counters on this creature'" (Sunbond); "Commander
    creatures you own have '{2}, Sacrifice an artifact: Put a +1/+1 counter on
    this creature'" (Clan Crafter). The ``SelfRef`` inside the granted ability is
    the creature that has it."""
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            mods = getattr(sdef, "modifications", None)
            for mod in mods if isinstance(mods, list) else ():
                if tag_of(mod) not in _GRANT_ABILITY_MOD_TAGS:
                    continue
                if any(_raises_its_holder(n) for n in iter_typed_nodes(mod)):
                    yield getattr(sdef, "affected", None)
                    break


def _raises_its_holder(node: TypedMirrorNode) -> bool:
    """A granted counter placement or pump on the creature that has it."""
    if tag_of(getattr(node, "target", None)) != "SelfRef":
        return False
    tag = tag_of(node)
    if tag == "PutCounter":
        return counter_raises(counter_kind(node))
    return tag == "Pump" and pump_raises(node)


def boosts_others_signals(tree: ConceptTree, out: Iterable[Signal]) -> list[Signal]:
    """boosts_others — anything that makes your OTHER creatures bigger, by
    delivery (ADR-0065), read beside the lanes' own signals of the same tree
    (``out``; it must run after every lane and the bridge rows):

    * ``effect`` — every ``effect_boost`` card;
    * ``counters`` — +1/+1 counters put on or moved onto another creature or a
      group (:func:`_counter_boosts`; ``counter_distribute``'s spreads), and a
      noncreature's grant of that growth to a group (Clan Crafter);
    * ``anthem`` — a static boost of a group that reaches your creatures
      (:func:`_anthem_reaches_yours`; Bad Moon's symmetric one counts);
    * ``attached`` — an Aura or Equipment that boosts the creature it is
      attached to (``counters_voltron.gear_pump_subjects``, the read behind
      ``voltron_makers|you|pump`` and ``|power``, a bestow creature's included),
      and an Aura's or Equipment's grant of growth to that creature (Sunbond);
    * ``target_spell`` / ``target_ability`` — the boost targets ONE creature
      that isn't an opponent's (``crosswalk.chosen_target``), as a spell (an
      instant or sorcery pump or +1/+1-counter spell; an Aura spell, CR
      303.4a, a bestowed one, 702.103b) or as an activated or triggered ability
      (an Equipment's equip, CR 702.6a; a delayed triggered ability, 603.7).

    Scope "you", HIGH; a page-only key (``signal_keys.PAGE_ONLY_KEYS``)."""
    held = {(s.key, s.subject) for s in out}
    found: list[str] = []

    def add(subject: str) -> None:
        if subject not in found:
            found.append(subject)

    if any(key == "effect_boost" for key, _subject in held):
        add(signal_keys.BOOST_EFFECT)
        for boost in effect_boost_units(tree):
            for node in boost.targeted:
                add(_target_subject(boost_delivery(boost.unit, tree, node)))
    counters, targeted = _counter_boosts(tree)
    if counters or any(key == "counter_distribute" for key, _subject in held):
        add(signal_keys.BOOST_COUNTERS)
    for unit, node in targeted:
        add(_target_subject(boost_delivery(unit, tree, node)))
    if _anthem_reaches_yours(tree):
        add(signal_keys.BOOST_ANTHEM)
    subtypes = {s.lower() for s in tree.card_subtypes}
    aura = "aura" in subtypes or any(k.lower() == "bestow" for k in tree.card_keywords)
    if set(gear_pump_subjects(tree, either_arm=True)) & _ATTACHED_GEAR_SUBJECTS and (
        not _attaches_to_opponents_only(tree)
    ):
        add(signal_keys.BOOST_ATTACHED)
        _attached_delivery(add, aura=aura, equipment="equipment" in subtypes)
    if not is_creature_body(tree):
        for affected in _granted_growth(tree):
            if names_attached_object(affected):
                add(signal_keys.BOOST_ATTACHED)
                _attached_delivery(add, aura=aura, equipment="equipment" in subtypes)
            elif controller_reach(filter_controller(affected)) == "yours":
                add(signal_keys.BOOST_COUNTERS)
    return [Signal(_BOOSTS_OTHERS, "you", s, "", tree.name, "high") for s in found]


def _attaches_to_opponents_only(tree: ConceptTree) -> bool:
    """Gear with no equip whose every attach targets an opponent's creature
    (Bloodthirsty Blade's "{1}: Attach this Equipment to target creature an
    opponent controls"): its boost is never yours (the coordinator's call,
    2026-11-25)."""
    if "equipment" not in {s.lower() for s in tree.card_subtypes} or any(
        k.lower() == "equip" for k in tree.card_keywords
    ):
        return False
    attaches = [
        getattr(node, "target", None)
        for unit in tree.units
        for node in iter_typed_nodes(unit.node)
        if tag_of(node) == "Attach"
    ]
    return bool(attaches) and all(
        controller_reach(filter_controller(target)) == "opponents"
        for target in attaches
    )


def _attached_delivery(
    add: Callable[[str], None], *, aura: bool, equipment: bool
) -> None:
    """An Aura (or a bestowed creature) reaches its creature as a spell that
    targets (CR 303.4a); an Equipment by equip, an ability (CR 702.6a)."""
    if aura:
        add(signal_keys.BOOST_TARGET_SPELL)
    if equipment:
        add(signal_keys.BOOST_TARGET_ABILITY)


def _target_subject(delivery: str) -> str:
    return (
        signal_keys.BOOST_TARGET_SPELL
        if delivery == "spell"
        else signal_keys.BOOST_TARGET_ABILITY
    )


LANES = (_self_boost,)
