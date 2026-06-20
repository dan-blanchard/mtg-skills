"""Tests for the sweep survivors + the named-mechanic long tail.

Rare named mechanics (monarch, energy, the Ring, voting, …) are exactly the novel
build-arounds the tool should surface, and they're precise named anchors so they
stay clean. Each is a real archetype getting its own avenue.
"""

from mtg_utils._deck_forge.signals import extract_signals, extract_signals_hybrid
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Trigger


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


# A minimal non-None IR: keyword-array lanes (e.g. specialize) read card["keywords"]
# directly, not the IR structure, so any non-None Card routes the hybrid to the IR
# path for the migrated key.
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _ks_hybrid(card):
    return {(s.key, s.scope) for s in extract_signals_hybrid(card, _bare_ir())}


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
    # ADR-0027: scry_surveil_matters migrated to the Card IR (the scried/surveiled
    # trigger events + the event='other' scry/surveil payoff marker), so it is
    # asserted via the hybrid path below, not this regex CASES loop.
    # named mechanics
    # ADR-0027: monarch_matters migrated to the Card IR (structural monarch effect
    # + ismonarch condition), so it is asserted via the hybrid path below, not this
    # regex CASES loop.
    (
        "initiative_matters",
        "you",
        "When this creature enters, you take the initiative.",
    ),
    # ADR-0027: ring_matters migrated to the Card IR (structural ring_tempt effect,
    # incl. the event='other' tempt trigger + the Ring-bearer raw-scan), so it is
    # asserted via the hybrid path below, not this regex CASES loop.
    # ADR-0027: venture_matters + energy_matters migrated to the Card IR (the venture/
    # energy effect categories + supplement markers), so they are proven via the hybrid
    # path in test_migrated_keys, not this regex CASES loop.
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
    # ADR-0027: experience_matters / mutate_matters migrated to the Card IR (the
    # GivePlayerCounter experience gainer + experience scaler operand; the mutate
    # keyword + "if it has mutate" payoff marker), so they are asserted via the
    # hybrid path below, not this regex CASES loop.
    ("poison_matters", "opponents", "This creature has infect."),
    ("modified_matters", "you", "Modified creatures you control get +1/+1."),
    (
        "food_matters",
        "you",
        "Whenever you sacrifice a Food, each opponent loses 1 life.",
    ),
    ("clue_matters", "you", "Whenever you investigate, draw a card."),
    # ADR-0027: blood_matters migrated to the Card IR (the token-subtype synergy
    # widening reads sacrifice subjects), so it is asserted via the hybrid path
    # below, not this regex CASES loop.
    (
        "daynight_matters",
        "you",
        "Daybound (If a player casts no spells during their own turn...)",
    ),
    # ADR-0027: coven_matters / voting_matters / token_doubling / blood_matters
    # migrated to the Card IR, so they are asserted via the hybrid path below, not
    # this regex CASES loop.
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


def test_coven_matters_is_ir_served():
    # ADR-0027: coven_matters is IR-served from the kept word-detector mirror
    # (\bcoven\b), so it comes through the hybrid path, not pure regex.
    c = {"name": "X", "oracle_text": "Coven — At the beginning of combat, scry 2."}
    assert ("coven_matters", "you") in _ks_hybrid(c)
    assert ("coven_matters", "you") not in _ks(c)


def test_voting_matters_is_ir_served():
    # ADR-0027: voting_matters is IR-served from the kept word-detector mirror, so
    # it comes through the hybrid path, not pure regex.
    c = {"name": "X", "oracle_text": "Each player votes for an option."}
    assert ("voting_matters", "each") in _ks_hybrid(c)
    assert ("voting_matters", "each") not in _ks(c)


