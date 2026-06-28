"""Tests for the sweep survivors + the named-mechanic long tail.

Rare named mechanics (monarch, energy, the Ring, voting, …) are exactly the novel
build-arounds the tool should surface, and they're precise named anchors so they
stay clean. Each is a real archetype getting its own avenue.
"""

from mtg_utils._deck_forge.signals import extract_signals, extract_signals_hybrid
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Trigger
from mtg_utils.testkit import test_card, test_signals


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


def _real(name):
    """(key, scope) set over the REAL Scryfall record + REAL projected IR (snapshot)."""
    return {(s.key, s.scope) for s in test_signals(name)}


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
    # ADR-0027: voltron_matters migrated to the Card IR (the LAST key — its regex
    # producers are deleted). The Equipment/Aura PAYOFF tell routes through the IR path,
    # so it is asserted via the hybrid path below (test_voltron_payoff_is_ir_served).
    # ADR-0027: vehicles_matter migrated to the Card IR (the byte-identical
    # VEHICLES_MATTER_MIRROR kept word mirror — the "Vehicles you control" anthem / crew
    # payoff / Vehicle-GRANTER lane — plus the per-clause Greasefang typed-gy Vehicle
    # arm), so it is asserted via the hybrid path below, not this regex CASES loop.
    # ADR-0027: scry_surveil_matters migrated to the Card IR (the scried/surveiled
    # trigger events + the event='other' scry/surveil payoff marker), so it is
    # asserted via the hybrid path below, not this regex CASES loop.
    # named mechanics
    # ADR-0027: monarch_matters migrated to the Card IR (structural monarch effect
    # + ismonarch condition), so it is asserted via the hybrid path below, not this
    # regex CASES loop.
    # ADR-0027: initiative_matters migrated to the Card IR (the \bthe initiative\b
    # _IR_KEPT_DETECTORS word mirror), so it is asserted via the hybrid path below,
    # not this regex CASES loop.
    # ADR-0027: ring_matters migrated to the Card IR (structural ring_tempt effect,
    # incl. the event='other' tempt trigger + the Ring-bearer raw-scan), so it is
    # asserted via the hybrid path below, not this regex CASES loop.
    # ADR-0027: venture_matters + energy_matters migrated to the Card IR (the venture/
    # energy effect categories + supplement markers), so they are proven via the hybrid
    # path in test_migrated_keys, not this regex CASES loop.
    # ADR-0027: devotion_matters / historic_matters / party_matters migrated to the
    # Card IR (the amount.op count operands + "devotion to <color>" / "\bhistoric\b" /
    # "creatures in your party" _IR_KEPT_DETECTORS word mirrors), so they are asserted
    # via the hybrid path below, not this regex CASES loop.
    # ADR-0027: superfriends_matters migrated to the Card IR (the byte-identical
    # SUPERFRIENDS_MATTERS_REGEX kept word mirror for the "planeswalkers you control" /
    # "loyalty counter" / "activate a loyalty ability" / "abilities of a planeswalker"
    # refs + a structural "control a <Name> planeswalker" Condition arm), so it is
    # asserted via the hybrid path below, not this regex CASES loop.
    # ADR-0027: legends_matter migrated to the Card IR (the HasSupertype:Legendary
    # subject predicate + a kept word mirror), so it is asserted via the hybrid path
    # below, not this regex CASES loop.
    # ADR-0027: big_hand_matters migrated to the Card IR (the v23 `no_max_handsize`
    # Effect structural arm + a byte-identical _BIG_HAND_MATTERS_MIRROR kept word mirror
    # for the "X = cards in your hand" P/T payoffs), so it is asserted via the hybrid
    # path below, not this regex CASES loop.
    # ADR-0027: exile_matters migrated to the Card IR (the byte-identical
    # EXILE_MATTERS_REGEX kept word mirror for the "cards you own in exile" / "for each
    # card ... in exile" exile-zone-as-resource refs phase scatters across count
    # operands / conditions), so it is asserted via the hybrid path below, not this
    # regex CASES loop.
    # ADR-0027: experience_matters / has_mutate migrated to the Card IR (the
    # GivePlayerCounter experience gainer + experience scaler operand; the mutate
    # keyword + "if it has mutate" payoff marker), so they are asserted via the
    # hybrid path below, not this regex CASES loop.
    # ADR-0027: poison_matters migrated to the Card IR (the infect/toxic/poisonous
    # Scryfall keywords + a kept word mirror for the granters/references), so it is
    # asserted via the hybrid path below, not this regex CASES loop.
    # ADR-0027: modified_matters migrated to the Card IR (the UNION kept WORD MIRROR —
    # `\bmodified\b` OR "power greater than its base power" — for the Neon Dynasty
    # "modified" archetype phase doesn't structure, CR 700.9), so it is asserted via the
    # hybrid path below, not this regex CASES loop.
    # ADR-0027: food_matters / treasure_matters / clue_matters migrated to the Card IR
    # (the token-subtype synergy widening reads make_token / sacrifice subjects; clue_
    # matters additionally rides a byte-identical \bclue\b|\binvestigate\b kept WORD
    # MIRROR for the keyword-only investigate cards phase folds into a subject=None
    # make_token), so they are asserted via the hybrid path in test_migrated_keys, not
    # this regex CASES loop.
    # ADR-0027: blood_matters migrated to the Card IR (the token-subtype synergy
    # widening reads sacrifice subjects), so it is asserted via the hybrid path
    # below, not this regex CASES loop.
    # ADR-0027: daynight_matters migrated to the Card IR (TWO structural arms — the
    # daybound/nightbound Scryfall KEYWORD via _IR_KEYWORD_MAP + the `day_night`
    # effect-category doer via _DOER_EFFECT_KEYS for the "it becomes day/night"
    # transition payoff), so it is asserted via the hybrid path below, not this regex
    # CASES loop.
    # ADR-0027: coven_matters / voting_matters / token_doubling / blood_matters /
    # counter_doubling migrated to the Card IR, so they are asserted via the hybrid path
    # below, not this regex CASES loop. (counter_doubling rides the byte-identical
    # COUNTER_DOUBLING_REGEX kept mirror in _signals_ir for the one-shot doublers phase
    # mangles — see test_counter_doubling_is_ir_served.)
    # ADR-0027: second_spell_matters migrated to the Card IR (a byte-identical
    # _SECOND_SPELL_MIRROR in _IR_KEPT_DETECTORS for the "second spell each turn"
    # payoff phase under-structures — a bare cast_spell trigger drops the qualifier),
    # so it is asserted via the hybrid path below, not this regex CASES loop.
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


