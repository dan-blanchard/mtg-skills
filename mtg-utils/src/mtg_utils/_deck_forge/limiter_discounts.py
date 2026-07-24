"""Rate v2 S2 — limiter discounts on matched pair rows (design note 2.6).

The pair ledger prices an interaction's EXISTENCE; a limiter printed on
the candidate's matching ability caps its RATE, and the flat row weight
overpays exactly there (the grounded panels' measured kills: Donal's
"only once each turn", Weaver's {T} activation, Vigean's negative-mana
loop under Urza). A matched row's weight multiplies by a discount only
on AFFIRMATIVE structural evidence from the attributed matching unit(s)
(S0 provenance seam, intersection semantics):

* ``once_per_turn`` x0.5 — the matching trigger carries phase's
  ``OncePerTurn`` constraint tag;
* ``tap_cost`` x0.75 — {T} among the matching ability's activation-cost
  leaves (a self-capping engine);
* ``cost_exceeds_yield`` x0.5 — the matching ability's activation mana
  cost strictly exceeds the anchor commander's per-use mana yield, read
  ONLY when the anchor has a structurally-readable mana ability.

Distinct limiter types MULTIPLY (monotone in limiter count; bound
[0.375, 1.0]); any unattributed matching ident, or any attributed unit
carrying no limiter, means NO discount (an engine with one uncapped
line is uncapped — the conservative no-evidence default throughout).
Unparsed and absent price identically at 1.0 BY DESIGN: the discount
fires on found evidence only, so parse coverage is never a pricing axis.

Ships default-off: ``pair_score`` applies discounts only when handed a
``discount_fn`` (this module's ``limiter_discount_fn(ctx)``); the flag
flips only if the S2 slice measurement accepts (ADR-0043 amended gates).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit
    from mtg_utils._deck_forge.pair_reads import PairContext, PairRead

from mtg_utils._card_ir.crosswalk import iter_cost_leaves, tag_of

# The frozen coefficient table (2.6 freeze-by-mechanism: CI pins content
# equality; changes are their own protocol event).
DISCOUNT_COEFFICIENTS: dict[str, float] = {
    "once_per_turn": 0.5,
    "tap_cost": 0.75,
    "cost_exceeds_yield": 0.5,
}


def _mana_cost_of(unit: AbilityUnit) -> int:
    """Generic + shard count across the unit's Mana cost leaves (the
    activation price in mana, 0 when free)."""
    total = 0
    for cc in unit.costs:
        for leaf in iter_cost_leaves(cc.node):
            if tag_of(leaf) != "Mana":
                continue
            cost = getattr(leaf, "cost", None) or leaf
            total += int(getattr(cost, "generic", 0) or 0)
            shards = getattr(cost, "shards", None) or ()
            total += len(shards)
    return total


def _has_tap_cost(unit: AbilityUnit) -> bool:
    return any(
        tag_of(leaf) == "Tap" for cc in unit.costs for leaf in iter_cost_leaves(cc.node)
    )


def _has_once_per_turn(unit: AbilityUnit) -> bool:
    return tag_of(getattr(unit.node, "constraint", None)) == "OncePerTurn"


def anchor_mana_yield(commander_records: list[dict]) -> int | None:
    """The anchor's per-use mana yield: the max number of mana added by
    any single activation of a commander mana ability (Urza: 1). None
    when no commander mana ability is structurally readable — the
    cost-vs-yield discount then never fires (no evidence, no discount).
    """
    from mtg_utils._deck_forge._ir_lookup import trees_for

    best: int | None = None
    for rec in commander_records:
        for tree in trees_for(rec):
            for unit in tree.units:
                if unit.origin != "ability":
                    continue
                if not getattr(unit.node, "is_mana_ability", False):
                    continue
                for c in unit.effects:
                    if tag_of(c.node) != "Mana":
                        continue
                    fixed = getattr(c.node, "mana", None) or getattr(
                        c.node, "amount", None
                    )
                    colors = getattr(fixed, "colors", None) if fixed else None
                    if colors is None:
                        # Fixed nested one level down (Urza shape).
                        for v in vars(c.node).values():
                            colors = getattr(v, "colors", None)
                            if colors is not None:
                                break
                    n = len(colors) if colors else 1
                    best = n if best is None else max(best, n)
    return best


def _unit_limiters(unit: AbilityUnit, anchor_yield: int | None) -> set[str]:
    found: set[str] = set()
    if _has_once_per_turn(unit):
        found.add("once_per_turn")
    if _has_tap_cost(unit):
        found.add("tap_cost")
    if (
        anchor_yield is not None
        and unit.origin == "ability"
        and _mana_cost_of(unit) > anchor_yield
    ):
        found.add("cost_exceeds_yield")
    return found


def limiter_discount_fn(ctx: PairContext) -> Callable:
    """Build the ``discount_fn`` pair_score consumes: (card, row,
    matched_idents) -> multiplier in [0.375, 1.0]. The anchor yield is
    computed once per context from the commander records the context was
    built with (attached by build_pair_context as ``_commander_records``).
    """
    from mtg_utils._deck_forge._ir_lookup import trees_for
    from mtg_utils._deck_forge.ident_provenance import unit_idents_for

    anchor_yield = anchor_mana_yield(getattr(ctx, "commander_records", ()) or [])

    def discount(card: dict, _row: PairRead, matched_idents: list[str]) -> float:
        try:
            attr = unit_idents_for(card)
            trees = trees_for(card)
        except (KeyError, ValueError, TypeError):
            return 1.0
        # Every matching ident must attribute, and EVERY attributed unit
        # must carry at least one limiter; the applied set is the
        # INTERSECTION-of-units' union-of-types per the "uncapped line"
        # rule: collect limiters present on ALL attributed units.
        common: set[str] | None = None
        for ident in matched_idents:
            units = [key for key, ids in attr.items() if ident in ids]
            if not units:
                return 1.0  # unattributed -> no evidence -> no discount
            for ti, ui in units:
                unit = trees[ti].units[ui]
                found = _unit_limiters(unit, anchor_yield)
                if not found:
                    return 1.0  # an uncapped line means uncapped
                common = found if common is None else (common & found)
        if not common:
            return 1.0
        mult = 1.0
        for kind in sorted(common):
            mult *= DISCOUNT_COEFFICIENTS[kind]
        return max(mult, 0.375)

    return discount


def matches_row(idents: frozenset[str], patterns: tuple[str, ...]) -> list[str]:
    """The candidate idents matching a row's candidate patterns."""
    return [i for i in idents if any(fnmatch.fnmatchcase(i, p) for p in patterns)]
