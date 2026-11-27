"""Read MTG Arena's ``Player.log``: the game-state messages its rules engine sends.

Arena runs its rules engine on the server and logs every message it sends the client
(Detailed Logs on). Each ``gameStateMessage`` carries the objects that changed, the
zones, and **annotations**: what just happened (a zone move, damage dealt, a life
change, a counter added) and which object caused it. This module turns a log into two
event streams, one game at a time:

* a :class:`Resolution` for each spell or ability that resolved: every annotation
  between its ``ResolutionStart`` and ``ResolutionComplete``, with each affected id
  resolved to a player seat or to the object's types, controller and owner as that
  message left them, and the battlefield at that moment;
* a :class:`TriggerFired` for each triggered ability Arena put on the stack, with the
  events of the object that set it off (:func:`events_of`).

An ability that sits on an emblem is the emblem's source card's (CR 114.1: an effect
of that card made the emblem), and one that sits on a rules **trigger holder** is the
holder's source, which Arena names for a rules mechanic ("Start Your Engines!") and
leaves unnamed for a game rule's own delayed trigger (earthbend's return, CR 701.66a);
:attr:`Resolution.holder` says which.

A message without ``turnInfo`` is in the turn the last one named. A game seen in two
logs (Player.log is archived as Player-prev.log on Arena's next launch) is read once,
keyed by match id and game number. Pure over lines of text.
"""

from __future__ import annotations

import collections
import gzip
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

__all__ = [
    "NO_X",
    "ChosenX",
    "Effect",
    "Resolution",
    "TriggerFired",
    "events_of",
    "num",
    "read_logs",
    "word",
]

#: How many earlier messages a trigger's event is looked for in: a target choice
#: or a cost can arrive a message or two before the trigger. A spell's cast is
#: remembered for as long as the spell is on the stack instead (manual mana taps
#: and each target choice take a message of their own).
_LOOKBACK = 3
#: The objects an ability can sit on with no card of its own: an emblem (CR 114.1)
#: and a rules trigger holder.
_HOLDERS = frozenset({"Emblem", "TriggerHolder"})
#: An object's combat state while attackers / blockers are declared and after.
_ATTACKING = frozenset({"AttackState_Declared", "AttackState_Attacking"})
_BLOCKING = frozenset({"BlockState_Declared", "BlockState_Blocking"})
#: The ``type`` of a ``CastingTimeOption`` persistent annotation that records a
#: chosen X in its ``value``. Arena's database names no such enum; over the
#: archived and live logs read on 2026-11-25, all 17 X spells paid for with mana
#: alone show mana paid = the fixed cost + this value, and the four others have
#: a named cost changer (March of Otherworldly Light's exiled cards) or pay X
#: in life (Fire Covenant).
_CHOSE_X = 2
#: A move's ``category`` → the events it is.
_MOVE_EVENTS = {
    "CastSpell": ("cast_spell",),
    "Draw": ("drawn",),
    "Discard": ("discarded",),
    "Sacrifice": ("sacrificed",),
}


@dataclass(frozen=True)
class Effect:
    """One annotation inside a resolution."""

    types: tuple[str, ...]
    affector: int | None
    affected: tuple[int, ...]
    details: dict
    #: Per affected id: ``{"player": seat}`` or the object's ``grpId``,
    #: ``card_types``, ``subtypes``, ``controller``, ``owner`` (empty when hidden).
    who: tuple[dict, ...]
    #: For a zone move, the destination zone's owner seat.
    zone_dest_owner: int | None = None


class ChosenX(NamedTuple):
    """The X Arena logged for a resolution: ``own``, the X the resolving spell
    or ability was itself cast or activated with, and ``spell``, the X the
    spell that became an ability's permanent was cast with — what that
    permanent's enters ability reads (CR 107.3m; for the permanent itself X is
    0, so nothing later in its life reads it)."""

    own: int | None = None
    spell: int | None = None


#: No X logged.
NO_X = ChosenX()


