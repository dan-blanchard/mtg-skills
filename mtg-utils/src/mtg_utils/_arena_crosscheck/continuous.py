"""What a resolution's continuous effect did, against Arena's logged objects (ADR-0064).

The strict checks score a continuous effect only as a kind and a pump's size.
This module checks what it did to the objects phase says it affects, where the
log shows both sides of the resolution (a resolution begins and completes in
one message; the reader keeps the objects as the message found them and as it
left them, ``Resolution.lki`` / ``permanents`` and ``after_lki`` / ``after``):

* **keyword grants** (layer 6, CR 613.1f): the abilities Arena lists on the
  object (``uniqueAbilities``, which Arena keeps current, a keyword granted
  again listed again) gained across the resolution against the keywords phase
  grants it (an ``AddKeyword`` in the effect's modifications, or the keyword a
  pump's own text grants that phase reads beside it,
  ``ConceptNode.body_keywords``). A keyword phase grants that Arena didn't add,
  or an evergreen keyword Arena added that phase doesn't grant, fails;
* **base power and toughness** (layer 7b, CR 613.4b, then 7c's
  modifications, 613.4c): the object's logged power and toughness after the
  resolution against the base phase sets plus the fixed changes beside it,
  where nothing modified it before (its logged values were its card's
  printed ones);
* **types, subtypes and colors** (layers 4 and 5, CR 613.1d-e): the added card
  types and subtypes among the object's logged ones after, its colors after
  equal to those phase sets.

The objects are the ability's own permanent (``SelfRef``), its targets
(``ParentTarget``) and a group a filter matches on the board (``Typed``, read
strictly: ``amounts``). Not checked, by reason on the row
(``continuous_unchecked``): a message that changed the board before or after
the resolution, another source's effect inside it, an object that left, a
filter or an object this read can't place, a dynamic amount, a switch of power
and toughness, an ability removed or a quoted ability granted, a base set on
an object that was already modified or isn't a creature. When the effect ends
("until end of turn") is not checked. Static abilities of permanents (an
anthem, which applies with no resolution) are out of scope.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, cast

from mtg_utils._arena_crosscheck.amounts import CountBoard, _matching
from mtg_utils._arena_crosscheck.effects import Check
from mtg_utils._arena_crosscheck.log import (
    BOARD_ANNOTATIONS,
    Effect,
    Permanent,
    Resolution,
    num,
    word,
)
from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    effect_filter,
    effect_targets,
    iter_mod_sites,
    mod_keyword_name,
    normalised_keyword_name,
    tag_of,
)

if TYPE_CHECKING:
    from mtg_utils._card_ir.mirror import TypedMirrorNode
    from mtg_utils.arena_card_db import ArenaAbility

__all__ = ["continuous_checks"]

#: The evergreen keywords an added Arena ability is read as (CR 702), folded as
#: ``crosswalk.normalised_keyword_name`` folds phase's: a gained one phase
#: doesn't grant is a finding. Any other gained ability (a quoted one) is not
#: read.
EVERGREEN = frozenset(
    {
        "deathtouch",
        "defender",
        "doublestrike",
        "firststrike",
        "flash",
        "flying",
        "haste",
        "hexproof",
        "indestructible",
        "lifelink",
        "menace",
        "reach",
        "shroud",
        "trample",
        "vigilance",
        "protection",
        "ward",
        "intimidate",
        "fear",
        "prowess",
    }
)
_COLOR_LETTERS = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}
#: Modifications this read checks; any other in a checked effect makes it
#: unchecked by its name.
_KEYWORD, _SET, _ADD = (
    "AddKeyword",
    ("SetPower", "SetToughness"),
    (
        "AddPower",
        "AddToughness",
    ),
)
_TYPES = ("AddType", "AddSubtype", "SetColor")
_UNREAD = {
    "SwitchPowerToughness": "switch",
    "RemoveKeyword": "removes abilities",
    "RemoveAllAbilities": "removes abilities",
    "GrantAbility": "quoted ability",
    "GrantTrigger": "quoted ability",
    "GrantStaticAbility": "quoted ability",
    "AddDynamicPower": "dynamic",
    "AddDynamicToughness": "dynamic",
}


def keyword_of(text: str | None, keyword: str | None = None) -> str | None:
    """The keyword an Arena ability is, folded: its ``BaseId`` keyword or its
    text, read as an evergreen keyword ("First strike", "Protection from red",
    "Ward {o2}", a ``BaseId`` of "Protection From" read as their keyword); a
    ``BaseId`` keyword of another kind as itself; ``None`` for any other
    ability."""
    for name in (keyword, re.sub(r"\s*\(.*\)$", "", text or "")):
        folded = normalised_keyword_name(name or "")
        for kw in EVERGREEN:
            if folded == kw or (kw in _PARAMETERIZED and folded.startswith(kw)):
                return kw
    return normalised_keyword_name(keyword) if keyword else None


#: Keywords Arena writes with what they apply to ("Protection from red",
#: "Ward {o2}", "Hexproof from black").
_PARAMETERIZED = frozenset({"protection", "ward", "hexproof"})


#: Phase's keyword names (folded) that Arena lists as another keyword's ability:
#: "hexproof from black" is a hexproof ability (CR 702.11d).
_AS_ARENA = {"hexprooffrom": "hexproof"}


def phase_keyword(name: str) -> str:
    """A keyword phase grants, folded as :func:`keyword_of` reads Arena's."""
    folded = normalised_keyword_name(name)
    return _AS_ARENA.get(folded, folded)


