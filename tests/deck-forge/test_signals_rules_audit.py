"""Fixes from the rules-lawyer category audit — each pins a CR-cited distinction
the detectors must respect (so we don't group mechanics the rules treat differently).
"""

from mtg_utils._deck_forge.signals import extract_signals


def _keys(card):
    return {s.key for s in extract_signals(card)}


# #1 Companion (CR 702.139) is a separate deck-construction rule from Partner (702.124).
def test_companion_is_its_own_key_not_partner():
    c = {
        "name": "Lurrus-like",
        "oracle_text": "Companion — Each permanent card in your starting deck has mana value 2 or less.",
    }
    k = _keys(c)
    assert "companion_keyword" in k
    assert "partner_background" not in k


def test_partner_still_fires():
    c = {"name": "Tymna-like", "oracle_text": "Partner with Thrasios, Triton Hero"}
    assert "partner_background" in _keys(c)


# #2 keyword_counter is the CR 122.1b closed set — ward/training are not counters.
def test_flying_counter_is_keyword_counter():
    c = {
        "name": "X",
        "oracle_text": "This creature enters with a flying counter on it.",
    }
    assert "keyword_counter" in _keys(c)


# #4 exile removal (bypasses indestructible/recursion) is its own slice vs destroy/damage.
def test_exile_removal_separate_from_destroy():
    ex = {"name": "X", "oracle_text": "Exile target creature."}
    de = {"name": "Y", "oracle_text": "Destroy target creature."}
    assert "exile_removal" in _keys(ex)
    assert "removal_matters" not in _keys(ex)
    assert "removal_matters" in _keys(de)
    assert "exile_removal" not in _keys(de)


# #5 clone (becomes/enters as a copy) must not fire on token-copy phrasing.
def test_token_copy_does_not_fire_clone():
    c = {"name": "X", "oracle_text": "Create a token that's a copy of target creature."}
    k = _keys(c)
    assert "token_copy_matters" in k
    assert "clone_matters" not in k


def test_clone_still_fires():
    c = {
        "name": "X",
        "oracle_text": "You may have this creature enter as a copy of any creature.",
    }
    assert "clone_matters" in _keys(c)


# #6 "attacks each combat if able" is a forced-attack requirement, not evasion.
def test_attacks_if_able_is_not_evasion():
    c = {"name": "X", "oracle_text": "This creature attacks each combat if able."}
    assert "evasion_self" not in _keys(c)


def test_cant_be_blocked_is_evasion():
    c = {"name": "X", "oracle_text": "This creature can't be blocked."}
    assert "evasion_self" in _keys(c)


# #7 combat damage to a creature must be COMBAT damage (CR 510 / 120.2a).
def test_noncombat_damage_to_creature_excluded():
    c = {
        "name": "X",
        "oracle_text": "Whenever this creature deals damage to a creature, draw a card.",
    }
    assert "combat_damage_to_creature" not in _keys(c)


def test_combat_damage_to_creature_fires():
    c = {
        "name": "X",
        "oracle_text": "Whenever this creature deals combat damage to a creature, draw a card.",
    }
    assert "combat_damage_to_creature" in _keys(c)


# #8 combat damage to opponents must be COMBAT damage, not any damage (burn/drain).
def test_noncombat_damage_to_opponent_excluded():
    c = {
        "name": "X",
        "oracle_text": "Whenever you cast a spell, this deals damage to an opponent.",
    }
    assert "combat_damage_to_opp" not in _keys(c)


# #12 Food keys on the Food-token mechanic, not the bare word.
def test_food_token_fires():
    assert "food_matters" in _keys({"name": "X", "oracle_text": "Create a Food token."})
    assert "food_matters" in _keys(
        {"name": "Y", "oracle_text": "Sacrifice a Food: Gain 3 life."}
    )