@dataclass(frozen=True)
class Resolution:
    game: tuple[str, int]
    turn: int | None
    instance: int
    grpid: int | None
    #: ``"card"`` for a spell, ``"ability"`` for an ability.
    kind: str
    #: The card the spell is, or the card the ability belongs to.
    source_grpid: int | None
    parent: int | None
    controller: int | None
    card_types: tuple[str, ...]
    effects: tuple[Effect, ...]
    #: ``(grpId, controller)`` of each card on the battlefield as it resolved.
    battlefield: tuple[tuple[int, int | None], ...]
    #: The game's player seats: an annotation they source is the game's own.
    seats: frozenset[int] = frozenset()
    #: The X Arena logged for it (:class:`ChosenX`).
    x: ChosenX = NO_X
    #: ``(grpId, controller)`` of each token on the battlefield as it resolved.
    battlefield_tokens: tuple[tuple[int, int | None], ...] = ()
    #: Whether the ability's own permanent (``parent``) was on the battlefield.
    parent_on_battlefield: bool = False
    #: The ids it targets (its ``TargetSpec`` annotations).
    targets: frozenset[int] = frozenset()
    #: ``"Emblem"`` / ``"TriggerHolder"`` for an ability that sits on one (module
    #: docstring), else ``None``.
    holder: str | None = None


@dataclass(frozen=True)
class TriggerFired:
    game: tuple[str, int]
    turn: int | None
    ability_grpid: int | None
    source_grpid: int | None
    controller: int | None
    #: The events of the object that set it off, or of its message and the few
    #: before when Arena names none (:func:`events_of`).
    events: frozenset[str] = field(default_factory=frozenset)
    #: As :attr:`Resolution.holder`.
    holder: str | None = None


def num(details: dict, key: str, default: int | None = 0) -> int | None:
    """An annotation detail's (single) number."""
    value = (details.get(key) or [default])[0]
    return value if isinstance(value, int) else default


def word(details: dict, key: str, default: str = "") -> str:
    """An annotation detail's (single) string."""
    value = (details.get(key) or [default])[0]
    return value if isinstance(value, str) else default


def _details(ann: dict) -> dict:
    return {
        x["key"]: (
            x.get("valueInt32") or x.get("valueString") or x.get("valueUint32") or []
        )
        for x in ann.get("details", [])
    }


