"""Shapes phase renamed, written back on the raw face records before strict load.

Unlike the misread corrections beside it (``branches``, ``dropped_keywords``), a row
here is no misparse: phase's new shape is right, and only expresses the same fact
in a form the reads don't key. Where one rename reaches more reads than a shared
walk can cover, the record also carries the old form every read already knows.

* **The owner of a card put into a graveyard.** A card put into a graveyard goes
  to its owner's (CR 400.3), so phase types a trigger's "put into your graveyard"
  ("Whenever a nontoken creature is put into your graveyard from the battlefield"
  — Bridge from Below; "Whenever one or more land cards are put into your
  graveyard from anywhere" — Titania, Voice of Gaea) as an ``Owned{controller}``
  property on a watched-card filter with no controller. The death, land-to-
  graveyard and type payoffs read the watched card's side off its
  ``controller`` (about 140 reads), so the owner is copied there, beside the
  ``Owned`` property it keeps; the same for "Whenever a permanent is returned
  to your hand" (Azorius Aethermage, phase v0.131.0). Only for a zone change
  into a graveyard or a hand: "a spell you don't own" (Don Andres, the
  Renegade) and a replacement's "a card an opponent owns" (Leyline of the Void)
  are read by their owner.
  ``test_graveyard_owner_controller_canary`` fails once phase writes the
  controller itself again.
* **A targeted object and what is attached to it.** "Destroy target creature
  with flying and all Equipment attached to that creature" (Eaten by Spiders),
  "Exile target attacking creature and all Equipment attached to it" (Soul
  Nova), "Return target creature … and each Aura attached to it to their owners'
  hands" (Portal of Sanctuary, Word of Undoing): phase v0.118.0 writes a
  ``TargetOnly`` of the object, then ONE mass verb (``DestroyAll`` /
  ``ChangeZoneAll`` / ``BounceAll``) over ``Or[ParentTarget, <the Equipment or
  Aura attached to it>]``. The removal, exile, bounce and enters reads key the
  targeted verb, so the object's arm is written back as that verb on the
  ``TargetOnly`` (``Destroy`` / ``ChangeZone`` / ``Bounce`` of the target), and
  the mass verb keeps the attached arm. ``test_targeted_and_attached_canary``
  fails once phase writes the targeted verb itself again.
* **A counted amount floored at zero.** "+X/+X, where X is the number of
  creatures you control" (Craterhoof Behemoth), "+1/+1 for each card in your
  graveyard" (Bonehoard): phase v0.131.0 wraps the counted quantity in
  ``ClampMin{minimum: 0, inner}`` (a count is never negative, so the floor
  changes no read). The pump, anthem, damage and draw reads take the count off
  the amount itself (about 530 sites in the corpus), so the wrapper is removed.
  A floor over an expression (an ``Offset``'s "X minus 2", a ``Difference``)
  stays: phase wrote the ``Offset`` one before, and the slot takes no bare
  expression. ``test_zero_floor_canary`` fails once phase stops wrapping the count.
* **Hexproof spelled out.** "Enchanted creature can't be the target of spells
  or abilities your opponents control" (Canopy Cover, Shielding Plax) and the
  same words granted for a turn (Vines of Vastwood, Veilstone Amulet) are what
  hexproof means (CR 702.11b). Phase v0.131.0 types them as a
  ``CantBeTargeted{who: Opponents}`` static mode, alone or under an
  ``AddStaticMode`` modification, where it wrote ``AddKeyword{Hexproof}``. The
  protection, keyword-grant and team-buff reads key the keyword, so it is
  written back. ``who: AllPlayers`` (Ground Seal's graveyard cards) is no
  hexproof and stays. ``test_spelled_out_hexproof_canary`` fails once phase
  writes the keyword again.
* **A target its owner shuffles into their library.** "The owner of target
  permanent shuffles it into their library, then …" (Chaos Warp, Oblation,
  Audacious Swap), "shuffle target card from a graveyard into its owner's
  library" (Turn the Earth): phase v0.131.0 writes a ``TargetOnly`` of the
  object, a ``ChangeZoneAll`` of ``ParentTarget`` into the library, then the
  shuffle and what follows on ``ScopedPlayer`` under an owner
  ``TrackedSetPossessor`` scope. The removal, draw, reveal and cheat reads key
  the targeted ``ChangeZone`` (``owner_library``) and a ``ParentTargetOwner``
  player, so both are written back. ``test_owner_shuffles_target_canary``
  fails once phase writes the targeted move itself again.
* **A graveyard arrival "from anywhere other than the battlefield".** "Whenever
  a Lhurgoyf permanent card is put into your graveyard from anywhere other than
  the battlefield" (Disa the Restless): phase v0.131.0 types the trigger as a
  ``ChangesZone`` into the graveyard whose one ``zone_change_clauses`` entry
  holds the watched card and the ``NotEquals`` origin, with no ``valid_card`` of
  its own. Every graveyard-arrival read takes the watched card off the trigger,
  so the clause's is copied there (its origin stays unset, the form of "from
  anywhere": the card has an owner and no controller, CR 108.4, and "dies" is
  from the battlefield alone, CR 700.4).
  ``test_single_clause_arrival_canary`` fails once phase writes the watched
  card on the trigger.
* **The card itself, owned by you.** "When this creature is put into your
  graveyard from the battlefield" (Zodiac Dragon, Brood of Cockroaches,
  Enigma Sphinx): phase v0.131.0 types the watched card as ``And[SelfRef, a
  card you own]`` — the owner of "your graveyard" (CR 400.3) — where it wrote
  ``SelfRef``. The self-trigger reads (a card's own death, its own return) key
  the bare ``SelfRef``, which is written back.
  ``test_self_owned_by_you_canary`` fails once phase writes it again.

Pure functions over plain dicts; nothing here reads the mirror or a tree.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator

_TRIGGER_KEYS = ("triggers", "trigger")


def _owner_only_arms(filt: object) -> Iterator[tuple[dict, str]]:
    """Each ``Typed`` arm of a watched-card filter (``Or`` / ``And`` arms too) that
    names its card's owner and no controller, with that owner."""
    if not isinstance(filt, dict):
        return
    if filt.get("type") in ("Or", "And"):
        for sub in filt.get("filters") or ():
            yield from _owner_only_arms(sub)
        return
    if filt.get("type") != "Typed" or filt.get("controller") is not None:
        return
    for prop in filt.get("properties") or ():
        if isinstance(prop, dict) and prop.get("type") == "Owned":
            owner = prop.get("controller")
            if isinstance(owner, str):
                yield filt, owner
            return


