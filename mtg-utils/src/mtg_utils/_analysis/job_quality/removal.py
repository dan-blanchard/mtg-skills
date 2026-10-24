"""Removal — how well a card does single-target permanent removal (the
``interaction`` role's removal half; counterspells and sweepers are other jobs).

Fitted on the 2,598 noncreature, non-planeswalker cards whose main job is
single-target removal: cross-validated Spearman 0.40 against play-rate; the
precon guides' removal adds sit at the 79th percentile of their color identity's
removal by this read (95th by play-rate — the rest is card age, reprints and
the alternative costs phase does not parse: Snuff Out, Deadly Rollick). Too weak
to order candidates; it GATES them (``JobRead.orders``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._analysis.job_quality._common import (
    KILL_SIZE,
    MASS_TAGS,
    activation_mana,
    cast_cost,
    faces,
    fixed_value,
    land_back,
    unit_kind,
    unpriced,
)
from mtg_utils._analysis.lanes.removal_tutors import removal_edict_answers
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._card_ir.crosswalk import (
    change_zone_dirs,
    effect_filter,
    effect_player_reach,
    filter_controller,
    filter_mana_value_floor,
    filter_predicates,
    iter_cost_leaves,
    tag_of,
)

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptNode

#: The permanent types an answer can be read as reaching (CR 110.4a).
_PERMANENT_TYPES = frozenset(
    {"Creature", "Artifact", "Enchantment", "Planeswalker", "Land", "Battle"}
)
#: A variable amount (X, a count) reads as a kill.
_SCALING = 99


@dataclass(frozen=True)
class _Answer:
    """One removal effect: how it removes, what it reaches, under what terms."""

    # exile | destroy | tuck | edict | damage | shrink | fight | bounce | counters
    mode: str
    breadth: int  # how many permanent types it can answer (0-6)
    conditional: bool  # a filter predicate, a mana-value bound, or a unit condition
    amount: int | None  # damage dealt / toughness taken away; None = not a sized effect
    kind: str  # spell | etb | activated | activated_sac | trigger | granted
    act_mana: int | None  # an activated ability's mana cost
    edict_each: bool  # a forced sacrifice on each opponent (not one target player)
    opp_only: bool  # the filter is an opponent's permanents


def _breadth(types: frozenset[str]) -> int:
    reach = set(types)
    if "Any" in reach:  # "any target" damage: a creature, planeswalker or battle
        reach |= {"Creature", "Planeswalker", "Battle"}
    if "Permanent" in reach:
        reach |= _PERMANENT_TYPES
    return len(reach & _PERMANENT_TYPES)


def _mode(c: ConceptNode, *, edict: bool) -> str:
    if edict:
        return "edict"
    if c.concept == "change_zone":
        dest = change_zone_dirs(c.node)[1]
        return {"Exile": "exile", "Library": "tuck"}.get(dest, "bounce")
    return {
        "put_library_position": "tuck",
        "destroy": "destroy",
        "deal_damage": "damage",
        "fight": "fight",
        "bounce": "bounce",
        "place_counter": "counters",
    }.get(c.concept, "shrink")


def _amount(c: ConceptNode) -> int | None:
    """Damage dealt, or toughness a shrink takes away; ``_SCALING`` for X."""
    if c.concept == "deal_damage":
        a = getattr(c.node, "amount", None)
        v = fixed_value(a)
        return v if v is not None else (_SCALING if a is not None else None)
    if c.concept == "pump":
        t = getattr(c.node, "toughness", None)
        v = fixed_value(t)
        if v is not None:
            return -v if v < 0 else None
        return _SCALING if t is not None else None
    return None


def _unit_kind(unit: AbilityUnit | None) -> str:
    """The base kind (``_common.unit_kind``), with ``granted`` for an effect no
    unit of the card's own carries, and ``activated_sac`` for an activation that
    asks a non-mana cost beyond tapping (a sacrifice, a life payment, a discard):
    the one-shot or conditional shape (Goblin Firebomb, Aetherflux)."""
    if unit is None:
        return "granted"
    kind = unit_kind(unit)
    if kind == "activated":
        leaves = {tag_of(n) for n in iter_cost_leaves(getattr(unit.node, "cost", None))}
        return "activated" if leaves <= {"Mana", "Tap", "Untap"} else "activated_sac"
    return kind


def _answers(card: dict) -> list[_Answer]:
    out: list[_Answer] = []
    # The public seam ``twohg_scan`` reads too: it keeps the edicts phase parses
    # with no player named (Papalymo Totolymo), served by the ledger's ident.
    trees = signal_trees_for(card, bulk=card)
    unit_of = {id(c): u for tree in trees for u in tree.units for c in u.effects}
    found = [
        (c, t, False)
        for c, t in removal_edict_answers(card, "removal", soft=True, trees=trees)
    ]
    found += [
        (c, t, True) for c, t in removal_edict_answers(card, "edict", trees=trees)
    ]
    for c, types, edict in found:
        if (tag_of(c.node) or "") in MASS_TAGS:
            continue
        unit = unit_of.get(id(c))
        filt = effect_filter(c.node)
        preds = [p for p in filter_predicates(filt) if p != "Another"]
        reach = (
            effect_player_reach(unit.node, c.node)
            if edict and unit is not None
            else None
        )
        out.append(
            _Answer(
                mode=_mode(c, edict=edict),
                breadth=_breadth(types),
                conditional=bool(preds)
                or filter_mana_value_floor(filt) is not None
                or (
                    unit is not None
                    and getattr(unit.node, "condition", None) is not None
                ),
                amount=_amount(c),
                kind=_unit_kind(unit),
                act_mana=activation_mana(unit),
                edict_each=reach in ("opponents", "per_opponent", "each"),
                opp_only=filter_controller(filt) == "Opponent",
            )
        )
    return out


#: Removal's weights, log10 play-rate per unit (ridge fit, 2026-10-19, rounded;
#: the land-back bonus capped — 33 cards fitted +1.15).
WEIGHTS: dict[str, float] = {
    "breadth": 0.06,  # per permanent type it can answer
    "unconditional": 0.15,  # no filter predicate, mana-value bound or condition
    "cheap": 0.20,  # costs 2 or less
    "three": 0.13,  # costs 3
    "instant": 0.09,  # an instant, flash, or an activated ability
    "cheap_instant_unconditional": 0.07,
    "small": -0.18,  # damage or a shrink under ``KILL_SIZE``
    "exile": 0.07,
    "edict_each": 0.35,  # each opponent sacrifices
    "etb": 0.16,  # rides a permanent entering (a body or an O-Ring)
    "land_back": 0.40,  # a modal double-faced card whose back is a land
    "activated_sac": -0.37,  # repeatable only at a sacrifice or a life payment
    "opp_only": 0.04,
}


def _removal_cost(card: dict, answers: list[_Answer]) -> float:
    """The mana the removal costs: the card's cast cost (``_common.cast_cost``),
    or one activation's mana when the answer is only an activated ability's (a
    card with no mana cost keeps its fixed cost)."""
    cost = cast_cost(card)
    if unpriced(card):
        return cost
    acts = [a.act_mana for a in answers if a.act_mana is not None]
    if acts and not any(a.kind in ("spell", "etb") for a in answers):
        cost = float(min(acts))
    return cost


def features(card: dict) -> dict[str, float] | None:
    """The removal read's features for ``card``, or ``None`` when it has no
    single-target removal (a sweeper is the board-wipe job)."""
    answers = _answers(card)
    if not answers:
        return None
    best = max(
        answers,
        key=lambda a: (
            a.breadth,
            a.mode in ("exile", "destroy", "tuck", "edict"),
            not a.conditional,
        ),
    )
    instant = (
        "Instant" in faces(card)[0]
        or "Flash" in (card.get("keywords") or ())
        or best.kind in ("activated", "activated_sac")
    )
    cost = _removal_cost(card, answers)
    unconditional = not best.conditional
    small = best.mode in ("damage", "shrink") and (best.amount or 0) < KILL_SIZE
    kinds = {a.kind for a in answers}
    return {
        "breadth": float(min(best.breadth, 4)),
        "unconditional": float(unconditional),
        "cheap": float(cost <= 2),
        "three": float(2 < cost <= 3),
        "instant": float(instant),
        "cheap_instant_unconditional": float(cost <= 2 and instant and unconditional),
        "small": float(small),
        "exile": float(any(a.mode == "exile" for a in answers)),
        "edict_each": float(any(a.edict_each for a in answers)),
        "etb": float("etb" in kinds),
        "land_back": float(land_back(card)),
        "activated_sac": float(
            "activated_sac" in kinds and not kinds & {"spell", "etb", "activated"}
        ),
        "opp_only": float(best.opp_only),
    }