def test_vehicles_matter_is_ir_served():
    # ADR-0027: vehicles_matter is IR-served from the byte-identical
    # VEHICLES_MATTER_MIRROR kept word mirror (the "Vehicles you control" anthem
    # branch), so it comes through the hybrid path, not pure regex.
    c = {"name": "X", "oracle_text": "Vehicles you control get +1/+1."}
    assert ("vehicles_matter", "you") in _ks_hybrid(c)
    assert ("vehicles_matter", "you") not in _ks(c)


def test_vehicles_matter_greasefang_arm_is_ir_served():
    # ADR-0027: the typed-graveyard-recursion Vehicle arm (Greasefang) — which the broad
    # kept mirror never anchored — is re-supplied PER-CLAUSE in extract_signals_ir, so it
    # too comes through the hybrid path, not pure regex.
    # Real Greasefang, Okiba Boss (snapshot): the typed-graveyard-recursion Vehicle arm
    # is re-supplied per-clause, so it comes through the IR path, not pure regex.
    assert ("vehicles_matter", "you") in _real("Greasefang, Okiba Boss")
    assert ("vehicles_matter", "you") not in _ks(test_card("Greasefang, Okiba Boss"))


def test_superfriends_matters_is_ir_served():
    # ADR-0027: superfriends_matters is IR-served from the byte-identical
    # SUPERFRIENDS_MATTERS_REGEX kept word mirror (the "planeswalkers you control"
    # anthem branch), so it comes through the hybrid path, not pure regex.
    c = {"name": "X", "oracle_text": "Planeswalkers you control have hexproof."}
    assert ("superfriends_matters", "you") in _ks_hybrid(c)
    assert ("superfriends_matters", "you") not in _ks(c)


