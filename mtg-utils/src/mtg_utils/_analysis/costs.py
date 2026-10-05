"""The mana a deck pays to cast a card on curve — its printed mana value, or a cheaper
unconditional alternative cost read off phase's keywords (``ConceptTree.
card_curve_costs``: warp, evoke, dash, blitz, prototype, impending). Suspend and
plot pay now and cast later, so they keep the printed value.

The tuner's curve, shape and efficiency read it: Anticausal Vestige (MV 6, warp {4})
plays as a 4-drop. A card phase hasn't parsed keeps its printed mana value.
"""

from __future__ import annotations

from collections.abc import Mapping

from mtg_utils._card_ir.trees import trees_for


def effective_mana_value(card: Mapping) -> float:
    """The printed mana value, or the cheapest curve alternative cost below it."""
    printed = float(card.get("cmc") or 0)
    costs = [c for tree in trees_for(dict(card)) for c in tree.card_curve_costs]
    return min([printed, *map(float, costs)])
