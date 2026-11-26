"""Where a creature boost lands, and how it gets there (ADR-0065).

The boost lanes split on two facts about each boost, read here once so every
lane asks the same question:

* **Who gets it** (:func:`boost_recipient`): the card itself (``"self"``),
  a creature or group of yours or either side's (``"yours"``), or only an
  opponent's (``"opponents"``). A boost that can only land on an opponent's
  creature is never yours (Dan's ruling, 2026-11-25).
* **How it is delivered** to one chosen creature (:func:`boost_delivery`): as
  a spell (CR 115.1a: an instant or sorcery whose spell ability says "target")
  or as an activated or triggered ability.

Phase writes the card itself as ``SelfRef`` (and, for a trigger that watches
only itself, never ``TriggeringSource``: Freelance Muscle's parked "it" is
rewritten to ``SelfRef``). A ``TriggeringSource`` on a trigger whose
``valid_card`` is the card is the OTHER object of the event: the creature
blocking or blocked by it (flanking's blocker, CR 702.25a; Flailing Drake's
"that creature"), the Vehicle it crews (Veteran Motorist). A creature that
blocks yours, or that yours blocks, is controlled by the defending or the
attacking player — another player (CR 509.1a) — so a combat trigger's other
creature is an opponent's.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Literal, NamedTuple

from mtg_utils._card_ir.crosswalk.core import AbilityUnit, ConceptNode, ConceptTree
from mtg_utils._card_ir.crosswalk.reads import (
    OBJECT_FILTER_TAGS,
    _find_owner_wrapper,
    acts_on_a_group,
    beholds,
    controller_side,
    counter_kind,
    effect_chosen_on_resolution,
    filter_controller,
    filter_inzone_zones,
    filter_names_creatures,
    iter_static_defs,
    iter_threaded_target_statics,
    iter_typed_nodes,
    memo_on,
    names_attached_object,
    pt_mod_signs,
    pump_raises,
    tag_of,
    targets_the_card,
    unit_keyword_grants,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode

BoostRecipient = Literal["self", "yours", "opponents", "unknown"]
BoostDelivery = Literal["spell", "ability"]

#: Trigger modes whose event has a second object, the one a ``TriggeringSource``
#: names when the trigger watches the card: the creature in combat with it
#: ("whenever ~ blocks or becomes blocked by a creature, that creature …", when
#: phase names it on ``valid_target``), the Vehicle or Mount it crews or saddles,
#: the permanent it becomes unattached from.
_COMBATANT_MODES: frozenset[str] = frozenset(
    {"Blocks", "BecomesBlocked", "BlocksOrBecomesBlocked"}
)
_CREW_MODES: frozenset[str] = frozenset({"Crews", "SaddlesOrCrews", "Unattach"})
#: The effects an "it" resolves for (the anaphor walk's ``effect_tags``).
_ANAPHOR_EFFECT_TAGS: frozenset[str] = frozenset(
    {"Pump", "PumpAll", "PutCounter", "MoveCounters", "ApplyPerpetual"}
)
#: A power/toughness counter kind in phase's spelling (``P1P1``, ``M1M1``,
#: ``P1P0``): the sign and size of each number.
_PT_COUNTER_RX = re.compile(r"^([PM])(\d+)([PM])(\d+)$")


def _mode(trig: object) -> str:
    mode = getattr(trig, "mode", None)
    return mode if isinstance(mode, str) else (tag_of(mode) or "")


def controller_reach(controller: str | None) -> BoostRecipient:
    """Whose creatures a filter's phase ``controller`` lets a boost reach:
    ``"opponents"`` for one only an opponent's creatures meet ("creatures your
    opponents control"), else ``"yours"`` — your own, either side's (Bad Moon's
    "Black creatures"), or the defending player's, who can be you: you cast a
    trick on "target creature defending player controls" while an opponent
    attacks you (Yare)."""
    if controller == "DefendingPlayer":
        return "yours"
    return "opponents" if controller_side(controller) == "opponents" else "yours"


def _filter_side(filt: object) -> BoostRecipient:
    return controller_reach(filter_controller(filt))


#: The targets that name an object a later "it" can refer back to.
_NAMED_OBJECT_TAGS: frozenset[str] = OBJECT_FILTER_TAGS | {"Any", "SelfRef"}
#: The effects that put a permanent of yours onto the battlefield a later "it"
#: names: a token (``reads.ends_target_thread``'s producers), a manifested card
#: ("manifest dread, then put two +1/+1 counters on that creature").
_MADE_PERMANENT_TAGS: frozenset[str] = frozenset(
    {"Token", "CopyTokenOf", "Manifest", "ManifestDread", "Cloak"}
)
#: What an "it" names after the chain made a token: the token you made.
MADE_TOKEN: object = object()


class _Anaphora(NamedTuple):
    """One unit's back-references, walked once: the chosen object each "it"
    names (``threaded``: id of an effect or a nested static → the filter the
    chain's own target thread gives it), and the trigger each node of a delayed
    triggered ability waits on (``delayed``: id → that trigger)."""

    threaded: dict[int, object]
    delayed: dict[int, TypedMirrorNode]
    #: id → the group or object a "those creatures" (``TrackedSet``) names.
    tracked: dict[int, object]
    #: id → what an "it" the target thread leaves open names: the last object an
    #: earlier effect named, a token the chain made, a creature it manifested.
    #: A recipient, never a target (:func:`chosen_target` reads only the thread).
    named: dict[int, object]


def _written_effects(node: object) -> Iterator[TypedMirrorNode]:
    """An ability's effects in the order its text gives them: each body's
    ``effect`` (a delayed trigger's and a choice's branches after it), its
    ``else_ability``, then its ``sub_ability`` chain. ``iter_typed_nodes`` walks
    fields, not that order."""
    body = getattr(node, "execute", None) if _is_trigger(node) else node
    while isinstance(body, TypedMirrorNode):
        effect = getattr(body, "effect", None)
        if isinstance(effect, TypedMirrorNode):
            yield effect
            if tag_of(effect) == "CreateDelayedTrigger":
                yield from _written_effects(getattr(effect, "effect", None))
            for branch in _listed(effect, "branches"):
                yield from _written_effects(branch)
        yield from _written_effects(getattr(body, "else_ability", None))
        for mode in _listed(body, "mode_abilities"):
            yield from _written_effects(mode)
        body = getattr(body, "sub_ability", None)


def _listed(node: object, field: str) -> list:
    """A list field of a mirror node, ``[]`` when absent (phase's ``MISSING``)."""
    value = getattr(node, field, None)
    return value if isinstance(value, list) else []


def _is_trigger(node: object) -> bool:
    return isinstance(getattr(node, "execute", None), TypedMirrorNode)


def _anaphora(unit: AbilityUnit) -> _Anaphora:
    def build(_unit: AbilityUnit) -> _Anaphora:
        tracked: dict[int, object] = {}
        named: dict[int, object] = {}
        threaded = {
            id(node): target
            for target, node in iter_threaded_target_statics(
                unit.node, effect_tags=_ANAPHOR_EFFECT_TAGS
            )
        }
        # A chain headed by a choice of objects (phase's ``TargetOnly``: "choose
        # two creatures you control … those creatures get +X/+X" — Spry and
        # Mighty, ``Any``; "put your choice of a +1/+1, first strike, … counter
        # on Me" — Me, the Immortal, ``SelfRef``) names them for every later
        # "it" the thread leaves open.
        head = getattr(getattr(unit.node, "execute", unit.node), "effect", None)
        chosen_head = getattr(head, "target", None)
        if tag_of(head) == "TargetOnly" and chosen_head is not None:
            for node in iter_typed_nodes(unit.node):
                if tag_of(getattr(node, "target", None)) == "ParentTarget":
                    threaded.setdefault(id(node), chosen_head)
        # A token the chain makes is what a later "it" names ("Create a 0/0
        # Fractal creature token. Put X +1/+1 counters on it" — Applied
        # Geometry): the thread ends at a token producer
        # (``reads.ends_target_thread``).
        made = False
        for node in _written_effects(unit.node):
            if tag_of(node) in _MADE_PERMANENT_TAGS:
                made = True
            elif made and tag_of(getattr(node, "target", None)) in (
                "ParentTarget",
                "TriggeringSource",
            ):
                named.setdefault(id(node), MADE_TOKEN)
        # "those creatures" (``TrackedSet``) after an effect over a group or a
        # chosen object names that object ("Creatures you control gain first
        # strike … they get +1/+1" — Savage Offensive), and the n-th chosen
        # object (``ParentTargetSlot``) the n-th ``TargetOnly``'s ("put a +1/+1
        # counter on target creature you control. Then that creature fights …"
        # — Duel for Dominance).
        chosen: list[object] = []
        group: object = None
        last: object = None
        for node in _written_effects(unit.node):
            target = getattr(node, "target", None)
            ttag = tag_of(target)
            # An "it" the target thread leaves open names the last object an
            # earlier effect acted on ("Prevent all damage … by target creature
            # you control. That creature gets +0/+X" — Kry Shield; "deals 3
            # damage to any target. If a creature is dealt damage this way, it
            # gets +5/+0" — Provoke the Trolls).
            if ttag == "ParentTarget" and last is not None and id(node) not in threaded:
                named.setdefault(id(node), last)
            if ttag in _NAMED_OBJECT_TAGS and not acts_on_a_group(node, unit):
                last = target
            if tag_of(node) == "TargetOnly" and target is not None:
                chosen.append(target)
            if ttag == "TrackedSet" and group is not None:
                tracked.setdefault(id(node), group)
            elif ttag == "ParentTargetSlot":
                index = getattr(target, "index", None)
                if isinstance(index, int) and 0 <= index < len(chosen):
                    threaded.setdefault(id(node), chosen[index])
            if ttag in OBJECT_FILTER_TAGS:
                group = target
            for st in _listed(node, "static_abilities"):
                if tag_of(getattr(st, "affected", None)) in OBJECT_FILTER_TAGS:
                    group = st.affected
        # A perpetual pump view is built fresh (``crosswalk.perpetual``): its
        # "it" is the typed ``ApplyPerpetual``'s ("Untap target Elf. It
        # perpetually gets +1/+1" — Freyalise, Skyshroud Partisan).
        sources = [
            threaded[id(n)]
            for n in _written_effects(unit.node)
            if tag_of(n) == "ApplyPerpetual" and id(n) in threaded
        ]
        for c in unit.effects:
            if c.perpetual and len(sources) == 1:
                threaded.setdefault(id(c.node), sources[0])
        delayed: dict[int, TypedMirrorNode] = {}
        for node in iter_typed_nodes(unit.node):
            if tag_of(node) != "CreateDelayedTrigger":
                continue
            trig = getattr(getattr(node, "condition", None), "trigger", None)
            if not isinstance(trig, TypedMirrorNode):
                # "At the beginning of the next end step": no watched object.
                trig = node
            for inner in iter_typed_nodes(getattr(node, "effect", None)):
                delayed.setdefault(id(inner), trig)
        return _Anaphora(threaded, delayed, tracked, named)

    return memo_on(unit, "_xw_boost_anaphora", build)


def _event_object(unit: AbilityUnit, node: object) -> BoostRecipient:
    """Whose creature a ``TriggeringSource`` names: the object of the trigger
    whose firing performs ``node`` — a delayed trigger's own, when it watches an
    event ("whenever one or more creatures attack …, those creatures …"), else
    the unit's. A trigger that watches the card names the card (a death's "exile
    it"; Protean Hydra's "put two +1/+1 counters on it"), except an event with a
    second object (:data:`_COMBATANT_MODES`, :data:`_CREW_MODES`): the
    creature in combat with it, which another player controls (CR 509.1a), or the
    Vehicle it crews."""
    trig = _anaphora(unit).delayed.get(id(node))
    if isinstance(trig, TypedMirrorNode) and _mode(trig):
        watched = getattr(trig, "valid_card", None)
        if watched is None:
            watched = getattr(trig, "valid_source", None)
        if tag_of(watched) in ("ParentTarget", "TrackedSet"):
            # A delayed trigger watching "it" / "those creatures" watches what the
            # ability that made it named ("Whenever either of those creatures
            # deals combat damage …, put a +1/+1 counter on it" — Love on the
            # Battlefield's attackers).
            trig = None
    else:
        trig = None
    if trig is None:
        if unit.origin != "trigger":
            return "unknown"
        trig = unit.node
    mode = _mode(trig)
    if mode == "YouAttack":
        # "Whenever you attack with …, those creatures …": your attackers (CR
        # 508.1a: the active player declares attackers).
        return "yours"
    # The watched object: the card or a filter; a damage trigger names its
    # source on ``valid_source`` ("Whenever a Vampire you control deals combat
    # damage to a player, put a +1/+1 counter on it" — Rakish Heir).
    watched = getattr(trig, "valid_card", None)
    if watched is None:
        watched = getattr(trig, "valid_source", None)
    if tag_of(watched) == "AttachedTo" or names_attached_object(watched):
        # "Whenever equipped creature attacks, put a +1/+1 counter on it" (Holy
        # Frazzle-Cannon): the creature its Aura or Equipment is on, either
        # side's.
        return "yours"
    if tag_of(watched) != "SelfRef":
        return (
            _filter_side(watched)
            if tag_of(watched) in OBJECT_FILTER_TAGS
            else "unknown"
        )
    if mode in _COMBATANT_MODES and getattr(trig, "valid_target", None) is not None:
        return "opponents"
    if mode in _CREW_MODES:
        return "yours"
    return "self"


def object_recipient(
    unit: AbilityUnit, target: object, node: object = None
) -> BoostRecipient:
    """Who an effect's ``target`` field names, for a boost: the card itself
    (``SelfRef``; an activated ability with no target acts on its own source —
    Shivan Dragon's "{R}: ~ gets +1/+0", which phase leaves untargeted), an
    opponent's creature only, a creature or group of yours or of either side,
    or ``"unknown"`` where the structure names no object. ``node`` is the
    effect (or nested static) the target belongs to: an "it" (``ParentTarget``)
    resolves through the chain's own target thread ("Untap target creature. It
    gets +2/+4" — Spidery Grasp) or a delayed trigger's watched object; a
    ``TriggeringSource`` through :func:`_event_object`."""
    if target is MADE_TOKEN:
        return "yours"
    tag = tag_of(target)
    if tag == "SelfRef":
        # An enters-with replacement's ``SelfRef`` is the entering object: "each
        # other creature you control enters with an additional +1/+1 counter"
        # (Metallic Mimic) — phase's ``ChangeZone`` event over a filter. Any other
        # replacement's is the card (Ravenous Slime's "if a creature an opponent
        # controls would die, … put … counters on ~", a ``Moved`` event).
        watched = getattr(unit.node, "valid_card", None)
        if (
            unit.origin == "replacement"
            and getattr(unit.node, "event", None) == "ChangeZone"
            and tag_of(watched) in OBJECT_FILTER_TAGS
        ):
            return _filter_side(watched)
        return "self"
    if tag is None:
        # An untargeted activated pump acts on its source; an untargeted
        # placement names no object.
        return (
            "self"
            if unit.kind == "Activated" and tag_of(node) in ("Pump", "PumpAll")
            else "unknown"
        )
    if tag == "PostReplacementDamageTarget":
        # The creature a damage replacement watched be dealt damage ("If damage
        # would be dealt to another creature you control, prevent that damage.
        # Put a +1/+1 counter on that creature" — Vigor; "equipped creature" —
        # Panther Habit).
        watched = getattr(unit.node, "valid_card", None)
        if unit.origin != "replacement" or watched is None:
            return "unknown"
        if tag_of(watched) == "AttachedTo" or names_attached_object(watched):
            return "yours"
        return object_recipient(unit, watched)
    if tag == "TriggeringSource":
        named = _anaphora(unit).named.get(id(node))
        if named is not None:
            return object_recipient(unit, named)
        return _event_object(unit, node)
    if tag == "CostPaidObject" and beholds(unit):
        # The beheld object (CR 701.4a): a card in your hand or a permanent you
        # control.
        return "yours"
    if tag == "LastCreated":
        # The token the chain just made ("Put X +1/+1 counters on it").
        return "yours"
    if tag == "EventTarget":
        # What a becomes-target trigger watched become the target (Daru
        # Spiritualist's "Cleric creature you control … it gets +0/+2").
        if unit.origin != "trigger":
            return "unknown"
        watched = getattr(unit.node, "valid_card", None)
        return "unknown" if watched is None else object_recipient(unit, watched)
    if tag == "TrackedSet":
        group = _anaphora(unit).tracked.get(id(node))
        return "unknown" if group is None else object_recipient(unit, group)
    if tag in ("ParentTarget", "ParentTargetSlot"):
        found = _anaphora(unit)
        threaded = found.threaded.get(id(node))
        if threaded is None:
            threaded = found.named.get(id(node))
        if threaded is not None:
            return object_recipient(unit, threaded)
        trig = found.delayed.get(id(node))
        if trig is not None and _mode(trig):
            watched = getattr(trig, "valid_card", None)
            return _filter_side(watched) if watched is not None else "unknown"
        # "For each creature you control with …, put … counters on that
        # creature" (Sovereign Okinec Ahau): the repeated object, the count's.
        repeat = getattr(_find_owner_wrapper(unit.node, node), "repeat_for", None)
        counted = getattr(getattr(repeat, "qty", None), "filter", None)
        if tag_of(counted) in OBJECT_FILTER_TAGS:
            return _filter_side(counted)
        # A trigger's "it" with no earlier object is the trigger's own object
        # ("Whenever a creature you control becomes blocked, it gets +1/+1" —
        # Somberwald Alpha), as ``TriggeringSource`` is.
        return _event_object(unit, node) if unit.origin == "trigger" else "unknown"
    if tag in OBJECT_FILTER_TAGS:
        return _filter_side(target)
    if tag == "Any":
        # Any object, of either side's (an uncontrolled filter's reach).
        return "yours"
    return "unknown"


def boost_recipient(unit: AbilityUnit, c: ConceptNode) -> BoostRecipient:
    """Who a ``pump``, ``place_counter`` or counter move of ``unit`` lands on
    (:func:`object_recipient` of its target). A perpetual pump of the card an
    earlier effect returned to the battlefield is the card itself (Vladimir and
    Godfrey); an anaphoric ``SelfRef`` the overlay corrections marked as an
    earlier clause's object is not (:func:`reads.targets_the_card`)."""
    if c.returned_self:
        return "self"
    if tag_of(c.node) == "AddPendingETBCounters":
        # "When you next cast a creature spell this turn, that creature enters
        # with two additional +1/+1 counters" (Yuna, Grand Summoner): another
        # creature of yours, never the source.
        return "yours"
    target = getattr(c.node, "target", None)
    if tag_of(target) == "SelfRef" and not targets_the_card(c):
        # The overlay corrections' anaphoric "it": an earlier clause's object,
        # of either side ("If target creature has toughness 5 or greater, it
        # gets +4/-4" — Blood Lust).
        return "yours"
    return object_recipient(unit, target, c.node)


def generic_effect_boosts(
    unit: AbilityUnit,
) -> Iterator[tuple[BoostRecipient, object, object]]:
    """Each timed P/T raise a ``GenericEffect`` of ``unit`` confers ("target
    creature gets +2/+2 and gains indestructible until end of turn" —
    Aethershield Artificer; "~ gets +1/+0 for each …"), as ``(recipient,
    GenericEffect, static)``: a static on ``SelfRef`` is the card, one on
    ``ParentTarget`` the effect's own target (or, with none, what the "it" names:
    :func:`object_recipient`), a filter its side."""
    for node in iter_typed_nodes(unit.node):
        if tag_of(node) != "GenericEffect":
            continue
        for st in _listed(node, "static_abilities"):
            if max(pt_mod_signs(st)) <= 0:
                continue
            affected = getattr(st, "affected", None)
            tag = tag_of(affected)
            if tag == "ParentTarget":
                target = getattr(node, "target", None)
                if target is None or tag_of(target) == "ParentTarget":
                    # The effect's "it" — the static's own thread.
                    yield object_recipient(unit, affected, st), node, st
                else:
                    yield object_recipient(unit, target, node), node, st
            else:
                yield object_recipient(unit, affected, st), node, st


def named_object(unit: AbilityUnit, node: object) -> object | None:
    """The object effect ``node`` of ``unit`` acts on: its own ``target``, or —
    for an "it" (``ParentTarget``) — the filter the chain's target thread or the
    last object an earlier effect named gives it, a delayed trigger's included
    ("Destroy that creature at the beginning of the next end step" — Blood
    Frenzy). ``None`` where the structure names none."""
    target = getattr(node, "target", None)
    if tag_of(target) not in ("ParentTarget", "ParentTargetSlot"):
        return target
    found = _anaphora(unit)
    return found.threaded.get(id(node)) or found.named.get(id(node))


def chosen_target(
    unit: AbilityUnit, node: object, target: object, owner: object = None
) -> object | None:
    """The one creature filter an effect ``node`` of ``unit`` targets with
    ``target`` (its own, or what its "it" names through the chain's thread), or
    ``None`` when it targets nothing: a group or the card, the object an Aura or
    Equipment is attached to (CR 115.10a: affected is not targeted), a choice
    made on resolution ("each player may put two +1/+1 counters on a creature
    they control" — Agitator Ant; phase's ``target_choice_timing:
    Resolution``), or an opponent's creature only. ``owner`` is the effect
    whose wrapper says when it chooses, when ``node`` is a static inside it."""
    found = _anaphora(unit)
    if tag_of(target) in ("ParentTarget", "ParentTargetSlot"):
        # A delayed trigger's "it" is no target of the ability that made it
        # (Valiant Farewell's boon).
        if id(node) in found.delayed:
            return None
        target = found.threaded.get(id(node))
    if tag_of(target) not in OBJECT_FILTER_TAGS or names_attached_object(target):
        return None
    # A card in a graveyard, a hand or a library is no creature to boost ("Return
    # target creature card from your graveyard … put two +1/+1 counters on it" —
    # Defy Death: the returned card, not a targeted creature).
    if set(filter_inzone_zones(target)) - {"Battlefield"}:
        return None
    if _filter_side(target) != "yours":
        return None
    if effect_chosen_on_resolution(unit.node, owner if owner is not None else node):
        return None
    return target


def counter_raises(kind: str) -> bool:
    """Whether a counter kind raises power or toughness (CR 122.1a: a +X/+Y
    counter adds X and Y): ``P1P1``, ``P1P0``, ``P0P1``; a -1/-1 counter
    doesn't, nor does any other counter (a stun, charge or experience counter)."""
    m = _PT_COUNTER_RX.match(kind.upper())
    if m is None:
        return False
    return (m.group(1) == "P" and int(m.group(2)) > 0) or (
        m.group(3) == "P" and int(m.group(4)) > 0
    )


def raises_with_counters(c: ConceptNode) -> bool:
    """A typed ``place_counter`` effect of a raising kind (:func:`counter_raises`)."""
    return c.concept == "place_counter" and counter_raises(counter_kind(c.node))


#: Where a counter that feeds a static sits: on the card itself (Rose Tyler's
#: "+1/+1 for each time counter on it", Beastmaster Ascension's "seven or more
#: quest counters on it"), or on any permanent of yours ("+1/+1 for each quest
#: counter among permanents you control" — Moira Brown's Book).
CounterSite = Literal["self", "yours"]
#: A counter of any kind (Gavel of the Righteous's "for each counter on this
#: Equipment").
ANY_COUNTER = "*"


def _counted_kind(node: object) -> str:
    """The counter kind a count or a ``HasCounters`` condition reads: a
    ``counter_type`` field, an ``OfType`` filter's ``data``, else any kind."""
    for field in ("counter_type", "data"):
        kind = getattr(node, field, None)
        if isinstance(kind, str):
            return kind.lower()
    return ANY_COUNTER


def _fed_counters(sdef: object) -> Iterator[tuple[str, CounterSite]]:
    """The counters a P/T-raising static counts or is conditioned on."""
    if max(pt_mod_signs(sdef)) <= 0:
        return
    for mod in _listed(sdef, "modifications"):
        for node in iter_typed_nodes(mod):
            tag = tag_of(node)
            if tag == "CountersOn" and tag_of(getattr(node, "scope", None)) == "Source":
                yield _counted_kind(node), "self"
            elif (
                tag == "CountersOnObjects"
                and controller_reach(filter_controller(getattr(node, "filter", None)))
                == "yours"
            ):
                yield _counted_kind(node), "yours"
    cond = getattr(sdef, "condition", None)
    if tag_of(cond) == "HasCounters":
        yield _counted_kind(getattr(cond, "counters", None)), "self"


def counter_fed_statics(tree: ConceptTree) -> frozenset[tuple[str, CounterSite]]:
    """``(counter kind, site)`` for every counter a static of the card (or of a
    token it makes) turns into power or toughness: its quantity counts that kind
    (``CountersOn`` the source, ``CountersOnObjects`` among your permanents) or
    its condition needs it (``HasCounters``), and its modification raises P/T
    (:func:`reads.pt_mod_signs`; CR 613.4c). Gavel of the Righteous's "Equipped
    creature gets +1/+1 for each counter on this Equipment" feeds on any counter
    on itself; its four-counter double strike adds no power and is not one. A
    base-P/T setting (CR 613.4b — Sephiroth, Fallen Hero's 7/5) is not a raise."""

    def read(tree: ConceptTree) -> frozenset[tuple[str, CounterSite]]:
        found: set[tuple[str, CounterSite]] = set()
        for unit in tree.units:
            defs = list(iter_static_defs(unit.node))
            for node in iter_typed_nodes(unit.node):
                if tag_of(node) in _MADE_PERMANENT_TAGS:
                    defs.extend(_listed(node, "static_abilities"))
            for sdef in defs:
                found.update(_fed_counters(sdef))
        return frozenset(found)

    return memo_on(tree, "_xw_counter_fed_statics", read)


def feeds_own_static(unit: AbilityUnit, tree: ConceptTree, c: ConceptNode) -> bool:
    """Whether counter placement ``c`` of ``unit`` grows a creature through a
    static of the same card (:func:`counter_fed_statics`): a counter of the
    kind the static counts, put on the card itself (Rose Tyler's time counters,
    Beastmaster Ascension's quest counters) or, for a static that counts among
    your permanents, on a permanent of yours (Moira Brown's quest counter). Dan's
    ruling, 2026-11-25: a combat trigger that places such a counter is a combat
    boost."""
    if c.concept != "place_counter":
        return False
    fed = counter_fed_statics(tree)
    if not fed:
        return False
    kind = counter_kind(c.node).lower()
    recipient = object_recipient(unit, getattr(c.node, "target", None), c.node)
    for fed_kind, site in fed:
        if fed_kind not in (kind, ANY_COUNTER):
            continue
        if recipient == "self" or (site == "yours" and recipient == "yours"):
            return True
    return False


def boost_delivery(
    unit: AbilityUnit, tree: ConceptTree, node: object = None
) -> BoostDelivery:
    """How effect ``node`` of ``unit`` reaches the creature it boosts: as a
    spell when it is in the spell ability of an instant or sorcery (CR 115.1a —
    the spell is targeted), else as an activated or triggered ability (CR
    115.1c, 115.1d): a cycling trigger on an instant is the ability's target, not
    the spell's (CR 115.1a's example), and so is a delayed triggered ability a
    spell creates (CR 603.7: "When you next cast a spell this turn, put X +1/+1
    counters on up to one target creature" — Ride the Avalanche)."""
    if (
        unit.origin == "ability"
        and unit.kind == "Spell"
        and {"Instant", "Sorcery"} & set(tree.card_types)
        and id(node) not in _anaphora(unit).delayed
    ):
        return "spell"
    return "ability"


def keyword_grant_deliveries(tree: ConceptTree) -> frozenset[BoostDelivery]:
    """How the card's keyword grants to a chosen creature of yours reach it
    (:func:`boost_delivery` over ``reads.unit_keyword_grants``, the walk the
    ``keyword_grant_target`` lane reads): ``"spell"`` for Gods Willing's "Target
    creature you control gains protection", ``"ability"`` for a creature's
    activated grant or Dirge of Dread's cycling trigger (CR 115.1a's example: a
    cycling trigger's target is the ability's, not the spell's)."""

    def read(tree: ConceptTree) -> frozenset[BoostDelivery]:
        return frozenset(
            boost_delivery(unit, tree)
            for unit in tree.units
            if any(
                filter_names_creatures(target)
                and filter_controller(target) != "Opponent"
                for target, _mod in unit_keyword_grants(unit)
            )
        )

    return memo_on(tree, "_xw_keyword_grant_deliveries", read)


def raises_pt(c: ConceptNode) -> bool:
    """A ``pump`` concept that raises power or toughness (:func:`reads.pump_raises`):
    "+2/-2" raises one and is a pump as well as a shrink (Lash of Malice)."""
    return c.concept == "pump" and pump_raises(c.node)
