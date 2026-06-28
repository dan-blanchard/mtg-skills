"""Every ability is an axis to build around — broad effect-axis detectors so a
commander whose ability is ramp / removal / a team buff / a tutor / etc. surfaces
that direction instead of reading as a value-pile.

Real-card pins run the REAL projected Card IR via ``mtg_utils.testkit``
(``test_signals`` = production hybrid over the real Scryfall record + real sidecar IR;
``test_card`` = the real minimal record). Pins on a controlled, made-up shape
("X"/"Healer"/"Mind Rot-like", or a synthetic project_card input) keep a thin synthetic
builder — the shape is the point, not a particular printing.
"""

from mtg_utils._deck_forge.signals import extract_signals, extract_signals_hybrid
from mtg_utils.card_ir import Card, Face
from mtg_utils.testkit import test_card, test_signals

# Card names referenced through the real-card helpers above. This table feeds the
# `build-card-snapshot` usage scanner (it parses `_REAL_CASES` dict VALUES, which
# also handles apostrophes — unlike the bare `test_card("…")` literal scan). Keep it
# in sync with the names used below; a missing entry fails loud (KeyError) at test
# time, never silently.
_REAL_CASES: dict[str, str] = {
    "Azami, Lady of Scrolls": "Azami, Lady of Scrolls",
    "Azusa, Lost but Seeking": "Azusa, Lost but Seeking",
    "Dark Deal": "Dark Deal",
    "Eladamri, Lord of Leaves": "Eladamri, Lord of Leaves",
    "Erayo, Soratami Ascendant": "Erayo, Soratami Ascendant",
    "Gandalf the White": "Gandalf the White",
    "Heartless Pillage": "Heartless Pillage",
    "Ishai, Ojutai Dragonspeaker": "Ishai, Ojutai Dragonspeaker",
    "Isshin, Two Heavens as One": "Isshin, Two Heavens as One",
    "Jolrael, Empress of Beasts": "Jolrael, Empress of Beasts",
    "Megrim": "Megrim",
    "Mind Rot": "Mind Rot",
    "River Song": "River Song",
    "Sheoldred, the Apocalypse": "Sheoldred, the Apocalypse",
}


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


# Real-card (key, scope) sets — production hybrid path / regex-only path, by name.
def _hyb_ks(name):
    return {(s.key, s.scope) for s in test_signals(name)}


def _reg_ks(name):
    return {(s.key, s.scope) for s in extract_signals(test_card(name))}


def _hyb_keys(name):
    return {s.key for s in test_signals(name)}


