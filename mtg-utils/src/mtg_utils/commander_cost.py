"""Effective commander cost (ADR-0044).

The Burgess land formula wants "how much mana do you need, and by when" for
the commander; printed mana value is its proxy. A self-discounting commander
(The Lord of the Eagles, {7}{U}{U}: "costs {X} less to cast, where X is the
total power of creatures you control with flying"; Ghalta, Primal Hunger)
breaks the proxy — the deck built around it never pays nine.

**Effective commander cost** (see ``deck-forge/CONTEXT.md``) is the earliest
turn T on which the deck expects to afford its commander: printed mana value
minus the floored expected value of the commander's OWN cost-reduction operand,
never below the colored pips, must be at most T (CR 601.2f: a reduction
subtracts from the total cost and only touches generic mana). It is never
above printed mana value and never below the residual cost.

The expectation is closed-form and stated: on the play, no mulligan, one land
per turn, 7 + (T - 1) cards seen (hypergeometric mean per card), matching
cards cast cheapest-first within the cumulative mana of turns 1..T-1 (turn T is
reserved for the commander), summing PRINTED power / toughness or counting
bodies. Anthems, granted keywords, variable power and interaction are not
modelled — the figure is an uninteracted-curve number and every consumer
labels it so.

Scope: the commander's own clause only (deck-side reducers and cost cheats are
separate, deferred decisions), and only battlefield-population operands
(``PropertyAggregate`` Sum of Power/Toughness, ``ObjectCount``) over a plain
``Typed`` filter (types / subtypes / ``WithKeyword``). Every other shape, a
conditional clause, a missing IR, or a clause-less commander degrades to
printed mana value with a REPORTED status — never silently.

The operand is read from phase's IR through the existing crosswalk lookup
(``trees_for``); population membership is matched against the hydrated
Scryfall record (type line, printed keywords, printed P/T), so the deck side
needs no per-card IR and has no coverage holes for digital-only cards.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mtg_utils._card_ir.crosswalk.reads import (
    aggregate_filter,
    filter_controller,
    filter_core_types,
    filter_keywords,
    filter_predicates,
    filter_subtypes,
    iter_typed_nodes,
    modify_cost_mode,
    static_mode_field,
    static_mode_tag,
    tag_of,
)
from mtg_utils._deck_forge._ir_lookup import trees_for

STATUS_MODELLED = "modelled"
STATUS_NONE = "none"  # the commander has no self-discount clause
STATUS_NO_IR = "unmodelled (no IR)"

_DEFAULT_HAND_SIZE = 7
_MANA_SYMBOL = re.compile(r"\{([^}]+)\}")


@dataclass(frozen=True)
class SelfDiscount:
    """A commander's own cost-reduction operand, in the shape the estimator prices.

    ``kind`` is ``"sum"`` (``PropertyAggregate`` Sum over ``property``) or
    ``"count"`` (``ObjectCount``); ``per_unit`` is the generic mana removed per
    unit of the operand; the three tuples are the population filter's type
    words, subtype words, and required keywords (all controller-You).
    """

    kind: str
    property: str | None
    per_unit: int
    core_types: tuple[str, ...]
    subtypes: tuple[str, ...]
    keywords: tuple[str, ...]

    def describe(self) -> str:
        pop = " ".join(
            w
            for w in (
                *self.core_types,
                *self.subtypes,
                *(f"with {k}" for k in self.keywords),
            )
        )
        what = f"total {self.property}" if self.kind == "sum" else "count"
        unit = (
            f"{{{self.per_unit}}} less per unit"
            if self.per_unit != 1
            else "{1} less per unit"
        )
        return f"{what} of {pop or 'permanents'} you control ({unit})"


# ── IR read ───────────────────────────────────────────────────────────────────


def read_self_discount(record: Mapping) -> SelfDiscount | str:
    """The commander's own cost reduction, or a status string explaining why it
    can't be priced (``STATUS_NONE`` / ``STATUS_NO_IR`` / ``unmodelled (<why>)``).

    Reads phase's ``ModifyCost{Reduce}`` static over ``SelfRef`` — the node the
    build-around ``cost_reduction`` lane deliberately skips — through the same
    structural helpers the lanes use. The first unsupported feature met wins the
    status, so a Karador reads ``unmodelled (ZoneCardCount)`` and Gwaihir
    ``unmodelled (conditional)``.
    """
    trees = trees_for(dict(record))
    if not trees:
        return STATUS_NO_IR
    for tree in trees:
        for unit in tree.units:
            for node in iter_typed_nodes(unit.node):
                if static_mode_tag(node) != "ModifyCost":
                    continue
                if modify_cost_mode(node) != "Reduce":
                    continue
                if tag_of(getattr(node, "affected", None)) != "SelfRef":
                    continue
                return _discount_from_node(node)
    return STATUS_NONE


def _discount_from_node(node: object) -> SelfDiscount | str:
    condition = getattr(node, "condition", None)
    if condition is not None and tag_of(condition) is not None:
        return "unmodelled (conditional)"
    amount = static_mode_field(node, "amount")
    shards = getattr(amount, "shards", None) or []
    generic = getattr(amount, "generic", None)
    if shards or not isinstance(generic, int) or generic < 1:
        return "unmodelled (non-generic amount)"
    qty = static_mode_field(node, "dynamic_count")
    tag = tag_of(qty)
    if qty is None or tag is None:
        return "unmodelled (fixed)"
    if tag == "PropertyAggregate":
        function = getattr(qty, "function", None)
        prop = getattr(qty, "property", None)
        if function != "Sum" or prop not in ("Power", "Toughness"):
            return f"unmodelled ({tag}: {function}/{prop})"
        filt = aggregate_filter(qty)
        kind = "sum"
    elif tag == "ObjectCount":
        filt = getattr(qty, "filter", None)
        kind = "count"
        prop = None
    else:
        return f"unmodelled ({tag})"
    if filt is None or tag_of(filt) != "Typed":
        return f"unmodelled ({tag}: unsupported filter)"
    controller = filter_controller(filt)
    if controller not in (None, "You"):
        return f"unmodelled ({tag}: controller {controller})"
    extra = tuple(p for p in filter_predicates(filt) if p != "WithKeyword")
    if extra:
        return f"unmodelled ({tag}: predicate {extra[0]})"
    return SelfDiscount(
        kind=kind,
        property=prop,
        per_unit=generic,
        core_types=filter_core_types(filt),
        subtypes=filter_subtypes(filt),
        keywords=filter_keywords(filt),
    )


# ── Population match against hydrated records ─────────────────────────────────


def _front_face(record: Mapping) -> Mapping:
    faces = record.get("card_faces") or []
    return faces[0] if faces and isinstance(faces[0], Mapping) else record


def _type_words(record: Mapping) -> set[str]:
    type_line = (record.get("type_line") or "").split("//")[0].lower()
    return set(re.findall(r"[a-z][a-z'\-]*", type_line))


def _keywords(record: Mapping) -> set[str]:
    return {str(k).lower() for k in (record.get("keywords") or [])}


def matches_population(record: Mapping, discount: SelfDiscount) -> bool:
    """Does this hydrated record's PRINTED identity satisfy the operand's filter?"""
    words = _type_words(record)
    for word in (*discount.core_types, *discount.subtypes):
        w = word.lower()
        if w == "permanent":
            if "instant" in words or "sorcery" in words:
                return False
            continue
        if w not in words:
            return False
    keywords = _keywords(record)
    return all(k.lower() in keywords for k in discount.keywords)


def _printed_stat(record: Mapping, field: str) -> int:
    value = record.get(field)
    if value is None:
        value = _front_face(record).get(field)
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0  # ``*`` / missing — conservative


def contribution(record: Mapping, discount: SelfDiscount) -> int:
    """This record's contribution to the operand once on the battlefield."""
    if discount.kind == "count":
        return 1
    return _printed_stat(
        record, "power" if discount.property == "Power" else "toughness"
    )