#: The zones a card goes to its owner's (CR 400.3) that a trigger watches by
#: "your": "put into your graveyard", "returned to your hand".
_OWNERS_ZONES = frozenset({"Graveyard", "Hand"})


def _graveyard_watched(trig: dict) -> Iterator[object]:
    """The watched-card filters of a trigger on a card put into a graveyard or a
    hand: the trigger's own ``valid_card`` for its own destination, and each
    folded zone change's into a graveyard (``zone_change_clauses``, the
    per-clause destination ``reads.trigger_zone_changes`` reads — Dreadhound)."""
    if trig.get("destination") in _OWNERS_ZONES:
        yield trig.get("valid_card")
    for clause in trig.get("zone_change_clauses") or ():
        if isinstance(clause, dict) and clause.get("destination") == "Graveyard":
            yield clause.get("valid_card")


def _single_clause_arrival(trig: dict) -> dict | None:
    """The watched card of a graveyard-arrival trigger that names it only on its
    one zone-change clause, a clause "from anywhere other than" a zone; else
    ``None``."""
    clauses = trig.get("zone_change_clauses") or ()
    if trig.get("valid_card") is not None or len(clauses) != 1:
        return None
    (clause,) = clauses
    if not isinstance(clause, dict):
        return None
    origin = clause.get("origin")
    watched = clause.get("valid_card")
    if (
        trig.get("destination") == "Graveyard"
        and clause.get("destination") == "Graveyard"
        and isinstance(origin, dict)
        and origin.get("type") == "NotEquals"
        and isinstance(watched, dict)
    ):
        return watched
    return None


def _triggers(rec: dict) -> Iterator[dict]:
    """Every trigger in ``rec``: a ``triggers`` entry, a ``trigger`` a static grants
    or a condition watches."""
    from mtg_utils._card_ir.trees import _iter_raw_dicts

    for holder in _iter_raw_dicts(rec, lambda d: any(k in d for k in _TRIGGER_KEYS)):
        for key in _TRIGGER_KEYS:
            value = holder.get(key)
            for trig in value if isinstance(value, list) else (value,):
                if isinstance(trig, dict):
                    yield trig


def _targeted_form(mass: dict, target: object) -> dict:
    """The targeted verb a mass verb over a target and its attachments restores
    for the target: ``Destroy`` / ``ChangeZone`` / ``Bounce``, keeping the mass
    verb's own fields."""
    kind = mass.get("type")
    if kind == "DestroyAll":
        return {
            "type": "Destroy",
            "target": target,
            "cant_regenerate": mass.get("cant_regenerate", False),
        }
    if kind == "ChangeZoneAll":
        return {
            "type": "ChangeZone",
            "origin": mass.get("origin"),
            "destination": mass.get("destination"),
            "target": target,
            "owner_library": False,
            "enter_transformed": False,
            "enter_tapped": False,
            "enters_attacking": False,
        }
    return {"type": "Bounce", "target": target, "destination": None}


