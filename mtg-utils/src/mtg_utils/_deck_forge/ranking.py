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
from mtg_utils.card_classify import (
    classifying_type_line,
    extract_price,
    get_oracle_text,
)


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
        # Transform-aware: match card_type against the FRONT face (what you play),
        # so a transform DFC's back-face type can't credit it — e.g. a Saga-front //
        # Land-back card must not satisfy a card_type='Land' creature-land search.
        type_line = classifying_type_line(card).lower()
        type_ok = not card_type or card_type in type_line
        return oracle_ok and type_ok

    return predicate


def _color_widening(card: dict, widening_base: str | None) -> int:
    """Count of NEW colors a candidate second commander adds to the deck's current
    identity (ADR-0019). ``0`` when ``widening_base`` is None — i.e. for every ranking
    that is not the partner avenue, where a card can't change the deck's color identity.
    """
    if widening_base is None:
        return 0
    return len(set(card.get("color_identity") or []) - set(widening_base))


def score_candidate(
    card: dict,
    *,
    active_signals: list,
    avenues: Sequence[dict] = (),
    widening_base: str | None = None,
    _avenue_preds: list[tuple[str, Callable[[dict], bool]]] | None = None,
    _signal_labels: list[str] | None = None,
) -> dict:
    """Return the multi-axis readout for one candidate (signals + avenues served).

    ``widening_base`` (the deck's current color identity) is set ONLY on the partner
    avenue: it adds the ``color_widening`` axis — how many new colors this candidate
    second commander unlocks — which becomes the primary partner sort key (ADR-0019).
    It is ``0`` everywhere else, so non-partner rankings are unchanged.

    ``_avenue_preds`` / ``_signal_labels`` are an internal fast path: avenue
    predicates and per-signal labels are identical across every card in a ranking,
    so ``rank_candidates`` builds them once and threads them in, avoiding a per-card
    regex recompile of every avenue and a redundant ``spec_for`` per signal. When
    omitted (direct callers, tests) they are derived here, so behavior is unchanged.
    """
    served: list[str] = []
    for i, signal in enumerate(active_signals):
        if serves(card, signal):
            if _signal_labels is not None:
                served.append(_signal_labels[i])
            else:
                spec = spec_for(signal)
                served.append(spec.label if spec else signal.key)
    preds = _avenue_preds if _avenue_preds is not None else _avenue_predicates(avenues)
    for label, predicate in preds:
        if predicate(card):
            served.append(label)
    seen: set[str] = set()
    unique = [s for s in served if not (s in seen or seen.add(s))]
    return {
        "synergy_fit": len(unique),
        "served": unique,
        "cmc": card.get("cmc") or 0.0,
        "price": extract_price(card),
        "roles": sorted(role_of(card)),
        "color_widening": _color_widening(card, widening_base),
    }


def rank_candidates(
    cards: list[dict],
    *,
    active_signals: list,
    avenues: Sequence[dict] = (),
    widening_base: str | None = None,
) -> list[dict]:
    """Score and sort candidates: synergy desc, then price asc (no-listing last).

    On the partner avenue (``widening_base`` set to the deck's color identity) the sort
    becomes strict-tiered with **color widening first** — the broadest color-openers
    surface above synergy (ADR-0019). With ``widening_base=None`` every
    ``color_widening`` is 0, so the leading key is constant and the order is identical
    to the legacy (synergy → price → cmc) sort.
    """
    # Avenue predicates and per-signal labels are constant across every candidate,
    # so build them once here instead of per card inside score_candidate.
    avenue_preds = _avenue_predicates(avenues)
    signal_labels: list[str] = []
    for signal in active_signals:
        spec = spec_for(signal)
        signal_labels.append(spec.label if spec else signal.key)
    scored = [
        {
            "card": c,
            "score": score_candidate(
                c,
                active_signals=active_signals,
                avenues=avenues,
                widening_base=widening_base,
                _avenue_preds=avenue_preds,
                _signal_labels=signal_labels,
            ),
        }
        for c in cards
    ]
    scored.sort(
        key=lambda r: (
            -r["score"]["color_widening"],
            -r["score"]["synergy_fit"],
            r["score"]["price"] if r["score"]["price"] is not None else math.inf,
            r["score"]["cmc"],
        )
    )
    return scored