def _strip(prefix: str, values: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(v.removeprefix(prefix) for v in values or ())


def _types(ann: dict) -> tuple[str, ...]:
    return _strip("AnnotationType_", ann.get("type"))


def events_of(anns: Iterable[dict], zones: dict) -> set[str]:
    """The events a run of annotations shows, in ``crosswalk.trigger_def_event``'s
    spelling where one fits: ``zone_change`` (any move), ``enters``, ``dies`` (any
    permanent to a graveyard, as phase's ``dies`` is), ``leaves``, ``cast_spell``,
    ``drawn``, ``discarded``, ``sacrificed``, ``phase``, ``deals_damage``,
    ``counter_added``, ``life_gained``, ``life_lost``, ``taps``, ``becomes_target``.

    A token Arena creates (``TokenCreated``, logged with no zone move) entered the
    battlefield: "The token enters the battlefield under that player's control"
    (CR 111.2), an enters event like any other (CR 603.6a)."""
    out: set[str] = set()
    for ann in anns:
        types = _types(ann)
        d = _details(ann)
        if "TokenCreated" in types:
            out.update(("zone_change", "enters"))
        elif "ZoneTransfer" in types:
            src = zones.get(num(d, "zone_src", None), ("",))[0]
            dest = zones.get(num(d, "zone_dest", None), ("",))[0]
            out.add("zone_change")
            out.update(_MOVE_EVENTS.get(word(d, "category"), ()))
            if dest == "Battlefield":
                out.add("enters")
            if src == "Battlefield":
                out.add("leaves")
                if dest == "Graveyard":
                    out.add("dies")
        elif "PhaseOrStepModified" in types:
            out.add("phase")
        elif "DamageDealt" in types:
            out.add("deals_damage")
        elif "CounterAdded" in types:
            out.add("counter_added")
        elif "ModifiedLife" in types:
            out.add("life_gained" if (num(d, "life") or 0) > 0 else "life_lost")
        elif "TappedUntappedPermanent" in types:
            out.add("taps")
        elif "PlayerSubmittedTargets" in types or "TargetSpec" in types:
            out.add("becomes_target")
    return out


def _lines(path: Path) -> Iterator[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        yield from handle


def _messages(lines: Iterable[str]) -> Iterator[dict]:
    """Each ``gameStateMessage`` in the log, in order."""
    for line in lines:
        if "greToClientEvent" not in line:
            continue
        try:
            event = json.loads(line[line.find("{") :])
        except ValueError:
            continue
        for msg in (event.get("greToClientEvent") or {}).get("greToClientMessages", []):
            state = msg.get("gameStateMessage")
            if state:
                yield state


def read_logs(
    paths: Iterable[Path],
) -> tuple[list[Resolution], list[TriggerFired], list[tuple[str, int]]]:
    """Every resolution and fired trigger in ``paths`` (``.log`` or ``.log.gz``),
    each game read once, and the games read."""
    seen: dict[tuple[str, int], Path] = {}
    reader = _Reader()
    for path in dict.fromkeys(p.resolve() for p in paths):  # each file once
        reader.read(path, seen)
    return reader.resolutions, reader.triggers, list(seen)


def _who(i: int, seats: set[int], objs: dict[int, dict]) -> dict:
    if i in seats:
        return {"player": i}
    o = objs.get(i)
    if not o:
        return {"object": i}
    keep = ("grpId", "card_types", "subtypes", "controller", "owner")
    return {"object": i, **{k: o[k] for k in keep}}


def _touches(ann: dict, ids: set[int]) -> bool:
    return ann.get("affectorId") in ids or bool(ids & set(ann.get("affectedIds", ())))


class _Reader:
    """One pass over each log, keeping the state of the game it is in."""

    def __init__(self) -> None:
        self.resolutions: list[Resolution] = []
        self.triggers: list[TriggerFired] = []
        #: The ``grpId`` of each kind of holder seen (:data:`_HOLDERS`): an
        #: ability whose source it is sits on one, its own parent or not.
        self.holder_grps: dict[int, str] = {}

    def read(self, path: Path, seen: dict[tuple[str, int], Path]) -> None:
        self.game: tuple[str, int] | None = None
        skip = False
        self._reset()
        self.seats: set[int] = set()
        for state in _messages(_lines(path)):
            info = state.get("gameInfo") or {}
            if info.get("matchID"):
                key = (info["matchID"], info.get("gameNumber", 1))
                if key != self.game:
                    self.game = key
                    skip = seen.setdefault(key, path) != path
                    self._reset()
            if self.game is not None and not skip:
                self._message(state, self.game)

    def _reset(self) -> None:
        self.zones: dict[int, tuple[str, int | None]] = {}
        self.zone_ids: dict[int, list[int]] = {}
        self.objs: dict[int, dict] = {}
        self.combat: dict[int, tuple[str, str]] = {}
        #: ability instance → the object that set it off (``TriggeringObject``)
        self.triggered_by: dict[int, int] = {}
        #: object id → the ids it had before (``ObjectIdChanged``)
        self.earlier: dict[int, set[int]] = collections.defaultdict(set)
        #: object id → the X it was cast or activated with
        self.x_of: dict[int, int] = {}
        #: object id → the move that cast it (a ``CastSpell`` zone transfer)
        self.cast_of: dict[int, dict] = {}
        #: spell or ability id → the ids it targets
        self.targets_of: dict[int, set[int]] = collections.defaultdict(set)
        #: the creatures put onto the battlefield attacking, this combat
        self.entered_attacking: set[int] = set()
        self.recent: collections.deque[list[dict]] = collections.deque(maxlen=_LOOKBACK)
        self.turn: int | None = None

    def _on_stack(self, i: int) -> bool:
        return any(
            i in ids
            for z, ids in self.zone_ids.items()
            if self.zones.get(z, ("",))[0] == "Stack"
        )

    def _source(self, o: dict) -> tuple[int | None, str | None]:
        """An ability object's card and, when it sits on one, the holder it sits
        on (module docstring): an emblem's or a trigger holder's own source."""
        src = o.get("src")
        holder = self.objs.get(o.get("parent")) or {}
        if holder.get("type") in _HOLDERS and src == holder.get("grpId"):
            return holder.get("src"), holder["type"]
        # a delayed trigger's holder is no parent of its ability (earthbend's
        # return names the land)
        return src, self.holder_grps.get(src) if src is not None else None

    def _message(self, state: dict, game: tuple[str, int]) -> None:
        for p in state.get("players", []):
            self.seats.add(p.get("systemSeatNumber"))
        for z in state.get("zones", []):
            zone_type = z.get("type", "").removeprefix("ZoneType_")
            self.zones[z["zoneId"]] = (zone_type, z.get("ownerSeatId"))
            self.zone_ids[z["zoneId"]] = z.get("objectInstanceIds", [])
        self.message_combat: dict[int, tuple[str, str]] = {}
        for o in state.get("gameObjects", []):
            self.objs[o["instanceId"]] = {
                "grpId": o.get("grpId"),
                "src": o.get("objectSourceGrpId"),
                "type": o.get("type", "").removeprefix("GameObjectType_"),
                "card_types": _strip("CardType_", o.get("cardTypes")),
                "subtypes": _strip("SubType_", o.get("subtypes")),
                "controller": o.get("controllerSeatId"),
                "owner": o.get("ownerSeatId"),
                "parent": o.get("parentId"),
            }
            if self.objs[o["instanceId"]]["type"] in _HOLDERS:
                self.holder_grps[o.get("grpId")] = self.objs[o["instanceId"]]["type"]
            self.combat[o["instanceId"]] = (
                o.get("attackState", ""),
                o.get("blockState", ""),
            )
            self.message_combat[o["instanceId"]] = self.combat[o["instanceId"]]
            if self.combat[o["instanceId"]][0] not in _ATTACKING:
                self.entered_attacking.discard(o["instanceId"])
        for ann in state.get("persistentAnnotations", []):
            if "TriggeringObject" in _types(ann) and ann.get("affectedIds"):
                self.triggered_by[ann.get("affectorId")] = ann["affectedIds"][0]
            if "TargetSpec" in _types(ann):
                # the choice's prompt names the spell or ability choosing
                for chooser in _details(ann).get("promptParameters") or [
                    ann.get("affectorId")
                ]:
                    self.targets_of[chooser] |= set(ann.get("affectedIds", ()))
            if "CastingTimeOption" in _types(ann):
                d = _details(ann)
                value = num(d, "value", None)
                if num(d, "type", None) == _CHOSE_X and value is not None:
                    for chooser in ann.get("affectedIds", []):
                        self.x_of[chooser] = value
        anns = sorted(state.get("annotations", []), key=lambda a: a.get("id", 0))
        for ann in anns:
            types = _types(ann)
            if "ObjectIdChanged" in types:
                d = _details(ann)
                new, orig = num(d, "new_id", None), num(d, "orig_id", None)
                if new is not None and orig is not None:
                    self.earlier[new] |= {orig, *self.earlier.get(orig, ())}
            elif "ZoneTransfer" in types and word(_details(ann), "category") == (
                "CastSpell"
            ):
                for spell in ann.get("affectedIds", ()):
                    self.cast_of[spell] = ann
            dest = self.zones.get(num(_details(ann), "zone_dest", None), ("",))[0]
            if "TokenCreated" in types or (
                "ZoneTransfer" in types and dest == "Battlefield"
            ):
                # put onto the battlefield attacking: never declared, so it never
                # "attacked" for a trigger (CR 508.4)
                self.entered_attacking |= {
                    i
                    for i in ann.get("affectedIds", ())
                    if self.combat.get(i, ("",))[0] in _ATTACKING
                }
        turn = (state.get("turnInfo") or {}).get("turnNumber") or self.turn
        self.turn = turn
        open_: dict | None = None
        for ann in anns:
            types = _types(ann)
            if "ResolutionStart" in types:
                open_ = self._open(ann)
            elif "ResolutionComplete" in types and open_ is not None:
                # a designation it marked an object with (a Case's solved, CR
                # 719.3b) is a persistent annotation numbered inside it
                start, end = open_.pop("start_id"), ann.get("id", 0)
                open_["effects"] += [
                    self._effect(p)
                    for p in state.get("persistentAnnotations", [])
                    if "Designation" in _types(p) and start < p.get("id", 0) < end
                ]
                effects = tuple(open_.pop("effects"))
                self.resolutions.append(
                    Resolution(game=game, turn=turn, effects=effects, **open_)
                )
                open_ = None
            elif open_ is not None:
                open_["effects"].append(self._effect(ann))
            if "AbilityInstanceCreated" in types:
                self._trigger(ann, anns, turn, game)
        self.recent.append(anns)

    def _open(self, ann: dict) -> dict:
        inst = ann.get("affectorId")
        o = self.objs.get(inst, {})
        is_card = o.get("type") == "Card"
        source, holder = (o.get("grpId"), None) if is_card else self._source(o)
        battlefield_ids = [
            i
            for z, ids in self.zone_ids.items()
            if self.zones[z][0] == "Battlefield"
            for i in ids
            if i in self.objs
        ]
        on_battlefield = [self.objs[i] for i in battlefield_ids]
        return {
            "start_id": ann.get("id", 0),
            "instance": inst,
            "grpid": num(_details(ann), "grpid", None),
            "kind": "card" if is_card else "ability",
            "source_grpid": source,
            "holder": holder,
            "parent": o.get("parent"),
            "controller": o.get("controller"),
            "card_types": tuple(o.get("card_types", ())),
            "effects": [],
            "battlefield": tuple(
                (p["grpId"], p["controller"])
                for p in on_battlefield
                if p["type"] == "Card"
            ),
            "battlefield_tokens": tuple(
                (p["grpId"], p["controller"])
                for p in on_battlefield
                if p["type"] == "Token"
            ),
            "parent_on_battlefield": o.get("parent") in battlefield_ids,
            "targets": frozenset(self.targets_of.get(inst, ())),
            "seats": frozenset(self.seats),
            # a permanent keeps its spell's id as it resolves, and gets a new one
            # when it leaves: one that came back was no X spell on the way in
            "x": ChosenX(self.x_of.get(inst), self.x_of.get(o.get("parent"))),
        }

    def _effect(self, ann: dict) -> Effect:
        d = _details(ann)
        dest_owner = None
        for key in ("zone_src", "zone_dest"):
            if key in d:
                zone = self.zones.get(d[key][0], (d[key][0], None))
                d[key] = [zone[0]]
                if key == "zone_dest":
                    dest_owner = zone[1]
        return Effect(
            types=_types(ann),
            affector=ann.get("affectorId"),
            affected=tuple(ann.get("affectedIds", [])),
            details=d,
            who=tuple(
                _who(i, self.seats, self.objs) for i in ann.get("affectedIds", [])
            ),
            zone_dest_owner=dest_owner,
        )

    def _trigger(
        self, ann: dict, anns: list[dict], turn: int | None, game: tuple[str, int]
    ) -> None:
        inst = (ann.get("affectedIds") or [None])[0]
        ability = self.objs.get(inst) or {}
        if ability.get("type") != "Ability":
            return
        earlier = [a for msg in self.recent for a in msg]
        cause = self.triggered_by.get(inst)
        if cause is not None:
            # the object that set it off: its own annotations, under any of its ids,
            # the whole message included (a cost can be logged after its trigger),
            # and the cast of a spell still on the stack, however long ago
            ids = {cause, *self.earlier.get(cause, ())}
            ids |= {new for new, olds in self.earlier.items() if olds & ids}
            casts = [
                self.cast_of[i] for i in ids if i in self.cast_of and self._on_stack(i)
            ]
            window = (a for a in casts + earlier + anns if _touches(a, ids))
            events = events_of(window, self.zones)
            combat = {i: self.combat.get(i, ("", "")) for i in ids}
        else:
            # no object named: the whole message, since Arena can log the trigger
            # ahead of the event that set it off in the same message
            events = events_of(earlier + anns, self.zones)
            combat = self.message_combat
        if any(
            a in _ATTACKING and i not in self.entered_attacking
            for i, (a, _) in combat.items()
        ):
            events.add("attacks")
        if any(b in _BLOCKING for _, b in combat.values()):
            events.add("blocks")
        if any(b == "BlockState_Blocked" for _, b in combat.values()):
            events.add("becomes_blocked")
        if not events:
            # a step trigger can name its step's object; the step is the message's
            events |= events_of(anns, self.zones) & {"phase"}
        source, holder = self._source(ability)
        self.triggers.append(
            TriggerFired(
                game=game,
                turn=turn,
                ability_grpid=ability.get("grpId"),
                source_grpid=source,
                controller=ability.get("controller"),
                events=frozenset(events),
                holder=holder,
            )
        )