def test_counter_doubling_is_ir_served():
    # ADR-0027: counter_doubling is IR-served. The one-shot "Double the number of …
    # counters" form (Vorel, Gilder Bairn, Kalonian Hydra) is what phase v0.1.19
    # mangles to a generic `double`/`place_counter`, so it rides the byte-identical
    # COUNTER_DOUBLING_REGEX kept word mirror in _signals_ir — through the hybrid path,
    # not pure regex.
    c = {
        "name": "X",
        "oracle_text": "Double the number of each kind of counter on target creature.",
    }
    assert ("counter_doubling", "you") in _ks_hybrid(c)
    assert ("counter_doubling", "you") not in _ks(c)


def test_modified_matters_word_arm_is_ir_served():
    # ADR-0027: modified_matters arm 1 — the direct `\bmodified\b` word of the UNION
    # kept WORD MIRROR (the Neon Dynasty "modified" archetype, CR 700.9: a permanent is
    # modified if it has a counter, is equipped, or is enchanted by an Aura its
    # controller controls). phase doesn't structure "modified", so it comes through the
    # hybrid path, not pure regex. scope "you".
    c = {"name": "X", "oracle_text": "Modified creatures you control get +1/+1."}
    assert ("modified_matters", "you") in _ks_hybrid(c)
    assert ("modified_matters", "you") not in _ks(c)


def test_modified_matters_base_power_arm_is_ir_served():
    # ADR-0027: modified_matters arm 2 — the indirect "power greater than its base
    # power" anchor of the UNION kept WORD MIRROR (Kutzil, Baird: the only way a
    # creature's power exceeds its BASE power is a counter or a pump, CR 613.4c layer
    # 7c — the modified-via-counter/Aura/Equip side). Comes through the hybrid path,
    # not pure regex. scope "you".
    c = {
        "name": "X",
        "oracle_text": (
            "Whenever a creature you control with power greater than its base "
            "power enters, draw a card."
        ),
    }
    assert ("modified_matters", "you") in _ks_hybrid(c)
    assert ("modified_matters", "you") not in _ks(c)


def test_second_spell_matters_is_ir_served():
    # ADR-0027: second_spell_matters is IR-served from the byte-identical
    # _SECOND_SPELL_MIRROR kept word detector (the "second spell each turn" payoff
    # phase under-structures), so it comes through the hybrid path, not pure regex.
    c = {
        "name": "X",
        "oracle_text": "Whenever you cast your second spell each turn, draw a card.",
    }
    assert ("second_spell_matters", "you") in _ks_hybrid(c)
    assert ("second_spell_matters", "you") not in _ks(c)


def test_daynight_matters_keyword_arm_is_ir_served():
    # ADR-0027: daynight_matters arm 1 — the daybound/nightbound Scryfall KEYWORD via
    # _IR_KEYWORD_MAP (read off the record dict's `keywords` array, so a bare IR routes
    # the hybrid to the IR path). A plain daybound werewolf with no transition payoff
    # fires keyword-only. scope "you". CR 726.
    c = {
        "name": "X",
        "type_line": "Creature — Human Werewolf",
        "oracle_text": "Daybound",
        "keywords": ["Daybound"],
    }
    assert ("daynight_matters", "you") in _ks_hybrid(c)
    assert ("daynight_matters", "you") not in _ks(c)


def test_daynight_matters_effect_arm_is_ir_served():
    # ADR-0027: daynight_matters arm 2 — the `day_night` EFFECT-category doer via
    # _DOER_EFFECT_KEYS (the "it becomes day/night" / "as long as it's day/night"
    # transition payoff phase structures cleanly). A keyword-LESS payoff (The Celestus,
    # Brimstone Vandal, Vadrik) fires this arm. scope "you". CR 726.
    c = {
        "name": "X",
        "type_line": "Artifact",
        "oracle_text": "When this artifact enters, it becomes day.",
    }
    ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="spell",
                        effects=(Effect(category="day_night", scope="any"),),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("daynight_matters", "you") in hybrid
    assert ("daynight_matters", "you") not in _ks(c)