CASES = [
    # ADR-0027: ramp migrated to the Card IR (the structural `ramp` category
    # for NON-LAND cards + a byte-identical kept mirror), so a bare mana rock
    # "{T}: Add {G}{G}." no longer fires on the regex path tested here — its IR path is
    # proven in test_migrated_keys.
    # ADR-0027: removal migrated to the Card IR (phase's single-target
    # destroy/damage SUBJECT), so it no longer fires on the regex path tested here —
    # its IR path is proven in test_migrated_keys.
    # ADR-0027: counter_control migrated to the Card IR (phase's `counter_spell`
    # effect category), so it no longer fires on the regex path tested here — its IR
    # path is proven in test_migrated_keys.
    # ADR-0027: team_buff migrated to the Card IR (phase's `grant_keyword` effect on a
    # generic "creatures you control" subject), so it no longer fires on the regex path
    # tested here — its IR path is proven in test_migrated_keys.
    # ADR-0027 reveal/dig-v2: tutor migrated to the Card IR (a BYTE-IDENTICAL
    # kept mirror == the deleted TUTOR_MATTERS_REGEX over the reminder-stripped oracle —
    # phase keeps a `tutor` EFFECT for every search incl. the opp/symmetric/composite/
    # reminder over-fires, so the regex IS the precise spec), so it no longer fires on the
    # regex path tested here — its IR path is proven in test_migrated_keys.
    # ADR-0027 β: gain_control migrated to the Card IR (a gated `cat=='gain_control'`
    # structural arm + a narrowed kept mirror + a facade cross-open reconciliation), so
    # it no longer fires on the regex path tested here — its IR path is proven in
    # test_migrated_keys and test_signals_generalized.
    # ADR-0027: opponent_discard migrated to the Card IR (four structural arms — POP1
    # ForcedDiscard / POP2 subject.controller / POP4 each scope / POP7 opp `discarded`
    # trigger — plus a NARROWED residue mirror, C3 SIDECAR v50), so it no longer fires on
    # the regex path tested here — its IR path is asserted by
    # test_opponent_discard_migrated_off_regex_onto_ir and the POP1/2/4/7 tests below.
    # ADR-0027: evasion_self migrated to the Card IR (a byte-identical kept WORD MIRROR
    # of the deleted _HAND_FLOOR producer + the _IR_KEYWORD_MAP['shadow'] recall arm), so
    # it no longer fires on the regex path tested here — its IR path is proven in
    # test_migrated_keys and test_cant_be_blocked_is_evasion (hybrid).
    # ADR-0027 v30: clone_makers migrated to the Card IR (a cat=='clone' structural arm
    # on the supplement-populated copied-type subject + a byte-identical CLONE_MATTERS_
    # REGEX kept WORD MIRROR), so it no longer fires on the regex path tested here — its
    # IR path is proven in test_migrated_keys and test_clone_still_fires (hybrid).
    # ADR-0027 reveal/dig-v2: cheat_into_play migrated to the Card IR (a STRUCTURAL
    # cat=='cheat_play'+to:battlefield+non-gy-source arm reading the project._recover_
    # cheat_into_play_source marker + a narrow _CHEAT_INTO_PLAY_RESIDUE_RE mirror), so it
    # no longer fires on the regex path tested here — its IR path is proven in
    # test_migrated_keys and test_polymorph_cheat_opens_cheat_into_play (hybrid).
    # ADR-0027 (t2b2-A): bounce_tempo migrated to the Card IR (phase's first-class
    # `bounce` effect category, gated on no-graveyard-zone + subject not controller=you),
    # so it no longer fires on the regex path tested here — its IR path is proven in
    # test_migrated_keys.
    # ADR-0027: cascade_matters (Scryfall cascade keyword + _CASCADE_GRANT marker) and
    # regenerate_makers (phase's regenerate effect + _REGENERATE_REF marker) migrated to
    # the Card IR, so they no longer fire on the regex path tested here — their IR paths
    # are proven in test_migrated_keys.
]


def test_effect_axis_detectors_fire():
    for key, scope, oracle in CASES:
        sigs = {
            (s.key, s.scope)
            for s in extract_signals({"name": "X", "oracle_text": oracle})
        }
        assert (key, scope) in sigs, f"{key}/{scope} did not fire on: {oracle}"


def test_opponent_discard_migrated_off_regex_onto_ir():
    # ADR-0027: opponent_discard fires from the hybrid IR path, not the regex path. With
    # a bare (structure-less) IR the forced "each opponent discards" forcer rides the
    # NARROWED residue mirror's "each opponent discards" alternation over the oracle (real
    # cards fire structurally via the POP projection threads — see the POP tests below).
    # A bare-IR + synthetic-oracle probe of the MIRROR-fallback path specifically.
    c = {
        "name": "Mind Rot-like",
        "oracle_text": "When this creature enters, each opponent discards a card.",
    }
    bare_ir = Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))
    assert not any(s.key == "opponent_discard" for s in extract_signals(c))
    assert any(
        (s.key, s.scope) == ("opponent_discard", "opponents")
        for s in extract_signals_hybrid(c, bare_ir)
    )


# --- ADR-0027 C3 opponent_discard structural arms (POP1/2/4/7), on real cards ---


def test_pop1_forced_discard_marker_opens_opponent_discard():
    """POP1 — a bare-Player "target player discards" projects scope 'opp' + a
    ForcedDiscard subject marker (Mind Rot). The v50 arm fires opponent_discard
    structurally on the real IR. CR 701.9."""
    assert ("opponent_discard", "opponents") in _hyb_ks("Mind Rot")


