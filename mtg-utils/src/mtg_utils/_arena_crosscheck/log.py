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

A game seen in two logs (Player.log is archived as Player-prev.log on Arena's next
launch) is read once, keyed by match id and game number. Pure over lines of text.
"""

from __future__ import annotations

import collections
import gzip
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Effect",
    "Resolution",
    "TriggerFired",
    "events_of",
    "num",
    "read_logs",
    "word",
]

#: How many earlier messages a trigger's event is looked for in: a spell's cast,
#: its targets and its mana arrive in separate messages.
_LOOKBACK = 3
#: An object's combat state while attackers / blockers are declared and after.
_ATTACKING = frozenset({"AttackState_Declared", "AttackState_Attacking"})
_BLOCKING = frozenset({"BlockState_Declared", "BlockState_Blocking"})
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


@dataclass(frozen=True)
class TriggerFired:
    game: tuple[str, int]
    turn: int | None
    ability_grpid: int | None
    source_grpid: int | None
    controller: int | None
    #: The events of the object that set it off, or of the last few messages when
    #: Arena names none (:func:`events_of`).
    events: frozenset[str] = field(default_factory=frozenset)


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
    ``counter_added``, ``life_gained``, ``life_lost``, ``taps``, ``becomes_target``."""
    out: set[str] = set()
    for ann in anns:
        types = _types(ann)
        d = _details(ann)
        if "ZoneTransfer" in types:
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
        self.recent: collections.deque[list[dict]] = collections.deque(maxlen=_LOOKBACK)

    def _message(self, state: dict, game: tuple[str, int]) -> None:
        for p in state.get("players", []):
            self.seats.add(p.get("systemSeatNumber"))
        for z in state.get("zones", []):
            zone_type = z.get("type", "").removeprefix("ZoneType_")
            self.zones[z["zoneId"]] = (zone_type, z.get("ownerSeatId"))
            self.zone_ids[z["zoneId"]] = z.get("objectInstanceIds", [])
        self.message_combat: list[tuple[str, str]] = []
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
            self.combat[o["instanceId"]] = (
                o.get("attackState", ""),
                o.get("blockState", ""),
            )
            self.message_combat.append(self.combat[o["instanceId"]])
        for ann in state.get("persistentAnnotations", []):
            if "TriggeringObject" in _types(ann) and ann.get("affectedIds"):
                self.triggered_by[ann.get("affectorId")] = ann["affectedIds"][0]
        anns = sorted(state.get("annotations", []), key=lambda a: a.get("id", 0))
        for ann in anns:
            if "ObjectIdChanged" in _types(ann):
                d = _details(ann)
                new, orig = num(d, "new_id", None), num(d, "orig_id", None)
                if new is not None and orig is not None:
                    self.earlier[new] |= {orig, *self.earlier.get(orig, ())}
        turn = (state.get("turnInfo") or {}).get("turnNumber")
        open_: dict | None = None
        for ann in anns:
            types = _types(ann)
            if "ResolutionStart" in types:
                open_ = self._open(ann)
            elif "ResolutionComplete" in types and open_ is not None:
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
        return {
            "instance": inst,
            "grpid": num(_details(ann), "grpid", None),
            "kind": "card" if is_card else "ability",
            "source_grpid": o.get("grpId") if is_card else o.get("src"),
            "parent": o.get("parent"),
            "controller": o.get("controller"),
            "card_types": tuple(o.get("card_types", ())),
            "effects": [],
            "battlefield": tuple(
                (self.objs[i]["grpId"], self.objs[i]["controller"])
                for z, ids in self.zone_ids.items()
                if self.zones[z][0] == "Battlefield"
                for i in ids
                if i in self.objs and self.objs[i]["type"] == "Card"
            ),
            "seats": frozenset(self.seats),
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
            # the whole message included (a cost can be logged after its trigger)
            ids = {cause, *self.earlier.get(cause, ())}
            ids |= {new for new, olds in self.earlier.items() if olds & ids}
            window = (a for a in earlier + anns if _touches(a, ids))
            events = events_of(window, self.zones)
            combat = [self.combat.get(i, ("", "")) for i in ids]
        else:
            before = [a for a in anns if a.get("id", 0) < ann.get("id", 0)]
            events = events_of(earlier + before, self.zones)
            combat = self.message_combat
        if any(a in _ATTACKING for a, _ in combat):
            events.add("attacks")
        if any(b in _BLOCKING for _, b in combat):
            events.add("blocks")
        if any(b == "BlockState_Blocked" for _, b in combat):
            events.add("becomes_blocked")
        if cause is None or not events:
            # a step trigger names no object; the step is the message's own
            events |= events_of(anns, self.zones) & {"phase"}
        self.triggers.append(
            TriggerFired(
                game=game,
                turn=turn,
                ability_grpid=ability.get("grpId"),
                source_grpid=ability.get("src"),
                controller=ability.get("controller"),
                events=frozenset(events),
            )
        )