def test_voting_matters_is_ir_served():
    # ADR-0027: voting_matters is IR-served from the kept word-detector mirror, so
    # it comes through the hybrid path, not pure regex.
    c = {"name": "X", "oracle_text": "Each player votes for an option."}
    assert ("voting_matters", "each") in _ks_hybrid(c)
    assert ("voting_matters", "each") not in _ks(c)


def test_initiative_matters_is_ir_served():
    # ADR-0027: initiative_matters is IR-served from the \bthe initiative\b kept
    # word-detector mirror, so it comes through the hybrid path, not pure regex.
    c = {
        "name": "X",
        "oracle_text": "When this creature enters, you take the initiative.",
    }
    assert ("initiative_matters", "you") in _ks_hybrid(c)
    assert ("initiative_matters", "you") not in _ks(c)


def test_devotion_historic_party_are_ir_served():
    # ADR-0027 #24b: devotion_matters now reads STRUCTURE — the op=='devotion' operand
    # the supplement re-supplies for the ramp/pump devotion-scalers phase collapses to
    # op=='variable' / drops (Karametra's Acolyte "Add {G} equal to your devotion to
    # green"). Asserted over the real projected IR via ``test_signals``.
    assert ("devotion_matters", "you") in _real("Karametra's Acolyte")
    # ADR-0027 #24g: historic_matters now reads STRUCTURE — supplement
    # `_recover_historic_subject` synthesizes the Historic subject Filter for the
    # historic cast-restriction phase drops (Raff Capashen's "cast historic spells as
    # though they had flash"). Asserted over real projected IR; the "\bhistoric\b"
    # mirror is deleted, so pure regex no longer serves it (CR 700.6).
    assert ("historic_matters", "you") in _real("Raff Capashen, Ship's Mage")
    assert ("historic_matters", "you") not in _ks(
        {"name": "X", "oracle_text": "Whenever you cast a historic spell, draw a card."}
    )
    # party stays a kept word-detector mirror (phase makes no count operand), so it
    # comes through the hybrid path off the oracle, not pure regex.
    c = {"name": "X", "oracle_text": "Whenever a creature in your party attacks, draw."}
    assert ("party_matters", "you") in _ks_hybrid(c), "party not IR-served"
    assert ("party_matters", "you") not in _ks(c), "party still regex-served"


def test_24g_colorless_historic_scaling_read_structure():
    # ADR-0027 #24g: three MED-residue lanes now read recovered structure off the IR;
    # their byte mirrors are deleted. Asserted over real projected IR (test_signals).
    # colorless_matters (CR 105.2c) — _recover_colorless_subject synthesizes a
    # ColorCount:EQ:0 subject Filter for the dropped "colorless" qualifier:
    assert ("colorless_matters", "you") in _real("Ghostfire Blade")  # equip cost-reduce
    assert ("colorless_matters", "you") in _real("Ugin, the Ineffable")  # cast-reduce
    assert ("colorless_matters", "you") in _real("Consign to Memory")  # counter-target
    # historic_matters (CR 700.6) — _recover_historic_subject synthesizes a Historic
    # subject Filter, incl. the cost-borne case (Sanctum Spirit's "Discard a historic
    # card" activation cost phase collapses to cost='discard'):
    assert ("historic_matters", "you") in _real("Sanctum Spirit")
    # scaling_pump (CR 613) — _recover_scaling_pump synthesizes a pump Effect with the
    # op='count' operand for the "gets +N/+N for each <X>" scaler phase routes through a
    # board_count / make_token / amount=None pump_target carrier:
    assert ("scaling_pump", "you") in _real("Karn, Scion of Urza")  # board_count token
    assert ("scaling_pump", "you") in _real("Gold Rush")  # amount=None pump_target
    # Moira Brown's recovered counter-scaler also opens any_counter_matters (the shared
    # recovery legitimately helps the neighbor lane — CR 122.1):
    moira = _real("Moira Brown, Guide Author")
    assert ("scaling_pump", "you") in moira
    assert ("any_counter_matters", "you") in moira


