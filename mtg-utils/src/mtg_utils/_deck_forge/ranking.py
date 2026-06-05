"""Transparent multi-axis candidate ranking (D6).

Every candidate exposes separate readouts — synergy fit (which signals it serves),
mana efficiency (cmc), and price — rather than one opaque score. EDHREC popularity
is deliberately absent. Default order is synergy fit then price (cheapest first),
with no-listing cards sorted last on the price axis (never treated as free — D7).
"""

from __future__ import annotations

import math

from mtg_utils._deck_forge.budgets import role_of
from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils.card_classify import extract_price


def score_candidate(card: dict, *, active_signals: list) -> dict:
    """Return the multi-axis readout for one candidate against the active signals."""
    served = []
    for signal in active_signals:
        if serves(card, signal):
            spec = spec_for(signal)
            served.append(spec.label if spec else signal.key)
    return {
        "synergy_fit": len(served),
        "served": served,
        "cmc": card.get("cmc", 0.0),
        "price": extract_price(card),
        "roles": sorted(role_of(card)),
    }


def rank_candidates(cards: list[dict], *, active_signals: list) -> list[dict]:
    """Score and sort candidates: synergy desc, then price asc (no-listing last)."""
    scored = [
        {"card": c, "score": score_candidate(c, active_signals=active_signals)}
        for c in cards
    ]
    scored.sort(
        key=lambda r: (
            -r["score"]["synergy_fit"],
            r["score"]["price"] if r["score"]["price"] is not None else math.inf,
            r["score"]["cmc"],
        )
    )
    return scored
