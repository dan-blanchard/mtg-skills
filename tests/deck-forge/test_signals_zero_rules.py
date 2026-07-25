"""Tests for the rules mined from the zero-signal commander tail (the families the
workflow surfaced as clean, measured wins). Each recovers a real archetype the
12-detector baseline missed, with a structural anchor that keeps it precise.

Every case here runs the REAL production extractor via ``mtg_utils.testkit``
(``test_signals`` = ``extract_signals`` over the real Scryfall record + real
snapshot-stored phase records). Bare key-membership for each of these keys is
already proven by ``tests/deck-forge/test_signal_keys_real_cards.py``'s
``_REAL_CASES`` table; every test kept here asserts something that table does not —
a specific SCOPE, an additive pairing (two keys firing together), or a negative
(the key does NOT fire on a lookalike card) — using a different representative card
than that table's row for the same key wherever one is needed to keep the two
files' regression coverage independent.
"""

from mtg_utils.testkit import test_signals


def _hyb_ks(name):
    return {(s.key, s.scope) for s in test_signals(name)}


def _hyb_keys(name):
    return {s.key for s in test_signals(name)}


def test_combat_damage_matters_scoped_opponents():
    # Edric, Spymaster of Trest — "deals combat damage to one of your opponents" reads
    # the structured recipient; the real extractor opens combat_damage_matters scoped
    # opponents (test_signal_keys_real_cards.py's own combat_damage_matters case
    # shares this same card but doesn't assert scope).
    assert ("combat_damage_matters", "opponents") in _hyb_ks(
        "Edric, Spymaster of Trest"
    )


def test_combat_damage_does_not_fire_on_plain_attack():
    # Sophina, Spearsage Deserter attacks and investigates — an attack trigger with
    # no combat-damage read at all. combat_damage_matters must stay silent.
    assert "combat_damage_matters" not in _hyb_keys("Sophina, Spearsage Deserter")
    assert "attack_matters" in _hyb_keys("Sophina, Spearsage Deserter")


def test_cost_reduction():
    # Danitha Capashen, Paragon — "Aura and Equipment spells you cast cost {1} less"
    # is a static ModifyCost{Reduce} on the spell_filter; the extractor opens
    # cost_reduction scoped you.
    assert ("cost_reduction", "you") in _hyb_ks("Danitha Capashen, Paragon")


def test_play_from_top_of_library_is_its_own_signal():
    # Playing off the top of the LIBRARY (Glarb, Calamity's Augur) is play_from_top — a
    # different zone than exile, so it is NOT cast_from_exile.
    keys = _hyb_ks("Glarb, Calamity's Augur")
    assert ("play_from_top", "you") in keys
    assert ("cast_from_exile", "you") not in keys


def test_cast_from_exile_play_from_exile_trigger():
    # Prosper, Tome-Bound — "Whenever you play a card from exile, create a Treasure" is
    # the canonical exile-cast PAYOFF.
    assert ("cast_from_exile", "you") in _hyb_ks("Prosper, Tome-Bound")


def test_discard_matters():
    # Hashaton, Scarab's Fist — "Whenever you discard a creature card …" payoff fires
    # from the scope-gated discarded-trigger structural arm (scope != "opp").
    assert ("discard_matters", "you") in _hyb_ks("Hashaton, Scarab's Fist")


def test_lifeloss_drain_scoped_opponents():
    # Gray Merchant of Asphodel — "each opponent loses X life" is the drain MAKER
    # side (_matters sweep, ADR-0034); the "any"-scope lose_life effect folds to
    # "opponents" because the clause explicitly targets opponents.
    assert ("lifeloss_makers", "opponents") in _hyb_ks("Gray Merchant of Asphodel")


def test_lifeloss_self_scoped_you():
    # Vilis, Broker of Blood — "Whenever you lose life, draw that many cards" is a
    # life_lost trigger payoff (scope you).
    assert ("lifeloss_matters", "you") in _hyb_ks("Vilis, Broker of Blood")


def test_lands_matter_count_payoff():
    # Walker of the Wastes — "This creature gets +1/+1 for each land you control" (the
    # Land count operand).
    assert ("lands_matter", "you") in _hyb_ks("Walker of the Wastes")


def test_card_draw_engine_bulk_draw():
    # Jin-Gitaxias, Core Augur — "draw seven cards" each end step opens
    # card_draw_engine.
    assert ("card_draw_engine", "you") in _hyb_ks("Jin-Gitaxias, Core Augur")


def test_card_draw_engine_skips_cantrip():
    # Defiant Strike — a one-shot "target creature gets +1/+0. Draw a card." cantrip
    # is not a repeatable draw engine.
    assert "card_draw_engine" not in _hyb_keys("Defiant Strike")


def test_card_draw_engine_skips_etb_oneshot():
    # Mulldrifter — a one-shot ETB "draw two cards" is not a repeatable draw engine.
    assert "card_draw_engine" not in _hyb_keys("Mulldrifter")


def test_card_draw_engine_each_player_wheel_scoped_each():
    # Nekusar, the Mindrazer — "each player draws an additional card" (a symmetric
    # wheel) opens card_draw_engine scoped "each" — a structurally distinct trigger
    # shape from the single-player repeated-draw representative case.
    assert ("card_draw_engine", "each") in _hyb_ks("Nekusar, the Mindrazer")


def test_direct_damage_pinger():
    # Kamahl, Pit Fighter — "{T}: deals 3 damage to any target" is repeatable
    # player-reach burn (CR 115.4 — any target can be a player).
    assert ("direct_damage", "you") in _hyb_ks("Kamahl, Pit Fighter")


def test_mana_amplifier():
    # Vorinclex, Voice of Hunger — "Whenever you tap a land for mana, add one mana …"
    # is the doubler arm, read additively — the doubler stays in the generic ramp
    # lane too.
    hybrid = _hyb_ks("Vorinclex, Voice of Hunger")
    assert ("mana_amplifier", "you") in hybrid
    assert ("ramp", "you") in hybrid


def test_keyword_granting_team_is_not_a_separate_signal():
    # Fervor — "Creatures you control have haste." A team keyword grant is already
    # covered by creatures_matter (the workflow flagged this family do-not-add); no
    # separate "team_keyword_grant" key exists anywhere in the served-key manifest.
    keys = _hyb_keys("Fervor")
    assert "team_keyword_grant" not in keys
    assert "creatures_matter" in keys