def test_legends_lands_suspend_are_ir_served():
    # ADR-0027 SWEEP batch: these cares-about lanes moved floor->kept, so they are
    # IR-served from their kept word-detector mirrors (the cost-reduction / target-
    # legendary / count-for-each refs phase leaves textual), not pure regex.
    for key, oracle in (
        ("legends_matter", "Legendary creatures you control get +1/+1."),
        ("lands_matter", "This creature gets +1/+0 for each land you control."),
        ("suspend_matters", "Remove a time counter from target permanent."),
    ):
        c = {"name": "X", "oracle_text": oracle}
        assert (key, "you") in _ks_hybrid(c), f"{key} not IR-served"
        assert (key, "you") not in _ks(c), f"{key} still regex-served"


def test_exile_matters_is_ir_served():
    # ADR-0027 #24b: exile_matters now reads STRUCTURE — the `in:exile` zone the
    # supplement stamps on the standing-in-exile P/T scaler ("cards you own in exile" —
    # Cosmogoyf) phase left zoneless, plus the cast-from-the-exile-pile engine (Mairsil
    # "you may cast a card exiled with ~"). Additive to the `in:exile` count operand /
    # `exile` Condition phase already structures (Ulamog / Ketramose). Asserted over the
    # real projected IR via ``test_signals``; distinct from exile_removal (`to:exile`).
    # CR 406.
    assert ("exile_matters", "you") in _real("Cosmogoyf")
    assert ("exile_matters", "you") in _real("Mairsil, the Pretender")


def test_big_hand_matters_is_ir_served():
    # ADR-0027: big_hand_matters migrated to the Card IR. The "X = cards in your hand"
    # P/T-scaling payoff (Maro) rides the byte-identical _BIG_HAND_MATTERS_MIRROR kept
    # word mirror (phase encodes it as a `characteristic_pt` Effect with NO in:hand
    # zone), so it is IR-served, not regex-served — proven over a bare IR.
    # Real Maro (snapshot): the "X = cards in your hand" P/T-scaling payoff opens the
    # lane on the IR path, not pure regex.
    assert ("big_hand_matters", "you") in _real("Maro")
    assert ("big_hand_matters", "you") not in _ks(test_card("Maro"))
    # The "no maximum hand size" ENABLER fires from the v23 `no_max_handsize` Effect
    # STRUCTURAL arm — proven on an IR carrying that Effect (Spellbook's whole text is
    # the cap-remover, but here we isolate the structural arm with a bare-text card so
    # the mirror can't supply it).
    enabler = {"name": "X", "type_line": "Artifact", "oracle_text": "Caps removed."}
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
                                category="no_max_handsize",
                                scope="you",
                                raw="You have no maximum hand size.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("big_hand_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(enabler, ir)
    }
    assert ("big_hand_matters", "you") not in _ks(enabler)


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
    # AND the Condition(ismonarch) gate. The grant shape is a SYNTHETIC logic probe (no
    # real card needed); the gated shape is proven on real Throne Warden below.
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

    # Real Throne Warden (snapshot): the condition-gated payoff ("if you're the monarch,
    # …") opens monarch via the Condition(ismonarch) gate on the IR path, not regex.
    assert ("monarch_matters", "you") in _real("Throne Warden")
    assert ("monarch_matters", "you") not in _ks(test_card("Throne Warden"))


def test_saddle_matters_is_ir_served():
    # ADR-0027: saddle_matters is IR-served — from phase's `saddle` effect category
    # (a "becomes saddled" grant narrowed into the `saddle` marker), via the hybrid.
    # Real Guidelight Matrix (snapshot): the "becomes saddled" grant opens the lane via
    # phase's `saddle` effect category on the IR path, not regex.
    assert ("saddle_matters", "you") in _real("Guidelight Matrix")
    assert ("saddle_matters", "you") not in _ks(test_card("Guidelight Matrix"))


