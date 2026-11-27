"""Amounts phase writes as a count, evaluated on the board Arena logged (ADR-0064).

"Deals damage equal to the number of creatures you control", "create a number of
tokens equal to its power", "draw half X cards, rounded down": the answer is
determined once, when the effect is applied (CR 608.2h), so it is read off the
battlefield as the resolution began (:class:`CountBoard`), and only when the log
can show it exactly. What it can evaluate (:func:`evaluate`):

* a fixed number, and the X Arena logged (the resolution's own, or the X paid
  for a permanent's spell that its enters ability reads, CR 107.3m);
* the number of permanents a filter matches (``ObjectCount``), every part of the
  filter decidable from the log (``crosswalk.filter_admits`` with a
  ``LoggedObject``: types, subtypes, supertypes, colors, the controller and owner
  side, token or not, "another");
* the distinct colors among such permanents (``DistinctColorsAmong``);
* the power or toughness of the ability's own permanent or of its one target,
  as last logged (its last known information if it left, CR 608.2h);
* the number of opponents or players (``PlayerCount``);
* and these with an offset, a factor, or divided and rounded the way the card
  says (CR 107.1a).

Anything else is left unchecked with its reason (:func:`evaluate` returns it as
a string): a quantity of another kind (a mana value, mana spent, cards in a
zone, counters, an event's amount), an object this read can't place (``that
creature``, a triggering object), a filter property the log can't show, and an
amount locked in before the resolution (an X announced as the spell was cast,
phase's ``announced_x``).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from mtg_utils._arena_crosscheck.log import (
    BOARD_ANNOTATIONS,
    NO_X,
    ChosenX,
    Effect,
    Permanent,
    word,
)
from mtg_utils._card_ir.crosswalk import (
    LoggedObject,
    ObjectFacts,
    filter_admits,
    tag_of,
)

__all__ = ["CountBoard", "changed_before", "evaluate", "is_count"]


@dataclass
class CountBoard:
    """What a resolution's counts are read off: the battlefield as it began,
    the last known information of its own permanent and its targets, its
    controller and the game's seats, the X Arena logged, its effects in the
    order logged (what changed the board before an amount, :func:`changed_before`),
    and the reasons a count went unchecked (filled as they are met)."""

    permanents: tuple[Permanent, ...]
    lki: tuple[Permanent, ...]
    controller: int | None
    seats: frozenset[int]
    parent: int | None
    targets: frozenset[int]
    x: ChosenX = NO_X
    effects: tuple[Effect, ...] = ()
    began_changed: bool = False
    unchecked: list[str] = field(default_factory=list)


def _changes_board(e: Effect) -> bool:
    if "ZoneTransfer" in e.types:
        zones = (word(e.details, "zone_src"), word(e.details, "zone_dest"))
        return "Battlefield" in zones
    return bool(BOARD_ANNOTATIONS & set(e.types))


def changed_before(board: CountBoard, is_amount: Callable[[Effect], bool]) -> bool:
    """Whether the board may have changed before Arena logged the first
    annotation of the amount (``is_amount``): its message changed it before the
    resolution began (``Resolution.changed_before``), or the resolution did
    before that annotation. Then the count, taken as that effect is applied
    (CR 608.2h), may differ from the board read ("Target creature gets +1/+0
    until end of turn. It deals damage equal to its power")."""
    if board.began_changed:
        return True
    for e in board.effects:
        if is_amount(e):
            return False
        if _changes_board(e):
            return True
    return False


def _side(board: CountBoard, seat: int | None) -> str:
    return "you" if seat == board.controller else "opponents"


def _facts(p: Permanent) -> ObjectFacts:
    return ObjectFacts(
        types=frozenset(p.card_types),
        subtypes=frozenset(p.subtypes),
        supertypes=frozenset(p.supertypes),
        colors=frozenset(p.colors),
        every_creature_type="AllCreatureTypes" in p.subtypes,
    )


def _matching(filt: object, board: CountBoard) -> list[Permanent] | str:
    """The permanents ``filt`` matches, or why the log can't say."""
    out = []
    for p in board.permanents:
        logged = LoggedObject(
            is_source=p.id == board.parent,
            token=p.kind == "Token",
            controller_side=_side(board, p.controller),
            owner_side=_side(board, p.owner),
        )
        match = filter_admits(filt, _facts(p), logged)
        if match is None:
            return "filter"
        if match:
            out.append(p)
    return out


def _object(scope: object, board: CountBoard) -> Permanent | str:
    """The object a power or toughness reads: the ability's own permanent
    (``Source``) or its one target (``Target``)."""
    tag = tag_of(scope)
    if tag == "Source":
        wanted = {board.parent} - {None}
    elif tag == "Target":
        wanted = set(board.targets) - {board.parent}
    else:
        return f"object:{tag}"
    found = [p for p in board.lki if p.id in wanted]
    return found[0] if len(found) == 1 else f"object:{tag}"


def _qty(qty: object, board: CountBoard) -> int | str:
    tag = tag_of(qty)
    if tag == "Variable" and getattr(qty, "name", None) == "X":
        return board.x.own if board.x.own is not None else "x"
    if tag == "CostXPaid":
        return board.x.spell if board.x.spell is not None else "x"
    if tag == "ObjectCount":
        found = _matching(getattr(qty, "filter", None), board)
        return found if isinstance(found, str) else len(found)
    if tag == "DistinctColorsAmong":
        source = getattr(qty, "source", None)
        if tag_of(source) != "Objects":
            return f"qty:{tag}"
        found = _matching(getattr(source, "filter", None), board)
        if isinstance(found, str):
            return found
        return len({c for p in found for c in p.colors})
    if tag in ("Power", "Toughness"):
        obj = _object(getattr(qty, "scope", None), board)
        if isinstance(obj, str):
            return obj
        value = obj.power if tag == "Power" else obj.toughness
        return value if value is not None else "object:unlogged"
    if tag == "PlayerCount":
        who = tag_of(getattr(qty, "filter", None))
        if len(board.seats) < 2 or who not in ("Opponent", "Player", "Any"):
            return f"qty:{tag}"
        return len(board.seats) - (1 if who == "Opponent" else 0)
    return f"qty:{tag}"


def evaluate(node: object, field: str, board: CountBoard) -> int | str:
    """An effect's ``field`` evaluated on ``board`` (module docstring), or the
    reason it can't be: a string."""
    return _expr(getattr(node, field, None), board)


def _expr(q: object, board: CountBoard) -> int | str:
    tag = tag_of(q)
    if tag == "Fixed":
        value = getattr(q, "value", None)
        return value if isinstance(value, int) else "qty:Fixed"
    if tag == "Ref":
        return _qty(getattr(q, "qty", None), board)
    if tag in ("Offset", "Multiply", "DivideRounded"):
        inner = _expr(getattr(q, "inner", None), board)
        if isinstance(inner, str):
            return inner
        if tag == "Offset":
            offset = getattr(q, "offset", None)
            return inner + offset if isinstance(offset, int) else "qty:Offset"
        if tag == "Multiply":
            factor = getattr(q, "factor", None)
            return inner * factor if isinstance(factor, int) else "qty:Multiply"
        divisor = getattr(q, "divisor", None)
        rounding = getattr(q, "rounding", None)
        if (
            not isinstance(divisor, int)
            or divisor <= 0
            or rounding
            not in (
                "Up",
                "Down",
            )
        ):
            return "qty:DivideRounded"
        half = inner / divisor
        return math.ceil(half) if rounding == "Up" else math.floor(half)
    return f"qty:{tag}"


def is_count(node: object, field: str) -> bool:
    """Whether an effect's ``field`` is an amount this module reads: present
    and not a fixed number or a bare X (the strict checks' own)."""
    q = getattr(node, field, None)
    if q is None or tag_of(q) in ("Fixed", None):
        return False
    qty = getattr(q, "qty", None) if tag_of(q) == "Ref" else None
    return tag_of(qty) not in ("Variable", "CostXPaid")
