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
  ``Owned`` property it keeps. Only for a zone change into a graveyard: "a spell
  you don't own" (Don Andres, the Renegade) and a replacement's "a card an
  opponent owns" (Leyline of the Void) are read by their owner.
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


def _graveyard_watched(trig: dict) -> Iterator[object]:
    """The watched-card filters of a trigger on a card put into a graveyard: the
    trigger's own ``valid_card`` for its own destination, and each folded zone
    change's (``zone_change_clauses``, the per-clause destination
    ``reads.trigger_zone_changes`` reads — Dreadhound)."""
    if trig.get("destination") == "Graveyard":
        yield trig.get("valid_card")
    for clause in trig.get("zone_change_clauses") or ():
        if isinstance(clause, dict) and clause.get("destination") == "Graveyard":
            yield clause.get("valid_card")


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


def _targeted_and_attached(rec: dict) -> Iterator[tuple[dict, dict, list]]:
    """``(ability, mass effect, attached arms)`` for each ability whose
    ``TargetOnly`` is followed by a mass verb over ``Or[ParentTarget, the
    attachments of it]``."""
    from mtg_utils._card_ir.trees import _iter_raw_dicts

    def heads(d: dict) -> bool:
        effect = d.get("effect")
        return isinstance(effect, dict) and effect.get("type") == "TargetOnly"

    for ability in _iter_raw_dicts(rec, heads):
        sub = ability.get("sub_ability")
        mass = sub.get("effect") if isinstance(sub, dict) else None
        if not isinstance(mass, dict):
            continue
        if mass.get("type") not in _TARGETED_AND_ATTACHED_VERBS:
            continue
        target = mass.get("target")
        if not (isinstance(target, dict) and target.get("type") == "Or"):
            continue
        arms = target.get("filters") or []
        parents = [a for a in arms if a == {"type": "ParentTarget"}]
        rest = [a for a in arms if a != {"type": "ParentTarget"}]
        if len(parents) == 1 and rest and all(_attached_to_parent(a) for a in rest):
            yield ability, mass, rest


def _restore_targeted_and_attached(rec: dict) -> dict:
    """``rec`` with each targeted-and-attached ability's targeted verb written
    back (a copy when any)."""
    found = list(_targeted_and_attached(rec))
    if not found:
        return rec
    memo: dict[int, object] = {}
    out = copy.deepcopy(rec, memo)
    for ability, mass, rest in found:
        new_ability = memo[id(ability)]
        new_mass = memo[id(mass)]
        assert isinstance(new_ability, dict)
        assert isinstance(new_mass, dict)
        target = new_ability["effect"]["target"]
        new_ability["effect"] = _targeted_form(new_mass, target)
        attached = [memo.get(id(a), a) for a in rest]
        if len(attached) == 1:
            new_mass["target"] = attached[0]
        else:
            new_mass["target"] = {"type": "Or", "filters": attached}
    return out


def restore_renamed_shapes(rec: dict) -> dict:
    """``rec`` with each renamed shape's old form beside it (a copy when any)."""
    rec = _restore_targeted_and_attached(rec)
    found = [
        (arm, owner)
        for trig in _triggers(rec)
        for filt in _graveyard_watched(trig)
        for arm, owner in _owner_only_arms(filt)
    ]
    if not found:
        return rec
    memo: dict[int, object] = {}
    out = copy.deepcopy(rec, memo)
    for arm, owner in found:
        target = memo[id(arm)]
        assert isinstance(target, dict)
        target["controller"] = owner
    return out