def test_soulbond_matters_is_ir_served():
    # ADR-0027: has_soulbond is IR-served — from the Scryfall `soulbond` keyword
    # AND a `soulbond` effect marker for non-keyword references ("paired with a
    # creature with soulbond" — Flowering Lumberknot), via the hybrid.
    # Real Flowering Lumberknot (snapshot): the non-keyword "paired with a creature with
    # soulbond" reference opens the lane via the `soulbond` effect marker, not regex.
    assert ("has_soulbond", "you") in _real("Flowering Lumberknot")
    assert ("has_soulbond", "you") not in _ks(test_card("Flowering Lumberknot"))


def test_coin_flip_is_ir_served():
    # ADR-0027: coin_flip is IR-served — the "Whenever you win/lose a coin flip"
    # PAYOFF trigger phase flattened to event="other" is appended as a coin_flip
    # marker effect (read via _DOER_EFFECT_KEYS), via the hybrid.
    # Real Chance Encounter (snapshot): the "Whenever you win a coin flip" payoff opens
    # the lane via the coin_flip marker on the IR path, not regex.
    assert ("coin_flip", "you") in _real("Chance Encounter")
    assert ("coin_flip", "you") not in _ks(test_card("Chance Encounter"))


def test_discover_matters_is_ir_served():
    # ADR-0027: discover_makers is IR-served — the keyword-less re-trigger payoff
    # ("Whenever you discover, discover again" — Curator) is a trigger phase
    # flattened to event="other", appended as a discover marker effect, via hybrid.
    # Real Curator of Sun's Creation (snapshot): the keyword-less "Whenever you discover"
    # re-trigger payoff opens the lane via the discover marker on the IR path, not regex.
    assert ("discover_makers", "you") in _real("Curator of Sun's Creation")
    assert ("discover_makers", "you") not in _ks(test_card("Curator of Sun's Creation"))


def test_ninjutsu_matters_is_ir_served():
    # ADR-0027: has_ninjutsu is IR-served — the keyword-less payoff commander
    # (Satoru: "Whenever you activate a ninjutsu ability") is a trigger phase
    # flattened to event="other", appended as a ninjutsu marker effect, via hybrid.
    # Real Satoru Umezawa (snapshot): the keyword-less "Whenever you activate a ninjutsu
    # ability" payoff opens the lane via the ninjutsu marker on the IR path, not regex.
    assert ("has_ninjutsu", "you") in _real("Satoru Umezawa")
    assert ("has_ninjutsu", "you") not in _ks(test_card("Satoru Umezawa"))


def test_ring_matters_is_ir_served():
    # ADR-0027: ring_matters is IR-served — a "Whenever the Ring tempts you" trigger
    # phase flattened to event="other" AND a "Ring-bearer" reference buried in any
    # effect raw (Sauron, no tempt trigger) are appended as ring_tempt marker
    # effects (read via _DOER_EFFECT_KEYS). Both structural shapes, via the hybrid.
    # Real Faramir, Field Commander (snapshot): the "Whenever the Ring tempts you"
    # trigger opens the lane via the ring_tempt marker on the IR path, not regex.
    assert ("ring_matters", "you") in _real("Faramir, Field Commander")
    assert ("ring_matters", "you") not in _ks(test_card("Faramir, Field Commander"))


def test_vehicles_does_not_fire_on_incidental_or_vehicle_target():
    # "creature or Vehicle you control" (singular) is a counters/combat-trick target,
    # not a vehicles build-around — must NOT fire vehicles_matter. ADR-0027: the lane
    # now rides the IR kept mirror, so assert the (no-)fire on the HYBRID path too.
    c = {
        "name": "Counter Trick",
        "oracle_text": "Put a +1/+1 counter on target creature or Vehicle you control.",
    }
    assert "vehicles_matter" not in _keys(c)
    assert "vehicles_matter" not in {
        s.key for s in extract_signals_hybrid(c, _bare_ir())
    }


