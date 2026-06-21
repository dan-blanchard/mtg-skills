"""Every ability is an axis to build around — broad effect-axis detectors so a
commander whose ability is ramp / removal / a team buff / a tutor / etc. surfaces
that direction instead of reading as a value-pile.
"""

from mtg_utils._deck_forge.signals import extract_signals, extract_signals_hybrid
from mtg_utils.card_ir import Ability, Card, Face, Trigger


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


CASES = [
    ("ramp_matters", "you", "{T}: Add {G}{G}."),
    # ADR-0027: removal_matters migrated to the Card IR (phase's single-target
    # destroy/damage SUBJECT), so it no longer fires on the regex path tested here —
    # its IR path is proven in test_migrated_keys.
    # ADR-0027: counter_control migrated to the Card IR (phase's `counter_spell`
    # effect category), so it no longer fires on the regex path tested here — its IR
    # path is proven in test_migrated_keys.
    # ADR-0027: team_buff migrated to the Card IR (phase's `grant_keyword` effect on a
    # generic "creatures you control" subject), so it no longer fires on the regex path
    # tested here — its IR path is proven in test_migrated_keys.
    (
        "tutor_matters",
        "you",
        "{T}: Search your library for a basic land card, then shuffle.",
    ),
    ("untap_engine", "you", "{T}: Untap another target permanent."),
    ("gain_control", "you", "{3}{U}: Gain control of target creature."),
    (
        "opponent_discard",
        "opponents",
        "When this creature enters, each opponent discards a card.",
    ),
    ("evasion_self", "you", "This creature can't be blocked."),
    (
        "clone_matters",
        "you",
        "This creature enters the battlefield as a copy of target creature.",
    ),
    (
        "cheat_into_play",
        "you",
        "Look at the top five cards of your library. Put a creature card from among them onto the battlefield.",
    ),
    # ADR-0027 (t2b2-A): bounce_tempo migrated to the Card IR (phase's first-class
    # `bounce` effect category, gated on no-graveyard-zone + subject not controller=you),
    # so it no longer fires on the regex path tested here — its IR path is proven in
    # test_migrated_keys.
    # ADR-0027: cascade_matters (Scryfall cascade keyword + _CASCADE_GRANT marker) and
    # regenerate_matters (phase's regenerate effect + _REGENERATE_REF marker) migrated to
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


# --- widens of existing keys ---------------------------------------------------


def test_landfall_widened_for_extra_land_drops():
    c = {
        "name": "Azusa-like",
        "oracle_text": "You may play two additional lands on each of your turns.",
    }
    assert any(s.key == "landfall" for s in extract_signals(c))


def test_land_creatures_widened_for_animation():
    # ADR-0027: land_creatures_matter migrated to the Card IR — the mass-animation
    # "all lands … become … creatures" tell rides the kept oracle mirror, so assert
    # via the hybrid path (any non-None IR routes to the mirror-bearing path).
    c = {
        "name": "Jolrael-like",
        "oracle_text": "{2}{G}: All lands target player controls become 3/3 creatures until end of turn.",
    }
    bare_ir = Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))
    assert any(
        s.key == "land_creatures_matter" for s in extract_signals_hybrid(c, bare_ir)
    )


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
    # ADR-0027: lifeloss_matters is IR-served; a "Pay N life:" cost buying a non-ramp
    # engine fires it from the IR (the paylife-cost + life_payment marker path).
    from mtg_utils._card_ir.project import project_card

    c = {"name": "Bargainer", "oracle_text": "{B}, Pay 2 life: Draw a card."}
    ir = project_card([{**c, "card_type": {"core_types": ["Artifact"]}}])
    assert any(s.key == "lifeloss_matters" for s in extract_signals_hybrid(c, ir))


# --- recognizable axes from the one-off tail ----------------------------------