def test_pop2_typed_opp_subject_controller_opens_opponent_discard():
    """POP2 — "target opponent discards" folds the effect scope to 'any' (Typed target),
    but the opponent lands on subject.controller=='opp' (Heartless Pillage). The
    discard-LOCAL subject.controller read fires opponent_discard. CR 701.9 / 102.2."""
    assert ("opponent_discard", "opponents") in _hyb_ks("Heartless Pillage")


def test_pop4_each_player_discard_opens_opponent_discard_each():
    """POP4 — a symmetric "each player discards" projects scope 'each' (Dark Deal); the
    'each' scope opens opponent_discard at the 'each' label (it hits opponents). CR
    701.9."""
    assert ("opponent_discard", "each") in _hyb_ks("Dark Deal")


def test_pop7_opponent_discarded_trigger_opens_opponent_discard():
    """POP7 — "whenever an opponent discards a card …" is a Discarded TRIGGER scope 'opp'
    with a non-discard punisher body (Megrim deals 2 damage). The trigger arm fires
    opponent_discard; DISJOINT from discard_matters (scope != 'opp'). CR 701.9 / 102.2."""
    keys = _hyb_ks("Megrim")
    assert ("opponent_discard", "opponents") in keys
    assert not any(k == "discard_matters" for k, _ in keys)


# --- widens of existing keys ---------------------------------------------------


def test_landfall_widened_for_extra_land_drops():
    # ADR-0027: landfall migrated — Azusa's extra-land STATIC ("play additional lands")
    # has no structural shape phase carries, so it fires from the _LANDFALL_MIRROR over
    # the oracle via the real IR, NOT the deleted regex producer.
    assert "landfall" not in {
        s.key for s in extract_signals(test_card("Azusa, Lost but Seeking"))
    }
    assert "landfall" in _hyb_keys("Azusa, Lost but Seeking")


def test_land_creatures_widened_for_animation():
    # ADR-0027: land_creatures_matter migrated to the Card IR — Jolrael, Empress of
    # Beasts' mass-animation "all lands … become … creatures" rides the kept oracle
    # mirror, asserted via the real IR.
    assert "land_creatures_matter" in _hyb_keys("Jolrael, Empress of Beasts")


def test_attack_matters_widened_for_isshin():
    # ADR-0027: attack_matters migrated — Isshin's "attacking causes …" static has no
    # structural shape phase carries, so it fires from the _ATTACK_MATTERS_MIRROR over
    # the oracle via the real IR, NOT the deleted regex producer.
    assert "attack_matters" not in {
        s.key for s in extract_signals(test_card("Isshin, Two Heavens as One"))
    }
    assert "attack_matters" in _hyb_keys("Isshin, Two Heavens as One")


def test_lifegain_widened_for_activated_gain():
    # ADR-0027 β: lifegain is IR-served; an activated "{T}: You gain 3 life" fires it
    # from the IR structural arm (the gain_life Effect, scope you/any). _matters sweep
    # (ADR-0034): gaining life is the MAKER side, so it fires lifegain_makers. A
    # synthetic project_card input pins the activated-gain shape generically.
    from mtg_utils._card_ir.project import project_card

    c = {"name": "Healer", "oracle_text": "{T}: You gain 3 life."}
    ir = project_card([{**c, "card_type": {"core_types": ["Artifact"]}}])
    assert any(s.key == "lifegain_makers" for s in extract_signals_hybrid(c, ir))


def test_lifeloss_widened_for_pay_life_engine():
    # ADR-0027: lifeloss is IR-served; a "Pay N life:" cost buying a non-ramp engine
    # fires it from the IR (the paylife-cost + life_payment marker path). _matters
    # sweep (ADR-0034): paying/losing life as a cost is the MAKER side, so it fires
    # lifeloss_makers. A synthetic project_card input pins the pay-life-engine shape.
    from mtg_utils._card_ir.project import project_card

    c = {"name": "Bargainer", "oracle_text": "{B}, Pay 2 life: Draw a card."}
    ir = project_card([{**c, "card_type": {"core_types": ["Artifact"]}}])
    assert any(s.key == "lifeloss_makers" for s in extract_signals_hybrid(c, ir))