def test_voltron_payoff_is_ir_served():
    # ADR-0027 (voltron migration — the LAST key): the Equipment/Aura PAYOFF tell now
    # fires from the IR path (a per-clause VOLTRON_PAYOFF_REGEX word arm UNIONed with the
    # structural _detect_voltron_payoff_ir), HIGH/scope you. The regex path no longer
    # emits it. CR 301.5 / 303.4 / 702.6 / 903.10a.
    c = {
        "name": "Sram-like",
        "type_line": "Legendary Creature — Dwarf Advisor",
        "oracle_text": "Whenever you attach an Equipment to a creature, draw a card.",
    }
    assert "voltron_matters" not in {s.key for s in extract_signals(c)}
    assert ("voltron_matters", "you") in _ks_hybrid(c)


def test_voltron_does_not_fire_on_equipment_payload():
    # The payload on an Equipment itself must not register as a voltron build-around —
    # the broad payoff regex deliberately keys on "equipped creatures" (PLURAL), so the
    # singular "Equipped creature gets +2/+2" gear payload stays off it.
    c = {
        "name": "Bear Sword",
        "oracle_text": "Equipped creature gets +2/+2.\nEquip {2}",
    }
    assert "voltron_matters" not in {
        s.key for s in extract_signals_hybrid(c, _bare_ir())
    }


