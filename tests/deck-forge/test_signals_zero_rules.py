"""Tests for the rules mined from the zero-signal commander tail (the families the
workflow surfaced as clean, measured wins). Each recovers a real archetype the
12-detector baseline missed, with a structural anchor that keeps it precise.

Real-card pins run the REAL projected Card IR via ``mtg_utils.testkit``
(``test_signals`` = production hybrid over the real Scryfall record + real sidecar IR;
``test_card`` = the real minimal record). Pins on a controlled, made-up shape
("Attacker"/"Drainer"/"Team Buff", or a synthetic generic) keep a thin synthetic
builder — the shape is the point, not a particular printing.
"""

from mtg_utils._deck_forge.signals import extract_signals, extract_signals_hybrid
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter
from mtg_utils.testkit import test_card, test_signals

# Card names referenced through the real-card helpers above. This table feeds the
# `build-card-snapshot` usage scanner (it parses `_REAL_CASES` dict VALUES, which
# also handles apostrophes — unlike the bare `test_card("…")` literal scan). Keep it
# in sync with the names used below; a missing entry fails loud (KeyError) at test
# time, never silently.
_REAL_CASES: dict[str, str] = {
    "Danitha Capashen, Paragon": "Danitha Capashen, Paragon",
    "Edric, Spymaster of Trest": "Edric, Spymaster of Trest",
    "Glarb, Calamity's Augur": "Glarb, Calamity's Augur",
    "Hashaton, Scarab's Fist": "Hashaton, Scarab's Fist",
    "Jin-Gitaxias, Core Augur": "Jin-Gitaxias, Core Augur",
    "Kamahl, Pit Fighter": "Kamahl, Pit Fighter",
    "Nekusar, the Mindrazer": "Nekusar, the Mindrazer",
    "Prosper, Tome-Bound": "Prosper, Tome-Bound",
    "Vilis, Broker of Blood": "Vilis, Broker of Blood",
    "Vorinclex, Voice of Hunger": "Vorinclex, Voice of Hunger",
    "Walker of the Wastes": "Walker of the Wastes",
}


def _keys(card):
    return {s.key for s in extract_signals(card)}


# A minimal non-None IR routes the hybrid to the IR path for ADR-0027-migrated keys
# whose IR source is a kept word-detector mirror over the record's oracle_text.
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _keys_hybrid(card):
    return {s.key for s in extract_signals_hybrid(card, _bare_ir())}


# Real-card signal sets — production hybrid path / regex-only path, by name.
def _hyb_ks(name):
    return {(s.key, s.scope) for s in test_signals(name)}


def _reg_ks(name):
    return {(s.key, s.scope) for s in extract_signals(test_card(name))}


def _hyb_keys(name):
    return {s.key for s in test_signals(name)}


def _reg_keys(name):
    return {s.key for s in extract_signals(test_card(name))}


def test_combat_damage_matters_scoped_opponents():
    # Edric, Spymaster of Trest — "deals combat damage to one of your opponents" reads the
    # structured recipient; the real IR opens combat_damage_matters scoped opponents.
    assert ("combat_damage_matters", "opponents") in _hyb_ks(
        "Edric, Spymaster of Trest"
    )


def test_combat_damage_does_not_fire_on_plain_attack():
    c = {
        "name": "Attacker",
        "oracle_text": "Whenever this creature attacks, draw a card.",
    }
    assert "combat_damage_matters" not in _keys_hybrid(c)


def test_cost_reduction():
    # Danitha Capashen, Paragon — "Aura and Equipment spells you cast cost {1} less" is a
    # static ModifyCost{Reduce} on the spell_filter; the real IR opens cost_reduction, the
    # legacy regex path does not.
    assert "cost_reduction" not in _reg_keys("Danitha Capashen, Paragon")
    assert ("cost_reduction", "you") in _hyb_ks("Danitha Capashen, Paragon")


def test_play_from_top_of_library_is_its_own_signal():
    # Playing off the top of the LIBRARY (Glarb, Calamity's Augur) is play_from_top — a
    # different zone than exile, so it is NOT cast_from_exile. The real IR opens
    # play_from_top (the structural cast_from_zone+from:library arm) and keeps
    # cast_from_exile out.
    keys = _hyb_ks("Glarb, Calamity's Augur")
    assert ("play_from_top", "you") in keys
    assert ("cast_from_exile", "you") not in keys


