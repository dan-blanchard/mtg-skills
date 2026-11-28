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
  events of the object that set it off (:func:`events_of`);
* an :class:`ObjectEvent` for each event of one object itself that a "When ~ …"
  trigger can watch (it entered or left the battlefield, was cast, attacked,
  blocked, became blocked), with the abilities Arena listed on it and every
  ability instance Arena created from it until the turn ended, and every
  permanent on the battlefield at it (:class:`BoardObject`, a watcher of it):
  what the reverse checks read for a trigger that never fired;
* an :class:`InstanceLog` for each ability instance Arena created, with the
  objects it came from and the one Arena says set it off;
* an :class:`Offer` for each legal action a game state lists (``actions``),
  once per game and cost, and the seats Arena asks for actions (the log's own
  player, :attr:`Logs.local`).

An annotation a full resync repeats (the same id, the same content) is read once
by all three, and an event a rollback undoes (an id reused for another
annotation) is marked so (:attr:`ObjectEvent.rolled_back`).

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
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import NamedTuple

__all__ = [
    "NO_X",
    "BoardObject",
    "ChosenX",
    "Effect",
    "Instance",
    "InstanceLog",
    "Logs",
    "ObjectEvent",
    "Offer",
    "Permanent",
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
#: Arena's ``CardColor`` names → the color letters (CR 105.1).
_COLORS = {
    "CardColor_White": "W",
    "CardColor_Blue": "U",
    "CardColor_Black": "B",
    "CardColor_Red": "R",
    "CardColor_Green": "G",
}
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


class Permanent(NamedTuple):
    """An object as a resolution began, as the log shows it: for counting the
    battlefield and reading an object's power (``Resolution.permanents``,
    ``Resolution.lki``)."""

    id: int
    grpid: int | None
    controller: int | None
    owner: int | None
    #: ``"Card"`` / ``"Token"``.
    kind: str
    card_types: tuple[str, ...]
    subtypes: tuple[str, ...]
    supertypes: tuple[str, ...]
    colors: tuple[str, ...]
    power: int | None
    toughness: int | None
    #: The ability ids Arena lists on it (``uniqueAbilities``).
    abilities: tuple[int, ...] = ()


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
    #: The message it is in: its place among the game's messages.
    message: int = 0
    #: Every card and token on the battlefield as it began.
    permanents: tuple[Permanent, ...] = ()
    #: The ability's own permanent (``parent``) and the objects it targets as
    #: last logged by then: their last known information if they left (CR
    #: 608.2h).
    lki: tuple[Permanent, ...] = ()
    #: Whether the message it began in changed the battlefield (an object's
    #: place, power or counters) before it began: then :attr:`permanents`,
    #: the board as the message began, may not be the board it began with.
    changed_before: bool = False
    #: Every card and token on the battlefield as its message left it (a
    #: resolution begins and completes in one message), and the ability's own
    #: permanent and its targets as last logged then.
    after: tuple[Permanent, ...] = ()
    after_lki: tuple[Permanent, ...] = ()
    #: Whether its message changed the battlefield after it completed: then
    #: :attr:`after` may not be the board it left.
    changed_after: bool = False
    #: Whether its message begins to show an ability another object added or
    #: removed (a new persistent ``AddAbility`` / ``RemoveAbility``, which
    #: Arena may log with no other annotation).
    other_abilities: bool = False


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


class Instance(NamedTuple):
    """An ability instance Arena created: its own id and its ability's."""

    id: int
    grpid: int


class InstanceLog(NamedTuple):
    """An ability instance Arena created, as the game logged it: the message it
    is in (its place in the game, :attr:`ObjectEvent.message`'s count), the
    objects it came from (its source and parent), and the object Arena says set
    it off (``TriggeringObject``), if it names one."""

    game: tuple[str, int]
    message: int
    turn: int | None
    id: int
    grpid: int
    sources: frozenset[int]
    cause: int | None


class BoardObject(NamedTuple):
    """A permanent on the battlefield at an object event: a watcher of it."""

    id: int
    grpid: int | None
    controller: int | None
    #: ``"Card"`` / ``"Token"``.
    kind: str
    #: The ability ids Arena listed on it (``uniqueAbilities``).
    abilities: tuple[int, ...]
    copy: bool
    face_down: bool
    #: Whether it entered or left the battlefield in the event's message: then
    #: whether it saw the event (entering at the same time, CR 603.6a; leaving
    #: at the same time, CR 603.10a) or not (moving before or after it) the log
    #: can't tell.
    moved: bool


@dataclass(frozen=True)
class ObjectEvent:
    """One event of an object itself, as a "When ~ …" trigger of its own watches
    it, and what Arena did after it.

    ``event`` is ``enters`` (a move onto the battlefield, or a token created:
    CR 111.2), ``leaves`` (a move off it; ``origin`` / ``destination`` say where
    to), ``cast_spell`` (a ``CastSpell`` move), ``attacks`` (declared: its
    attack state went from declared to attacking, so never one put onto the
    battlefield attacking, CR 508.3a and 508.4), ``blocks`` (likewise) or
    ``becomes_blocked`` (a declared blocker names it)."""

    game: tuple[str, int]
    turn: int | None
    event: str
    #: A zone move's zones (Arena's ``ZoneType`` names), else ``None``.
    origin: str | None
    destination: str | None
    #: The object as the event saw it: as it entered, or as it last was on the
    #: battlefield for a leave (CR 603.10a: leaves-the-battlefield abilities
    #: look back in time).
    grpid: int | None
    controller: int | None
    #: ``"Card"`` / ``"Token"`` (Arena's object type).
    kind: str
    #: The ability ids Arena listed on it (``uniqueAbilities``).
    abilities: tuple[int, ...]
    #: Whether Arena marks it a copy (``isCopy``).
    copy: bool
    #: Whether Arena marks it face down (``isFacedown``).
    face_down: bool
    #: Each ability instance Arena created from it (the instance's source or
    #: parent is the object, under any id it had, and the object Arena says set
    #: it off, ``TriggeringObject``, is the object or unnamed), from the event's
    #: message until the turn ended. Another event of the object in that window
    #: is offered the same instances: which event one answers is the checker's
    #: to decide (``check.Checker.expected``), since Arena's link names the
    #: object, never its event.
    fired: tuple[Instance, ...]
    #: Whether the turn ended before the log moved on: ``False`` when the game
    #: (or the log) ended first, so a trigger may never have been put on the
    #: stack.
    turn_ended: bool
    #: Arena's ``category`` for a zone move (``Resolve``, ``SBA_Damage``, …).
    category: str = ""
    #: Its place among the game's object events, in the order the log shows
    #: them: the same logs number them the same whatever parses them.
    ordinal: int = 0
    #: The object's card types (Arena's ``cardTypes``), as it was.
    card_types: tuple[str, ...] = ()
    #: ``(grpId, controller)`` of each card on the battlefield at the event (for
    #: a leave, with every card that left it in the same message: CR 603.10a).
    battlefield: tuple[tuple[int, int | None], ...] = ()
    #: Whether Arena undid it: a later message reused the id of the annotation
    #: it came from for another one (a cancelled cast is rolled back that way).
    rolled_back: bool = False
    #: The message it is in: its place among the game's messages.
    message: int = 0
    #: The object's id at the event (for a leave, its battlefield id), and every
    #: id it had by then.
    object_id: int = 0
    ids: frozenset[int] = frozenset()
    #: The object's subtypes, supertypes and colors (``W``/``U``/``B``/``R``/
    #: ``G``) as Arena logged them, and its owner.
    subtypes: tuple[str, ...] = ()
    supertypes: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    owner: int | None = None
    #: Every permanent on the battlefield at the event, a watcher of it (for a
    #: leave, with those that left it in the same message: CR 603.10a).
    board: tuple[BoardObject, ...] = ()

    @property
    def events(self) -> frozenset[str]:
        """The event in :func:`events_of`'s spelling: a move is a
        ``zone_change`` too, a leave to a graveyard ``dies``, and a leave
        Arena files as a sacrifice ``sacrificed``."""
        out = {self.event}
        if self.event in ("enters", "leaves", "cast_spell"):
            out.add("zone_change")
        if self.event == "leaves" and self.destination == "Graveyard":
            out.add("dies")
        out.update(_MOVE_EVENTS.get(self.category, ()))
        return frozenset(out)


#: The legal actions recorded (``Offer.kind``): a cast, an activation, an
#: Adventure's cast or a modal double-faced card's back face's play. Not mana
#: abilities, land plays or special actions.
_OFFER_KINDS = frozenset({"Cast", "Activate", "CastAdventure", "PlayMDFC"})


class Offer(NamedTuple):
    """A legal action Arena listed for a player (a game state's ``actions``),
    the first time it listed it with that cost: an action is listed again at
    every priority."""

    game: tuple[str, int]
    turn: int | None
    message: int
    seat: int | None
    #: ``Cast`` / ``Activate`` / ``CastAdventure`` / ``PlayMDFC``.
    kind: str
    instance: int | None
    #: The object's card as logged then.
    grpid: int | None
    object_kind: str
    #: The object's zone (Arena's ``ZoneType`` name).
    zone: str | None
    #: ``abilityGrpId``: the ability activated, or the one a cast is by.
    ability: int | None
    #: ``alternativeGrpId``: the ability an alternative cast is (flashback's).
    alternative: int | None
    #: ``sourceId``: the object whose ability offers the alternative.
    source: int | None
    #: ``manaCost``: each entry's colors (``Generic``, ``White``, ``X``, two for
    #: a hybrid) and count.
    mana: tuple[tuple[tuple[str, ...], int], ...]
    #: The object as logged then, and the battlefield then.
    facts: Permanent | None
    permanents: tuple[Permanent, ...]
    #: Whether Arena marks the object's cost modified then (a persistent
    #: ``ModifiedCost`` annotation names it).
    modified_cost: bool = False


class Logs(NamedTuple):
    """Everything :func:`read_logs` reads, each game once."""

    resolutions: list[Resolution]
    triggers: list[TriggerFired]
    games: list[tuple[str, int]]
    events: list[ObjectEvent]
    instances: tuple[InstanceLog, ...] = ()
    offers: tuple[Offer, ...] = ()
    #: game → the seats Arena asked for actions in its log: the log's player
    local: dict[tuple[str, int], frozenset[int]] = {}  # noqa: RUF012
    #: game → the first turn its log shows
    first_turns: dict[tuple[str, int], int] = {}  # noqa: RUF012


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


def _declarations(
    o: dict, before: tuple[str, str], now: tuple[str, str]
) -> list[tuple[int, str]]:
    """The declarations an object's new combat state locks in: an attacker
    (declared, then attacking: one put onto the battlefield attacking was never
    declared, CR 508.3a and 508.4, and a creature unselected before the attack
    is locked in goes back from declared to none), a blocker likewise, and the
    attackers a declared blocker names (``becomes_blocked``)."""
    out: list[tuple[int, str]] = []
    if before[0] == "AttackState_Declared" and now[0] == "AttackState_Attacking":
        out.append((o["instanceId"], "attacks"))
    if before[1] == "BlockState_Declared" and now[1] == "BlockState_Blocking":
        out.append((o["instanceId"], "blocks"))
        out += [
            (attacker, "becomes_blocked")
            for attacker in (o.get("blockInfo") or {}).get("attackerIds", ())
        ]
    return out


def _lines(path: Path) -> Iterator[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        yield from handle


def _messages(
    lines: Iterable[str], local: Callable[[Iterable[int]], None] | None = None
) -> Iterator[dict]:
    """Each ``gameStateMessage`` in the log, in order. ``local`` is told the
    seats Arena asks for an action (``ActionsAvailableReq``'s
    ``systemSeatIds``, sent only to that player): the log's own player's."""
    for line in lines:
        if "greToClientEvent" not in line:
            continue
        try:
            event = json.loads(line[line.find("{") :])
        except ValueError:
            continue
        for msg in (event.get("greToClientEvent") or {}).get("greToClientMessages", []):
            if local is not None and msg.get("type") == _ASKS_FOR_ACTION:
                local(msg.get("systemSeatIds") or ())
            state = msg.get("gameStateMessage")
            if state:
                yield state


#: The message Arena asks a player to act with: sent only to that player.
_ASKS_FOR_ACTION = "GREMessageType_ActionsAvailableReq"


def read_logs(paths: Iterable[Path]) -> Logs:
    """Every resolution, fired trigger and object event in ``paths`` (``.log`` or
    ``.log.gz``), each game read once, and the games read."""
    seen: dict[tuple[str, int], Path] = {}
    reader = _Reader()
    for path in dict.fromkeys(p.resolve() for p in paths):  # each file once
        reader.read(path, seen)
    return Logs(
        reader.resolutions,
        reader.triggers,
        list(seen),
        reader.events,
        tuple(reader.instances),
        tuple(reader.offers),
        dict(reader.local),
        dict(reader.first_turns),
    )


def _who(i: int, seats: set[int], objs: dict[int, dict]) -> dict:
    if i in seats:
        return {"player": i}
    o = objs.get(i)
    if not o:
        return {"object": i}
    keep = ("grpId", "card_types", "subtypes", "controller", "owner")
    return {"object": i, **{k: o[k] for k in keep}}


@dataclass
class _OpenEvent:
    """An object event whose turn hasn't ended: the object's ids and the
    ability instances created from it so far."""

    event: ObjectEvent
    ids: set[int]
    fired: list[Instance] = field(default_factory=list)
    #: The id of the annotation it came from (``None`` for a combat
    #: declaration, read off the objects).
    ann_id: int | None = None


#: Annotations that change what a count over the battlefield reads: its
#: population (a token made or deleted, a copy made), an object's power or
#: toughness, and whose or what an object is (its controller, types, colors).
#: A move to or from the battlefield is one too (:func:`_changes_board`).
BOARD_ANNOTATIONS = frozenset(
    {
        "TokenCreated",
        "TokenDeleted",
        "CopiedObject",
        "PowerToughnessModCreated",
        "LayeredEffectCreated",
        # an effect ending: a pump's, an anthem's keyword's (CR 613)
        "LayeredEffectDestroyed",
        "CounterAdded",
        "CounterRemoved",
        "ControllerChanged",
        "ModifiedType",
        "ModifiedColor",
    }
)


def _changes_board(ann: dict, zones: dict) -> bool:
    types = _types(ann)
    if "ZoneTransfer" in types:
        d = _details(ann)
        moved = (num(d, "zone_src", None), num(d, "zone_dest", None))
        return any(zones.get(z, ("",))[0] == "Battlefield" for z in moved)
    return bool(BOARD_ANNOTATIONS & set(types))


def _mana_colors(colors: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(c.removeprefix("ManaColor_") for c in colors))


def _permanent(i: int, o: dict) -> Permanent:
    return Permanent(
        i,
        o.get("grpId"),
        o.get("controller"),
        o.get("owner"),
        o.get("type", ""),
        tuple(o.get("card_types", ())),
        tuple(o.get("subtypes", ())),
        tuple(o.get("supertypes", ())),
        tuple(o.get("colors", ())),
        o.get("power"),
        o.get("toughness"),
        tuple(o.get("abilities", ())),
    )


def _board_object(i: int, o: dict, *, moved: bool) -> BoardObject:
    return BoardObject(
        i,
        o.get("grpId"),
        o.get("controller"),
        o.get("type", ""),
        tuple(o.get("abilities", ())),
        bool(o.get("copy")),
        bool(o.get("face_down")),
        moved,
    )


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
        self.events: list[ObjectEvent] = []
        self.instances: list[InstanceLog] = []
        self.offers: list[Offer] = []
        #: game → the seats Arena asked for actions in its log (the local player)
        self.local: dict[tuple[str, int], frozenset[int]] = {}
        #: game → the first turn its log shows (a log can begin mid-game)
        self.first_turns: dict[tuple[str, int], int] = {}
        #: The object events whose turn hasn't ended.
        self.open_events: list[_OpenEvent] = []

    def read(self, path: Path, seen: dict[tuple[str, int], Path]) -> None:
        self.game: tuple[str, int] | None = None
        skip = False
        self._reset()
        self.seats: set[int] = set()

        def asked(seats: Iterable[int]) -> None:
            if self.game is not None and not skip:
                self.local[self.game] = self.local.get(self.game, frozenset()) | set(
                    seats
                )

        for state in _messages(_lines(path), asked):
            info = state.get("gameInfo") or {}
            if info.get("matchID"):
                key = (info["matchID"], info.get("gameNumber", 1))
                if key != self.game:
                    self._close_events(turn_ended=False)
                    self.game = key
                    skip = seen.setdefault(key, path) != path
                    self._reset()
            if self.game is not None and not skip:
                self._message(state, self.game)
        self._close_events(turn_ended=False)

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
        #: object id → the id it had just before (``ObjectIdChanged``)
        self.prev_id: dict[int, int] = {}
        #: the attackers a declared blocker named, by turn
        self.blocked: set[tuple[int, int | None]] = set()
        #: annotation id → the annotation as first logged (JSON): a full
        #: resync (``GameStateType_Full``) repeats annotations, and a rollback
        #: reuses ids for new ones
        self.ann_seen: dict[int, str] = {}
        #: the object events opened so far this game, and its messages
        self.event_count = 0
        self.message_count = 0
        self.before_objs: dict[int, dict] = {}
        self.before_zones: dict[int, list[int]] = {}
        self.board_changes: list[int] = []
        self.ability_changes: list[int | None] = []
        #: the legal actions recorded this game (:meth:`_offers`)
        self.offered: set[tuple] = set()
        #: the persistent annotations in force, by id
        self.persistent: dict[int, dict] = {}
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
        # the objects and zones as the message found them: a message's objects
        # and zones are as it leaves them, after its annotations
        self.before_objs = {
            o["instanceId"]: self.objs[o["instanceId"]]
            for o in state.get("gameObjects", [])
            if o["instanceId"] in self.objs
        }
        self.before_zones = {
            z["zoneId"]: self.zone_ids[z["zoneId"]]
            for z in state.get("zones", [])
            if z["zoneId"] in self.zone_ids
        }
        for z in state.get("zones", []):
            zone_type = z.get("type", "").removeprefix("ZoneType_")
            self.zones[z["zoneId"]] = (zone_type, z.get("ownerSeatId"))
            self.zone_ids[z["zoneId"]] = z.get("objectInstanceIds", [])
        self.message_combat: dict[int, tuple[str, str]] = {}
        #: (object id, event) for each declaration this message locked in
        declared: list[tuple[int, str]] = []
        for o in state.get("gameObjects", []):
            before = self.combat.get(o["instanceId"], ("", ""))
            self.objs[o["instanceId"]] = {
                "grpId": o.get("grpId"),
                "src": o.get("objectSourceGrpId"),
                "type": o.get("type", "").removeprefix("GameObjectType_"),
                "card_types": _strip("CardType_", o.get("cardTypes")),
                "subtypes": _strip("SubType_", o.get("subtypes")),
                "controller": o.get("controllerSeatId"),
                "owner": o.get("ownerSeatId"),
                "parent": o.get("parentId"),
                "abilities": tuple(
                    a.get("grpId") for a in o.get("uniqueAbilities", ())
                ),
                "copy": bool(o.get("isCopy")),
                "face_down": bool(o.get("isFacedown")),
                "supertypes": _strip("SuperType_", o.get("superTypes")),
                "power": (o.get("power") or {}).get("value"),
                "toughness": (o.get("toughness") or {}).get("value"),
                "colors": tuple(_COLORS[c] for c in o.get("color", ()) if c in _COLORS),
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
            declared += _declarations(o, before, self.combat[o["instanceId"]])
        for gone in state.get("diffDeletedPersistentAnnotationIds") or ():
            self.persistent.pop(gone, None)
        turn_number = (state.get("turnInfo") or {}).get("turnNumber")
        if turn_number is not None:
            self.first_turns.setdefault(game, turn_number)
        #: (affector, id) of each ability added or removed that this message
        #: begins to show (``AddAbility`` / ``RemoveAbility`` are persistent)
        self.ability_changes = [
            ann.get("affectorId")
            for ann in state.get("persistentAnnotations", [])
            if ann.get("id", 0) not in self.persistent
            and {"AddAbility", "RemoveAbility"} & set(_types(ann))
        ]
        for ann in state.get("persistentAnnotations", []):
            self.persistent[ann.get("id", 0)] = ann
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
                    self.prev_id[new] = orig
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
                # "attacked" for a trigger (CR 508.3a, 508.4)
                self.entered_attacking |= {
                    i
                    for i in ann.get("affectedIds", ())
                    if self.combat.get(i, ("",))[0] in _ATTACKING
                }
        turn = (state.get("turnInfo") or {}).get("turnNumber") or self.turn
        self.turn = turn
        # a resync's repeats are read once (the move and resolution records)
        fresh = self._fresh(anns)
        self._object_events(fresh, declared, turn, game)
        self._offers(state.get("actions") or (), turn, game)
        open_: dict | None = None
        #: the ids of this message's annotations that change the battlefield
        self.board_changes = [
            a.get("id", 0) for a in fresh if _changes_board(a, self.zones)
        ]
        for ann in fresh:
            types = _types(ann)
            if "ResolutionStart" in types:
                open_ = self._open(ann)
            elif "ResolutionComplete" in types and open_ is not None:
                # a designation it marked an object with (a Case's solved, CR
                # 719.3b) is a persistent annotation numbered inside it
                start, end = open_.pop("start_id"), ann.get("id", 0)
                open_["after"] = tuple(
                    _permanent(i, self.objs[i])
                    for z, ids in self.zone_ids.items()
                    if self.zones.get(z, ("",))[0] == "Battlefield"
                    for i in ids
                    if i in self.objs and self.objs[i]["type"] in ("Card", "Token")
                )
                seen = {open_["parent"], *open_["targets"]} - {None}
                open_["after_lki"] = tuple(
                    _permanent(i, self.objs[i]) for i in seen if i in self.objs
                )
                open_["changed_after"] = any(i > end for i in self.board_changes)
                own = {open_["instance"], open_["parent"]}
                open_["other_abilities"] = any(
                    a not in own for a in self.ability_changes
                )
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

    def _fresh(self, anns: list[dict]) -> list[dict]:
        """The annotations not logged before: a repeat (a full resync's, the
        same annotation again) is dropped, and an id reused for a new one is a
        rollback, which undoes every open event that came from an annotation
        numbered from it on."""
        out = []
        for ann in anns:
            aid, text = ann.get("id"), json.dumps(ann, sort_keys=True)
            if aid is None:
                out.append(ann)
                continue
            before = self.ann_seen.get(aid)
            if before == text:
                continue
            if before is not None:
                self._close_events(
                    turn_ended=False,
                    rolled_back=True,
                    unless=lambda e, aid=aid: e.ann_id is None or e.ann_id < aid,
                )
            self.ann_seen[aid] = text
            out.append(ann)
        return out

    def _board(self, moved: set[int]) -> list[BoardObject]:
        return [
            _board_object(i, o, moved=i in moved)
            for z, ids in self.zone_ids.items()
            if self.zones.get(z, ("",))[0] == "Battlefield"
            for i in ids
            if (o := self.objs.get(i)) and o["type"] in ("Card", "Token")
        ]

    def _battlefield(self) -> list[tuple[int, int | None]]:
        return [
            (o["grpId"], o["controller"])
            for z, ids in self.zone_ids.items()
            if self.zones.get(z, ("",))[0] == "Battlefield"
            for i in ids
            if (o := self.objs.get(i)) and o["type"] == "Card"
        ]

    def _offers(
        self, actions: Iterable[dict], turn: int | None, game: tuple[str, int]
    ) -> None:
        """Record each legal action Arena lists (``actions``) the first time
        it is listed in the game with that cost: an action is listed again at
        every priority, so a row per (seat, action, object's card, ability,
        alternative, cost) is enough."""
        for entry in actions:
            act = entry.get("action") or {}
            kind = str(act.get("actionType", "")).removeprefix("ActionType_")
            if kind not in _OFFER_KINDS:
                continue
            obj = self.objs.get(act.get("instanceId")) or {}
            mana = tuple(
                (_mana_colors(m.get("color", ())), m.get("count", 1))
                for m in act.get("manaCost") or ()
            )
            key = (
                game,
                entry.get("seatId"),
                kind,
                obj.get("grpId"),
                act.get("abilityGrpId"),
                act.get("alternativeGrpId"),
                mana,
            )
            if key in self.offered:
                continue
            self.offered.add(key)
            zone = next(
                (
                    self.zones.get(z, ("",))[0]
                    for z, ids in self.zone_ids.items()
                    if act.get("instanceId") in ids
                ),
                None,
            )
            self.offers.append(
                Offer(
                    game=game,
                    turn=turn,
                    message=self.message_count,
                    seat=entry.get("seatId"),
                    kind=kind,
                    instance=act.get("instanceId"),
                    grpid=obj.get("grpId"),
                    object_kind=obj.get("type", ""),
                    zone=zone,
                    ability=act.get("abilityGrpId"),
                    alternative=act.get("alternativeGrpId"),
                    source=act.get("sourceId"),
                    mana=mana,
                    facts=_permanent(act.get("instanceId") or 0, obj) if obj else None,
                    permanents=tuple(
                        _permanent(i, self.objs[i])
                        for z, ids in self.zone_ids.items()
                        if self.zones.get(z, ("",))[0] == "Battlefield"
                        for i in ids
                        if i in self.objs and self.objs[i]["type"] in ("Card", "Token")
                    ),
                    modified_cost=any(
                        act.get("instanceId") in a.get("affectedIds", ())
                        for a in self.persistent.values()
                        if "ModifiedCost" in _types(a)
                    ),
                )
            )

    def _object_events(
        self,
        anns: list[dict],
        declared: list[tuple[int, str]],
        turn: int | None,
        game: tuple[str, int],
    ) -> None:
        """Close the object events of an earlier turn, open this message's, and
        give each open one the ability instances Arena created from its object
        in this message (the whole message: Arena logs a dies trigger's instance
        ahead of the move that set it off)."""
        self._close_events(turn_ended=True, unless=lambda e: e.event.turn == turn)
        self.message_count += 1
        moves = [
            (ann, _details(ann))
            for ann in anns
            if "ZoneTransfer" in _types(ann) or "TokenCreated" in _types(ann)
        ]
        # the ids that entered and left the battlefield in this message
        entered = {
            i
            for ann, d in moves
            if "TokenCreated" in _types(ann)
            or self.zones.get(num(d, "zone_dest", None), ("",))[0] == "Battlefield"
            for i in ann.get("affectedIds", ())
        }
        gone = [
            self.prev_id.get(i, i)
            for ann, d in moves
            if self.zones.get(num(d, "zone_src", None), ("",))[0] == "Battlefield"
            for i in ann.get("affectedIds", ())
        ]
        board = self._battlefield()
        on = self._board(entered)
        # what left the battlefield in this message: it was there for a leave
        # trigger looking back (CR 603.10a)
        left = [
            (was["grpId"], was["controller"])
            for i in gone
            if (was := self.objs.get(i)) and was["type"] == "Card"
        ]
        left_board = [
            _board_object(i, was, moved=True)
            for i in gone
            if (was := self.objs.get(i)) and was["type"] in ("Card", "Token")
        ]
        for i, event in declared:
            if event == "becomes_blocked":
                if (i, turn) in self.blocked:
                    continue  # a second blocker: one event
                self.blocked.add((i, turn))
            self._open_event(
                game, turn, event, i, self.objs.get(i, {}), board=board, watchers=on
            )
        for ann, d in moves:
            aid = ann.get("id")
            if "TokenCreated" in _types(ann):
                for i in ann.get("affectedIds", ()):
                    obj = self.objs.get(i, {})
                    self._open_event(
                        game,
                        turn,
                        "enters",
                        i,
                        obj,
                        dest="Battlefield",
                        board=board,
                        ann_id=aid,
                        watchers=on,
                    )
                continue
            src = self.zones.get(num(d, "zone_src", None), ("",))[0]
            dest = self.zones.get(num(d, "zone_dest", None), ("",))[0]
            category = word(d, "category")
            for i in ann.get("affectedIds", ()):
                # a leave sees the object as it last was (its id before)
                was = self.objs.get(self.prev_id.get(i, i), {})
                now = self.objs.get(i, {})
                if dest == "Battlefield":
                    self._open_event(
                        game,
                        turn,
                        "enters",
                        i,
                        now,
                        board=board,
                        watchers=on,
                        ann_id=aid,
                        src=src,
                        dest=dest,
                        category=category,
                    )
                if src == "Battlefield":
                    self._open_event(
                        game,
                        turn,
                        "leaves",
                        i,
                        was,
                        board=board + left,
                        watchers=on + left_board,
                        object_id=self.prev_id.get(i, i),
                        ann_id=aid,
                        src=src,
                        dest=dest,
                        category=category,
                    )
                if category == "CastSpell":
                    self._open_event(
                        game,
                        turn,
                        "cast_spell",
                        i,
                        now,
                        board=board,
                        watchers=on,
                        ann_id=aid,
                        src=src,
                        dest=dest,
                        category=category,
                    )
        for ann in anns:
            if "AbilityInstanceCreated" not in _types(ann):
                continue
            inst = (ann.get("affectedIds") or [None])[0]
            ability = self.objs.get(inst) or {}
            if inst is None or ability.get("type") != "Ability":
                continue
            if ability.get("grpId") is None:
                continue
            sources = {
                i
                for i in (ann.get("affectorId"), ability.get("parent"))
                if i is not None
            }
            # the object Arena says set it off, when it names one
            cause = self.triggered_by.get(inst)
            self.instances.append(
                InstanceLog(
                    game,
                    self.message_count,
                    turn,
                    inst,
                    ability["grpId"],
                    frozenset(sources),
                    cause,
                )
            )
            for e in self.open_events:
                if e.ids & sources and (cause is None or cause in e.ids):
                    e.fired.append(Instance(inst, ability["grpId"]))

    def _open_event(
        self,
        game: tuple[str, int],
        turn: int | None,
        event: str,
        i: int,
        obj: dict,
        *,
        src: str | None = None,
        dest: str | None = None,
        category: str = "",
        board: Sequence[tuple[int, int | None]] = (),
        ann_id: int | None = None,
        watchers: Sequence[BoardObject] = (),
        object_id: int | None = None,
    ) -> None:
        ids = {i, *self.earlier.get(i, ())}
        record = ObjectEvent(
            game=game,
            turn=turn,
            event=event,
            origin=src,
            destination=dest,
            grpid=obj.get("grpId"),
            controller=obj.get("controller"),
            kind=obj.get("type", ""),
            abilities=obj.get("abilities", ()),
            copy=obj.get("copy", False),
            face_down=obj.get("face_down", False),
            fired=(),
            turn_ended=False,
            category=category,
            ordinal=self.event_count,
            card_types=tuple(obj.get("card_types", ())),
            battlefield=tuple(board),
            message=self.message_count,
            object_id=i if object_id is None else object_id,
            ids=frozenset(ids),
            subtypes=tuple(obj.get("subtypes", ())),
            supertypes=tuple(obj.get("supertypes", ())),
            colors=tuple(obj.get("colors", ())),
            owner=obj.get("owner"),
            board=tuple(watchers),
        )
        self.event_count += 1
        self.open_events.append(_OpenEvent(record, ids, ann_id=ann_id))

    def _close_events(
        self,
        *,
        turn_ended: bool,
        rolled_back: bool = False,
        unless: Callable[[_OpenEvent], bool] = lambda _: False,
    ) -> None:
        """Turn the open events into :class:`ObjectEvent` records, all but
        those ``unless`` keeps open."""
        still: list[_OpenEvent] = []
        for e in self.open_events:
            if unless(e):
                still.append(e)
                continue
            self.events.append(
                replace(
                    e.event,
                    fired=tuple(e.fired),
                    turn_ended=turn_ended,
                    rolled_back=rolled_back,
                )
            )
        self.open_events = still

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
        seen = {o.get("parent"), *self.targets_of.get(inst, ())} - {None}
        # the board as the message began (what it shows is after it)
        was = {**self.objs, **self.before_objs}
        began = [
            i
            for z, ids in {**self.zone_ids, **self.before_zones}.items()
            if self.zones.get(z, ("",))[0] == "Battlefield"
            for i in ids
            if i in was
        ]
        start = ann.get("id", 0)
        return {
            "message": self.message_count,
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
            "permanents": tuple(
                _permanent(i, was[i])
                for i in began
                if was[i]["type"] in ("Card", "Token")
            ),
            "lki": tuple(_permanent(i, was[i]) for i in seen if i in was),
            "changed_before": any(i < start for i in self.board_changes),
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