# ── Estimator ─────────────────────────────────────────────────────────────────


def _mana_value(record: Mapping) -> float:
    value = record.get("cmc")
    if value is None:
        value = _front_face(record).get("cmc")
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def expected_operand(
    deck_entries: Sequence[tuple[Mapping, int]],
    discount: SelfDiscount,
    *,
    turn: int,
    library_size: int,
    hand_size: int = _DEFAULT_HAND_SIZE,
) -> float:
    """The expected operand on turn ``turn`` (before floor): hypergeometric mean of
    each matching card's copies seen by then, cast cheapest-first within the mana
    of turns 1..turn-1. ``deck_entries`` are ``(hydrated record, quantity)`` for
    the non-commander deck; ``library_size`` is the deck size minus commanders.
    """
    if turn < 1 or library_size < 1:
        return 0.0
    seen = min(1.0, (hand_size + turn - 1) / library_size)
    budget = turn * (turn - 1) / 2
    matches = sorted(
        (
            (_mana_value(rec), contribution(rec, discount), qty)
            for rec, qty in deck_entries
            if qty > 0 and matches_population(rec, discount)
        ),
        key=lambda t: (t[0], -t[1]),
    )
    used = 0.0
    total = 0.0
    for cost, contrib, qty in matches:
        copies = qty * seen
        mana = copies * cost
        if mana <= 0:
            total += copies * contrib
            continue
        if used + mana <= budget:
            total += copies * contrib
            used += mana
            continue
        fraction = max(0.0, (budget - used) / mana)
        total += copies * contrib * fraction
        break
    return total


