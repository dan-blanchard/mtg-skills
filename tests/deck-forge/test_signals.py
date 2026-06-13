"""Tests for deterministic signal extraction (the discovery-engine keystone).

The headline guard: a signal that concerns OPPONENTS' graveyards must be scoped
"opponents", never a generic graveyard signal that would justify self-mill (the
Tinybones overgeneralization the whole tool exists to prevent).
"""

from mtg_utils._deck_forge.signals import Signal, aggregate_signals, extract_signals


def _keys(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


def test_creature_etb_scoped_to_you():
    card = {
        "name": "ETB Boss",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    assert ("creature_etb", "you") in _keys(card)


def test_creature_etb_scoped_to_opponents():
    card = {
        "name": "Punisher",
        "oracle_text": "Whenever a creature an opponent controls enters, it deals 1 damage to them.",
    }
    assert ("creature_etb", "opponents") in _keys(card)


def test_graveyard_signal_scoped_to_opponents_not_generic():
    # The Tinybones case: benefits from OPPONENTS' graveyards filling.
    card = {
        "name": "Tinybones, the Pickpocket",
        "oracle_text": (
            "Whenever an opponent puts one or more cards into their graveyard, "
            "you may exile a card from that graveyard and play it."
        ),
    }
    sigs = extract_signals(card)
    gy = [s for s in sigs if s.key == "graveyard_matters"]
    assert gy, "expected a graveyard signal"
    assert all(s.scope == "opponents" for s in gy)
    # It must NOT be scoped to 'you' — that would justify self-mill.
    assert ("graveyard_matters", "you") not in _keys(card)


def test_graveyard_signal_scoped_to_you_for_reanimator():
    card = {
        "name": "Reanimator",
        "oracle_text": "Return target creature card from your graveyard to the battlefield.",
    }
    assert ("graveyard_matters", "you") in _keys(card)


def test_lifegain_matters():
    card = {
        "name": "Soul Warden's Friend",
        "oracle_text": "Whenever you gain life, put a +1/+1 counter on this creature.",
    }
    assert ("lifegain_matters", "you") in _keys(card)


def test_vanilla_keyword_card_has_no_signals():
    card = {"name": "Air Elemental", "oracle_text": "Flying"}
    assert extract_signals(card) == []


JYOTI = {
    "name": "Jyoti, Moag Ancient",
    "oracle_text": (
        "When Jyoti enters, create a 1/1 green Forest Dryad land creature token "
        "for each time you've cast your commander from the command zone this game. "
        "(They're affected by summoning sickness.)\n"
        "At the beginning of each combat, land creatures you control get +X/+X "
        "until end of turn, where X is Jyoti's power."
    ),
}


def test_land_creatures_matter_detected_on_jyoti():
    keys = _keys(JYOTI)
    # The defining theme of the commander — must be its own signal, not collapsed
    # into generic "creatures matter".
    assert ("land_creatures_matter", "you") in keys
    # The generic go-wide signal still fires too (regression safety).
    assert ("creatures_matter", "you") in keys


def test_land_creatures_matter_from_anthem_payoff():
    sylvan = {
        "name": "Sylvan Advocate",
        "oracle_text": (
            "Vigilance\nAs long as you control six or more lands, this creature "
            "and land creatures you control get +2/+2."
        ),
    }
    assert ("land_creatures_matter", "you") in _keys(sylvan)


def test_plant_token_maker_is_not_a_land_creatures_signal():
    # Avenger makes *Plant* creature tokens — never "land creatures". The whole
    # point of the scoped vocabulary: this must NOT register as land-creatures.
    avenger = {
        "name": "Avenger of Zendikar",
        "oracle_text": (
            "When Avenger of Zendikar enters, create a 0/1 green Plant creature "
            "token for each land you control."
        ),
    }
    keys = _keys(avenger)
    assert ("land_creatures_matter", "you") not in keys
    assert ("land_creatures_matter", "any") not in keys


def test_signal_carries_source_and_quote():
    card = {
        "name": "ETB Boss",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    sig = next(s for s in extract_signals(card) if s.key == "creature_etb")
    assert sig.source == "ETB Boss"
    assert "creature you control enters" in sig.text.lower()


def test_aggregate_dedupes_across_records():
    a = {
        "name": "A",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    b = {
        "name": "B",
        "oracle_text": "Whenever a creature you control enters, gain 1 life.",
    }
    agg = aggregate_signals([a, b])
    etb = [s for s in agg if s.key == "creature_etb" and s.scope == "you"]
    assert len(etb) == 1  # deduped by (key, scope, subject)


def test_signal_is_hashable_frozen():
    s = Signal(key="x", scope="you", subject="", text="t", source="c")
    assert len({s, s}) == 1


# ── Reanimator payoff: "entered/cast from a graveyard" (Celes, Rune Knight) ──────
# The generic graveyard_matters lane is the FUEL (fill your yard / self-mill); a
# commander that rewards a creature ENTERING from a graveyard (reanimation) or being
# CAST from a graveyard (escape/disturb) is a reanimator PAYOFF — its own avenue.
CELES = {
    "name": "Celes, Rune Knight",
    "type_line": "Legendary Creature — Human Wizard Knight",
    "oracle_text": (
        "When Celes enters, discard any number of cards, then draw that many cards "
        "plus one.\n"
        "Whenever one or more other creatures you control enter, if one or more of them "
        "entered from a graveyard or was cast from a graveyard, put a +1/+1 counter on "
        "each creature you control."
    ),
    "color_identity": ["B", "R", "W"],
}


def test_reanimator_payoff_detected_for_celes():
    assert ("reanimator", "you") in _keys(CELES)


def test_reanimator_and_graveyard_fuel_both_fire_for_celes():
    keys = _keys(CELES)
    assert ("reanimator", "you") in keys  # the payoff (reanimation/cast-from-grave)
    assert ("graveyard_matters", "you") in keys  # the fuel (fill your own graveyard)


def test_reanimator_quotes_the_payoff_clause():
    sig = next(s for s in extract_signals(CELES) if s.key == "reanimator")
    assert sig.scope == "you"
    assert "from a graveyard" in sig.text.lower()


def test_reanimator_not_fired_by_regrowth_to_hand():
    # Returning a card to HAND is graveyard-return, not reanimation — no payoff trigger.
    card = {
        "name": "Regrowth",
        "oracle_text": "Return target card from your graveyard to your hand.",
    }
    assert ("reanimator", "you") not in _keys(card)


def test_reanimator_not_fired_by_plain_reanimation_spell():
    # A reanimation spell is an ENABLER (found by the avenue's search), not itself the
    # payoff trigger — its text says "to the battlefield", never "enters/cast from".
    card = {
        "name": "Animate Dead-like",
        "oracle_text": "Return target creature card from your graveyard to the battlefield.",
    }
    assert ("reanimator", "you") not in _keys(card)


# ── Aristocrats: death-trigger doublers open the lane (the Teysa case) ───────────
# A commander that DOUBLES death triggers ("if a creature dying causes a triggered
# ability ... that ability triggers an additional time") is an aristocrats commander
# even though it never says "whenever ... dies". It must open the death lane so the
# drain payoffs (Blood Artist / Zulaport) surface.
def test_death_trigger_doubler_opens_aristocrats_lane():
    teysa = {
        "name": "Teysa Karlov",
        "oracle_text": (
            "If a creature dying causes a triggered ability of a permanent you control "
            "to trigger, that ability triggers an additional time.\n"
            "Creature tokens you control have vigilance and lifelink."
        ),
    }
    assert any(k == "death_matters" for k, _ in _keys(teysa))


def test_dies_in_passing_does_not_open_aristocrats():
    # A one-off non-death clause must NOT mint the aristocrats lane (no over-general).
    card = {
        "name": "Exiler",
        "oracle_text": "When this creature deals combat damage to a player, exile it.",
    }
    assert not any(k == "death_matters" for k, _ in _keys(card))


# ── Cast-an-X-spell routes to the X lane, not Spellslinger (Sythis / Emry) ──────
def test_enchantment_cast_opens_enchantments_not_spellslinger():
    # "Whenever you cast an enchantment spell" is ENCHANTRESS, not spellslinger — the
    # greedy spellcast detector used to mis-route Sythis to instants/sorceries.
    sythis = {
        "name": "Sythis, Harvest's Hand",
        "type_line": "Legendary Enchantment Creature — Dryad",
        "oracle_text": "Whenever you cast an enchantment spell, you gain 1 life and draw a card.",
    }
    keys = _keys(sythis)
    assert ("enchantments_matter", "you") in keys
    assert not any(k == "spellcast_matters" for k, _ in keys)


def test_affinity_and_artifact_cast_open_artifacts_lane():
    # Affinity (reminder text stripped) + casting artifacts from graveyard make Emry an
    # artifacts commander; she must open the Artifacts lane.
    emry = {
        "name": "Emry, Lurker of the Loch",
        "type_line": "Legendary Creature — Merfolk Wizard",
        "oracle_text": "Affinity for artifacts\nWhen Emry enters, mill four cards.\n"
        "{T}: Choose target artifact card in your graveyard. You may cast that card this turn.",
    }
    assert ("artifacts_matter", "you") in _keys(emry)
    sai = {
        "name": "Sai, Master Thopterist",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": "Whenever you cast an artifact spell, create a 1/1 colorless Thopter artifact creature token with flying.",
    }
    assert ("artifacts_matter", "you") in _keys(sai)


def test_token_doubler_opens_tokens_lane():
    # A token DOUBLER (Adrix) wants token-MAKERS to double — it must open the tokens
    # lane, not only "Doubling".
    adrix = {
        "name": "Adrix and Nev, Twincasters",
        "type_line": "Legendary Creature — Crab Wizard",
        "oracle_text": "If one or more tokens would be created under your control, twice "
        "that many of those tokens are created instead.",
    }
    assert ("tokens_matter", "you") in _keys(adrix)


# ── Landfall: a land-recursion commander opens the lands lane (the Windgrace case) ─
# A commander whose payoff replays lands from the graveyard ("return … land cards from
# your graveyard to the battlefield") is a lands-matter commander and must open the
# landfall lane so its payoffs (Lotus Cobra / Scute Swarm) surface, even with no literal
# "landfall" / "play an additional land".
def test_land_recursion_commander_opens_landfall_lane():
    windgrace = {
        "name": "Lord Windgrace",
        "oracle_text": (
            "−3: Return up to two target land cards from your graveyard to the "
            "battlefield."
        ),
    }
    assert ("landfall", "you") in _keys(windgrace)


# ── Lifegain payoffs that gate on HAVING gained life (Aerith / Celestine) ────────
# "if you gained life this turn" / "the amount of life you gained this turn" is a
# lifegain PAYOFF — it cares whether you gained life — but the detector only caught
# "whenever you gain life". These commanders showed ONLY an incidental graveyard
# signal; their real theme (lifegain) was invisible.
def test_lifegain_conditional_payoff_opens_lane():
    aerith = {
        "name": "Aerith, Last Ancient",
        "oracle_text": (
            "Lifelink\nRaise — At the beginning of your end step, if you gained life "
            "this turn, return target creature card from your graveyard to your hand. "
            "If you gained 7 or more life this turn, return that card to the "
            "battlefield instead."
        ),
    }
    assert ("lifegain_matters", "you") in _keys(aerith)


def test_lifegain_amount_gained_payoff_opens_lane():
    celestine = {
        "name": "Celestine, the Living Saint",
        "oracle_text": (
            "Flying, lifelink\nHealing Tears — At the beginning of your end step, "
            "return target creature card with mana value X or less from your graveyard "
            "to the battlefield, where X is the amount of life you gained this turn."
        ),
    }
    assert ("lifegain_matters", "you") in _keys(celestine)


def test_combat_damage_to_player_does_not_open_lifegain():
    # Precision: a card that merely says "life" in passing (lose life) must not mint
    # the lifegain lane via the new past-tense branch.
    card = {
        "name": "Drainer",
        "oracle_text": "When this creature deals combat damage to a player, they lose 2 life.",
    }
    assert ("lifegain_matters", "you") not in _keys(card)


# ── Evasion keywords whose "can't be blocked" lives only in stripped reminder text ─
# Horsemanship / menace / fear / intimidate / shadow / skulk are all CR blocking
# restrictions (702.31 / .111 / .36 / .13 / .28 / .118). Their mechanic is in the
# parenthetical reminder, which extract_signals strips — so the bare keyword word is
# all that's left and the detector must recognize it (Guan Yu showed NO evasion lane).
def test_horsemanship_opens_evasion_lane():
    guan_yu = {
        "name": "Guan Yu, Sainted Warrior",
        "oracle_text": (
            "Horsemanship (This creature can't be blocked except by creatures with "
            "horsemanship.)\nWhen Guan Yu is put into your graveyard from the "
            "battlefield, you may shuffle Guan Yu into your library."
        ),
    }
    assert ("evasion_self", "you") in _keys(guan_yu)


def test_menace_opens_evasion_lane():
    card = {
        "name": "Menacer",
        "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)",
    }
    assert ("evasion_self", "you") in _keys(card)


def test_plain_vigilance_creature_no_evasion_lane():
    # Precision: a non-evasion keyword must not open the evasion lane.
    card = {"name": "Watcher", "oracle_text": "Vigilance"}
    assert ("evasion_self", "you") not in _keys(card)
