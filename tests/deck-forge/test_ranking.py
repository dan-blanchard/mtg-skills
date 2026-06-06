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


def test_avenues_contribute_to_synergy_fit():
    avenues = [
        {"label": "Land creatures", "search": {"oracle": "becomes a .*creature"}}
    ]
    manland = {
        "name": "Manland",
        "type_line": "Land",
        "cmc": 0.0,
        "oracle_text": "Mishra's Factory becomes a 2/2 Assembly-Worker creature.",
        "prices": {"usd": "0.50"},
    }
    score = score_candidate(manland, active_signals=[], avenues=avenues)
    assert score["synergy_fit"] == 1
    assert "Land creatures" in score["served"]


def test_serving_a_signal_and_an_avenue_stacks():
    avenues = [{"label": "Land creatures", "search": {"oracle": "land creature"}}]
    # Serves creature_etb (makes a creature token) AND the land-creature avenue.
    card = {
        "name": "Land Token Maker",
        "type_line": "Sorcery",
        "cmc": 3.0,
        "oracle_text": "Create a 1/1 green land creature token.",
        "prices": {"usd": "1.00"},
    }
    score = score_candidate(card, active_signals=[ETB], avenues=avenues)
    assert score["synergy_fit"] == 2


def test_avenue_card_type_constraint_excludes_wrong_types():
    # A "creature-lands" avenue (type=Land) must not credit a clone that merely
    # says "becomes a ... creature" but isn't a land (the Silent Hallcreeper bug).
    avenues = [
        {
            "label": "Creature-lands",
            "search": {"card_type": "Land", "oracle": "becomes a .*creature"},
        }
    ]
    manland = {
        "name": "Mishra's Factory",
        "type_line": "Land",
        "cmc": 0.0,
        "oracle_text": "This land becomes a 2/2 Assembly-Worker artifact creature.",
        "prices": {"usd": "1"},
    }
    clone = {
        "name": "Silent Hallcreeper",
        "type_line": "Enchantment Creature — Horror",
        "cmc": 5.0,
        "oracle_text": "This creature becomes a copy of another target creature.",
        "prices": {"usd": "1"},
    }
    assert (
        "Creature-lands"
        in score_candidate(manland, active_signals=[], avenues=avenues)["served"]
    )
    assert (
        "Creature-lands"
        not in score_candidate(clone, active_signals=[], avenues=avenues)["served"]
    )


def test_rank_sorts_by_synergy_then_price_with_no_listing_last():
    ranked = rank_candidates(
        [TOKEN_MAKER, DUAL_PURPOSE, NO_LISTING], active_signals=[ETB, LIFE]
    )
    names = [r["card"]["name"] for r in ranked]
    # DUAL_PURPOSE (synergy 2) first; then the two synergy-1 cards by price asc,
    # with the no-listing card last.
    assert names[0] == "Lifegain Tokens"
    assert names.index("Token Maker") < names.index("Rare Token Maker")