def test_plus_one_matters_widened_for_distributors():
    # A distributor like "+1/+1 counter on each creature you control" (Mikaeus) is a
    # counters engine. ADR-0027: plus_one_matters migrated to the IR — the placement
    # projects a place_counter(p1p1); assert via the hybrid (production) path.
    c = {
        "name": "Mikaeus-like",
        "oracle_text": "At the beginning of your end step, put a +1/+1 counter on each creature you control.",
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
                            Effect(
                                category="place_counter",
                                scope="you",
                                counter_kind="p1p1",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert any(s.key == "plus_one_matters" for s in extract_signals_hybrid(c, ir))


def test_poison_scoped_to_opponents():
    # ADR-0027: poison_matters is IR-served (the infect Scryfall keyword + a kept word
    # mirror for the granters/references), so it comes through the hybrid path, scoped
    # to opponents, not pure regex.
    c = {
        "name": "Skithiryx-like",
        "oracle_text": "Infect\nThis creature can't be blocked.",
    }
    assert ("poison_matters", "opponents") in _ks_hybrid(c)
    assert ("poison_matters", "opponents") not in _ks(c)


# --- mechanics recovered from the "rejected" families (still-zero commanders) ---


def test_token_copy_engine():
    # ADR-0027 C5: token_copy_makers is FULLY STRUCTURAL — a CopyTokenOf projects to a
    # make_token whose subject carries the "Copy" predicate (CR 707), which the
    # structural arm reads; no regex mirror.
    c = {
        "name": "Orthion-like",
        "oracle_text": "{1}{R}, {T}: Create a token that's a copy of another target creature you control.",
    }
    ir = Card(
        oracle_id="x",
        name="Orthion-like",
        faces=(
            Face(
                name="Orthion-like",
                abilities=(
                    Ability(
                        kind="activated",
                        effects=(
                            Effect(
                                category="make_token",
                                scope="you",
                                subject=Filter(
                                    card_types=("Creature",), predicates=("Copy",)
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("token_copy_makers", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }


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
    # ADR-0027: dice_matters migrated to the Card IR — phase's native roll_die effect
    # (and the "whenever you roll" payoff marker) opens the lane via _DOER_EFFECT_KEYS,
    # so it comes through the hybrid path, not the deleted regex.
    c = {
        "name": "Wyll-like",
        "oracle_text": "Whenever you roll one or more dice, create a Treasure token.",
    }
    ir = Card(
        oracle_id="x",
        name="Wyll-like",
        faces=(
            Face(
                name="Wyll-like",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="other"),
                        effects=(
                            Effect(
                                category="roll_die",
                                scope="you",
                                raw="Whenever you roll one or more dice",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("dice_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }
    assert ("dice_matters", "you") not in _ks(c)


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
    # ADR-0027: connive_makers migrated to the Card IR — phase's `connive` effect
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
    assert ("connive_makers", "you") in hybrid
    assert ("connive_makers", "you") not in _ks(c)


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
    # ADR-0027: experience migrated to the Card IR. ADR-0034 _matters sweep: the
    # GivePlayerCounter experience GAINER (phase's experience_counter effect
    # category) is the MAKER arm, so it opens experience_makers (the payoff scaler
    # arm keeps experience_matters).
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
    assert ("experience_makers", "you") in hybrid
    assert ("experience_makers", "you") not in _ks(c)


def test_mutate_is_ir_served():
    # ADR-0027: has_mutate migrated to the Card IR — the Scryfall mutate keyword
    # opens it via _IR_KEYWORD_MAP (a mutate creature carries the keyword).
    c = {
        "name": "X",
        "oracle_text": "Mutate {2}{G}{U}",
        "keywords": ["Mutate"],
    }
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, _ks_bare_ir())}
    assert ("has_mutate", "you") in hybrid
    assert ("has_mutate", "you") not in _ks(c)


def _ks_bare_ir():
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def test_prowess_keyword_surfaces_spellslinger():
    # spellcast_matters is migrated (ADR-0027 SIDECAR 50); prowess opens it via the
    # _IR_KEYWORD_MAP (byte-identical Scryfall keyword array) on the hybrid path.
    c = {"name": "X", "oracle_text": "Prowess", "keywords": ["Prowess"]}
    assert ("spellcast_matters", "you") in _ks_hybrid(c)


def test_loot_outlet_is_a_discard_avenue():
    # ADR-0027: discard_matters migrated to the Card IR — the loot outlet ("draw a
    # card, then discard") fires from the byte-identical _LOOT_FULLTEXT_RE kept-mirror
    # in the IR path (which scans the record oracle, so a bare non-None IR routes the
    # hybrid to it), NOT the deleted regex producer.
    c = {"name": "X", "oracle_text": "{T}: Draw a card, then discard a card."}
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, _ks_bare_ir())}
    assert ("discard_matters", "you") in hybrid
    assert ("discard_matters", "you") not in _ks(c)


def _spell_copy_ir() -> Card:
    return Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="spell",
                        effects=(
                            Effect(
                                category="spell_copy",
                                scope="you",
                                raw="Copy target instant or sorcery spell.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_spell_copy():
    # ADR-0027: spell_copy_makers migrated to the IR (phase's spell_copy effect /
    # copy keywords / granted-copy marker) — the regex path no longer emits it.
    c = {
        "name": "X",
        "oracle_text": "Copy target instant or sorcery spell you control.",
    }
    assert ("spell_copy_makers", "you") not in _ks(c)
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, _spell_copy_ir())}
    assert ("spell_copy_makers", "you") in hybrid


def test_kitsa_gets_three_avenues():
    # Real Kitsa, Otterball Elite (snapshot): prowess → spellslinger, the loot outlet →
    # discard, and "Copy target instant or sorcery" → spell_copy, all three over real IR.
    keys = {s.key for s in test_signals("Kitsa, Otterball Elite")}
    assert "spellcast_matters" in keys  # prowess → spellslinger
    assert "discard_matters" in keys  # loot outlet
    assert "spell_copy_makers" in keys  # copy spells


def test_type_matters_catches_another_singular_tribal():
    # Marwyn: "another Elf you control" (singular) was missed by the "other Xs" form.
    c = {
        "name": "Marwyn-like",
        "oracle_text": "Whenever another Elf you control enters, put a +1/+1 counter on this creature.",
    }
    # ADR-0027: type_matters migrated → hybrid path.
    got = {(s.key, s.scope, s.subject) for s in extract_signals_hybrid(c, _bare_ir())}
    assert ("type_matters", "you", "Elf") in got
