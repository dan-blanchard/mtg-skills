"""The mana-base swaps (the 2026-10-30 plan, Phase C): fix the lands first.

The upgrade guides' largest generic add class is lands — a tapped dual or a
Guildgate traded for an untapped dual or an on-plan utility land at the same land
count — and the tune never touched a land (the land count is the land tooling's).
Fixing the mana is usually the biggest buff a precon gets, so these swaps go
first in the tune, within a purse of their own so they never buy true duals on a
budget that has a plan to pay for.

Cuts, in order: a land that enters tapped unconditionally and does nothing but
make mana (read off its trees: a ``tap_untap`` replacement with no condition and
no other unit than its mana abilities and an as-enters colour choice — Guildgates,
Thriving lands, the tapped duals; a bounce land's return trigger and a Temple's
scry keep them out), then a basic beyond the colour demand ``mana_audit`` reads.
Never a land the commander's needs or a main lane count (Yuma's Deserts), a land
that makes a colour the deck would otherwise lack, or any land when the count is
at the band floor (every swap here keeps the count: one land out, one in).

Adds: untapped lands in the deck's identity that make a colour the cut made and
the deck needs, ranked by colour coverage (two needed colours over one), then
play-rate, then price — at most ``LAND_BUDGET_SHARE`` of the budget in all and
``LAND_PRICE_SHARE`` times the even share per land, so pain, check, Pathway, bond
and slow lands qualify everywhere and shocks, fetches and true duals only on a
large budget. Each swap counts against the tune's max-swaps, as the guides count
them.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from mtg_utils._card_ir.crosswalk.reads import (
    _present,
    mana_restrictions,
    mana_spell_type_restriction,
    produced_colors,
    tag_of,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.card_classify import extract_price, is_basic_land, is_land
from mtg_utils.card_search import edhrec_popularity

#: The most of the budget the mana base may take in one tune.
LAND_BUDGET_SHARE = 0.25
#: The most one land may cost, as a multiple of the even share (budget / swaps).
LAND_PRICE_SHARE = 2.0
#: The most of a tune's swaps the mana base may take (two of thirty: a
#: five-colour precon's eleven tapped lands would otherwise take a third of the
#: tune, and every land swap is a card swap the plan's issues don't get).
LAND_SWAP_SHARE = 0.07
#: How many lands' worth of over-supply a colour must show before one of its
#: basics is surplus (one land of slack, so a 2-of-5 colour isn't trimmed to a
#: fraction).
_BASIC_SLACK = 1.0

_COLOR_FOR_BASIC = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}


def enters_tapped_unconditionally(record: dict) -> bool:
    """A land whose trees hold a ``tap_untap`` replacement with no condition and
    no choice ("~ enters tapped." — Guildgates, Thriving lands, the tapped duals;
    not Glacial Fortress's "unless", not Hallowed Fountain's "you may pay 2
    life", which parse with a condition or without the tap effect)."""
    if not is_land(record):
        return False
    for tree in trees_for(dict(record)):
        for unit in tree.units:
            if unit.origin != "replacement":
                continue
            if not any(c.concept == "tap_untap" for c in unit.effects):
                continue
            node = unit.node
            if _present(getattr(node, "condition", None)):
                continue
            if getattr(node, "optional", False):
                continue
            return True
    return False


def mana_only(record: dict) -> bool:
    """A land whose every unit is a mana ability or an as-enters replacement
    (the tapped clause, a Thriving land's colour choice): nothing the deck would
    keep it for beyond its mana."""
    if not is_land(record):
        return False
    for tree in trees_for(dict(record)):
        for unit in tree.units:
            if unit.origin == "replacement":
                continue
            if unit.origin == "ability" and all(
                c.concept == "ramp" for c in unit.effects
            ):
                continue
            # A gain-land's "you gain 1 life" is no reason to keep it (the
            # guides cut Jungle Hollow and its kin as tapped lands).
            if (
                unit.origin == "trigger"
                and unit.effects
                and all(c.concept == "gain_life" for c in unit.effects)
            ):
                continue
            return False
    return True


def bounces_or_sacrifices(record: dict) -> bool:
    """A land whose enters trigger returns a land or sacrifices itself (the
    Lairs, Karoo bounce lands) is no mana-base upgrade, untapped or not."""
    for tree in trees_for(dict(record)):
        for unit in tree.units:
            if unit.origin == "trigger" and any(
                c.concept in ("bounce", "sacrifice") for c in unit.effects
            ):
                return True
    return False


def produced(record: Mapping) -> frozenset[str]:
    """The colours of mana the land makes (``produced_mana``, colours only)."""
    return frozenset(c for c in (record.get("produced_mana") or ()) if c in "WUBRG")


_ALL_COLOURS = frozenset("WUBRG")


def _costs_mana(cost: object) -> bool:
    """Whether an activation cost includes mana (a ``Mana`` cost, or a
    ``Composite`` with one: Aysen Abbey's "{1}, {T}: Add {W}")."""
    tag = tag_of(cost)
    if tag == "Mana":
        return True
    if tag == "Composite":
        return any(
            tag_of(part) == "Mana" for part in (getattr(cost, "costs", None) or ())
        )
    return False


def unrestricted_colours(record: dict) -> frozenset[str]:
    """The colours the land makes with a plain ``{T}`` and no strings: no spend
    restriction (Unclaimed Territory's creature type, Plaza of Heroes' legendary
    spells), no activation condition (Spire of Industry's artifact), no mana in
    the activation cost (Three Tree City's {2}). A Guildgate, a pain land, City
    of Brass and Reflecting Pool keep theirs; a land with only strings makes
    none for the mana base's purpose."""
    out: set[str] = set()
    for tree in trees_for(dict(record)):
        for unit in tree.units:
            if unit.origin != "ability":
                continue
            node = unit.node
            if _present(getattr(node, "activation_restrictions", None)):
                continue
            if _costs_mana(getattr(node, "cost", None)):
                continue
            for c in unit.effects:
                if c.concept != "ramp":
                    continue
                if mana_restrictions(c.node) or mana_spell_type_restriction(c.node):
                    continue
                got = produced_colors(c.node)
                out.update(
                    _ALL_COLOURS
                    if got == "any"
                    else (x for x in got if x in _ALL_COLOURS)
                )
    return frozenset(out)


@dataclass(frozen=True)
class LandPlan:
    """What the mana-base pass may do: the cuts in order, each with the
    colours its replacement must keep making."""

    cuts: tuple[tuple[dict, frozenset[str]], ...]
    needed: frozenset[str]


def land_plan(
    land_records: Sequence[dict],
    audit: Mapping,
    *,
    keep: Callable[[dict], bool],
) -> LandPlan:
    """The lands a tune may swap, in order: tapped mana-only lands, then basics
    of an over-supplied colour. ``audit`` is ``mana_audit``'s result (its
    ``pip_demand_pct``, ``land_color_production`` and ``land_count``);
    ``keep(record)`` says a land is on the plan (a need or a main lane counts
    it) and must stay. A land making a colour the deck would otherwise lack
    stays: its replacement must make every colour it made that the deck needs,
    so no cut loses a colour."""
    demand = {c: float(p) for c, p in (audit.get("pip_demand_pct") or {}).items() if p}
    needed = frozenset(demand)
    production: dict[str, int] = dict(audit.get("land_color_production") or {})
    land_count = int(audit.get("land_count") or len(land_records))
    cuts: list[tuple[dict, frozenset[str]]] = []
    seen: set[str] = set()

    def consider(record: dict) -> None:
        name = record.get("name", "")
        if name in seen or keep(record):
            return
        colours = produced(record) & needed
        # A colour this land alone keeps above demand must be replaced, not lost:
        # the swap's add has to make it.
        must = frozenset(
            c
            for c in colours
            if production.get(c, 0) - 1 < demand.get(c, 0.0) * land_count
        )
        seen.add(name)
        cuts.append((record, must))

    for record in land_records:
        if (
            not is_basic_land(record)
            and enters_tapped_unconditionally(record)
            and mana_only(record)
        ):
            consider(record)
    # Surplus basics: the colour over-supplied by the most lands first.
    basics: dict[str, list[dict]] = {}
    for record in land_records:
        colour = _COLOR_FOR_BASIC.get(record.get("name", ""))
        if colour:
            basics.setdefault(colour, []).append(record)
    surplus = sorted(
        ((production.get(c, 0) - demand.get(c, 0.0) * land_count, c) for c in basics),
        reverse=True,
    )
    for excess, colour in surplus:
        if excess < _BASIC_SLACK or (colour not in needed and excess <= 0):
            continue
        spare = int(excess - _BASIC_SLACK) + 1
        for record in basics[colour][:spare]:
            if record.get("name", "") not in seen:
                seen.add(record.get("name", ""))
                cuts.append((record, frozenset()))
    return LandPlan(cuts=tuple(cuts), needed=needed)


def land_candidates(
    pool: Sequence[dict],
    *,
    needed: Collection[str],
    exclude: Collection[str],
) -> list[dict]:
    """The untapped nonbasic lands of ``pool`` (the identity's lands, in the
    search's play-rate order) making at least one needed colour, best first:
    the most needed colours covered, then play-rate, then price."""
    wanted = frozenset(needed)
    out = []
    for card in pool:
        if not is_land(card) or is_basic_land(card) or card.get("name") in exclude:
            continue
        if enters_tapped_unconditionally(card) or bounces_or_sacrifices(card):
            continue
        colours = unrestricted_colours(card) & wanted
        if not colours:
            continue
        # Coverage counts the colours the deck needs; among lands covering as
        # many, the one with the fewest colours beyond them first (a Golgari
        # dual over City of Brass in a Golgari deck: the guides add the pair's
        # dual, not a rainbow land with a drawback), then play-rate, then price.
        coverage = min(len(colours), len(wanted))
        extra = len(unrestricted_colours(card) - wanted)
        out.append(
            (
                -coverage,
                extra,
                edhrec_popularity(card),
                extract_price(card) or 1e9,
                card,
            )
        )
    out.sort(key=lambda t: t[:4])
    return [t[4] for t in out]


def pick_add(
    candidates: Sequence[dict],
    *,
    must: frozenset[str],
    used: Collection[str],
    price_cap: float,
    affordable: Callable[[dict], float | None],
) -> tuple[dict, float] | None:
    """The first candidate making every colour in ``must``, not yet used, whose
    cost the purse allows under ``price_cap``."""
    for card in candidates:
        if card.get("name") in used or not must <= unrestricted_colours(card):
            continue
        cost = affordable(card)
        if cost is None or cost > price_cap:
            continue
        return card, cost
    return None
