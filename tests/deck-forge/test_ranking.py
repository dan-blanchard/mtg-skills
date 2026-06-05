"""Tests for transparent multi-axis candidate ranking (D6)."""

from mtg_utils._deck_forge.ranking import rank_candidates, score_candidate
from mtg_utils._deck_forge.signals import Signal

ETB = Signal("creature_etb", "you", "", "", "cmd")
LIFE = Signal("lifegain_matters", "you", "", "", "cmd")

TOKEN_MAKER = {
    "name": "Token Maker",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "oracle_text": "Create three 1/1 Soldier creature tokens.",
    "prices": {"usd": "0.50"},
}
DUAL_PURPOSE = {
    "name": "Lifegain Tokens",
    "type_line": "Sorcery",
    "cmc": 4.0,
    "oracle_text": "Create two 1/1 creature tokens. You gain 3 life.",
    "prices": {"usd": "2.00"},
}
NO_LISTING = {
    "name": "Rare Token Maker",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "oracle_text": "Create four 1/1 creature tokens.",
    "prices": {},
}


def test_synergy_fit_counts_served_signals():
    score = score_candidate(TOKEN_MAKER, active_signals=[ETB, LIFE])
    assert score["synergy_fit"] == 1
    assert any("Creatures entering" in s for s in score["served"])


def test_dual_purpose_card_serves_two_signals():
    score = score_candidate(DUAL_PURPOSE, active_signals=[ETB, LIFE])
    assert score["synergy_fit"] == 2


def test_score_exposes_price_and_cmc():
    score = score_candidate(TOKEN_MAKER, active_signals=[ETB])
    assert score["cmc"] == 3.0
    assert score["price"] == 0.5
    assert score_candidate(NO_LISTING, active_signals=[ETB])["price"] is None


def test_rank_sorts_by_synergy_then_price_with_no_listing_last():
    ranked = rank_candidates(
        [TOKEN_MAKER, DUAL_PURPOSE, NO_LISTING], active_signals=[ETB, LIFE]
    )
    names = [r["card"]["name"] for r in ranked]
    # DUAL_PURPOSE (synergy 2) first; then the two synergy-1 cards by price asc,
    # with the no-listing card last.
    assert names[0] == "Lifegain Tokens"
    assert names.index("Token Maker") < names.index("Rare Token Maker")