def colored_pips(mana_cost: str | None) -> int:
    """Symbols a generic-only reduction can never remove: every non-numeric,
    non-X symbol ({U}, {U/B}, {U/P}, {C}, {S}, {2/U}) counts one (CR 601.2f)."""
    count = 0
    for symbol in _MANA_SYMBOL.findall(mana_cost or ""):
        if symbol.isdigit() or symbol.upper() in ("X", "Y", "Z"):
            continue
        count += 1
    return count


def effective_commander_cost(
    commander: Mapping,
    deck_entries: Sequence[tuple[Mapping, int]],
    *,
    library_size: int,
    hand_size: int = _DEFAULT_HAND_SIZE,
) -> dict:
    """The ADR-0044 block for one commander: ``{name, printed, pips, effective,
    residual, status, operand, turns}``. ``effective`` is the affordable turn (the
    Burgess term); ``residual`` the mana actually paid on that turn; ``turns`` the
    per-turn table (expected operand after floor, residual) up to the affordable
    turn. Any non-``modelled`` status returns printed mana value unchanged.
    """
    printed = int(_mana_value(commander))
    pips = colored_pips(
        commander.get("mana_cost") or _front_face(commander).get("mana_cost")
    )
    block: dict = {
        "name": commander.get("name"),
        "printed": printed,
        "pips": pips,
        "effective": printed,
        "residual": printed,
        "status": STATUS_NONE,
        "operand": None,
        "turns": [],
        "assumptions": "on the play, no mulligan, one land per turn, printed P/T and "
        "keywords only, no interaction",
    }
    discount = read_self_discount(commander)
    if isinstance(discount, str):
        block["status"] = discount
        return block
    block["status"] = STATUS_MODELLED
    block["operand"] = discount.describe()
    turns: list[dict] = []
    for turn in range(1, printed + 1):
        expected = math.floor(
            expected_operand(
                deck_entries,
                discount,
                turn=turn,
                library_size=library_size,
                hand_size=hand_size,
            )
        )
        residual = max(pips, printed - discount.per_unit * expected)
        turns.append({"turn": turn, "expected_operand": expected, "residual": residual})
        if residual <= turn:
            block.update(effective=turn, residual=residual, turns=turns)
            return block
    block["turns"] = turns
    return block
