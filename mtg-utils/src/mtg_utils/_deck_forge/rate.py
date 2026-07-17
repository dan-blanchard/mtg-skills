"""Rate — per-card cost-effectiveness percentiles (ADR-0042).

How good a card is AT ITS JOB for its mana: a percentile of effect-per-mana
within the card's peer CLASS, computed over a caller-provided pool (the whole
bulk in production, the committed snapshot in CI). Crowd-independent by
construction — the effect side is read off the card's own concept trees,
never playrate.

v1 classes, in priority order (the first class a card measures in is its
primary job):

* ``tokens`` — creature-token stats per mana: Σ count x (power+toughness)/2
  over ``Token`` effect nodes with Fixed shapes.
* ``damage`` — damage per mana: ``Fixed`` amounts of ``DealDamage`` /
  ``DamageEachPlayer`` / ``DamageAll`` nodes; a your-board ObjectCount amount
  (the damage_for_each shape) prices at ``_NOMINAL_BOARD`` (a mid-game
  go-wide board); ``Variable`` X amounts are skipped (announcement-fixed
  mana, CR 107.3b — an X-spell's rate is its mana sink, not a fixed number).
* ``draw`` — cards per mana: ``Fixed`` ``Draw`` counts.

Cost basis: a SPELL unit prices at the card's mana value; an ACTIVATED
unit prices at its own activation mana (generic + colored shards — the
engine's rate is what one activation buys, the body is sunk). TRIGGER-origin
effects are deliberately unmeasured: a trigger's effect is per-EVENT (Impact
Tremors deals 1 per creature entering, not 1 per cast), so pricing one event
at full mana value under-rates every triggered engine — measured live: the
first cut did exactly that and the C-alone study regressed 6.1% -> 4.3%
recall@100 before this exclusion. Triggered engines rate neutral until a
per-event basis exists. Storm/Replicate double a spell-basis effect (the
copies are the card's whole point; x2 is the deliberately conservative
floor of CR 702.40's one-copy-per-prior-spell scaling).

A card no formula can read has NO class and rates neutral (0.5): Rate never
punishes what it can't measure. The curated ability-quality table (ADR-0040)
is the adjudicated fallback surface for formula-resistant classes — grown
per-adjudication, deliberately not seeded here.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

from mtg_utils._card_ir.crosswalk import (
    filter_controller,
    ref_count_filter,
    tag_of,
)
from mtg_utils._deck_forge._ir_lookup import trees_for

# A mid-game go-wide board: what a your-board-count damage spell (Mob
# Justice) typically reads on the turn it matters.
_NOMINAL_BOARD = 4.0
# Storm / Replicate: the conservative copy floor (one prior spell).
_COPY_KEYWORDS = frozenset({"storm", "replicate"})

_DAMAGE_TAGS = frozenset({"DealDamage", "DamageEachPlayer", "DamageAll"})


@dataclass(frozen=True)
class RateIndex:
    """Sorted per-class effect-per-mana populations (the percentile basis)."""

    classes: dict[str, list[float]] = field(default_factory=dict)


def _fixed(node: object, fld: str) -> float | None:
    v = getattr(node, fld, None)
    if v is None:
        return None
    inner = getattr(v, "value", None)
    return float(inner) if isinstance(inner, (int, float)) else None


def _activation_mana(unit: object) -> float | None:
    """The mana an activation costs (generic + colored shards), or None when
    the unit has no readable Mana cost node."""
    for c in getattr(unit, "costs", ()) or ():
        if tag_of(c.node) != "Mana":
            continue
        cost = getattr(c.node, "cost", None)
        if cost is None:
            continue
        generic = getattr(cost, "generic", 0) or 0
        shards = getattr(cost, "shards", ()) or ()
        return float(generic) + float(len(shards))
    return None


def _damage_amount(node: object) -> float | None:
    amt = _fixed(node, "amount")
    if amt is not None:
        return amt
    filt = ref_count_filter(node, "amount")
    if filt is not None and filter_controller(filt) == "You":
        return _NOMINAL_BOARD
    return None


def effect_metric(card: dict) -> tuple[str, float] | None:
    """(class, effect-per-mana) for the card's primary measurable job, or
    ``None`` when no v1 formula reads it (→ neutral 0.5)."""
    trees = trees_for(card)
    if not trees:
        return None
    mv = max(float(card.get("cmc") or 0.0), 1.0)
    copy_mult = (
        2.0
        if _COPY_KEYWORDS & {k.lower() for k in (card.get("keywords") or ())}
        else 1.0
    )

    # Spell-basis effects sum across SPELL units (one cast resolves them
    # all, priced at mv); each activated unit prices on its own; trigger
    # units are skipped (per-event effects — see the module docstring).
    spell: dict[str, float] = {"tokens": 0.0, "damage": 0.0, "draw": 0.0}
    activated: list[tuple[str, float]] = []
    for tree in trees:
        for unit in tree.units:
            if unit.origin == "trigger":
                continue
            act_cost = _activation_mana(unit) if unit.kind == "Activated" else None
            for c in unit.effects:
                tag = tag_of(c.node)
                if tag == "Token":
                    count = _fixed(c.node, "count")
                    p = _fixed(c.node, "power")
                    t = _fixed(c.node, "toughness")
                    if count is None or p is None or t is None:
                        continue
                    cls, eff = "tokens", count * (p + t) / 2.0
                elif tag in _DAMAGE_TAGS:
                    amt = _damage_amount(c.node)
                    if amt is None:
                        continue
                    cls, eff = "damage", amt
                elif tag == "Draw":
                    count = _fixed(c.node, "count")
                    if count is None:
                        continue
                    cls, eff = "draw", count
                else:
                    continue
                if act_cost is not None:
                    activated.append((cls, eff / max(act_cost, 1.0)))
                else:
                    spell[cls] += eff

    per_class: dict[str, float] = {}
    for cls, total in spell.items():
        if total > 0:
            per_class[cls] = total * copy_mult / mv
    for cls, metric in activated:
        per_class[cls] = max(per_class.get(cls, 0.0), metric)
    for cls in ("tokens", "damage", "draw"):
        if cls in per_class:
            return cls, round(per_class[cls], 4)
    return None


def build_rate_index(records: list[dict]) -> RateIndex:
    """Percentile populations per class over *records* (the whole bulk pool
    in production; any large pool works — percentiles need peers, not a
    specific census)."""
    classes: dict[str, list[float]] = {}
    for rec in records:
        m = effect_metric(rec)
        if m is not None:
            classes.setdefault(m[0], []).append(m[1])
    return RateIndex({cls: sorted(vals) for cls, vals in classes.items()})


def rate_for(card: dict, index: RateIndex | None) -> float:
    """The card's Rate: its effect-per-mana percentile within its class
    (midpoint convention for ties), 0.5 when unmeasured or without an
    index — neutral never re-ranks."""
    if index is None:
        return 0.5
    m = effect_metric(card)
    if m is None:
        return 0.5
    cls, value = m
    population = index.classes.get(cls)
    if not population or len(population) < 5:
        # Too few peers for a meaningful percentile — stay neutral.
        return 0.5
    lo = bisect_left(population, value)
    hi = bisect_right(population, value)
    return round((lo + hi) / 2.0 / len(population), 4)
