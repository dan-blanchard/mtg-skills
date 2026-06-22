"""Tests for the rules mined from the zero-signal commander tail (the families the
workflow surfaced as clean, measured wins). Each recovers a real archetype the
12-detector baseline missed, with a structural anchor that keeps it precise.
"""

from mtg_utils._deck_forge.signals import extract_signals, extract_signals_hybrid
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter


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
    c = {
        "name": "Attacker",
        "oracle_text": "Whenever this creature attacks, draw a card.",
    }
    assert "combat_damage_matters" not in _keys(c)


def test_cost_reduction():
    # ADR-0027 β: cost_reduction is IR-served — a static ModifyCost{Reduce} Effect whose
    # subject is the spell_filter (here Aura/Equipment). The structural arm fires on the
    # non-None subject; the legacy regex path no longer emits it.
    c = {
        "name": "Danitha Capashen, Paragon",
        "type_line": "Legendary Creature — Human Knight",
        "oracle_text": (
            "First strike, vigilance, lifelink\n"
            "Aura and Equipment spells you cast cost {1} less to cast."
        ),
    }
    ir = Card(
        oracle_id="x",
        name="Danitha Capashen, Paragon",
        faces=(
            Face(
                name="Danitha Capashen, Paragon",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="cost_reduction",
                                scope="you",
                                subject=Filter(subtypes=("Aura", "Equipment")),
                                raw=(
                                    "Aura and Equipment spells you cast cost "
                                    "{1} less to cast."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "cost_reduction" not in _keys(c)
    assert ("cost_reduction", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }


def test_play_from_top_of_library_is_its_own_signal():
    # Playing off the top of the LIBRARY (Future Sight / Glarb) is play_from_top — a
    # different zone than exile, so it is NOT cast_from_exile. ADR-0027 β: play_from_top
    # migrated to the Card IR, so it is served from the hybrid — here via the structural
    # STATIC cast_from_zone+from:library arm (project._top_play_permission_marker over
    # phase's TopOfLibraryCastPermission mode). cast_from_exile stays out on both paths.
    c = {
        "name": "Glarb, Calamity's Augur",
        "oracle_text": "Deathtouch\nYou may look at the top card of your library any time.\nYou may play lands and cast spells with mana value 4 or greater from the top of your library.\n{T}: Surveil 2.",
    }
    ir = Card(
        oracle_id="x",
        name="Glarb, Calamity's Augur",
        faces=(
            Face(
                name="Glarb, Calamity's Augur",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="cast_from_zone",
                                scope="you",
                                zones=("from:library",),
                                raw=(
                                    "You may play lands and cast spells with mana "
                                    "value 4 or greater from the top of your library."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(c, ir)}
    assert ("play_from_top", "you") in keys
    assert ("cast_from_exile", "you") not in keys


def test_cast_from_exile_play_from_exile_trigger():
    c = {
        "name": "Prosper, Tome-Bound",
        "oracle_text": (
            "Deathtouch\nMystic Arcanum — At the beginning of your end step, exile the top card of your library. Until the end of your next turn, you may play that card.\nPact Boon — Whenever you play a card from exile, create a Treasure token."
        ),
    }
    assert ("cast_from_exile", "you") in _ks(c)


def test_discard_matters():
    c = {
        "name": "Hashaton, Scarab's Fist",
        "oracle_text": "Whenever you discard a creature card, you may pay {2}{U}. If you do, create a tapped token that's a copy of that card, except it's a 4/4 black Zombie.",
    }
    assert ("discard_matters", "you") in _ks(c)


def test_lifeloss_drain_scoped_opponents():
    # ADR-0027: lifeloss_matters is IR-served — a `lose_life` drain (scope any/opp →
    # opponents).
    c = {
        "name": "Drainer",
        "oracle_text": "Whenever a creature you control dies, each opponent loses 1 life.",
    }
    ir = Card(
        oracle_id="x",
        name="Drainer",
        faces=(
            Face(
                name="Drainer",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(Effect(category="lose_life", scope="any"),),
                    ),
                ),
            ),
        ),
    )
    assert ("lifeloss_matters", "opponents") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }


def test_lifeloss_self_scoped_you():
    # ADR-0027: lifeloss_matters is IR-served — "whenever you lose life" is a
    # `life_lost` trigger payoff (scope you → you).
    from mtg_utils.card_ir import Trigger

    c = {
        "name": "Vilis-like",
        "oracle_text": "Whenever you lose life, draw that many cards.",
    }
    ir = Card(
        oracle_id="x",
        name="Vilis-like",
        faces=(
            Face(
                name="Vilis-like",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="life_lost", scope="you"),
                        effects=(Effect(category="draw", scope="you"),),
                    ),
                ),
            ),
        ),
    )
    assert ("lifeloss_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }


def test_lands_matter_count_payoff():
    # ADR-0027: lands_matter migrated to the Card IR (the amount.subject=Land count
    # operand + a kept word mirror for the "for each land you control" forms phase
    # flattens to a bare effect), so it is served via the hybrid path, not pure regex.
    c = {
        "name": "Radha-like",
        "oracle_text": "This creature gets +1/+1 for each land you control.",
    }
    bare = Card(oracle_id="x", name="Radha-like", faces=(Face(name="Radha-like"),))
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(c, bare)}
    assert ("lands_matter", "you") in hybrid
    assert ("lands_matter", "you") not in _ks(c)


def test_card_draw_engine_bulk_draw():
    c = {
        "name": "Jin-Gitaxias, Core Augur",
        "oracle_text": "Flash\nAt the beginning of your end step, draw seven cards.\nEach opponent's maximum hand size is reduced by seven.",
    }
    assert ("card_draw_engine", "you") in _ks(c)


def test_card_draw_engine_skips_cantrip():
    c = {"name": "Opt-like", "oracle_text": "Scry 1, then draw a card."}
    assert "card_draw_engine" not in _keys(c)


def test_card_draw_engine_skips_etb_oneshot():
    c = {
        "name": "ETB Draw",
        "oracle_text": "When this creature enters, draw two cards.",
    }
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
        "oracle_text": "Haste (This creature can attack and {T} as soon as it comes under your control.)\n{T}: Kamahl deals 3 damage to any target.",
    }
    assert ("direct_damage", "you") in _ks(c)


def test_mana_amplifier():
    c = {
        "name": "Vorinclex, Voice of Hunger",
        "oracle_text": "Trample\nWhenever you tap a land for mana, add one mana of any type that land produced.\nWhenever an opponent taps a land for mana, that land doesn't untap during its controller's next untap step.",
    }
    assert ("mana_amplifier", "you") in _ks(c)


def test_keyword_granting_team_is_not_a_separate_signal():
    # Deliberately NOT added — team keyword grants are already covered by
    # creatures_matter (the workflow flagged this family do-not-add). creatures_matter
    # MIGRATED to the Card IR (ADR-0027), so the team grant fires it via the grant_
    # keyword arm on the hybrid path.
    c = {
        "name": "Team Buff",
        "oracle_text": "Other creatures you control have flying.",
    }
    ir = Card(
        oracle_id="x",
        name="Team Buff",
        faces=(
            Face(
                name="Team Buff",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="grant_keyword",
                                scope="you",
                                subject=Filter(
                                    card_types=("Creature",), controller="you"
                                ),
                                counter_kind="flying",
                                raw="Other creatures you control have flying.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "team_keyword_grant" not in _keys(c)
    assert ("creatures_matter", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }
