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


# ── Zero-avenue commander recovery: themeless beaters, variable counters, global lords
# These commanders extracted NO avenues at all — the worst case (0/10 coverage).
def test_variable_x_counters_opens_counters_lane():
    # Halana and Alena: a recurring engine that puts a VARIABLE number of +1/+1
    # counters on your team each combat — a counters commander, but the count-anchor
    # ('for each'/'number of') gate missed the 'X +1/+1 counters' scaling form.
    halana = {
        "name": "Halana and Alena, Partners",
        "type_line": "Legendary Creature — Human Ranger",
        "oracle_text": (
            "First strike\nReach\nAt the beginning of combat on your turn, put X "
            "+1/+1 counters on another target creature you control, where X is Halana "
            "and Alena's power. That creature gains haste until end of turn."
        ),
    }
    assert any(k == "counters_matter" for k, _ in _keys(halana))


def test_cheap_vanilla_legend_opens_voltron_fallback():
    # Isamaru: the iconic 2/2 vanilla voltron commander. Commander damage is the only
    # plan, so the themeless-creature fallback must open voltron even at low power.
    isamaru = {
        "name": "Isamaru, Hound of Konda",
        "type_line": "Legendary Creature — Dog",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert ("voltron_matters", "you") in _keys(isamaru)


def test_indestructible_beater_opens_voltron_fallback():
    # Konda: indestructible + vigilance beater — a resilient commander-damage threat
    # whose keywords weren't in the voltron set.
    konda = {
        "name": "Konda, Lord of Eiganjo",
        "type_line": "Legendary Creature — Human Samurai",
        "power": "3",
        "toughness": "3",
        "keywords": ["Vigilance", "Indestructible"],
        "oracle_text": "Vigilance, indestructible\nBushido 5",
    }
    assert ("voltron_matters", "you") in _keys(konda)


def test_themeless_one_one_does_not_open_voltron():
    # Precision: a 1/1 themeless legend is too small to be a commander-damage plan.
    chump = {
        "name": "Tiny Legend",
        "type_line": "Legendary Creature — Human",
        "power": "1",
        "toughness": "1",
        "oracle_text": "",
    }
    assert ("voltron_matters", "you") not in _keys(chump)


def test_global_tribal_anthem_opens_tribe():
    # Soraya: "Bird creatures get +1/+1" is a Bird lord — but the anthem patterns
    # required 'you control'/'other', missing the bare global-lord phrasing.
    soraya = {
        "name": "Soraya the Falconer",
        "type_line": "Legendary Creature — Human",
        "oracle_text": "Bird creatures get +1/+1.",
    }
    sigs = extract_signals(soraya)
    assert any(s.key == "type_matters" and s.subject == "Bird" for s in sigs)


# ── Artifact commanders that phrase the theme without "artifacts you control" ─────
# Foundry Inspector (artifact cost reducer) is top-synergy for these but the lane
# never opened: they sacrifice artifacts (Bosh), copy artifact abilities (Kurkesh),
# or turn permanents INTO artifacts (Memnarch).
def test_artifact_sac_outlet_opens_artifacts_lane():
    bosh = {
        "name": "Bosh, Iron Golem",
        "type_line": "Legendary Artifact Creature — Golem",
        "oracle_text": "Trample\n{3}{R}, Sacrifice an artifact: Bosh deals damage "
        "equal to that artifact's mana value to any target.",
    }
    assert ("artifacts_matter", "you") in _keys(bosh)


def test_artifact_ability_payoff_opens_artifacts_lane():
    kurkesh = {
        "name": "Kurkesh, Onakke Ancient",
        "type_line": "Legendary Creature — Ogre Shaman",
        "oracle_text": "Whenever you activate an ability of an artifact, if it isn't a "
        "mana ability, you may pay {R}. If you do, copy that ability.",
    }
    assert ("artifacts_matter", "you") in _keys(kurkesh)


def test_artifact_type_granter_opens_artifacts_lane():
    memnarch = {
        "name": "Memnarch",
        "type_line": "Legendary Artifact Creature — Wizard",
        "oracle_text": "{1}{U}: Target permanent becomes an artifact in addition to "
        "its other types.\n{3}{U}{U}: Gain control of target artifact.",
    }
    assert ("artifacts_matter", "you") in _keys(memnarch)


def test_artifact_removal_does_not_open_artifacts_lane():
    # Precision: destroying an opponent's artifact is removal, not an artifact theme.
    card = {
        "name": "Disenchanter",
        "oracle_text": "When this creature enters, destroy target artifact or enchantment.",
    }
    assert ("artifacts_matter", "you") not in _keys(card)


# ── creature_etb scope tracks the ENTERING creature's controller, not the payoff ──
# Purphoros: "Whenever another creature YOU control enters, deal 2 damage to each
# opponent." The entering creature is yours — so this is creature_etb YOU (an ETB
# go-wide engine that wants Panharmonicon / flicker / ETB creatures). The payoff
# hitting opponents must NOT flip the scope.
def test_creature_etb_scope_follows_entering_controller_not_payoff():
    purphoros = {
        "name": "Purphoros, God of the Forge",
        "oracle_text": (
            "Indestructible\nWhenever another creature you control enters, Purphoros "
            "deals 2 damage to each opponent."
        ),
    }
    keys = _keys(purphoros)
    assert ("creature_etb", "you") in keys
    assert ("creature_etb", "opponents") not in keys


def test_etb_trigger_doubler_opens_etb_lane():
    # Yarok doubles every permanent-ETB trigger — he's an ETB-value commander who wants
    # ETB creatures, flicker, and other doublers, so he must open the creature_etb lane.
    yarok = {
        "name": "Yarok, the Desecrated",
        "oracle_text": (
            "Deathtouch, lifelink\nIf a permanent entering causes a triggered ability "
            "of a permanent you control to trigger, that ability triggers an "
            "additional time."
        ),
    }
    assert ("creature_etb", "you") in _keys(yarok)


# ── Artifact-token makers ARE artifact commanders (Food/Treasure/Clue are artifacts) ─
# A Treasure / Food / Clue / Blood maker should open the artifacts lane so artifact
# payoffs (Academy Manufactor, Foundry Inspector, artifact sac) surface — the serve
# already credits them; the detector missed the lane-opening (Korvold, Gyome).
def test_treasure_maker_opens_artifacts_lane():
    goldspan = {
        "name": "Goldspan Dragon",
        "type_line": "Legendary Creature — Dragon",
        "oracle_text": "Flying, haste\nWhenever Goldspan Dragon attacks or becomes "
        "the target of a spell, create a Treasure token.",
    }
    assert ("artifacts_matter", "you") in _keys(goldspan)


def test_food_maker_opens_artifacts_lane():
    gyome = {
        "name": "Gyome, Master Chef",
        "type_line": "Legendary Creature — Elf Peasant",
        "oracle_text": "Whenever you gain life, create a Food token.",
    }
    assert ("artifacts_matter", "you") in _keys(gyome)


def test_creature_token_maker_does_not_open_artifacts_lane():
    # Precision: a Soldier-token maker is NOT an artifacts commander.
    card = {
        "name": "Soldier Boss",
        "type_line": "Legendary Creature — Human",
        "oracle_text": "At the beginning of your end step, create two 1/1 white "
        "Soldier creature tokens.",
    }
    assert ("artifacts_matter", "you") not in _keys(card)