def test_type_matters_other_x_creatures():
    # Eladamri, Lord of Leaves: "Other Elf creatures have forestwalk." (no "you control")
    c = {
        "name": "Eladamri, Lord of Leaves",
        "type_line": "Legendary Creature — Elf Warrior",
        "oracle_text": "Other Elf creatures have forestwalk. (They can't be blocked as long as defending player controls a Forest.)\nOther Elves have shroud. (They can't be the targets of spells or abilities.)",
    }
    got = {(s.key, s.subject) for s in extract_signals(c)}
    assert ("type_matters", "Elf") in got


def test_type_matters_activated_tribal():
    # Azami: tribal subtype named in an activated cost.
    c = {
        "name": "Azami",
        "oracle_text": "Tap an untapped Wizard you control: Draw a card.",
    }
    assert any(
        s.key == "type_matters" and s.subject == "Wizard" for s in extract_signals(c)
    )


def test_opponent_cast_matters():
    # ADR-0027: opponent_cast_matters migrated to the Card IR (the cast_spell trigger
    # scope=opp arm + a kept word mirror for the symmetric-punisher tail), so it is
    # served via the hybrid path, not pure regex.
    c = {
        "name": "Ishai, Ojutai Dragonspeaker",
        "oracle_text": (
            "Flying\nWhenever an opponent casts a spell, put a +1/+1 counter on "
            "Ishai, Ojutai Dragonspeaker."
        ),
    }
    ir = Card(
        oracle_id="x",
        name="Ishai, Ojutai Dragonspeaker",
        faces=(
            Face(
                name="Ishai, Ojutai Dragonspeaker",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="cast_spell", scope="opp"),
                    ),
                ),
            ),
        ),
    )
    assert ("opponent_cast_matters", "opponents") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }
    assert "opponent_cast_matters" not in {s.key for s in extract_signals(c)}


def test_spell_count_storm_widen():
    c = {
        "name": "Erayo",
        "oracle_text": "Whenever the fourth spell of a turn is cast, flip this creature.",
    }
    assert any(s.key == "second_spell_matters" for s in extract_signals(c))


def test_legends_matter_for_cast_legendary():
    # ADR-0027: legends_matter migrated to the Card IR (the HasSupertype:Legendary
    # subject predicate + a kept word mirror for the cast-legendary / target-legendary
    # refs phase leaves textual), so it is served via the hybrid path, not pure regex.
    c = {
        "name": "Gandalf",
        "oracle_text": "You may cast legendary spells as though they had flash.",
    }
    bare = Card(oracle_id="x", name="Gandalf", faces=(Face(name="Gandalf"),))
    assert any(s.key == "legends_matter" for s in extract_signals_hybrid(c, bare))
    assert not any(s.key == "legends_matter" for s in extract_signals(c))


def test_opponent_library_manipulation_punisher():
    # River Song's Spoilers: punish opponents for scry/surveil/search (opponents
    # scope — distinct from your own scry_surveil payoff).
    c = {
        "name": "River Song",
        "oracle_text": "Meet in Reverse — You draw cards from the bottom of your library rather than the top.\nSpoilers — Whenever an opponent scries, surveils, or searches their library, put a +1/+1 counter on River Song. Then River Song deals damage to that player equal to its power.",
    }
    assert ("opponent_search_matters", "opponents") in _ks(c)


def test_your_scry_is_not_an_opponent_punisher():
    c = {"name": "X", "oracle_text": "Whenever you scry, draw a card."}
    assert "opponent_search_matters" not in {s.key for s in extract_signals(c)}


def test_opponent_draw_punisher():
    # ADR-0027: opponent_draw_matters is IR-served from a "drawn" trigger scoped to
    # an opponent, so it needs the matching IR, not pure regex.
    c = {
        "name": "Leela",
        "oracle_text": "Whenever an opponent draws a card except the first one they draw in each draw step, that player loses 1 life.",
    }
    ir = Card(
        oracle_id="x",
        name="Leela",
        faces=(
            Face(
                name="Leela",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="drawn", scope="opp"),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("opponent_draw_matters", "opponents") in hybrid
    assert ("opponent_draw_matters", "opponents") not in _ks(c)