def _gained(
    before: Permanent, after: Permanent, ability: Callable[[int], ArenaAbility]
) -> list[str]:
    """The keywords ``after`` lists beyond ``before`` (a multiset: a keyword
    granted again is listed again)."""
    added = collections.Counter(after.abilities) - collections.Counter(before.abilities)
    out = []
    for grp in added.elements():
        a = ability(grp)
        if (kw := keyword_of(a.text, a.keyword)) is not None:
            out.append(kw)
    return out


#: A pump's chosen target, as a static's ``ParentTarget`` names it.
_TARGETED = "ParentTarget"


def _grants(a: object, c: ConceptNode) -> list[tuple[object, object]]:
    """``(affected filter, modification)`` for each modification the effect
    makes, and a pump's own keywords (``ConceptNode.body_keywords``) as
    strings, on its target when it targets (:data:`_TARGETED`) or else the
    group its filter names."""
    out: list[tuple[object, object]] = [
        (getattr(sdef, "affected", None), mod)
        for sdef, mod in iter_mod_sites(c.node, deep=True)
    ]
    if tag_of(c.node) in ("Pump", "PumpAll") and c.body_keywords:
        unit = getattr(a, "unit", None)
        targeted = effect_targets(getattr(a, "root", None), c.node, unit)
        affected = _TARGETED if targeted else effect_filter(c.node)
        out += [(affected, kw) for kw in c.body_keywords]
    return out


class _Board:
    """The objects before and after, and the group read."""

    def __init__(self, res: Resolution) -> None:
        self.res = res
        self.before = {p.id: p for p in (*res.permanents, *res.lki)}
        self.after = {p.id: p for p in (*res.after, *res.after_lki)}
        self.board_before = {p.id for p in res.permanents}
        self.board_after = {p.id for p in res.after}
        self.count = CountBoard(
            res.permanents, res.lki, res.controller, res.seats, res.parent, res.targets
        )

    def objects(self, affected: object) -> list[int] | str:
        tag = _TARGETED if affected == _TARGETED else tag_of(affected)
        if tag == "SelfRef":
            ids = [self.res.parent] if self.res.parent is not None else []
        elif tag == "ParentTarget":
            ids = sorted(set(self.res.targets) - {self.res.parent})
        elif tag in ("Typed", "Or", "And"):
            found = _matching(affected, self.count)
            if isinstance(found, str):
                return "filter"
            ids = [p.id for p in found]
        else:
            return f"object:{tag}"
        if not ids:
            return "no object"
        # on the battlefield before and after (a card in a graveyard that
        # gains flashback is no permanent Arena lists abilities of)
        if any(i not in self.board_before or i not in self.board_after for i in ids):
            return "object not on the battlefield"
        return ids


def _other_effect(res: Resolution) -> bool:
    """Whether another source's effect changed the board inside the
    resolution (an anthem's layered effect for a token it made, a
    replacement)."""
    own = {res.instance, res.parent, None, *res.seats}
    return any(
        e.affector not in own and (BOARD_ANNOTATIONS & set(e.types) or _moves(e))
        for e in res.effects
    )


def _moves(e: Effect) -> bool:
    return "ZoneTransfer" in e.types and "Battlefield" in (
        word(e.details, "zone_src"),
        word(e.details, "zone_dest"),
    )


def _printed(record: dict | None) -> tuple[int, int] | None:
    if not record or record.get("card_faces"):
        return None
    p, t = record.get("power"), record.get("toughness")
    if isinstance(p, str) and isinstance(t, str) and p.isdigit() and t.isdigit():
        return int(p), int(t)
    return None


