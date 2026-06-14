"""Tests for the sweep survivors + the named-mechanic long tail.

Rare named mechanics (monarch, energy, the Ring, voting, …) are exactly the novel
build-arounds the tool should surface, and they're precise named anchors so they
stay clean. Each is a real archetype getting its own avenue.
"""

from mtg_utils._deck_forge.signals import extract_signals


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


def _keys(card):
    return {s.key for s in extract_signals(card)}


# (expected_key, expected_scope, oracle text exercising the anchor)
CASES = [
    # sweep survivors
    (
        "voltron_matters",
        "you",
        "Whenever you attach an Equipment to a creature, draw a card.",
    ),
    ("vehicles_matter", "you", "Vehicles you control get +1/+1."),
    (
        "scry_surveil_matters",
        "you",
        "Whenever you scry, put a +1/+1 counter on this creature.",
    ),
    # named mechanics
    ("monarch_matters", "you", "When this creature enters, you become the monarch."),
    (
        "initiative_matters",
        "you",
        "When this creature enters, you take the initiative.",
    ),
    ("ring_matters", "you", "Whenever this creature attacks, the Ring tempts you."),
    ("venture_matters", "you", "When this creature enters, venture into the dungeon."),
    ("energy_matters", "you", "When this creature enters, you get {E}{E}."),
    (
        "devotion_matters",
        "you",
        "Your devotion to green is increased by this creature.",
    ),
    ("superfriends_matters", "you", "Planeswalkers you control have hexproof."),
    ("historic_matters", "you", "Whenever you cast a historic spell, draw a card."),
    ("legends_matter", "you", "Legendary creatures you control get +1/+1."),
    ("big_hand_matters", "you", "You have no maximum hand size."),
    ("party_matters", "you", "Whenever a creature in your party attacks, draw a card."),
    (
        "exile_matters",
        "you",
        "This creature gets +1/+0 for each card you own in exile.",
    ),
    (
        "experience_matters",
        "you",
        "When this creature enters, you get an experience counter.",
    ),
    ("poison_matters", "opponents", "This creature has infect."),
    ("modified_matters", "you", "Modified creatures you control get +1/+1."),
    ("mutate_matters", "you", "Mutate {2}{G}{U}"),
    (
        "food_matters",
        "you",
        "Whenever you sacrifice a Food, each opponent loses 1 life.",
    ),
    ("clue_matters", "you", "Whenever you investigate, draw a card."),
    ("blood_matters", "you", "Whenever you sacrifice a Blood token, draw a card."),
    (
        "daynight_matters",
        "you",
        "Daybound (If a player casts no spells during their own turn...)",
    ),
    ("voting_matters", "each", "Each player votes for an option."),
    ("coven_matters", "you", "Coven — At the beginning of combat, scry 2."),
    (
        "token_doubling",
        "you",
        "If an effect would create tokens, instead it creates twice that many.",
    ),
    (
        "counter_doubling",
        "you",
        "Double the number of each kind of counter on target creature.",
    ),
    (
        "second_spell_matters",
        "you",
        "Whenever you cast your second spell each turn, draw a card.",
    ),
]


def test_named_mechanic_and_survivor_rules_fire():
    for key, scope, oracle in CASES:
        sigs = {
            (s.key, s.scope)
            for s in extract_signals({"name": "X", "oracle_text": oracle})
        }
        assert (key, scope) in sigs, f"{key}/{scope} did not fire on: {oracle}"


def test_vehicles_does_not_fire_on_incidental_or_vehicle_target():
    # "creature or Vehicle you control" (singular) is a counters/combat-trick target,
    # not a vehicles build-around — must NOT fire vehicles_matter.
    c = {
        "name": "Counter Trick",
        "oracle_text": "Put a +1/+1 counter on target creature or Vehicle you control.",
    }
    assert "vehicles_matter" not in _keys(c)


def test_voltron_does_not_fire_on_equipment_payload():
    # The payload on an Equipment itself must not register as a voltron build-around.
    c = {
        "name": "Bear Sword",
        "oracle_text": "Equipped creature gets +2/+2.\nEquip {2}",
    }
    assert "voltron_matters" not in _keys(c)


def test_counters_matter_widened_for_distributors():
    # The old rule needed "for each"/"number of"; a distributor like
    # "+1/+1 counter on each creature you control" (Mikaeus) must now register.
    c = {
        "name": "Mikaeus-like",
        "oracle_text": "At the beginning of your end step, put a +1/+1 counter on each creature you control.",
    }
    assert any(s.key == "counters_matter" for s in extract_signals(c))


def test_poison_scoped_to_opponents():
    c = {
        "name": "Skithiryx-like",
        "oracle_text": "Infect\nThis creature can't be blocked.",
    }
    assert ("poison_matters", "opponents") in _ks(c)


# --- mechanics recovered from the "rejected" families (still-zero commanders) ---


def test_token_copy_engine():
    c = {
        "name": "Orthion-like",
        "oracle_text": "{1}{R}, {T}: Create a token that's a copy of another target creature you control.",
    }
    assert ("token_copy_matters", "you") in _ks(c)


def test_specialize():
    c = {"name": "Shadowheart-like", "oracle_text": "Specialize {1}{B}"}
    assert ("specialize_matters", "you") in _ks(c)


def test_dice_rolling():
    c = {
        "name": "Wyll-like",
        "oracle_text": "Whenever you roll one or more dice, create a Treasure token.",
    }
    assert ("dice_matters", "you") in _ks(c)


def test_commit_a_crime():
    c = {
        "name": "Vadmir-like",
        "oracle_text": "Whenever you commit a crime, put a +1/+1 counter on this creature.",
    }
    assert ("crimes_matter", "you") in _ks(c)


def test_connive_keyword():
    c = {
        "name": "Prowler-like",
        "oracle_text": "Whenever this creature attacks, it connives.",
    }
    assert ("connive_matters", "you") in _ks(c)


def test_prowess_keyword_surfaces_spellslinger():
    c = {"name": "X", "oracle_text": "Prowess", "keywords": ["Prowess"]}
    assert ("spellcast_matters", "you") in _ks(c)


def test_loot_outlet_is_a_discard_avenue():
    c = {"name": "X", "oracle_text": "{T}: Draw a card, then discard a card."}
    assert ("discard_matters", "you") in _ks(c)


def test_spell_copy():
    c = {
        "name": "X",
        "oracle_text": "Copy target instant or sorcery spell you control.",
    }
    assert ("spell_copy_matters", "you") in _ks(c)


def test_kitsa_gets_three_avenues():
    c = {
        "name": "Kitsa, Otterball Elite",
        "oracle_text": (
            "Vigilance\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\n{T}: Draw a card, then discard a card.\n{2}, {T}: Copy target instant or sorcery spell you control. You may choose new targets for the copy. Activate only if Kitsa's power is 3 or greater."
        ),
        "keywords": ["Prowess", "Vigilance"],
    }
    keys = _keys(c)
    assert "spellcast_matters" in keys  # prowess → spellslinger
    assert "discard_matters" in keys  # loot outlet
    assert "spell_copy_matters" in keys  # copy spells


def test_type_matters_catches_another_singular_tribal():
    # Marwyn: "another Elf you control" (singular) was missed by the "other Xs" form.
    c = {
        "name": "Marwyn-like",
        "oracle_text": "Whenever another Elf you control enters, put a +1/+1 counter on this creature.",
    }
    got = {(s.key, s.scope, s.subject) for s in extract_signals(c)}
    assert ("type_matters", "you", "Elf") in got
