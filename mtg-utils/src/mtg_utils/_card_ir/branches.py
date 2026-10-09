"""Phase's branch shapes on the raw face records, before strict load.

Two products read the same records:

* the **misread registry** (:data:`BRANCH_MISREADS`): branches phase parses into a
  shape no structural read can tell apart from the card's own, each with a
  ``retirement_canary`` test and the record paths to drop. ``"always"`` rows are
  dropped from every tree (the branch phase invents or mis-narrows); ``"certain"``
  rows only from the certain records below (a branch another player decides that
  phase files as the controller's);
* the **certain records** (:func:`certain_records`): the records with every
  branch the controller doesn't decide, or only a natural top die face reaches,
  pruned away — so every walk over a tree built from them, structural or raw,
  sees only the outcomes the controller decides (ADR-0047 amendment, the certain
  tree).

Pure functions over plain dicts; nothing here reads the mirror or a tree.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

# A branching effect node's tag → the list field holding its alternatives: a
# ``ChooseOneOf``'s branches (an unbulleted "X or Y" choice), a ``Vote``'s outcomes
# (CR 701.38a), a ``RollDie``'s result rows (CR 706). One table: the crosswalk's
# effect walk and owner reads derive their field lists from it.
BRANCH_LISTS: dict[str, str] = {
    "ChooseOneOf": "branches",
    "Vote": "per_choice_effect",
    "RollDie": "results",
}

# ``optional_for`` values naming a player other than (or besides) the controller:
# "any player may …" (Worms of the Earth), "any other player may pay 2 life"
# (Zur's Weirding).
OTHER_PLAYER_OPTIONS = frozenset({"AnyPlayer", "AnyOpponent", "AnyOtherPlayer"})
_OPPONENT_PLAYER_SCOPES = frozenset({"Opponent", "Opponents", "EachOpponent"})
_OPPONENT_VOTERS = frozenset({"EachOpponent"})

Path = tuple[str | int, ...]


def _type(node: object) -> object:
    """A raw record node's ``type`` — or a loaded mirror node's tag, so the same
    predicates serve the crosswalk's walks over the loaded tree."""
    if isinstance(node, dict):
        return node.get("type")
    return getattr(type(node), "_tag", None)


def _get(node: object, key: str) -> object:
    if isinstance(node, dict):
        return node.get(key)
    return getattr(node, key, None)


def uncertain_list(node: object, holder: object) -> bool:
    """Whether a branching node's alternatives are another player's pick:

    * a ``ChooseOneOf`` whose ``chooser`` isn't the ``Controller`` (a villainous
      choice, CR 701.55a — Dr. Eggman; Midnight Crusader Shuttle's defending
      player);
    * a ``ChooseOneOf`` its holding wrapper hands to opponents (``player_scope``:
      "each opponent may sacrifice a nonland permanent … or discard a card" —
      Osseous Sticktwister, whose ruling has each opponent choose) or to "any
      player" (``optional_for`` — Worms of the Earth);
    * a ``Vote`` only opponents cast ("each opponent chooses money, friends, or
      secrets" — Master of Ceremonies). Friend-or-foe (``ControllerLabels``) is
      the controller's: "You make this choice for yourself as well as each other
      player" (Pir's Whim's ruling)."""
    t = _type(node)
    if t == "ChooseOneOf":
        if _type(_get(node, "chooser")) != "Controller":
            return True
        if holder is not None and (
            _type(_get(holder, "player_scope")) in _OPPONENT_PLAYER_SCOPES
            or _get(holder, "optional_for") in OTHER_PLAYER_OPTIONS
        ):
            return True
    if t == "Vote":
        return _type(_get(node, "voter_scope")) in _OPPONENT_VOTERS
    return False


def natural_top_only(roll: object, row: object) -> bool:
    """Whether a die-roll row can only come up on the die's top face rolled
    naturally (The Deck of Many Things' "20 |" under a subtraction, Mathise's
    "20 |"): its range starts at the die's size and the card's own roll has no
    adding modifier. CR 706.2 lets modifiers come from other sources too; this
    judges the card's own."""
    sides, lo = _get(roll, "sides"), _get(row, "min")
    return (
        isinstance(sides, int)
        and isinstance(lo, int)
        and lo >= sides
        and _type(_get(roll, "modifier")) in (None, "Subtract")
    )


def _punisher_else(node: dict, *, after_other_option: bool) -> bool:
    """Whether ``node`` is the "If they do … Otherwise …" conditional that follows
    another player's option (Zur's Weirding: "any other player may pay 2 life. If
    a player does, … Otherwise, that player draws a card") — its branches are that
    player's call."""
    cond = node.get("condition")
    return (
        after_other_option
        and isinstance(node.get("else_ability"), dict)
        and _type(cond) == "EffectOutcome"
        and isinstance(cond, dict)
        and cond.get("signal") == "OptionalEffectPerformed"
    )