def test_cast_from_exile_play_from_exile_trigger():
    # Prosper, Tome-Bound — "Whenever you play a card from exile, create a Treasure" is the
    # canonical exile-cast PAYOFF. The real IR opens cast_from_exile (the kept word mirror
    # over the reminder-stripped oracle); the regex path no longer emits it.
    assert ("cast_from_exile", "you") in _hyb_ks("Prosper, Tome-Bound")
    assert ("cast_from_exile", "you") not in _reg_ks("Prosper, Tome-Bound")


def test_discard_matters():
    # Hashaton, Scarab's Fist — "Whenever you discard a creature card …" payoff fires from
    # the scope-gated `discarded`-trigger structural arm (scope != "opp") on the real IR,
    # NOT the deleted regex producer.
    assert ("discard_matters", "you") in _hyb_ks("Hashaton, Scarab's Fist")
    assert ("discard_matters", "you") not in _reg_ks("Hashaton, Scarab's Fist")


def test_lifeloss_drain_scoped_opponents():
    # ADR-0027: lifeloss_matters is IR-served — a `lose_life` drain (scope any/opp →
    # opponents). A synthetic dies-drain shape pins the scope fold generically.
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
    # Vilis, Broker of Blood — "Whenever you lose life, draw that many cards" is a
    # life_lost trigger payoff (scope you). The real IR opens lifeloss_matters/you.
    assert ("lifeloss_matters", "you") in _hyb_ks("Vilis, Broker of Blood")


def test_lands_matter_count_payoff():
    # Walker of the Wastes — "This creature gets +1/+1 for each land you control" (the
    # Land count operand). The real IR opens lands_matter; the regex path does not.
    assert ("lands_matter", "you") in _hyb_ks("Walker of the Wastes")
    assert ("lands_matter", "you") not in _reg_ks("Walker of the Wastes")


def test_card_draw_engine_bulk_draw():
    # Jin-Gitaxias, Core Augur — "draw seven cards" each end step opens card_draw_engine
    # on the real IR.
    assert ("card_draw_engine", "you") in _hyb_ks("Jin-Gitaxias, Core Augur")


def test_card_draw_engine_skips_cantrip():
    c = {"name": "Opt-like", "oracle_text": "Scry 1, then draw a card."}
    assert "card_draw_engine" not in _keys_hybrid(c)


def test_card_draw_engine_skips_etb_oneshot():
    c = {
        "name": "ETB Draw",
        "oracle_text": "When this creature enters, draw two cards.",
    }
    assert "card_draw_engine" not in _keys_hybrid(c)


def test_card_draw_engine_each_player_wheel_scoped_each():
    # Nekusar, the Mindrazer — "each player draws an additional card" (a symmetric wheel)
    # opens card_draw_engine on the real IR.
    assert "card_draw_engine" in _hyb_keys("Nekusar, the Mindrazer")


def test_direct_damage_pinger():
    # Kamahl, Pit Fighter — "{T}: deals 3 damage to any target" is repeatable player-reach
    # burn (CR 115.4 — any target can be a player). The real IR opens direct_damage.
    assert ("direct_damage", "you") in _hyb_ks("Kamahl, Pit Fighter")


def test_mana_amplifier():
    # Vorinclex, Voice of Hunger — "Whenever you tap a land for mana, add one mana …" is
    # the doubler arm (a triggered ramp Mana effect matching the amount-increase
    # discriminator). The real IR opens mana_amplifier additively (ramp_matters also
    # keeps firing); the regex path emits neither.
    assert "mana_amplifier" not in _reg_keys("Vorinclex, Voice of Hunger")
    hybrid = _hyb_ks("Vorinclex, Voice of Hunger")
    assert ("mana_amplifier", "you") in hybrid
    # read additively — the doubler stays in the generic ramp lane too.
    assert ("ramp_matters", "you") in hybrid


def test_keyword_granting_team_is_not_a_separate_signal():
    # Deliberately NOT added — team keyword grants are already covered by
    # creatures_matter (the workflow flagged this family do-not-add). A synthetic team
    # grant pins the do-not-add: team_keyword_grant must not exist; creatures_matter fires
    # via the grant_keyword arm on the hybrid path.
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