def continuous_checks(
    effects: Iterable[tuple[object, ConceptNode, bool]],
    res: Resolution,
    ability: Callable[[int], ArenaAbility],
    record_of: Callable[[int | None], dict | None],
    counter_name: Callable[[int | None], str | None] = lambda _: None,
) -> tuple[list[Check], list[str]]:
    """The checks of what the resolution's continuous effects did (module
    docstring), and the reasons any went unchecked. ``effects`` are the
    chosen abilities' ``(ability, concept, may not happen)``; ``ability``
    reads an Arena ability id, ``record_of`` a card's record by ``grpId``.

    Several chosen abilities are alternatives (a modal spell's modes, phase's
    one ability per mode: Secret Identity's Conceal and Reveal): each is
    checked alone, and the resolution is the one whose checks all pass. Arena
    logs no mode choice (no annotation names the mode of a modal spell), so
    when none passes, when several do, or when the one that passes asks for no
    more than one that fails (a mode that grants flying beside one that grants
    flying and trample: the second could have been chosen and gone wrong),
    which mode Arena chose the log can't say (``modes``)."""
    groups: dict[int, list] = {}
    for e in effects:
        groups.setdefault(id(e[0]), []).append(e)
    results = [
        _checks(g, res, ability, record_of, counter_name) for g in groups.values()
    ]
    results = [r for r in results if r[0] or r[1]]
    if len(results) <= 1:
        return (results[0][0], results[0][1]) if results else ([], [])
    passing = [r for r in results if r[0] and all(c.ok for c in r[0])]
    if len(passing) == 1:
        sig = _wants(passing[0][0])
        if not any(r is not passing[0] and sig <= _wants(r[0]) for r in results):
            return passing[0][0], passing[0][1]
    return [], sorted({"modes", *(u for r in results for u in r[1])})


def _wants(checks: Sequence[Check]) -> frozenset[tuple[str, str]]:
    """What a mode's checks ask for, comparable across modes: each keyword,
    type or color by itself, a base power and toughness whole."""
    out: set[tuple[str, str]] = set()
    for c in checks:
        if c.check == "base P/T" or not isinstance(c.expected, list):
            out.add((c.check, repr(c.expected)))
        else:
            out.update((c.check, str(x)) for x in c.expected)
    return frozenset(out)


def _checks(
    effects: Iterable[tuple[object, ConceptNode, bool]],
    res: Resolution,
    ability: Callable[[int], ArenaAbility],
    record_of: Callable[[int | None], dict | None],
    counter_name: Callable[[int | None], str | None],
) -> tuple[list[Check], list[str]]:
    """:func:`continuous_checks` for one ability's effects.

    An ability a keyword of which phase read off a pump's text
    (``body_keywords``: the recovery stage's partly-read grant) may hold a
    branch phase didn't type (Stolen Vitality's "If it's your turn, … gains
    trample. Otherwise, it gains first strike", both grants unconditional in
    phase's parse): its keywords are only allowed, never wanted, so they rule
    out an extra keyword but none is reported missing (``partly read`` when
    Arena added none of them). Another change of power and toughness in the
    ability beside a base set (a pump, a counter: layer 7c, CR 613.4c) leaves
    the base unchecked."""
    effects = list(effects)
    partly = any(
        c.body_keywords and tag_of(c.node) in ("Pump", "PumpAll") for _, c, _ in effects
    )
    other_pt = any(
        c.concept in _OTHER_PT and tag_of(c.node) != "GenericEffect"
        for _, c, _ in effects
    )
    wanted: dict[int, dict] = collections.defaultdict(
        lambda: {
            "kw": set(),
            "allowed": set(),
            "set": [None, None],
            "add": [0, 0],
            "types": set(),
            "subtypes": set(),
            "colors": None,
            "maybe": False,
        }
    )
    unchecked: list[str] = []
    board: _Board | None = None
    for a, c, maybe in effects:
        grants = _grants(a, c)
        if not grants:
            continue
        mods = [m for _, m in grants if not isinstance(m, str)]
        tags = {tag_of(m) for m in mods}
        checked = {_KEYWORD, *_SET, *_TYPES} | ({*_ADD} if tags & set(_SET) else set())
        if not (tags & checked or any(isinstance(m, str) for _, m in grants)):
            continue
        if reasons := sorted({_UNREAD[t] for t in tags if t in _UNREAD}):
            unchecked += reasons
            continue
        board = board or _Board(res)
        for affected, mod in grants:
            ids = board.objects(affected)
            if isinstance(ids, str):
                unchecked.append(ids)
                continue
            for i in ids:
                w = wanted[i]
                w["maybe"] = w["maybe"] or maybe
                tag = "AddKeyword" if isinstance(mod, str) else tag_of(mod)
                if tag == "AddKeyword":
                    name = (
                        mod
                        if isinstance(mod, str)
                        else mod_keyword_name(cast("TypedMirrorNode", mod))
                    )
                    w["allowed" if partly else "kw"].add(phase_keyword(name or ""))
                elif tag in _SET:
                    w["set"][_SET.index(tag)] = getattr(mod, "value", None)
                elif tag in _ADD:
                    w["add"][_ADD.index(tag)] += getattr(mod, "value", 0) or 0
                elif tag == "AddType":
                    w["types"].add(str(getattr(mod, "core_type", "")))
                elif tag == "AddSubtype":
                    w["subtypes"].add(str(getattr(mod, "subtype", "")))
                elif tag == "SetColor":
                    w["colors"] = {
                        _COLOR_LETTERS.get(str(x), str(x))
                        for x in getattr(mod, "colors", ()) or ()
                    }
    if not wanted:
        return [], sorted(set(unchecked))
    if res.changed_before or res.changed_after:
        return [], sorted({*unchecked, "board-changed"})
    if _other_effect(res) or res.other_abilities:
        return [], sorted({*unchecked, "other-effect"})
    assert board is not None
    out: list[Check] = []
    for i, w in wanted.items():
        before, after = board.before[i], board.after[i]
        counters = _counter_keywords(res, i, counter_name)
        keyword = _keyword_check(w, _gained(before, after, ability), counters)
        if isinstance(keyword, str):
            unchecked.append(keyword)
        else:
            out += keyword
        counted = any(
            "CounterAdded" in e.types and i in e.affected for e in res.effects
        )
        base = (
            "base: other change"
            if w["set"] != [None, None] and (other_pt or counted)
            else _base_check(w, before, after, record_of)
        )
        if isinstance(base, str):
            unchecked.append(base)
        elif base is not None:
            out.append(base)
        out += _type_checks(w, after)
    return out, sorted(set(unchecked))