#: The mass verbs phase writes over a target and its attachments.
_TARGETED_AND_ATTACHED_VERBS = frozenset({"DestroyAll", "ChangeZoneAll", "BounceAll"})


def _attached_to_parent(arm: object) -> bool:
    """Whether a filter arm is "the [Equipment / Aura] attached to it": an
    ``AttachedTo`` property whose host is the ``ParentTarget``."""
    if not isinstance(arm, dict):
        return False
    for prop in arm.get("properties") or ():
        if isinstance(prop, dict) and prop.get("type") == "AttachedTo":
            host = prop.get("to")
            if isinstance(host, dict):
                filt = host.get("filter")
                if isinstance(filt, dict) and filt.get("type") == "ParentTarget":
                    return True
    return False


def _heads_with_target_only(d: dict) -> bool:
    effect = d.get("effect")
    return isinstance(effect, dict) and effect.get("type") == "TargetOnly"


def _targeted_and_attached(ability: dict) -> tuple[dict, list] | None:
    """``(mass effect, attached arms)`` when the ``TargetOnly`` heading
    ``ability`` is followed by a mass verb over ``Or[ParentTarget, the
    attachments of it]``."""
    sub = ability.get("sub_ability")
    mass = sub.get("effect") if isinstance(sub, dict) else None
    if not isinstance(mass, dict):
        return None
    if mass.get("type") not in _TARGETED_AND_ATTACHED_VERBS:
        return None
    target = mass.get("target")
    if not (isinstance(target, dict) and target.get("type") == "Or"):
        return None
    arms = target.get("filters") or []
    parents = [a for a in arms if a == {"type": "ParentTarget"}]
    rest = [a for a in arms if a != {"type": "ParentTarget"}]
    if len(parents) == 1 and rest and all(_attached_to_parent(a) for a in rest):
        return mass, rest
    return None


def _copied(memo: dict[int, object], node: dict) -> dict:
    """``node``'s copy in a ``copy.deepcopy`` memo."""
    new = memo[id(node)]
    assert isinstance(new, dict)
    return new


def _write_targeted_verb(
    memo: dict[int, object], ability: dict, mass: dict, rest: list
) -> None:
    """On the copy: the targeted verb on the ``TargetOnly``, the attached arms
    left on the mass verb."""
    new_ability = _copied(memo, ability)
    new_mass = _copied(memo, mass)
    target = new_ability["effect"]["target"]
    new_ability["effect"] = _targeted_form(new_mass, target)
    attached = [memo.get(id(a), a) for a in rest]
    if len(attached) == 1:
        new_mass["target"] = attached[0]
    else:
        new_mass["target"] = {"type": "Or", "filters": attached}


def _is_zero_floor(node: object) -> bool:
    """Whether ``node`` is a count floored at zero: ``ClampMin{minimum: 0}`` over
    a ``Ref``, the quantity phase wrote bare before v0.131.0. A floored
    expression (an ``Offset``'s "X minus 2", a ``Difference`` — Doran, Besieged
    by Time) keeps its floor: the slot takes no bare expression."""
    if not (isinstance(node, dict) and node.get("type") == "ClampMin"):
        return False
    inner = node.get("inner")
    return (
        node.get("minimum") == 0
        and isinstance(inner, dict)
        and inner.get("type") == "Ref"
    )


#: The static mode phase types "can't be the target of spells or abilities your
#: opponents control" as, and the modification it wrote before.
_OPPONENTS_CANT_TARGET = {"CantBeTargeted": {"who": "Opponents"}}
_ADD_HEXPROOF = {"type": "AddKeyword", "keyword": "Hexproof"}


#: "A card you own", with nothing else said of it.
_OWNED_BY_YOU = {
    "type": "Typed",
    "controller": None,
    "type_filters": [],
    "properties": [{"type": "Owned", "controller": "You"}],
}
_SELF = {"type": "SelfRef"}


def _is_self_owned_by_you(node: dict) -> bool:
    """Whether ``node`` is ``And[SelfRef, a card you own]``."""
    arms = node.get("filters")
    return (
        node.get("type") == "And"
        and isinstance(arms, list)
        and len(arms) == 2
        and _SELF in arms
        and _OWNED_BY_YOU in arms
    )