def test_token_doubling_is_ir_served():
    # ADR-0027: token_doubling is IR-served from the structural token-doubling
    # replacement effect, so it needs the matching IR (a bare mirror won't fire it).
    c = {
        "name": "X",
        "oracle_text": (
            "If an effect would create tokens, instead it creates twice that many."
        ),
    }
    ir = Card(
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
                                category="token_doubling",
                                scope="you",
                                raw="creates twice that many tokens",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("token_doubling", "you") in hybrid
    assert ("token_doubling", "you") not in _ks(c)


def test_blood_matters_is_ir_served():
    # ADR-0027: blood_matters is IR-served — the token-subtype synergy widening reads
    # a `sacrificed` Trigger (or `sacrifice` Effect) whose subject Filter carries the
    # Blood subtype, so a Blood sacrifice PAYOFF fires it via the hybrid path, not the
    # deleted "blood tokens?" floor regex.
    c = {
        "name": "X",
        "oracle_text": "Whenever you sacrifice a Blood token, draw a card.",
    }
    ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(
                            event="sacrificed",
                            scope="you",
                            subject=Filter(
                                subtypes=("Blood",),
                                controller="you",
                                predicates=("Token",),
                            ),
                        ),
                        effects=(
                            Effect(category="draw", scope="you", raw="draw a card"),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("blood_matters", "you") in hybrid
    assert ("blood_matters", "you") not in _ks(c)


def test_monarch_matters_is_ir_served():
    # ADR-0027: monarch_matters is IR-served — from phase's `monarch` effect
    # category (a "you become the monarch" grant narrowed into the `monarch` marker)
    # AND the Condition(ismonarch) gate. Two structural shapes, both via the hybrid.
    from mtg_utils.card_ir import Condition

    grant = {"name": "X", "oracle_text": "When this enters, you become the monarch."}
    grant_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="monarch",
                                scope="you",
                                raw="you become the monarch",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(grant, grant_ir)}
    assert ("monarch_matters", "you") in hybrid
    assert ("monarch_matters", "you") not in _ks(grant)

    # The condition-gated payoff (Throne Warden: "if you're the monarch, …").
    gated = {
        "name": "Throne Warden",
        "type_line": "Creature — Human Soldier",
        "oracle_text": (
            "At the beginning of your end step, if you're the monarch, put a "
            "+1/+1 counter on this creature."
        ),
    }
    gated_ir = Card(
        oracle_id="y",
        name="Throne Warden",
        faces=(
            Face(
                name="Throne Warden",
                abilities=(
                    Ability(
                        kind="triggered",
                        condition=Condition(kind="ismonarch"),
                        effects=(
                            Effect(
                                category="place_counter",
                                counter_kind="p1p1",
                                raw="put a +1/+1 counter on ~",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    gated_hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(gated, gated_ir)}
    assert ("monarch_matters", "you") in gated_hybrid
    assert ("monarch_matters", "you") not in _ks(gated)


def test_saddle_matters_is_ir_served():
    # ADR-0027: saddle_matters is IR-served — from phase's `saddle` effect category
    # (a "becomes saddled" grant narrowed into the `saddle` marker), via the hybrid.
    c = {
        "name": "Guidelight Matrix",
        "type_line": "Artifact",
        "oracle_text": (
            "When this artifact enters, draw a card.\n{2}, {T}: Target Mount you "
            "control becomes saddled until end of turn. Activate only as a sorcery."
        ),
    }
    ir = Card(
        oracle_id="x",
        name="Guidelight Matrix",
        faces=(
            Face(
                name="Guidelight Matrix",
                abilities=(
                    Ability(
                        kind="activated",
                        cost="mana,tap",
                        effects=(
                            Effect(
                                category="saddle",
                                scope="you",
                                raw="Target Mount you control becomes saddled",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("saddle_matters", "you") in hybrid
    assert ("saddle_matters", "you") not in _ks(c)


def test_soulbond_matters_is_ir_served():
    # ADR-0027: soulbond_matters is IR-served — from the Scryfall `soulbond` keyword
    # AND a `soulbond` effect marker for non-keyword references ("paired with a
    # creature with soulbond" — Flowering Lumberknot), via the hybrid.
    c = {
        "name": "Flowering Lumberknot",
        "type_line": "Creature — Plant",
        "oracle_text": (
            "This creature can't attack or block unless it's paired with a "
            "creature with soulbond."
        ),
    }
    ir = Card(
        oracle_id="x",
        name="Flowering Lumberknot",
        faces=(
            Face(
                name="Flowering Lumberknot",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="soulbond",
                                scope="you",
                                raw="paired with a creature with soulbond",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("soulbond_matters", "you") in hybrid
    assert ("soulbond_matters", "you") not in _ks(c)


def _triggered_other(category: str, raw: str) -> Card:
    # The shape project._narrow_trigger_other_refs produces: a triggered ability
    # phase flattened to event="other", with the precise marker effect appended.
    return Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="other"),
                        effects=(Effect(category=category, scope="you", raw=raw),),
                    ),
                ),
            ),
        ),
    )


def test_coin_flip_is_ir_served():
    # ADR-0027: coin_flip is IR-served — the "Whenever you win/lose a coin flip"
    # PAYOFF trigger phase flattened to event="other" is appended as a coin_flip
    # marker effect (read via _DOER_EFFECT_KEYS), via the hybrid.
    c = {
        "name": "Chance Encounter",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever you win a coin flip, put a luck counter on this enchantment."
        ),
    }
    ir = _triggered_other(
        "coin_flip", "Whenever you win a coin flip, put a luck counter on ~."
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("coin_flip", "you") in hybrid
    assert ("coin_flip", "you") not in _ks(c)


def test_discover_matters_is_ir_served():
    # ADR-0027: discover_matters is IR-served — the keyword-less re-trigger payoff
    # ("Whenever you discover, discover again" — Curator) is a trigger phase
    # flattened to event="other", appended as a discover marker effect, via hybrid.
    c = {
        "name": "Curator of Sun's Creation",
        "type_line": "Creature — Human Artificer",
        "oracle_text": (
            "Whenever you discover, discover again for the same value. This ability "
            "triggers only once each turn."
        ),
    }
    ir = _triggered_other(
        "discover", "Whenever you discover, discover again for the same value."
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("discover_matters", "you") in hybrid
    assert ("discover_matters", "you") not in _ks(c)


def test_ninjutsu_matters_is_ir_served():
    # ADR-0027: ninjutsu_matters is IR-served — the keyword-less payoff commander
    # (Satoru: "Whenever you activate a ninjutsu ability") is a trigger phase
    # flattened to event="other", appended as a ninjutsu marker effect, via hybrid.
    c = {
        "name": "Satoru Umezawa",
        "type_line": "Legendary Creature — Human Ninja",
        "oracle_text": (
            "Whenever you activate a ninjutsu ability, look at the top three cards "
            "of your library."
        ),
    }
    ir = _triggered_other(
        "ninjutsu",
        "Whenever you activate a ninjutsu ability, look at the top three cards.",
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("ninjutsu_matters", "you") in hybrid
    assert ("ninjutsu_matters", "you") not in _ks(c)


def test_ring_matters_is_ir_served():
    # ADR-0027: ring_matters is IR-served — a "Whenever the Ring tempts you" trigger
    # phase flattened to event="other" AND a "Ring-bearer" reference buried in any
    # effect raw (Sauron, no tempt trigger) are appended as ring_tempt marker
    # effects (read via _DOER_EFFECT_KEYS). Both structural shapes, via the hybrid.
    c = {
        "name": "Faramir, Field Commander",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "Whenever the Ring tempts you, if you chose a creature other than "
            "Faramir, Field Commander as your Ring-bearer, create a 1/1 white Human "
            "Soldier creature token."
        ),
    }
    ir = _triggered_other(
        "ring_tempt",
        "Whenever the Ring tempts you, if you chose a creature other than ~ as your "
        "Ring-bearer, create a token.",
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("ring_matters", "you") in hybrid
    assert ("ring_matters", "you") not in _ks(c)


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
    # ADR-0027: specialize_matters is IR-served (the Scryfall `specialize`
    # keyword), so it comes through the hybrid path, not pure regex.
    c = {
        "name": "Shadowheart-like",
        "oracle_text": "Specialize {1}{B}",
        "keywords": ["Specialize"],
    }
    assert ("specialize_matters", "you") in _ks_hybrid(c)
    # And the legacy regex path no longer emits it.
    assert ("specialize_matters", "you") not in _ks(c)


def test_dice_rolling():
    c = {
        "name": "Wyll-like",
        "oracle_text": "Whenever you roll one or more dice, create a Treasure token.",
    }
    assert ("dice_matters", "you") in _ks(c)


def test_commit_a_crime():
    # ADR-0027: crimes_matter migrated to the Card IR — the "Whenever you commit a
    # crime" TRIGGER form binds via phase's commit_crime trigger event (the condition
    # form rides a `crime` marker), read through the hybrid IR path, not the regex.
    c = {
        "name": "Vadmir-like",
        "oracle_text": (
            "Whenever you commit a crime, put a +1/+1 counter on this creature."
        ),
    }
    ir = Card(
        oracle_id="x",
        name="Vadmir-like",
        faces=(
            Face(
                name="Vadmir-like",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="commit_crime", scope="you"),
                        effects=(
                            Effect(
                                category="place_counter",
                                scope="you",
                                counter_kind="p1p1",
                                raw="put a +1/+1 counter on this creature",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("crimes_matter", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }
    assert ("crimes_matter", "you") not in _ks(c)


def test_connive_keyword():
    # ADR-0027: connive_matters migrated to the Card IR — phase's `connive` effect
    # category (a self-conniving card) opens the lane via _DOER_EFFECT_KEYS, so it
    # comes through the hybrid path, not the deleted regex.
    c = {
        "name": "Prowler-like",
        "oracle_text": "Whenever this creature attacks, it connives.",
    }
    ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(category="connive", scope="you", raw="it connives"),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("connive_matters", "you") in hybrid
    assert ("connive_matters", "you") not in _ks(c)


def _one_ability_ir(ability):
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=(ability,)),))


def test_scry_surveil_is_ir_served():
    # ADR-0027: scry_surveil_matters migrated to the Card IR — phase's `scry_surveil`
    # effect category (the event='other' scry/surveil payoff) opens it via the hybrid.
    c = {
        "name": "X",
        "oracle_text": "Whenever you scry, put a +1/+1 counter on this creature.",
    }
    ir = _one_ability_ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="other"),
            effects=(
                Effect(category="scry_surveil", scope="you", raw="whenever you scry"),
            ),
        )
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("scry_surveil_matters", "you") in hybrid
    assert ("scry_surveil_matters", "you") not in _ks(c)


def test_experience_is_ir_served():
    # ADR-0027: experience_matters migrated to the Card IR — the GivePlayerCounter
    # experience GAINER (phase's experience_counter effect category) opens it.
    c = {
        "name": "X",
        "oracle_text": "When this creature enters, you get an experience counter.",
    }
    ir = _one_ability_ir(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="experience_counter",
                    scope="you",
                    raw="you get an experience counter",
                ),
            ),
        )
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("experience_matters", "you") in hybrid
    assert ("experience_matters", "you") not in _ks(c)


def test_mutate_is_ir_served():
    # ADR-0027: mutate_matters migrated to the Card IR — the Scryfall mutate keyword
    # opens it via _IR_KEYWORD_MAP (a mutate creature carries the keyword).
    c = {
        "name": "X",
        "oracle_text": "Mutate {2}{G}{U}",
        "keywords": ["Mutate"],
    }
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, _ks_bare_ir())}
    assert ("mutate_matters", "you") in hybrid
    assert ("mutate_matters", "you") not in _ks(c)


def _ks_bare_ir():
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


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
