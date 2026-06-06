"""Every ability is an axis to build around — broad effect-axis detectors so a
commander whose ability is ramp / removal / a team buff / a tutor / etc. surfaces
that direction instead of reading as a value-pile.
"""

from mtg_utils._deck_forge.signals import extract_signals


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


CASES = [
    ("ramp_matters", "you", "{T}: Add {G}{G}."),
    ("removal_matters", "you", "{2}{B}: Destroy target creature."),
    ("counter_control", "you", "{U}: Counter target spell unless its controller pays {2}."),
    ("team_buff", "you", "Each other creature you control has hexproof."),
    ("tutor_matters", "you", "{T}: Search your library for a basic land card, then shuffle."),
    ("untap_engine", "you", "{T}: Untap another target permanent."),
    ("gain_control", "you", "{3}{U}: Gain control of target creature."),
    ("opponent_discard", "opponents", "When this creature enters, each opponent discards a card."),
    ("evasion_self", "you", "This creature can't be blocked."),
    ("clone_matters", "you", "This creature enters the battlefield as a copy of target creature."),
    ("cheat_into_play", "you", "Look at the top five cards of your library. Put a creature card from among them onto the battlefield."),
    ("bounce_tempo", "you", "{1}{U}: Return target creature to its owner's hand."),
    ("cascade_matters", "you", "Cascade"),
    ("regenerate_matters", "you", "{R}: Regenerate this creature."),
]


def test_effect_axis_detectors_fire():
    for key, scope, oracle in CASES:
        sigs = {(s.key, s.scope) for s in extract_signals({"name": "X", "oracle_text": oracle})}
        assert (key, scope) in sigs, f"{key}/{scope} did not fire on: {oracle}"


# --- widens of existing keys ---------------------------------------------------


def test_landfall_widened_for_extra_land_drops():
    c = {"name": "Azusa-like", "oracle_text": "You may play two additional lands on each of your turns."}
    assert any(s.key == "landfall" for s in extract_signals(c))


def test_land_creatures_widened_for_animation():
    c = {
        "name": "Jolrael-like",
        "oracle_text": "{2}{G}: All lands target player controls become 3/3 creatures until end of turn.",
    }
    assert any(s.key == "land_creatures_matter" for s in extract_signals(c))


def test_attack_matters_widened_for_isshin():
    c = {
        "name": "Isshin-like",
        "oracle_text": "If a creature attacking causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
    }
    assert any(s.key == "attack_matters" for s in extract_signals(c))


def test_lifegain_widened_for_activated_gain():
    c = {"name": "Healer", "oracle_text": "{T}: You gain 3 life."}
    assert any(s.key == "lifegain_matters" for s in extract_signals(c))


def test_lifeloss_widened_for_pay_life_engine():
    c = {"name": "Bargainer", "oracle_text": "{B}, Pay 2 life: Draw a card."}
    assert any(s.key == "lifeloss_matters" for s in extract_signals(c))