# --- recognizable axes from the one-off tail ----------------------------------


def test_type_matters_other_x_creatures():
    # Eladamri, Lord of Leaves: "Other Elf creatures have forestwalk." (no "you control")
    # — the real IR opens type_matters:Elf.
    got = {(s.key, s.subject) for s in test_signals("Eladamri, Lord of Leaves")}
    assert ("type_matters", "Elf") in got


def test_type_matters_activated_tribal():
    # Azami, Lady of Scrolls: tribal subtype named in an activated cost ("Tap an untapped
    # Wizard you control"). ADR-0027: type_matters via the real IR.
    assert any(
        s.key == "type_matters" and s.subject == "Wizard"
        for s in test_signals("Azami, Lady of Scrolls")
    )


def test_opponent_cast_matters():
    # ADR-0027: opponent_cast_matters migrated to the Card IR (the cast_spell trigger
    # scope=opp arm). Ishai, Ojutai Dragonspeaker fires it via the real IR, not the
    # regex path.
    assert ("opponent_cast_matters", "opponents") in _hyb_ks(
        "Ishai, Ojutai Dragonspeaker"
    )
    assert ("opponent_cast_matters", "opponents") not in _reg_ks(
        "Ishai, Ojutai Dragonspeaker"
    )


def test_spell_count_storm_widen():
    # ADR-0027: second_spell_matters migrated to the Card IR (the _SECOND_SPELL_MIRROR
    # kept word detector — phase parses "fourth spell of a turn" as a bare cast_spell
    # trigger with no count qualifier). Erayo, Soratami Ascendant fires it via the real
    # IR, not the regex path.
    assert "second_spell_matters" not in {
        s.key for s in extract_signals(test_card("Erayo, Soratami Ascendant"))
    }
    assert "second_spell_matters" in _hyb_keys("Erayo, Soratami Ascendant")


def test_legends_matter_for_cast_legendary():
    # ADR-0027: legends_matter migrated to the Card IR (the HasSupertype:Legendary
    # subject predicate + a kept word mirror for the cast-legendary refs). Gandalf the
    # White's "cast legendary spells as though they had flash" fires it via the real IR,
    # not the regex path.
    assert "legends_matter" in _hyb_keys("Gandalf the White")
    assert "legends_matter" not in {
        s.key for s in extract_signals(test_card("Gandalf the White"))
    }


def test_opponent_library_manipulation_punisher():
    # River Song's Spoilers: punish opponents for scry/surveil/search (opponents scope —
    # distinct from your own scry_surveil payoff). ADR-0027 β: opponent_search_matters is
    # IR-served from an opp-scoped `lib_search` trigger. River Song fires it via the real
    # IR, not the regex path.
    assert ("opponent_search_matters", "opponents") in _hyb_ks("River Song")
    assert ("opponent_search_matters", "opponents") not in _reg_ks("River Song")


def test_your_scry_is_not_an_opponent_punisher():
    c = {"name": "X", "oracle_text": "Whenever you scry, draw a card."}
    assert "opponent_search_matters" not in {s.key for s in extract_signals(c)}


def test_opponent_draw_punisher():
    # ADR-0027: opponent_draw_matters is IR-served from a "drawn" trigger scoped to an
    # opponent. Sheoldred, the Apocalypse ("Whenever an opponent draws a card, they lose
    # 2 life") fires it via the real IR, not the regex path.
    assert ("opponent_draw_matters", "opponents") in _hyb_ks(
        "Sheoldred, the Apocalypse"
    )
    assert ("opponent_draw_matters", "opponents") not in _reg_ks(
        "Sheoldred, the Apocalypse"
    )
