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
from collections.abc import Callable, Sequence

from mtg_utils._deck_forge.budgets import role_of
from mtg_utils._deck_forge.signal_specs import serve_from_dict, serves, spec_for
from mtg_utils.card_classify import extract_price, get_oracle_text


def _avenue_predicates(
    avenues: Sequence[dict],
) -> list[tuple[str, Callable[[dict], bool]]]:
    """(label, card->bool) per avenue.

    Two classification regimes, matching how each was authored:
      - explicit structured ``serve`` (type/keyword/oracle, e.g. Spellslinger): the
        SAME precise OR-predicate the spec serves on, so the avenue credits a real
        cantrip by TYPE (oracle says only 'draw a card') and a prowess creature by
        KEYWORD.
      - bare ``search`` fragment (legacy): oracle regex AND card_type substring — the
        original behavior, so an avenue scoped to ``card_type='Land'`` won't credit a
        non-land clone that merely matches the oracle regex."""
    out = []
    for avenue in avenues:
        serve_data = avenue.get("serve")
        if serve_data is not None:
            label = avenue.get("label", "avenue")
            out.append((label, serve_from_dict(serve_data).matches))
            continue
        search = avenue.get("search") or {}
        oracle = search.get("oracle")
        card_type = (search.get("card_type") or "").lower()
        if not oracle and not card_type:
            continue
        regex: re.Pattern[str] | None = None
        if oracle:
            try:
                regex = re.compile(oracle, re.IGNORECASE)
            except re.error:
                continue  # an uncompilable avenue regex credits nothing
        out.append((avenue.get("label", "avenue"), _search_and(regex, card_type)))
    return out


def _search_and(
    regex: re.Pattern[str] | None, card_type: str
) -> Callable[[dict], bool]:
    """A card serves the avenue only if it satisfies BOTH the avenue's oracle regex
    and its card_type substring (mirrors how the card_search FIND ANDs them)."""

    def predicate(card: dict) -> bool:
        oracle_ok = (
            regex is None or regex.search(get_oracle_text(card) or "") is not None
        )
        type_line = (card.get("type_line") or "").lower()
        type_ok = not card_type or card_type in type_line
        return oracle_ok and type_ok

    return predicate


def score_candidate(
    card: dict, *, active_signals: list, avenues: Sequence[dict] = ()
) -> dict:
    """Return the multi-axis readout for one candidate (signals + avenues served)."""
    served: list[str] = []
    for signal in active_signals:
        if serves(card, signal):
            spec = spec_for(signal)
            served.append(spec.label if spec else signal.key)
    for label, predicate in _avenue_predicates(avenues):
        if predicate(card):
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
    cards: list[dict], *, active_signals: list, avenues: Sequence[dict] = ()
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
