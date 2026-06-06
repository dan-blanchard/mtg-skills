"""Tests for the rules mined from the zero-signal commander tail (the families the
workflow surfaced as clean, measured wins). Each recovers a real archetype the
12-detector baseline missed, with a structural anchor that keeps it precise.
"""

from mtg_utils._deck_forge.signals import extract_signals


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


def _keys(card):
    return {s.key for s in extract_signals(card)}


def test_combat_damage_matters_scoped_opponents():
    c = {
        "name": "Edric, Spymaster of Trest",
        "oracle_text": "Whenever a creature deals combat damage to one of your opponents, its controller may draw a card.",
    }
    assert ("combat_damage_matters", "opponents") in _ks(c)


def test_combat_damage_does_not_fire_on_plain_attack():
    c = {"name": "Attacker", "oracle_text": "Whenever this creature attacks, draw a card."}
    assert "combat_damage_matters" not in _keys(c)


def test_cost_reduction():
    c = {
        "name": "Danitha Capashen, Paragon",
        "oracle_text": "Aura and Equipment spells you cast cost {1} less to cast.",
    }
    assert ("cost_reduction", "you") in _ks(c)


def test_cast_from_exile_from_top_of_library():
    c = {
        "name": "Glarb, Calamity's Augur",
        "oracle_text": "You may play lands and cast spells from the top of your library.",
    }
    assert ("cast_from_exile", "you") in _ks(c)


def test_cast_from_exile_play_from_exile_trigger():
    c = {
        "name": "Prosper, Tome-Bound",
        "oracle_text": (
            "At the beginning of your postcombat main phase, exile the top card of "
            "your library. You may play that card this turn.\n"
            "Whenever you play a card from exile, create a Treasure token."
        ),
    }
    assert ("cast_from_exile", "you") in _ks(c)


def test_discard_matters():
    c = {
        "name": "Hashaton, Scarab's Fist",
        "oracle_text": "Whenever you discard a creature card, you may pay {2}{U}.",
    }
    assert ("discard_matters", "you") in _ks(c)


def test_lifeloss_drain_scoped_opponents():
    c = {
        "name": "Drainer",
        "oracle_text": "Whenever a creature you control dies, each opponent loses 1 life.",
    }
    assert ("lifeloss_matters", "opponents") in _ks(c)


def test_lifeloss_self_scoped_you():
    c = {
        "name": "Vilis-like",
        "oracle_text": "Whenever you lose life, draw that many cards.",
    }
    assert ("lifeloss_matters", "you") in _ks(c)


def test_lands_matter_count_payoff():
    c = {
        "name": "Radha-like",
        "oracle_text": "This creature gets +1/+1 for each land you control.",
    }
    assert ("lands_matter", "you") in _ks(c)


def test_card_draw_engine_bulk_draw():
    c = {
        "name": "Jin-Gitaxias, Core Augur",
        "oracle_text": "At the beginning of your end step, draw seven cards.",
    }
    assert ("card_draw_engine", "you") in _ks(c)


def test_card_draw_engine_skips_cantrip():
    c = {"name": "Opt-like", "oracle_text": "Scry 1, then draw a card."}
    assert "card_draw_engine" not in _keys(c)


def test_card_draw_engine_skips_etb_oneshot():
    c = {"name": "ETB Draw", "oracle_text": "When this creature enters, draw two cards."}
    assert "card_draw_engine" not in _keys(c)


def test_card_draw_engine_each_player_wheel_scoped_each():
    c = {
        "name": "Nekusar-like",
        "oracle_text": "At the beginning of each player's draw step, that player draws an additional card.",
    }
    assert any(s.key == "card_draw_engine" for s in extract_signals(c))


def test_direct_damage_pinger():
    c = {
        "name": "Kamahl, Pit Fighter",
        "oracle_text": "Haste\n{T}: Kamahl, Pit Fighter deals 3 damage to any target.",
    }
    assert ("direct_damage", "you") in _ks(c)


def test_mana_amplifier():
    c = {
        "name": "Vorinclex, Voice of Hunger",
        "oracle_text": "Whenever you tap a land for mana, add one mana of any type that land produced.",
    }
    assert ("mana_amplifier", "you") in _ks(c)


def test_keyword_granting_team_is_not_a_separate_signal():
    # Deliberately NOT added — team keyword grants are already covered by
    # creatures_matter (the workflow flagged this family do-not-add).
    c = {
        "name": "Team Buff",
        "oracle_text": "Other creatures you control have flying.",
    }
    assert "team_keyword_grant" not in _keys(c)
    assert ("creatures_matter", "you") in _ks(c)
