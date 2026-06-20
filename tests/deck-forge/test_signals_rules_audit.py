"""Fixes from the rules-lawyer category audit — each pins a CR-cited distinction
the detectors must respect (so we don't group mechanics the rules treat differently).
"""

from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._deck_forge.signals import (
    Signal,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face


def _keys(card):
    return {s.key for s in extract_signals(card)}


# A minimal non-None IR for ADR-0027 keys whose IR source reads the Scryfall
# keyword array (any non-None Card routes the hybrid to the IR path).
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _keys_hybrid(card):
    return {s.key for s in extract_signals_hybrid(card, _bare_ir())}


def _signals(card):
    return list(extract_signals(card))


# #1 Companion (CR 702.139) is a separate deck-construction rule from Partner (702.124).
def test_companion_is_its_own_key_not_partner():
    # ADR-0027: companion_keyword is IR-served from the Scryfall `companion`
    # keyword array, so it comes through the hybrid path, not pure regex.
    c = {
        "name": "Lurrus-like",
        "oracle_text": "Companion — Each permanent card in your starting deck has mana value 2 or less.",
        "keywords": ["Companion"],
    }
    k = _keys_hybrid(c)
    assert "companion_keyword" in k
    assert "partner_background" not in k
    assert "companion_keyword" not in _keys(c)


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


# #13 stun (CR 122.1d) and shield (122.1c) counters are replacement-effect counters
# that grant NO keyword ability; "aegis" is not a CR counter at all. None belong on
# keyword_counter, whose premise is the CR 122.1b closed keyword-counter list.
def test_stun_counter_is_not_keyword_counter():
    c = {
        "name": "Sleep-Cursed Faerie",
        "type_line": "Creature — Faerie Wizard",
        "oracle_text": (
            "Flying, ward {2}\n"
            "This creature enters tapped with three stun counters on it. "
            "(If it would become untapped, remove a stun counter from it instead.)\n"
            "{1}{U}: Untap this creature."
        ),
    }
    assert "keyword_counter" not in _keys(c)


def test_shield_counter_is_not_keyword_counter():
    c = {
        "name": "Diamond City",
        "type_line": "Land",
        "oracle_text": (
            "This land enters with a shield counter on it. (If it would be dealt "
            "damage or destroyed, remove a shield counter from it instead.)\n"
            "{T}: Add {C}.\n{T}: Move a shield counter from this land onto target "
            "creature. Activate only if two or more creatures entered the "
            "battlefield under your control this turn."
        ),
    }
    assert "keyword_counter" not in _keys(c)


def test_keyword_counter_still_fires_on_real_keyword():
    # The CR 122.1b members (flying/deathtouch/…) still register.
    c = {"name": "X", "oracle_text": "Put a deathtouch counter on target creature."}
    assert "keyword_counter" in _keys(c)


# #14 all-damage doublers/triplers (Furnace of Rath, Fiery Emancipation) are
# replacement effects that fire on COMBAT damage too — they belong on damage_doubling,
# not the "noncombat damage" lane (CR 510 combat vs 702.19a noncombat).
def test_all_damage_doubler_is_damage_doubling_not_noncombat():
    c = {
        "name": "Furnace of Rath",
        "type_line": "Enchantment",
        "oracle_text": (
            "If a source would deal damage to a permanent or player, it deals "
            "double that damage to that permanent or player instead."
        ),
    }
    k = _keys(c)
    assert "damage_doubling" in k
    assert "noncombat_damage_payoff" not in k


def test_triple_damage_is_damage_doubling():
    c = {
        "name": "Fiery Emancipation",
        "type_line": "Enchantment",
        "oracle_text": (
            "If a source you control would deal damage to a permanent or player, "
            "it deals triple that damage to that permanent or player instead."
        ),
    }
    assert "damage_doubling" in _keys(c)


# MV-scaling burn (Kaervek) is the genuine noncombat payoff and must still open it.
def test_mv_scaling_burn_still_opens_noncombat():
    c = {
        "name": "Kaervek the Merciless",
        "type_line": "Legendary Creature — Human Shaman",
        "oracle_text": (
            "Whenever an opponent casts a spell, Kaervek deals damage equal to "
            "that spell's mana value to any target."
        ),
    }
    assert "noncombat_damage_payoff" in _keys(c)


# #15 Named counters are NOT interchangeable (CR 122.1): each gets its own lane, so a
# rad commander must not open oil/ki/shield, and shield (122.1c, excluded from
# keyword_counter) has its own home. fade is dropped (Fading clock, CR 702.32).
def test_named_counters_are_separate_lanes():
    # ADR-0027: rad_counter_matters migrated to the Card IR — "rad counter(s)" phase
    # mangles, recovered by a `rad_counter` marker, read through the hybrid IR path.
    rad = {"name": "X", "oracle_text": "Each player gets a rad counter."}
    rad_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="rad_counter",
                                scope="opp",
                                raw="rad counter",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "rad_counter_matters" in {s.key for s in extract_signals_hybrid(rad, rad_ir)}
    k = _keys(rad)
    assert "rad_counter_matters" not in k  # regex path no longer produces it
    assert "oil_counter_matters" not in k
    assert "shield_counter_matters" not in k
    assert "named_counter_mechanic" not in k  # the old junk-drawer key is gone

    assert "oil_counter_matters" in _keys(
        {"name": "Y", "oracle_text": "Put two oil counters on it."}
    )
    assert "shield_counter_matters" in _keys(
        {
            "name": "Z",
            "oracle_text": "This creature enters with a shield counter on it.",
        }
    )
    # fade is not a payoff axis — it must not open any named-counter lane
    fade = _keys({"name": "W", "oracle_text": "Remove a fade counter from it."})
    assert not any(k2.endswith("_counter_matters") for k2 in fade)


# #16 End-the-turn (CR 724, your-turn engine) is its own you-scoped lane, split from
# the opponents/any-scoped timing-restriction lane.
def test_end_the_turn_split_from_timing_restriction():
    # ADR-0027: end_the_turn migrated to the Card IR — phase's `end_the_turn` effect
    # category opens it via the hybrid (Obeka); timing_control stays on regex. The
    # split (end_the_turn ≠ the opponents-scoped timing restriction) still holds.
    obeka = {
        "name": "X",
        "oracle_text": "{T}: The player whose turn it is may end the turn.",
    }
    obeka_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="activated",
                        cost="tap",
                        effects=(
                            Effect(
                                category="end_the_turn",
                                scope="any",
                                raw="may end the turn",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    obeka_hybrid = {s.key for s in extract_signals_hybrid(obeka, obeka_ir)}
    assert "end_the_turn" in obeka_hybrid
    assert "timing_control" not in obeka_hybrid

    teferi = {
        "name": "Y",
        "oracle_text": "Each opponent can cast spells only any time they could cast a sorcery.",
    }
    assert "timing_control" in _keys(teferi)
    assert "end_the_turn" not in _keys(teferi)


# #17 Donate = a control change (CR 701.12). A group-hug "target opponent draws/creates"
# card must NOT open the donate lane.
def test_donate_is_control_change_only():
    zedruu = {
        "name": "X",
        "oracle_text": "Target player gains control of target permanent you control.",
    }
    assert "donate_matters" in _keys(zedruu)

    grouphug = {"name": "Y", "oracle_text": "Target opponent draws two cards."}
    assert "donate_matters" not in _keys(grouphug)


# #18 Meld (CR 701.42) is subject-bearing: a meld piece's lane serves ONLY its named
# partner (which references this card by name), never every meld half.
def test_meld_pair_serves_only_its_partner():
    front = {
        "name": "Commander A",
        "oracle_text": (
            "At the beginning of your end step, if you both own and control "
            "Commander A and a creature named Partner B, exile them, then meld "
            "them into Melded C."
        ),
    }
    back = {
        "name": "Partner B",
        "oracle_text": "Flying\n(Melds with Commander A.)",
    }
    unrelated = {"name": "Other Meld", "oracle_text": "(Melds with Someone Else.)"}

    meld_sigs = [s for s in _signals(front) if s.key == "meld_pair"]
    assert meld_sigs, "front meld piece should open meld_pair"
    sig = meld_sigs[0]
    assert sig.subject == "Commander A"  # subject is THIS card's name
    assert serves(back, sig) is True  # the partner names this card
    assert serves(unrelated, sig) is False  # not every meld half

    # The back piece (reminder-only) also opens, keyed to its own name.
    back_sigs = [s for s in _signals(back) if s.key == "meld_pair"]
    assert back_sigs
    assert back_sigs[0].subject == "Partner B"


def test_meld_pair_excluded_from_static_gate():
    # Subject-bearing key with no subject resolves to no static spec (it's gated out).
    assert (
        spec_for(Signal(key="meld_pair", scope="you", subject="", text="", source=""))
        is None
    )


# #19 Flip (CR 710) is a self-contained single-card mechanic, split from meld.
def test_flip_self_fires_and_is_not_meld():
    flip = {"name": "X", "oracle_text": "{T}: Do a thing. Then flip this creature."}
    k = _keys(flip)
    assert "flip_self" in k
    assert "meld_pair" not in k
    assert "flip_meld_matters" not in k  # old fused key is gone