#: Phase's concepts that change power and toughness beside a base set.
_OTHER_PT = frozenset({"pump", "place_counter", "double_pt"})


def _counter_keywords(
    res: Resolution, i: int, counter_name: Callable[[int | None], str | None]
) -> list[str]:
    """The keywords of the keyword counters the resolution put on object
    ``i``: a keyword counter gives its object the keyword (CR 122.1b), which
    Arena lists among its abilities (Arwen, Mortal Queen's lifelink
    counter)."""
    out = []
    for e in res.effects:
        if "CounterAdded" in e.types and i in e.affected:
            kw = keyword_of(counter_name(num(e.details, "counter_type", None)))
            if kw is not None:
                out.append(kw)
    return out


def _keyword_check(
    w: dict, gained: Sequence[str], counters: Sequence[str] = ()
) -> list[Check] | str:
    """The keyword check of one object (module docstring): the keywords
    granted, the keyword counters' keywords set apart, a parameterized
    keyword (protection, ward, hexproof from) by its kind only, what it
    applies to and what it costs not compared."""
    left = collections.Counter(gained) - collections.Counter(counters)
    have = set(left) | set(counters)
    want: set[str] = w["kw"]
    allowed: set[str] = w["allowed"] | want
    extra = sorted({g for g in left if g in EVERGREEN and g not in allowed})
    missing = [k for k in sorted(want) if k not in have]
    if not want:
        if extra or (w["allowed"] & have):
            return [Check("keyword grant", sorted(allowed), sorted(gained), not extra)]
        return "partly read" if w["allowed"] else []
    if missing and w["maybe"] and not gained:
        return []  # an effect that may not happen didn't
    ok = not missing and not extra
    return [Check("keyword grant", sorted(want), sorted(gained), ok)]


def _base_check(
    w: dict,
    before: Permanent,
    after: Permanent,
    record_of: Callable[[int | None], dict | None],
) -> Check | str | None:
    power, toughness = w["set"]
    if power is None and toughness is None:
        return None
    if power is None or toughness is None:
        return "base: one of power and toughness"
    printed = _printed(record_of(before.grpid)) if before.kind == "Card" else None
    if printed is None:
        return "base: printed unknown"
    if (before.power, before.toughness) != printed:
        return "base: modified before"
    expected = [power + w["add"][0], toughness + w["add"][1]]
    observed = [after.power, after.toughness]
    return Check("base P/T", expected, observed, observed == expected)


def _type_checks(w: dict, after: Permanent) -> list[Check]:
    out = []
    if w["types"] or w["subtypes"]:
        have = {*after.card_types, *after.subtypes}
        want = sorted(w["types"] | w["subtypes"])
        out.append(Check("type change", want, sorted(have), set(want) <= have))
    if w["colors"] is not None:
        out.append(
            Check(
                "color change",
                sorted(w["colors"]),
                sorted(after.colors),
                set(after.colors) == w["colors"],
            )
        )
    return out
