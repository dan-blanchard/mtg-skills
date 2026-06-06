"""Transparent multi-axis candidate ranking (D6).

Every candidate exposes separate readouts — synergy fit (which signals/avenues it
serves), mana efficiency (cmc), and price — rather than one opaque score. EDHREC
popularity is deliberately absent. Default order is synergy fit then price (cheapest
first), with no-listing cards sorted last on the price axis (never treated as free).

Synergy fit counts both the deck's scoped signals AND the active avenues (each
avenue's search-oracle is a matcher), so a card that feeds several lanes outscores
one that feeds a single broad signal — which is what makes the ranking discriminate.
"""

from __future__ import annotations

import math
import re

from mtg_utils._deck_forge.budgets import role_of
from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils.card_classify import extract_price, get_oracle_text


def _avenue_matchers(avenues) -> list[tuple[str, re.Pattern[str] | None, str]]:
    """(label, oracle-regex|None, card_type-substring) per avenue. A card serves an
    avenue only if it satisfies BOTH constraints the avenue's search declares — so an
    avenue scoped to ``card_type='Land'`` won't credit a non-land that merely matches
    the oracle regex (mirrors how the search itself ANDs type + oracle)."""
    out: list[tuple[str, re.Pattern[str] | None, str]] = []
    for avenue in avenues:
        search = avenue.get("search") or {}
        pattern = search.get("oracle")
        card_type = (search.get("card_type") or "").lower()
        regex: re.Pattern[str] | None = None
        if pattern:
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error:
                continue
        if regex is None and not card_type:
            continue
        out.append((avenue.get("label", "avenue"), regex, card_type))
    return out


def score_candidate(card: dict, *, active_signals: list, avenues=()) -> dict:
    """Return the multi-axis readout for one candidate (signals + avenues served)."""
    served: list[str] = []
    for signal in active_signals:
        if serves(card, signal):
            spec = spec_for(signal)
            served.append(spec.label if spec else signal.key)
    oracle = get_oracle_text(card) or ""
    type_line = (card.get("type_line") or "").lower()
    for label, regex, card_type in _avenue_matchers(avenues):
        if regex is not None and not regex.search(oracle):
            continue
        if card_type and card_type not in type_line:
            continue
        served.append(label)
    seen: set[str] = set()
    unique = [s for s in served if not (s in seen or seen.add(s))]
    return {
        "synergy_fit": len(unique),
        "served": unique,
        "cmc": card.get("cmc", 0.0),
        "price": extract_price(card),
        "roles": sorted(role_of(card)),
    }


def rank_candidates(
    cards: list[dict], *, active_signals: list, avenues=()
) -> list[dict]:
    """Score and sort candidates: synergy desc, then price asc (no-listing last)."""
    scored = [
        {
            "card": c,
            "score": score_candidate(c, active_signals=active_signals, avenues=avenues),
        }
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
