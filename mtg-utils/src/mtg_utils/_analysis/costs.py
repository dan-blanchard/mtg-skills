"""The mana a deck pays to cast a card on curve — its printed mana value, or a cheaper
unconditional alternative cost read off phase's keywords (``ConceptTree.
card_curve_costs``: warp, evoke, dash, blitz, prototype, impending). Suspend and
plot pay now and cast later, so they keep the printed value.

The tuner's curve, shape and efficiency read it: Anticausal Vestige (MV 6, warp {4})
plays as a 4-drop. A card phase hasn't parsed keeps its printed mana value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mtg_utils._card_ir.trees import trees_for


def effective_mana_value(card: Mapping) -> float:
    """The printed mana value, or the cheapest curve alternative cost below it."""
    printed = float(card.get("cmc") or 0)
    costs = [c for tree in trees_for(dict(card)) for c in tree.card_curve_costs]
    return min([printed, *map(float, costs)])


#: What an X in a mana cost is worth when the cost a card is cast for is
#: estimated: an X spell is cast for value at X ≥ 3 (Martial Coup wants five,
#: Comet Storm three), where its printed mana value counts X as 0 (CR 202.3e).
#: The lane's own call; the tuner's mana-value bands read the same number.
X_COST_VALUE = 3.0

#: The keywords whose share of a spell's cost no fixed number states: convoke
#: (CR 702.51a), delve (702.66a) and improvise (702.126a) let tapped creatures,
#: exiled cards or tapped artifacts pay "rather than pay" that mana; affinity
#: (702.41a) costs {1} less "for each [text] you control"; emerge (702.119a) is
#: an alternative cost, reduced by the sacrificed creature's mana value. Such a
#: card sets no top end and meets no cap (:func:`cast_costs`).
SELF_PAYING_KEYWORDS = frozenset(
    {"Affinity", "Convoke", "Delve", "Emerge", "Improvise"}
)

#: Casting face down for {3} rather than its mana cost: morph (CR 702.37a), its
#: megamorph variant, and disguise (702.168a).
FACE_DOWN_KEYWORDS = frozenset({"Morph", "Megamorph", "Disguise"})
#: What a face-down cast pays (CR 702.37a, 702.168a).
FACE_DOWN_COST = 3.0

#: The opponents an undaunted card counts: "This spell costs {1} less to cast for
#: each opponent you have" (CR 702.125a), in a four-player Commander pod.
POD_OPPONENTS = 3


@dataclass(frozen=True)
class CastCosts:
    """What a card costs on the tuner's curve cap (ADR-0066): ``cheapest``, the
    cheapest mode it can be cast in (None: never capped), and ``top``, the cost
    the deck pays for its big mode when the card stands in the deck (None: left
    out of the deck's top end, as a card whose printed cost nobody pays)."""

    cheapest: float | None
    top: float | None


def _face_cost(mana_cost: str | None) -> float | None:
    from mtg_utils._card_ir.crosswalk.cost_text import mana_value_of_cost

    value = mana_value_of_cost(mana_cost or "")
    if value is None:
        return None
    return value + (X_COST_VALUE if "{X}" in (mana_cost or "") else 0.0)


def cast_costs(
    card: Mapping,
    deck_entries: Sequence[tuple[Mapping, int]] = (),
    *,
    library_size: int = 99,
) -> CastCosts:
    """``card``'s :class:`CastCosts`. Its modes: the printed cost, an X at
    :data:`X_COST_VALUE` (X is 0 off the stack, CR 202.3e); a split card's two
    halves (each half is cast on its own, CR 709.3, though the card's mana value
    combines them, 709.4) and an adventurer card's two ways (716.3: "normally or
    as an Adventure"); a curve alternative cost (the ones
    :func:`effective_mana_value` reads). ``cheapest`` is the least of them and
    ``top`` the printed (big) one, a split card's costlier half. Besides:

    - A modal double-faced card with a land face is never capped — it is never
      stuck in hand, played as that land (CR 712.9) — and sets the top at its
      spell's cost.
    - A face-down card (:data:`FACE_DOWN_KEYWORDS`) is cast for {3} and left out
      of the top; so is a "costs less" clause of its own the ADR-0044 estimator
      cannot price in ``deck_entries`` (checked at its printed cost), while a
      priced one counts at the estimator's affordable turn on both sides.
    - Undaunted counts at printed less :data:`POD_OPPONENTS` on both sides.
    - :data:`SELF_PAYING_KEYWORDS`: neither side.

    The tuner's curve, shape and efficiency reads keep
    :func:`effective_mana_value`."""
    from mtg_utils.commander_cost import (
        STATUS_MODELLED,
        STATUS_NO_IR,
        STATUS_NONE,
        colored_pips,
        effective_commander_cost,
        read_self_discount,
    )

    trees = trees_for(dict(card))
    keywords = {k for tree in trees[:1] for k in tree.card_keywords}
    if SELF_PAYING_KEYWORDS & keywords:
        return CastCosts(None, None)
    faces = card.get("card_faces") or []
    layout = card.get("layout") or ""
    # A multi-face record's own cost joins the faces' ("{5}{B}{B} // {3}{B}"):
    # the front face's is the card's printed one.
    mana_cost = (faces[0].get("mana_cost") if faces else None) or card.get("mana_cost")
    printed = _face_cost(mana_cost)
    if printed is None:
        printed = float(card.get("cmc") or 0.0)
    halves = [
        c
        for f in faces
        if layout in ("split", "aftermath", "adventure")
        and (c := _face_cost(f.get("mana_cost"))) is not None
    ]
    if layout in ("split", "aftermath") and halves:
        printed = max(halves)
    modes = [
        printed,
        *halves,
        *(float(c) for tree in trees for c in tree.card_curve_costs),
    ]
    if "Undaunted" in keywords:
        reduced = max(float(colored_pips(mana_cost)), printed - POD_OPPONENTS)
        return CastCosts(min([reduced, *modes[1:]]), reduced)
    if layout == "modal_dfc" and any(
        "Land" in (f.get("type_line") or "") for f in faces[1:]
    ):
        return CastCosts(None, printed)
    if FACE_DOWN_KEYWORDS & keywords:
        return CastCosts(min([FACE_DOWN_COST, *modes]), None)
    discount = read_self_discount(card)
    if discount not in (STATUS_NONE, STATUS_NO_IR):
        block = (
            effective_commander_cost(card, deck_entries, library_size=library_size)
            if deck_entries
            else None
        )
        if block is None or block["status"] != STATUS_MODELLED:
            return CastCosts(min(modes), None)
        priced = float(block["effective"])
        return CastCosts(min([priced, *modes]), priced)
    return CastCosts(min(modes), printed)