def _prune(node: object, holder: dict | None, *, after_other_option: bool) -> bool:
    """Prune the uncertain branches under ``node`` in place; whether any went."""
    changed = False
    if isinstance(node, list):
        for item in node:
            changed |= _prune(item, None, after_other_option=False)
        return changed
    if not isinstance(node, dict):
        return False
    field = BRANCH_LISTS.get(_type(node))
    alts = node.get(field) if field else None
    if isinstance(alts, list) and alts:
        if uncertain_list(node, holder):
            node[field] = []
            changed = True
        elif field == "results":
            kept = [row for row in alts if not natural_top_only(node, row)]
            if len(kept) != len(alts):
                node[field] = kept
                changed = True
    if _punisher_else(node, after_other_option=after_other_option):
        node["else_ability"] = None
        changed = True
    other_option = node.get("optional_for") in OTHER_PLAYER_OPTIONS
    for key, value in node.items():
        changed |= _prune(
            value,
            node if key == "effect" else None,
            after_other_option=other_option and key == "sub_ability",
        )
    return changed


# ── The misread registry ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class BranchMisread:
    card: str
    misread: str
    canary: str
    drop: tuple[Path, ...]
    when: Literal["always", "certain"]


BRANCH_MISREADS: tuple[BranchMisread, ...] = (
    BranchMisread(
        card="Fraying Line",
        misread=(
            '"that player may pay {2} … Otherwise, exile this artifact and each '
            'creature without a rope counter on it": the payment is a PayCost with '
            "payer: Controller, so its Otherwise branch reads as the controller's"
        ),
        canary="test_other_player_branch_misreads_canary",
        drop=(("triggers", 1, "execute", "sub_ability", "else_ability"),),
        when="certain",
    ),
    BranchMisread(
        card="Osseous Sticktwister",
        misread=(
            "\"Then ~ deals damage … to each opponent who didn't sacrifice a "
            'permanent or discard a card this way" parses as a second choice whose '
            "second branch is a discard nobody is told to make"
        ),
        canary="test_phantom_choice_discard_canary",
        drop=(("triggers", 0, "execute", "sub_ability", "effect", "branches", 1),),
        when="always",
    ),
    BranchMisread(
        card="Spitting Slug",
        misread=(
            '"Otherwise, each creature blocking or blocked by this creature gains '
            'first strike" loses its narrowing: the grant reaches every creature'
        ),
        canary="test_unnarrowed_grant_branch_canary",
        drop=(("triggers", 0, "execute", "sub_ability", "else_ability"),),
        when="always",
    ),
)


def resolve_path(rec: object, path: Path) -> object:
    """The value at ``path`` in a raw record, or ``None`` when it doesn't resolve."""
    node = rec
    for step in path:
        if isinstance(step, int):
            if not isinstance(node, list) or not -len(node) <= step < len(node):
                return None
            node = node[step]
        else:
            if not isinstance(node, dict):
                return None
            node = node.get(step)
    return node


def _drop(rec: dict, path: Path) -> bool:
    parent = resolve_path(rec, path[:-1])
    last = path[-1]
    if isinstance(last, int) and isinstance(parent, list) and last < len(parent):
        del parent[last]
        return True
    if isinstance(last, str) and isinstance(parent, dict) and parent.get(last):
        parent[last] = None
        return True
    return False


def _misreads_for(name: str, *, certain: bool) -> Iterator[BranchMisread]:
    for row in BRANCH_MISREADS:
        if row.card == name and (row.when == "always" or certain):
            yield row


def apply_misreads(rec: dict) -> dict:
    """``rec`` with its ``"always"`` misread rows dropped (a copy when any apply)."""
    rows = list(_misreads_for(rec.get("name") or "", certain=False))
    if not rows:
        return rec
    out = copy.deepcopy(rec)
    for row in rows:
        for path in row.drop:
            _drop(out, path)
    return out


def certain_records(recs: Sequence[dict]) -> tuple[dict, ...] | None:
    """Deep copies of ``recs`` with every branch the controller doesn't decide, or
    only a natural top die face reaches, pruned (:func:`uncertain_list`,
    :func:`natural_top_only`, the "otherwise" after another player's option, and
    the ``"certain"`` misread rows); ``None`` when nothing was pruned."""
    out = copy.deepcopy(list(recs))
    changed = False
    for rec in out:
        for row in _misreads_for(rec.get("name") or "", certain=True):
            if row.when == "certain":
                for path in row.drop:
                    changed |= _drop(rec, path)
        changed |= _prune(rec, None, after_other_option=False)
    return tuple(out) if changed else None