def _node_form(node: dict) -> dict | None:
    """The old form of one renamed node, or ``None`` when it is none of them: a
    zero floor's count, the card itself owned by you, a spelled-out hexproof's
    keyword (the modification, or the static whose own mode it is)."""
    if _is_zero_floor(node):
        return node["inner"]
    if _is_self_owned_by_you(node):
        return dict(_SELF)
    if node.get("mode") != _OPPONENTS_CANT_TARGET:
        return None
    if node.get("type") == "AddStaticMode":
        return dict(_ADD_HEXPROOF)
    mods = node.get("modifications")
    if isinstance(mods, list):
        return {
            **node,
            "mode": "Continuous",
            "modifications": [*mods, dict(_ADD_HEXPROOF)],
        }
    return None


def _with_node_forms(node: object) -> object:
    """``node`` with each renamed node (:func:`_node_form`) in its old form; the
    same object when it holds none."""
    if isinstance(node, dict):
        form = _node_form(node)
        if form is not None:
            return _with_node_forms(form)
        out = None
        for key, value in node.items():
            new = _with_node_forms(value)
            if new is not value:
                if out is None:
                    out = dict(node)
                out[key] = new
        return node if out is None else out
    if isinstance(node, list):
        items = None
        for i, value in enumerate(node):
            form = _with_node_forms(value)
            if form is not value:
                if items is None:
                    items = list(node)
                items[i] = form
        return node if items is None else items
    return node


def _owner_shuffle(ability: dict) -> tuple[dict, dict] | None:
    """``(the move's wrapper, the shuffle's wrapper)`` when the ``TargetOnly``
    heading ``ability`` is followed by a ``ChangeZoneAll`` of ``ParentTarget``
    into the library, then a step scoped to that card's owner."""
    move = ability.get("sub_ability")
    if not isinstance(move, dict):
        return None
    mass = move.get("effect")
    if not (
        isinstance(mass, dict)
        and mass.get("type") == "ChangeZoneAll"
        and mass.get("destination") == "Library"
        and mass.get("target") == {"type": "ParentTarget"}
    ):
        return None
    after = move.get("sub_ability")
    if not isinstance(after, dict):
        return None
    scope = after.get("player_scope")
    if (
        isinstance(scope, dict)
        and scope.get("type") == "TrackedSetPossessor"
        and scope.get("possession") == "Owner"
    ):
        return move, after
    return None


def _write_owner_shuffle(
    memo: dict[int, object], ability: dict, move: dict, after: dict
) -> None:
    """On the copy: the targeted move written back, its owner named
    ``ParentTargetOwner``."""
    from mtg_utils._card_ir.trees import _iter_raw_dicts

    new_ability = _copied(memo, ability)
    new_after = _copied(memo, after)
    mass = _copied(memo, move)["effect"]
    new_ability["effect"] = {
        **_targeted_form(mass, new_ability["effect"]["target"]),
        "owner_library": True,
    }
    new_ability.pop("declares_chosen_group", None)
    new_ability["sub_ability"] = new_after
    del new_after["player_scope"]
    for node in list(_iter_raw_dicts(new_after, lambda _d: True)):
        if node == {"type": "ScopedPlayer"}:
            node["type"] = "ParentTargetOwner"
        elif node.get("condition") == {"type": "HasObjectTarget"}:
            node["condition"] = None


def restore_renamed_shapes(rec: dict) -> dict:
    """``rec`` with each renamed shape written in its old form — in place of the
    new one, or beside it where the reads take both (the owner copied onto
    ``controller``); a copy when any, never the input."""
    from mtg_utils._card_ir.trees import _iter_raw_dicts

    forms = _with_node_forms(rec)
    assert isinstance(forms, dict)
    heads = list(_iter_raw_dicts(forms, _heads_with_target_only))
    attached = [(a, *found) for a in heads if (found := _targeted_and_attached(a))]
    shuffles = [(a, *found) for a in heads if (found := _owner_shuffle(a))]
    triggers = list(_triggers(forms))
    arrivals = [
        (trig, watched)
        for trig in triggers
        if (watched := _single_clause_arrival(trig)) is not None
    ]
    owned = [
        (arm, owner)
        for trig in triggers
        for filt in _graveyard_watched(trig)
        for arm, owner in _owner_only_arms(filt)
    ]
    if not (attached or shuffles or arrivals or owned):
        return forms
    memo: dict[int, object] = {}
    out = copy.deepcopy(forms, memo)
    for ability, mass, rest in attached:
        _write_targeted_verb(memo, ability, mass, rest)
    for ability, move, after in shuffles:
        _write_owner_shuffle(memo, ability, move, after)
    for arm, owner in owned:
        _copied(memo, arm)["controller"] = owner
    # After the owner is copied: the trigger's watched card is the clause's.
    for trig, watched in arrivals:
        _copied(memo, trig)["valid_card"] = copy.deepcopy(_copied(memo, watched))
    return out
