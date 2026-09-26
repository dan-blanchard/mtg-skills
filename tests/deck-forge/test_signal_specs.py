"""Tests for signal specs: how a signal maps to cards that FEED it.

Headline guard: a card that feeds an *opponents'-graveyard* signal must mill
opponents, not yourself. Self-mill must NOT register as serving it.
"""

import dataclasses
import re

import pytest

from mtg_utils._analysis import signal_specs
from mtg_utils._analysis.signal_specs import (
    _CHOSEN_TYPE_IDENTS,
    Serve,
    search_filters,
    serve_from_dict,
    serves,
    spec_for,
)
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir, test_signals


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record for *name* (ADR-0056), with its crosswalk trees
    memo seeded first — so a serve's structural ``signal_idents`` arm reads the
    card's real idents in CI exactly as it does locally (no phase cache)."""
    test_card_ir(name)
    return test_card(name)


def test_serve_all_of_requires_every_subserve():
    # AND-composition: a Serve with `all_of` matches only when EVERY sub-serve matches
    # (each sub-serve is itself an OR-of-dimensions). Lets us express "dies-value AND
    # cmc>=5" — a high-value clone target — which the flat OR-Serve could not.
    big_dies = Serve(
        all_of=(
            Serve(oracle=re.compile(r"when .* dies", re.IGNORECASE)),
            Serve(cmc_min=5),
        )
    )
    kokusho = _card("Kokusho, the Evening Star")
    # Has a dies trigger (undying's reminder text) but cmc 1 — not a clone bomb.
    young_wolf = _card("Young Wolf")
    big_vanilla = _card("Craw Wurm")  # cmc>=5 but no dies trigger
    assert big_dies.matches(kokusho) is True
    assert big_dies.matches(young_wolf) is False
    assert big_dies.matches(big_vanilla) is False
    # not_oracle still vetoes at the top level
    veto = Serve(
        all_of=(Serve(oracle=re.compile("when .* dies", re.IGNORECASE)),),
        not_oracle=re.compile("each opponent", re.IGNORECASE),
    )
    assert veto.matches(kokusho) is False
    # round-trips through as_dict / serve_from_dict
    rebuilt = serve_from_dict(big_dies.as_dict())
    assert rebuilt.matches(kokusho) is True
    assert rebuilt.matches(young_wolf) is False
    assert rebuilt.matches(big_vanilla) is False


def _lane_covers(card, sig):
    """True if a card is surfaced by the lane via its main serve OR any sub-avenue —
    mirroring how the engine renders an avenue plus its extras."""
    spec = spec_for(sig)
    if spec is None:
        return False
    if spec.serve.matches(card):
        return True
    return any(
        (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in spec.extras
    )


def test_stax_serves_nonbasic_land_hate():
    # Land-denial IS stax — a stax/land-hate commander (Zhao "nonbasic lands enter
    # tapped", Thalia) wants Blood Moon-style nonbasic hate (Magus of the Moon, Burning
    # Earth, Price of Progress). The serve had "nonbasic ... enters tapped" / "don't
    # untap" but missed "are Mountains" / "taps a nonbasic land" / "number of nonbasic".
    sig = _sig("stax_taxes", "opponents")
    magus = _card("Magus of the Moon")
    burning = _card("Burning Earth")
    assert _lane_covers(magus, sig) is True
    assert _lane_covers(burning, sig) is True
    # Over-fire guard: a basic-land ramp spell is not land-denial stax.
    ramp = _card("Rampant Growth")
    assert _lane_covers(ramp, sig) is False


def test_stax_serves_opponent_skip_step_imposition():
    # Forcing opponents to skip a step/phase is stax (CR 500.11) — the same family as
    # "opponents can't cast/attack/untap" the lane already serves. Fatespinner's skip
    # clause subject is "The player" (the opponent named the sentence before), so the
    # opponent/that-player/the-player skip branch must catch it. Without it Fatespinner
    # served nothing -> filler -> the spread_thin pass cut the deck's stax piece.
    sig = _sig("stax_taxes", "opponents")
    fatespinner = _card("Fatespinner")
    assert _lane_covers(fatespinner, sig) is True
    # Over-fire guard: a SELF skip-step drawback ("skip your ...") is not stax —
    # Necropotence skips its own controller's draw step.
    drawback = _card("Necropotence")
    assert _lane_covers(drawback, sig) is False


def test_free_creature_payoff_serves_only_zero_cost_creatures():
    # Satoru's "no mana was spent to cast" payoff wants 0-cost CREATURES (Ornithopter),
    # not 0-cost mana rocks (Lotus Petal is {0} but not a creature) and not normal-cost
    # creatures. The serve ANDs mana_cost {0} with a creature type. Real oracle.
    sig = _sig("free_creature_payoff", "you")
    ornithopter = _card("Ornithopter")
    lotus_petal = _card("Lotus Petal")
    grizzly_bears = _card("Grizzly Bears")
    assert serves(ornithopter, sig) is True  # 0-cost creature
    assert serves(lotus_petal, sig) is False  # 0-cost, but not a creature
    assert serves(grizzly_bears, sig) is False  # creature, but not 0-cost


def test_mass_death_payoff_serves_board_wipes_and_mass_reanimation():
    # A "for each creature that died this turn" payoff (Tobias / Mahadi / Nevinyrral)
    # maximizes deaths-per-turn, then converts: board wipes (Wrath of God; Blasphemous
    # Act's "deals 13 damage to each creature") force the big turn, and MASS-reanimation
    # ("return ... all ... cards ... graveyard ... to the battlefield" — Storm of Souls,
    # Faith's Reward) refills the board after. Real oracle.
    sig = _sig("mass_death_payoff", "you")
    for name in (
        "Wrath of God",
        "Blasphemous Act",
        "Storm of Souls",
        "Faith's Reward",
    ):
        assert serves(_card(name), sig) is True, name
    # NOT single-target reanimation — Raise Dead returns ONE creature to hand; that's
    # the reanimator lane, not refilling a wiped board. Real oracle.
    raise_dead = _card("Raise Dead")
    assert serves(raise_dead, sig) is False


def test_land_protection_serves_indestructible_and_untargetable_lands():
    # A land-animation commander (Noyan Dar) wants its creature-lands kept alive: Terra
    # Eternal ("All lands have indestructible") and Tomik ("Lands … can't be the targets
    # of … your opponents"). A mana dork is not land protection. Real oracle.
    sig = _sig("land_protection", "you")
    terra_eternal = _card("Terra Eternal")
    tomik = _card("Tomik, Distinguished Advokist")
    assert serves(terra_eternal, sig) is True
    assert serves(tomik, sig) is True
    llanowar_elves = _card("Llanowar Elves")
    assert serves(llanowar_elves, sig) is False


def test_entered_attacker_serves_etb_pump_and_haste():
    # Samut wants enter-trigger pump + haste so a freshly-entered creature swings at
    # once. Primal Forcemage (+3/+3 on enter) and Ogre Battledriver (+2/+0 and haste on
    # enter) feed it; Impact Tremors (ETB-ping, no pump/haste) does not. Real oracle.
    sig = _sig("entered_attacker", "you")
    primal_forcemage = _card("Primal Forcemage")
    ogre_battledriver = _card("Ogre Battledriver")
    assert serves(primal_forcemage, sig) is True
    assert serves(ogre_battledriver, sig) is True
    impact_tremors = _card("Impact Tremors")
    assert serves(impact_tremors, sig) is False


def test_target_redirect_serves_spell_redirect():
    # Rayne wants target-redirect: Spellskite ("change a target of target spell or
    # ability to this creature") and Misdirection ("change the target of target spell").
    # A burn spell is not. Real oracle.
    sig = _sig("target_redirect", "you")
    spellskite = _card("Spellskite")
    misdirection = _card("Misdirection")
    assert serves(spellskite, sig) is True
    assert serves(misdirection, sig) is True
    lightning_bolt = _card("Lightning Bolt")
    assert serves(lightning_bolt, sig) is False


def test_free_spell_storm_serves_zero_cost_nonland_spells():
    # Thrasta wants free spells to chain: Lotus Petal and Memnite (both {0} nonland). A
    # 1-cmc creature isn't free; a 0-mv basic land isn't a spell cast. Real oracle.
    sig = _sig("free_spell_storm", "you")
    lotus_petal = _card("Lotus Petal")
    memnite = _card("Memnite")
    assert serves(lotus_petal, sig) is True
    assert serves(memnite, sig) is True
    llanowar_elves = _card("Llanowar Elves")
    forest = _card("Forest")
    assert serves(llanowar_elves, sig) is False  # not free
    assert serves(forest, sig) is False  # 0-mv but a land, not a spell


def test_scavenge_fuel_serves_high_power_creatures():
    # Varolz wants high-power creatures (scavenge = +1/+1 counters equal to power). Force
    # of Savagery (8/0) feeds it; a 2/2 bear does not. Real oracle.
    sig = _sig("scavenge_fuel", "you")
    force_of_savagery = _card("Force of Savagery")
    grizzly = _card("Grizzly Bears")
    assert serves(force_of_savagery, sig) is True
    assert serves(grizzly, sig) is False


def test_land_exchange_serves_land_swap():
    # Sharkey wants land-exchange: Political Trickery and Vedalken Plotter ("exchange
    # control of target land you control and target land an opponent controls"). A plain
    # ramp spell is not. Real oracle.
    sig = _sig("land_exchange", "you")
    political_trickery = _card("Political Trickery")
    vedalken_plotter = _card("Vedalken Plotter")
    assert serves(political_trickery, sig) is True
    assert serves(vedalken_plotter, sig) is True
    rampant_growth = _card("Rampant Growth")
    assert serves(rampant_growth, sig) is False


def test_life_payment_insurance_serves_dont_lose_at_zero():
    # Selenia wants life-loss insurance: Phyrexian Unlife ("don't lose the game for
    # having 0 or less life") and Angel's Grace ("you can't lose the game this turn"). A
    # mana dork is not insurance. Real oracle.
    sig = _sig("life_payment_insurance", "you")
    phyrexian_unlife = _card("Phyrexian Unlife")
    angels_grace = _card("Angel's Grace")
    assert serves(phyrexian_unlife, sig) is True
    assert serves(angels_grace, sig) is True
    llanowar_elves = _card("Llanowar Elves")
    assert serves(llanowar_elves, sig) is False


def test_target_own_payoff_serves_free_self_targeting():
    # Monk Gyatso wants free ways to target his own creatures: the en-Kor cycle ("{0}: …
    # dealt to target creature you control") triggers airbend on demand. A vanilla bear
    # is not a self-targeter. Real oracle.
    sig = _sig("target_own_payoff", "you")
    nomads_en_kor = _card("Nomads en-Kor")
    warrior_en_kor = _card("Warrior en-Kor")
    assert serves(nomads_en_kor, sig) is True
    assert serves(warrior_en_kor, sig) is True
    grizzly = _card("Grizzly Bears")
    assert serves(grizzly, sig) is False


def test_multicolor_matters_serves_payoffs_not_every_gold_card():
    # Niv wants multicolored PAYOFFS: General Ferrous Rokiric ("whenever you cast a
    # multicolored spell …") and Bring to Light (converge). A plain gold creature with no
    # multicolor payoff (Soulherder) is not credited — that would be the whole deck. Real
    # oracle.
    sig = _sig("multicolor_matters", "you")
    rokiric = _card("General Ferrous Rokiric")
    bring_to_light = _card("Bring to Light")
    assert serves(rokiric, sig) is True
    assert serves(bring_to_light, sig) is True
    soulherder = _card("Soulherder")
    assert serves(soulherder, sig) is False


def test_land_denial_serves_symmetric_land_punishers():
    # Taniwha wants symmetric land-bounce/sac stax: Mana Breach and Overburden ("that
    # player returns a land they control"). A mana dork is not land denial. Real oracle.
    sig = _sig("land_denial", "you")
    mana_breach = _card("Mana Breach")
    overburden = _card("Overburden")
    assert serves(mana_breach, sig) is True
    assert serves(overburden, sig) is True
    llanowar_elves = _card("Llanowar Elves")
    assert serves(llanowar_elves, sig) is False


def test_lose_unless_hand_serves_drawback_negation():
    # Phage wants to negate "you lose unless cast from hand": Netherborn Altar (commander
    # to hand), Platinum Angel ("can't lose the game"), Torpor Orb (ETBs don't trigger,
    # silencing the lose-trigger). A burn spell does not. Real oracle.
    sig = _sig("lose_unless_hand", "you")
    netherborn_altar = _card("Netherborn Altar")
    platinum_angel = _card("Platinum Angel")
    torpor_orb = _card("Torpor Orb")
    assert serves(netherborn_altar, sig) is True
    assert serves(platinum_angel, sig) is True
    assert serves(torpor_orb, sig) is True
    lightning_bolt = _card("Lightning Bolt")
    assert serves(lightning_bolt, sig) is False


def test_speed_matters_serves_cheap_unblockable_only():
    # ADR-0034 _matters sweep: the cheap-evasion enabler moved to the MAKER spec
    # (speed_makers) — advancing speed by chipping life is a maker-side avenue.
    # Vnwxt's speed ramps when an opponent loses life, so it wants CHEAP unblockable
    # creatures that connect early (Slither Blade, {U}). The cmc_max gate excludes an
    # expensive unblockable (Tidal Kraken, mv 8) — that's not the early-pressure
    # package. Rides a sub-avenue, so check _lane_covers. Real oracle.
    sig = _sig("speed_makers", "you")
    slither_blade = _card("Slither Blade")
    assert _lane_covers(slither_blade, sig) is True
    # Expensive unblockable is not the cheap early-pressure package (cmc gate):
    # Tidal Kraken's text is Slither Blade's word for word, only the mv differs.
    big_unblockable = _card("Tidal Kraken")
    assert _lane_covers(big_unblockable, sig) is False


def test_timing_control_serves_cast_and_activate_lock():
    # Dosan ("Players can cast spells only during their own turns") is a timing-lock
    # commander; City of Solitude is a near-copy ("cast spells AND ACTIVATE ABILITIES
    # only during their own turns") — the timing_control regex required "spells only"
    # contiguously and missed the "and activate abilities" variant. Real oracle.
    sig = _sig("timing_control", "opponents")
    city_of_solitude = _card("City of Solitude")
    assert serves(city_of_solitude, sig) is True


def test_damage_prevention_serves_block_any_number_and_redirect_soak():
    # A damage-PREVENTION commander (Oriss "{T}: prevent all damage to target creature")
    # turns a "block any number of creatures" wall (Palace Guard) or a redirect-to-one
    # soak (Pariah) into a hard lock — block/soak everything, then prevent it. These ride
    # a sub-avenue, so check _lane_covers. Real oracle.
    sig = _sig("damage_prevention", "you")
    palace_guard = _card("Palace Guard")
    pariah = _card("Pariah")
    assert _lane_covers(palace_guard, sig) is True
    assert _lane_covers(pariah, sig) is True
    grizzly = _card("Grizzly Bears")
    assert _lane_covers(grizzly, sig) is False


def test_island_matters_serves_island_makers():
    # Zhou Yu wants opponents to control Islands. Quicksilver Fountain (flood counters →
    # Islands) and Stormtide Leviathan ("All lands are Islands") feed it; a mana dork
    # does not. Real oracle.
    sig = _sig("island_matters", "you")
    quicksilver_fountain = _card("Quicksilver Fountain")
    stormtide_leviathan = _card("Stormtide Leviathan")
    assert serves(quicksilver_fountain, sig) is True
    assert serves(stormtide_leviathan, sig) is True
    llanowar_elves = _card("Llanowar Elves")
    assert serves(llanowar_elves, sig) is False


def test_tap_down_blockers_serves_opponent_tappers():
    # Tromokratis wants to tap opponents' creatures so they can't all block. Sleep ("Tap
    # all creatures target player controls") and Blustersquall ("Tap target creature you
    # don't control") feed it; a burn spell does not. Real oracle.
    sig = _sig("tap_down_blockers", "you")
    sleep = _card("Sleep")
    blustersquall = _card("Blustersquall")
    assert serves(sleep, sig) is True
    assert serves(blustersquall, sig) is True
    lightning_bolt = _card("Lightning Bolt")
    assert serves(lightning_bolt, sig) is False


def test_per_target_payoff_serves_variable_target_spells():
    # Hinata (spells cost {1} less per target) wants spells whose target COUNT scales —
    # X-target and "any number of targets" — so the discount compounds. Aurelia's Fury
    # (divided among any number of targets) and Distorting Wake (X target permanents) are
    # premium; a single-target removal (Doom Blade) gives only {1} off and isn't the
    # payoff. Real oracle.
    sig = _sig("per_target_payoff", "you")
    aurelias_fury = _card("Aurelia's Fury")
    distorting_wake = _card("Distorting Wake")
    assert serves(aurelias_fury, sig) is True
    assert serves(distorting_wake, sig) is True
    # Single-target removal is only a {1} discount — not the multi-target payoff.
    doom_blade = _card("Doom Blade")
    assert serves(doom_blade, sig) is False


def test_ability_strip_payoff_serves_big_drawback_creatures():
    # Abigale strips a target's abilities + buffs it, so she wants BIG creatures whose
    # crippling drawback she removes (Rotting Regisaur 7/6 upkeep-discard; Nyxathid 7/7
    # that shrinks). The serve ANDs a crippling-drawback clause with power >= 5: a big
    # vanilla beater (Colossal Dreadmaw — no drawback) and a small drawback creature
    # (Scarred Puma — power 2) are both excluded. Real oracle.
    sig = _sig("ability_strip_payoff", "you")
    rotting_regisaur = _card("Rotting Regisaur")
    nyxathid = _card("Nyxathid")
    assert serves(rotting_regisaur, sig) is True
    assert serves(nyxathid, sig) is True
    # Big body, no drawback to strip → not the payoff.
    colossal_dreadmaw = _card("Colossal Dreadmaw")
    assert serves(colossal_dreadmaw, sig) is False
    # Crippling drawback but too small to be worth stripping + buffing.
    scarred_puma = _card("Scarred Puma")
    assert serves(scarred_puma, sig) is False


def test_arcane_matters_serves_arcane_subtype_spells():
    # An Arcane-tribal commander wants Arcane-subtype spells (CR 205.3k). Eerie
    # Procession (Sorcery — Arcane) and Psychic Puppetry (Instant — Arcane) feed it; a
    # plain non-Arcane instant (Lightning Bolt) does not. Real oracle.
    sig = _sig("arcane_matters", "you")
    eerie = _card("Eerie Procession")
    psychic_puppetry = _card("Psychic Puppetry")
    assert serves(eerie, sig) is True
    assert serves(psychic_puppetry, sig) is True
    lightning_bolt = _card("Lightning Bolt")
    assert serves(lightning_bolt, sig) is False


def test_tribal_serve_matches_type_tokens_never_substrings():
    # A tribal lane's type serve matches whole type-line TOKENS (CR 205.3 —
    # each subtype is its own word), never substrings of another type. The
    # substring behavior served every Pirate on the Rat lane ("pi[rat]e") and
    # every Mountain on a Mount lane — user-reported from the deck-forge UI.
    # Real snapshot records.
    rat_sig = Signal(
        key="type_matters", scope="you", subject="Rat", text="", source="c"
    )
    assert serves(test_card("Marrow-Gnawer"), rat_sig) is True
    assert serves(test_card("Daring Saboteur"), rat_sig) is False  # Pirate
    # planeswalker type line "Legendary Planeswalker — Angrath" contains 'rat'
    assert serves(test_card("Angrath, the Flame-Chained"), rat_sig) is False

    mount_sig = Signal(
        key="type_matters", scope="you", subject="Mount", text="", source="c"
    )
    assert serves(test_card("Bulwark Ox"), mount_sig) is True  # Ox Mount
    assert serves(test_card("Mountain"), mount_sig) is False

    orc_sig = Signal(
        key="type_matters", scope="you", subject="Orc", text="", source="c"
    )
    assert serves(test_card("Orcish Lumberjack"), orc_sig) is True
    assert serves(test_card("Divination"), orc_sig) is False  # "s[orc]ery"


def test_enlist_matters_serves_enlisters_and_stayback_fodder():
    # Aradesh wants the enlist creatures themselves (keyword bearers) on the main serve,
    # and big stay-back fodder to tap (the sub-avenue): Relic Golem (6/6, can't attack
    # unless an opponent has 8+ graveyard cards) is ideal — tap it for 6 power. A vanilla
    # bear is neither. Real oracle.
    sig = _sig("has_enlist", "you")
    benalish = _card("Benalish Faithbonder")
    relic_golem = _card("Relic Golem")
    assert serves(benalish, sig) is True  # enlist creature (keyword)
    assert _lane_covers(relic_golem, sig) is True  # stay-back fodder (sub-avenue)
    grizzly = _card("Grizzly Bears")
    assert _lane_covers(grizzly, sig) is False


def test_power_tap_engine_serves_untap_effects():
    # A power-scaling tap engine (Mona Lisa) wants UNTAP effects to re-tap. Witch's Web
    # ("Untap it.") and Kiora's Follower ("Untap another target permanent.") feed it; a
    # burn spell (Lightning Bolt) does not. Real oracle.
    sig = _sig("power_tap_engine", "you")
    witchs_web = _card("Witch's Web")
    kioras_follower = _card("Kiora's Follower")
    assert serves(witchs_web, sig) is True
    assert serves(kioras_follower, sig) is True
    lightning_bolt = _card("Lightning Bolt")
    assert serves(lightning_bolt, sig) is False


def test_exert_matters_serves_exert_creatures():
    # A pseudo-vigilance commander (Johan) wants exert creatures — Champion of Rhonas
    # (Exert keyword). A vanilla creature is not served. Real oracle.
    sig = _sig("exert_matters", "you")
    champion = _card("Champion of Rhonas")
    grizzly = _card("Grizzly Bears")
    assert serves(champion, sig) is True
    assert serves(grizzly, sig) is False


def test_type_change_serves_type_changers_not_tribal_anthems():
    # A type-hoser (Gor Muldrak) wants genuine creature-type CHANGERS — Standardize
    # ("Each creature becomes that type"), Unnatural Selection ("Target creature becomes
    # that type") — so it can force opponents into the punished type. A tribal anthem
    # that merely "choose a creature type" then buffs your own board (Icon of Ancestry)
    # is NOT a changer. Real oracle.
    sig = _sig("type_change", "you")
    standardize = _card("Standardize")
    unnatural_selection = _card("Unnatural Selection")
    assert serves(standardize, sig) is True
    assert serves(unnatural_selection, sig) is True
    icon_of_ancestry = _card("Icon of Ancestry")
    assert serves(icon_of_ancestry, sig) is False


def test_recast_etb_serves_aggressive_etb_not_activated_drain():
    # A Sneak/bounce-replay commander (Oroku Saki) recasts cheap aggressive-ETB creatures
    # to repeat the bleed. Virus Beetle ("When this creature enters, each opponent
    # discards a card") feeds it; Engine Rat's drain is an ACTIVATED ability ("{5}{B}:
    # Each opponent loses 2 life"), not an enter-trigger, so recasting it does nothing.
    # Real oracle.
    sig = _sig("recast_etb", "you")
    virus_beetle = _card("Virus Beetle")
    engine_rat = _card("Engine Rat")
    assert serves(virus_beetle, sig) is True
    assert serves(engine_rat, sig) is False


def test_damage_redirect_serves_creature_dealt_damage_payoffs():
    # A redirect-to-self commander (Daughter of Autumn: "next 1 damage to target white
    # creature is dealt to Daughter instead" — CR 614.9 redirection replacement) soaks
    # the damage on HERSELF, so it wants payoffs watching a CREATURE YOU CONTROL being
    # dealt damage (Rite of Passage) or an Aura on the soak creature (Druid's Call).
    # NOT generic enrage ("whenever THIS creature is dealt damage" — Siegehorn): the
    # original creature is never dealt the redirected damage, so its trigger can't fire.
    # Real oracle.
    sig = _sig("damage_redirect", "you")
    rite_of_passage = _card("Rite of Passage")
    druids_call = _card("Druid's Call")
    assert serves(rite_of_passage, sig) is True
    assert serves(druids_call, sig) is True
    # Generic enrage targets ITSELF, which never receives the redirected damage.
    siegehorn = _card("Siegehorn Ceratops")
    assert serves(siegehorn, sig) is False


def test_outlaw_matters_serves_token_makers_and_recursion():
    # Vial Smasher's outlaw payoff wants cards that MAKE outlaw tokens (Mercenary /
    # Pirate / Rogue / Assassin / Warlock) and outlaw RECURSION — not just creatures
    # that ARE outlaws. The serve had only the type-line gate + "outlaws you control".
    # Real oracle.
    sig = _sig("outlaw_matters", "you")
    brimstone_roundup = _card("Brimstone Roundup")
    back_in_town = _card("Back in Town")
    raise_the_alarm = _card("Raise the Alarm")
    assert serves(brimstone_roundup, sig) is True  # makes Mercenary tokens
    assert serves(back_in_town, sig) is True  # returns outlaw creature cards
    assert serves(raise_the_alarm, sig) is False  # non-outlaw (Soldier) tokens


def test_opponent_exile_serves_the_exile_enablers():
    # Umbris grows per "card your opponents own in exile", so it wants the ENABLERS that
    # exile opponents' cards (Leyline of the Void, Ashiok, Bojuka Bog). ADR-0034 split
    # those graveyard-hate DOERS into opponent_exile_makers (the maker serve spec); the
    # opponent_exile_matters payoff lane keeps the "opponents own in exile" reference
    # counters. The enablers serve from the makers spec. Real oracle.
    sig = _sig("opponent_exile_makers", "opponents")
    leyline_of_the_void = _card("Leyline of the Void")
    ashiok_dream_render = _card("Ashiok, Dream Render")
    deep_analysis = _card("Deep Analysis")
    assert serves(leyline_of_the_void, sig) is True  # exile-instead-of-GY enabler
    assert serves(ashiok_dream_render, sig) is True  # exile each opponent's graveyard
    assert serves(deep_analysis, sig) is False  # exiles your own card, not opponents'


def test_cast_from_exile_serves_suspend_foretell_rebound():
    # Suspend (CR 702.62a: when the last time counter is removed, you may play it FROM
    # EXILE), Foretell (702.143), and Rebound (702.88a: "cast this card from exile") all
    # cast the card from exile — a cast-from-exile commander wants them. The serve only had
    # "plot" + cast-from-exile prose, so the other keywords were missed. Authoritative
    # Scryfall keywords array (not regex-guessed from prose). Real oracle.
    sig = _sig("cast_from_exile", "you")
    profane_tutor = _card("Profane Tutor")
    behold_the_multiverse = _card("Behold the Multiverse")
    staggershock = _card("Staggershock")
    lightning_bolt = _card("Lightning Bolt")
    assert serves(profane_tutor, sig) is True  # Suspend
    assert serves(behold_the_multiverse, sig) is True  # Foretell
    assert serves(staggershock, sig) is True  # Rebound
    assert serves(lightning_bolt, sig) is False  # no cast-from-exile


def test_keyword_soup_serves_keyword_dense_creatures():
    # The sweep 'keyword_soup' signal (Rayami absorbs keywords from dead creatures; Akroma
    # Vision / Indominus Rex share them) was stuck on the narrow sweep regex, not the
    # keyword-count serve that 'keyword_soup_makers' (Odric) already had — so keyword-
    # dense creatures weren't served. Real oracle.
    sig = _sig("keyword_soup", "you")
    venomthrope = _card("Venomthrope")
    stonecoil_serpent = _card("Stonecoil Serpent")
    grizzly_bears = _card("Grizzly Bears")
    assert serves(venomthrope, sig) is True  # 3 evergreen keywords
    assert serves(stonecoil_serpent, sig) is True  # 3 evergreen keywords
    assert serves(grizzly_bears, sig) is False  # no keywords


def test_color_hoser_serves_anti_color_hate():
    # color_hoser is opened by anti-color commanders (Major Teroh "exile all black",
    # Ascendant Evincar, Crovax, Dromar, Llawan, Jaya) but its serve matched only Painter
    # changers. Those decks want anti-color HATE — "[color] creatures can't attack",
    # "protection from [color]", "destroy all [color] creatures". Real oracle.
    sig = _sig("color_hoser", "you")
    light_of_day = _card("Light of Day")
    absolute_grace = _card("Absolute Grace")
    perish = _card("Perish")
    wrath_of_god = _card("Wrath of God")
    assert serves(light_of_day, sig) is True  # [color] creatures can't attack/block
    assert serves(absolute_grace, sig) is True  # protection from [color]
    assert serves(perish, sig) is True  # destroy all [color] creatures
    assert serves(wrath_of_god, sig) is False  # "all creatures" (no color) stays out


def test_color_change_serves_color_conditional_payoffs():
    # A color-CHANGER (Blind Seer: "target spell or permanent becomes the color of your
    # choice") enables color-conditional mass effects — make everything one color, then
    # "return/destroy all [color]" is a board wipe. Color is a continuously-checked
    # characteristic (CR 105 / 613 layer 5, confirmed via rules-lawyer), so this is a real
    # mechanical synergy. The serve only credited other color-CHANGERS. Real oracle.
    sig = _sig("color_change", "you")
    hibernation = _card("Hibernation")
    wash_out = _card("Wash Out")
    llawan = _card("Llawan, Cephalid Empress")
    wrath_of_god = _card("Wrath of God")
    assert serves(hibernation, sig) is True  # return all GREEN permanents
    assert serves(wash_out, sig) is True  # return all permanents of the color
    assert serves(llawan, sig) is True  # return all BLUE creatures
    assert serves(wrath_of_god, sig) is False  # "all creatures" (no color) stays out


def test_lifeloss_drain_serves_damage_to_opponents():
    # Damage to a player IS life loss (CR 120.3a), so pingers / group-slug that deal
    # damage to opponents (Kessig Flamebreather) are drain payoffs — a drain commander
    # (Ob Nixilis, Rakdos, Valgavoth) wants them. The serve had only direct "loses life"
    # prose. A creature-only ping (removal) stays out. Real oracle.
    sig = _sig("lifeloss_matters", "opponents")
    kessig_flamebreather = _card("Kessig Flamebreather")
    sulfuric_vortex = _card("Sulfuric Vortex")
    flame_slash = _card("Flame Slash")
    assert serves(kessig_flamebreather, sig) is True  # damage to each opponent = drain
    assert serves(sulfuric_vortex, sig) is True  # group-slug "that player" = drain
    assert serves(flame_slash, sig) is False  # creature-only, no opponent life loss


def test_token_maker_serves_offspring_keyword():
    # Offspring (CR keyword) makes a 1/1 token copy of the creature — token-making that
    # lives in the reminder text deck-forge strips, so it needs the authoritative Scryfall
    # keyword. A go-wide / token deck wants the extra body. (phase_crosscheck-surfaced.)
    sig = _sig("token_maker", "you")
    prosperous_bandit = _card("Prosperous Bandit")
    grizzly_bears = _card("Grizzly Bears")
    assert serves(prosperous_bandit, sig) is True  # Offspring = makes a token copy
    assert serves(grizzly_bears, sig) is False


def test_discard_matters_serves_self_discard_outlets():
    # A discard-payoff commander (Rielle "whenever you discard ... draw") wants self-
    # discard OUTLETS: wheels ("discard all the cards in your hand"), "discard X cards"
    # as a cost (Turbulent Dreams, Firestorm). The serve only had loot ("discard a/two:")
    # and "draw then discard". Real oracle.
    sig = _sig("discard_matters", "you")
    tolarian = _card("Tolarian Winds")
    firestorm = _card("Firestorm")
    assert _lane_covers(tolarian, sig) is True
    assert _lane_covers(firestorm, sig) is True
    # Over-fire guard: forcing an OPPONENT to discard is hand-attack, not a self-outlet.
    opp_discard = _card("Mind Rot")
    assert _lane_covers(opp_discard, sig) is False


SELF_MILL = _card("Stitcher's Supplier")
OPPONENT_MILL = _card("Maddening Cacophony")
TOKEN_MAKER = _card("Raise the Alarm")
BURN = _card("Lightning Bolt")
LIFEGAIN = _card("Sacred Nectar")


def test_opponents_graveyard_signal_served_by_opponent_mill_not_self_mill():
    sig = _sig("graveyard_matters", "opponents")
    assert serves(OPPONENT_MILL, sig) is True
    assert serves(SELF_MILL, sig) is False


def test_opponents_graveyard_serves_symmetric_mill_and_their_graveyard_reanimation():
    # An opponent-graveyard reanimator (Tariel, Valgavoth) wants two things the lane
    # missed: SYMMETRIC mill ("each player mills" fills opponents' graveyards too) and
    # reanimation that pulls from ANOTHER player's graveyard ("creature card in that
    # player's graveyard. Put those onto the battlefield"). Breach the Multiverse does
    # both. Real oracle.
    sig = _sig("graveyard_matters", "opponents")
    breach = _card("Breach the Multiverse")
    sepulchral = _card("Sepulchral Primordial")
    assert serves(breach, sig) is True
    assert serves(sepulchral, sig) is True
    # Over-fire guard: pure self-mill (fills only YOUR graveyard) is not this lane.
    assert serves(SELF_MILL, sig) is False


def test_your_graveyard_signal_served_by_self_mill():
    sig = _sig("graveyard_matters", "you")
    assert serves(SELF_MILL, sig) is True


def test_combat_damage_to_opp_serves_damage_amplifiers():
    # A commander that deals combat damage to opponents (Shredder, Virtus) wants
    # damage / life-loss AMPLIFIERS — Wound Reflection doubles opponents' life loss,
    # Gratuitous Violence doubles creature damage. They sit in lifeloss_matters, a
    # sibling lane the combat-damage commander never opened. Real oracle.
    sig = _sig("combat_damage_to_opp", "opponents")
    wound_reflection = _card("Wound Reflection")
    gratuitous = _card("Gratuitous Violence")
    assert _lane_covers(wound_reflection, sig) is True
    assert _lane_covers(gratuitous, sig) is True
    # Over-fire guard: a plain lifegain spell is not a damage amplifier.
    lifegain = _card("Healing Salve")
    assert _lane_covers(lifegain, sig) is False


def test_clone_serves_high_value_dies_trigger_creatures():
    # A clone deck (The Ever-Changing 'Dane) copies high-mana-value creatures with a
    # strong DEATH trigger — the copy re-fires the trigger when it dies (Kokusho drains,
    # Keiga steals, Junji). clone served big bodies (power>=6) but not these (power 4-5,
    # cmc 5-6). The serve needs "self-dies VALUE trigger AND mana value >= 5" — an AND
    # the flat OR-Serve couldn't express. Real oracle.
    sig = _sig("clone_makers", "you")
    kokusho = _card("Kokusho, the Evening Star")
    junji = _card("Junji, the Midnight Sky")
    assert _lane_covers(kokusho, sig) is True
    assert _lane_covers(junji, sig) is True
    # Over-fire guard: a cmc-1 undying body has a dies trigger but is NOT a clone bomb.
    young_wolf = _card("Young Wolf")
    assert _lane_covers(young_wolf, sig) is False


def test_ninjutsu_lane_serves_ninja_creatures():
    # A ninjutsu deck (Yuriko, Satoru, Higure) wants the NINJA creatures themselves —
    # the ninjutsu payoff swapped in via an unblocked attacker — not just the evasion
    # carriers. The lane served evasion keywords but not the ninjutsu keyword. Real card.
    sig = _sig("has_ninjutsu", "you")
    # Satoru himself carries no Ninjutsu keyword (he GRANTS ninjutsu to cards in
    # hand), so the keyword branch is exercised by a real ninjutsu Ninja.
    deep_hours = _card("Ninja of the Deep Hours")
    silver_fur = _card("Silver-Fur Master")
    assert _lane_covers(deep_hours, sig) is True
    assert _lane_covers(silver_fur, sig) is True
    # Commander ninjutsu is a ninjutsu variant (CR 702.49d): Yuriko — the canonical
    # ninjutsu commander — carries only the "Commander ninjutsu" keyword, so the lane
    # missed her and commander_fit then mis-flagged the deck "built for a different
    # commander". The serve must credit the variant.
    yuriko = _card("Yuriko, the Tiger's Shadow")
    assert _lane_covers(yuriko, sig) is True
    # Over-fire guard: a vanilla creature is not a ninjutsu card.
    bear = _card("Grizzly Bears")
    assert _lane_covers(bear, sig) is False


def test_aristocrats_lanes_serve_death_doublers_and_dies_return_grants():
    # An aristocrats/death commander (Orca) wants death-trigger DOUBLERS (Teysa, Drivnod
    # — the deaths-Panharmonicon) and dies-return GRANTERS (Feign Death, Supernatural
    # Stamina — loop a key creature with a sac outlet). death/sacrifice served neither.
    # Real oracle.
    drivnod = _card("Drivnod, Carnage Dominus")
    feign_death = _card("Feign Death")
    for key, scope in (("death_matters", "any"), ("sacrifice_outlets", "you")):
        sig = _sig(key, scope)
        assert _lane_covers(drivnod, sig) is True, key
        assert _lane_covers(feign_death, sig) is True, key
    # Over-fire guard: an ETB-trigger doubler (Panharmonicon) is NOT a DEATH-trigger
    # doubler — the death-doubler branch must require "creature dying", not "entering".
    panharmonicon = _card("Panharmonicon")
    assert _lane_covers(panharmonicon, _sig("death_matters", "any")) is False


def test_blink_serves_self_bounce_recast_engines():
    # A blink/flicker deck wants self-bounce recast engines (Whitemane Lion, Kor
    # Skyfisher) — bouncing your own ETB creature and recasting re-fires the ETB, the
    # same value blink gives. The serve missed the "you may return ANOTHER TARGET
    # creature you control" wording (Jeskai Barricade), and blink_flicker lacked the
    # self-bounce extra. Real oracle.
    sig = _sig("blink_flicker", "you")
    jeskai = _card("Jeskai Barricade")
    whitemane = _card("Whitemane Lion")
    assert _lane_covers(jeskai, sig) is True
    assert _lane_covers(whitemane, sig) is True


def test_creature_etb_served_by_token_maker_not_burn():
    sig = _sig("creature_etb", "you")
    assert serves(TOKEN_MAKER, sig) is True
    assert serves(BURN, sig) is False


def test_lifegain_served_by_lifegain_card():
    assert serves(LIFEGAIN, _sig("lifegain_matters", "you")) is True


def test_spec_for_returns_label_and_avenue():
    spec = spec_for(_sig("creature_etb", "you"))
    assert spec is not None
    assert spec.label
    assert spec.avenue


def test_search_filters_inject_color_identity_and_format():
    filters = search_filters(
        _sig("creature_etb", "you"), color_identity="GW", fmt="commander"
    )
    assert filters["color_identity"] == "GW"
    assert filters["format"] == "commander"
    # carries the spec's discriminating filter (oracle and/or presets)
    assert "oracle" in filters or "preset_names" in filters


def test_unknown_signal_has_no_spec_and_serves_false():
    sig = _sig("totally_unknown_signal", "you")
    assert spec_for(sig) is None
    assert serves(TOKEN_MAKER, sig) is False


# --- reanimator payoff (the Celes case) ----------------------------------------
# The avenue must surface the two enabler families that trigger the payoff:
# reanimation effects (a creature enters from a graveyard) and cast-from-graveyard
# creatures (escape/disturb). Self-mill alone is FUEL, not a reanimator enabler.
REANIMATION_SPELL = _card("Zombify")
ESCAPE_CREATURE = _card("Woe Strider")
GRAVEYARD_RETURN = _card("Regrowth")


def test_reanimator_served_by_reanimation_and_escape():
    sig = _sig("reanimator", "you")
    assert serves(REANIMATION_SPELL, sig) is True
    assert serves(ESCAPE_CREATURE, sig) is True
    # graveyard-return to HAND is not a reanimator enabler (no creature re-enters play)
    assert serves(GRAVEYARD_RETURN, sig) is False
    # pure self-mill is fuel, not an enabler
    assert serves(SELF_MILL, sig) is False


def test_reanimator_credits_persist_and_undying():
    # CR 702.79 / 702.93: persist & undying return the creature FROM THE GRAVEYARD to
    # the battlefield, so it re-enters from a graveyard — a reanimator payoff fires.
    sig = _sig("reanimator", "you")
    persist = _card("Murderous Redcap")
    undying = _card("Geralf's Messenger")
    assert serves(persist, sig) is True
    assert serves(undying, sig) is True


def test_reanimator_spec_searches_with_a_discriminator():
    spec = spec_for(_sig("reanimator", "you"))
    assert spec is not None
    assert spec.label
    assert spec.avenue
    filters = search_filters(
        _sig("reanimator", "you"), color_identity="BRW", fmt="commander"
    )
    assert "oracle" in filters or "preset_names" in filters


# --- aristocrats death-drain payoff (Blood Artist / Zulaport) -------------------
BLOOD_ARTIST = _card("Blood Artist")
ZULAPORT = _card("Zulaport Cutthroat")


def test_death_drain_served_by_both_aristocrats_and_sacrifice_lanes():
    # The drain payoff must be on-theme for BOTH the death lane and the sacrifice lane
    # (a sac-outlet commander like Yawgmoth opens sacrifice_outlets, not death_matters).
    for sig in (_sig("death_matters", "any"), _sig("sacrifice_outlets", "you")):
        assert serves(BLOOD_ARTIST, sig) is True
        assert serves(ZULAPORT, sig) is True


def test_sacrifice_lane_does_not_serve_plain_lifegain():
    # A bare lifegain card is not a sacrifice/aristocrats enabler.
    assert serves(LIFEGAIN, _sig("sacrifice_outlets", "you")) is False


# --- landfall: payoffs + extra lands + lands-from-graveyard ---------------------
LANDFALL_PAYOFF = _card("Lotus Cobra")
EXTRA_LANDS = _card("Azusa, Lost but Seeking")
LANDS_FROM_GRAVE = _card("Ramunap Excavator")


def test_landfall_serves_payoffs_extra_lands_and_recursion():
    sig = _sig("landfall", "you")
    assert serves(LANDFALL_PAYOFF, sig) is True  # the payoff itself (was uncovered)
    assert serves(EXTRA_LANDS, sig) is True  # extra-land enabler
    assert serves(LANDS_FROM_GRAVE, sig) is True  # land recursion (was uncovered)


def test_landfall_does_not_serve_unrelated_burn():
    assert serves(BURN, _sig("landfall", "you")) is False


# --- blink: the lane must surface ETB-value creatures + ETB-trigger doublers ----
ETB_VALUE_CREATURE = _card("Mulldrifter")
ETB_DOUBLER = _card("Panharmonicon")
FLICKER_EFFECT = _card("Ephemerate")


def test_blink_lane_surfaces_targets_and_doublers_not_just_flicker():
    sig = _sig("blink_flicker", "you")
    assert _lane_covers(FLICKER_EFFECT, sig) is True  # the flicker effect (existing)
    assert _lane_covers(ETB_VALUE_CREATURE, sig) is True  # the target to flicker (new)
    assert _lane_covers(ETB_DOUBLER, sig) is True  # ETB-trigger doubler (new)


def test_blink_lane_does_not_surface_vanilla_creature():
    vanilla = _card("Grizzly Bears")
    assert _lane_covers(vanilla, _sig("blink_flicker", "you")) is False


# --- counter doublers must surface across every counter lane -------------------
DOUBLING_SEASON = _card("Doubling Season")
HARDENED_SCALES = _card("Hardened Scales")
COUNTER_LANES = [
    ("plus_one_matters", "any"),
    ("proliferate_matters", "you"),
    ("self_counter_grow", "you"),
    ("counter_manipulation", "you"),
    ("counter_distribute", "you"),
]


def test_counter_doublers_surface_across_every_counter_lane():
    # A counters commander wants the doublers (Doubling Season / Hardened Scales /
    # Corpsejack) no matter which counter lane its oracle happens to open.
    for key, scope in COUNTER_LANES:
        sig = _sig(key, scope)
        assert _lane_covers(DOUBLING_SEASON, sig), f"{key}: Doubling Season uncovered"
        assert _lane_covers(HARDENED_SCALES, sig), f"{key}: Hardened Scales uncovered"


def test_self_growth_lane_surfaces_counter_placement_support():
    # A self-growth counters commander (Skullbriar) wants +1/+1 counter placement, not
    # just doublers.
    placement = _card("Unexpected Fangs")
    assert _lane_covers(placement, _sig("self_counter_grow", "you")) is True


def test_combat_lane_credits_single_creature_attack_triggers():
    sig = _sig("attack_matters", "you")
    aggro = _card("Vicious Conquistador")
    defensive = _card("Isperia, Supreme Judge")
    assert serves(aggro, sig) is True
    assert serves(defensive, sig) is False  # "attacks you" is not an aggro payoff


def test_etb_lane_surfaces_value_creatures_and_doublers():
    sig = _sig("creature_etb", "you")
    assert _lane_covers(ETB_VALUE_CREATURE, sig) is True  # Mulldrifter
    assert _lane_covers(ETB_DOUBLER, sig) is True  # Panharmonicon


def test_aristocrats_credits_plural_creatures_die():
    # "Whenever one or more creatures die" (Morbid Opportunist) is the same payoff as
    # "dies" — plural phrasing must not be missed. ADR-0027: death_matters migrated to
    # the Card IR; the plural "creatures die" branch rides the byte-identical
    # _DEATH_MATTERS_MIRROR (scope "any") on the IR path.

    # Real production extractor over the real card (the plural "creatures die" branch
    # rides the kept mirror).
    keys = {(s.key, s.scope) for s in test_signals("Morbid Opportunist")}
    assert any(k == "death_matters" for k, _ in keys)
    assert serves(test_card("Morbid Opportunist"), _sig("death_matters", "any")) is True


def test_vehicles_lane_opens_for_granter_and_credits_support():
    # A vehicle-GRANTER ("becomes a Vehicle … gains crew") must open the Vehicles lane,
    # and vehicle SUPPORT (cheat a Vehicle into play, mana to cast Vehicle spells) must
    # be credited — not just core "Vehicles you control / crew" text.
    # ADR-0027: vehicles_matter migrated to the Card IR — the Vehicle-GRANTER
    # ("becomes a Vehicle … gains crew") lane fires through the hybrid path (the
    # byte-identical VEHICLES_MATTER_MIRROR kept word mirror), not the pure regex path.
    assert any(
        k == "vehicles_matter"
        for k, _ in {(s.key, s.scope) for s in test_signals("Captain Rex Nebula")}
    )
    oviya = _card("Oviya, Automech Artisan")
    stablemaster = _card("Intrepid Stablemaster")
    assert serves(oviya, _sig("vehicles_matter", "you")) is True
    assert serves(stablemaster, _sig("vehicles_matter", "you")) is True


def test_become_a_type_cards_match_the_type_lane():
    # "Become"/"are" TYPE granters belong in that type's deck: artifact-makers in
    # artifact decks, tribal type-granters in that tribe's deck.
    for n in ("Mycosynth Lattice", "Liquimetal Coating", "March of the Machines"):
        assert serves(_card(n), _sig("artifacts_matter", "you")) is True, n
    # Type-AGNOSTIC tribal enablers (Xenograft, Arcane Adaptation) GRANT the chosen type
    # to your board — they grow the tribe, so they're credited to EVERY tribe, but via the
    # dedicated "enabler" sub-avenue, NOT as a payoff or a tribe member (B1).
    goblin = Signal(
        key="type_matters", scope="you", subject="Goblin", text="", source="c"
    )
    goblin_payoff = spec_for(goblin).extras[0]  # the "Goblin payoffs" sub-avenue
    # B1 keeps granters out of the main serve's BODY arms (type line / oracle); the
    # ADR-0040 structural arm then credits them at the serve level by their own
    # type_changers idents — a hand-typed record (no oracle_id) never reached that
    # arm, so the real card pins both halves.
    main = spec_for(goblin).serve
    body_arms = dataclasses.replace(main, signal_idents=frozenset())
    for n in ("Xenograft", "Arcane Adaptation"):
        card = _card(n)
        assert _lane_covers(card, goblin) is True, n  # surfaced via the enabler lane
        assert body_arms.matches(card) is False, n  # not a tribe member (B1)
        assert main.matches(card) is True, n  # credited structurally (ADR-0040)
        payoff_serve = goblin_payoff.serve or serve_from_dict(goblin_payoff.search)
        assert payoff_serve.matches(card) is False, n  # and NOT a payoff


def test_grant_become_credited_for_clone_enchantment_food():
    # DB-mined grant phrasings (search the DB, don't guess) — a clone ("as a copy of any
    # creature"), an enchantment-grant ("are enchantments in addition"), and a Food-grant
    # ("are Foods in addition") must hit their lanes (main serve or a sub-avenue).
    cases = [
        ("clone_makers", _card("Clone")),
        ("enchantments_matter", _card("Enchanted Evening")),
        ("food_matters", _card("The Food Court")),
        ("domain_matters", _card("Prismatic Omen")),
        ("color_change", _card("Painter's Servant")),
        ("color_change", _card("Indigo Faerie")),
    ]
    for key, card in cases:
        assert _lane_covers(card, _sig(key, "you")) is True, (key, card["name"])


def test_edicts_and_third_person_sac_feed_aristocrats():
    # Edict creatures ("each player sacrifices a creature" — Plaguecrafter, Fleshbag)
    # are the aristocrats sac package; the serve matched only "sacrifice a", not the
    # 3rd-person "sacrifices a".
    for key, scope in [("sacrifice_outlets", "you"), ("death_matters", "any")]:
        for n in ("Plaguecrafter", "Fleshbag Marauder"):
            card = _card(n)
            assert _lane_covers(card, _sig(key, scope)), (key, n)


def test_pillowfort_and_tax_feed_stax():
    sig = _sig("stax_taxes", "opponents")
    for n in ("Ghostly Prison", "Smothering Tithe"):
        assert _lane_covers(_card(n), sig), n


def test_power_matters_credits_threshold_payoffs():
    # power_matters should credit the PAYOFFS that key on power thresholds (Garruk's
    # Uprising, ferocious dorks like Whisperer of the Wilds), not only the big
    # bodies themselves.
    sig = _sig("power_matters", "you")
    for n in ("Garruk's Uprising", "Whisperer of the Wilds"):
        assert serves(_card(n), sig) is True, n


def test_being_an_artifact_or_enchantment_by_type_is_on_theme():
    # The big "floor" miss: a card is on-theme for an artifacts/enchantments deck by
    # BEING that type (affinity/metalcraft/constellation/count all count the card),
    # even with no "artifact"/"enchantment" oracle text. EDHREC synergy proves it —
    # artifact lands / rocks are disproportionately in artifact decks.
    art = _sig("artifacts_matter", "you")
    for n in ("Seat of the Synod", "Mind Stone", "Solemn Simulacrum"):
        assert serves(_card(n), art) is True, n
    ench = _sig("enchantments_matter", "you")
    spirited = _card("Spirited Companion")
    assert serves(spirited, ench) is True


def test_artifact_subtypes_count_as_artifacts():
    # CR 205.3g: Equipment, Vehicle, etc. ARE artifact types, so a card that makes or
    # cares about them is an artifact-count / affinity / metalcraft enabler.
    sig = _sig("artifacts_matter", "you")
    cards = [
        ("Vehicle maker", "Create a colorless Vehicle artifact token."),
        ("Equipment count", "For each Equipment you control, scry 1."),
        ("Vehicles lord", "Vehicles you control get +1/+1."),
    ]
    for n, o in cards:
        assert (
            serves({"name": n, "type_line": "Artifact", "oracle_text": o}, sig) is True
        ), n


def test_enchantment_subtypes_count_as_enchantments():
    # CR 205.3h: Aura, Saga, Class, Curse, etc. ARE enchantment types, so a card that
    # makes or cares about them is a constellation / enchantment-count enabler.
    sig = _sig("enchantments_matter", "you")
    cards = [
        ("Saga count", "For each Saga you control, draw a card."),
        ("Auras lord", "Auras you control have totem armor."),
        ("Class matters", "Whenever a Class you control levels up, gain 1 life."),
    ]
    for n, o in cards:
        assert (
            serves({"name": n, "type_line": "Enchantment", "oracle_text": o}, sig)
            is True
        ), n


def test_enchantment_token_makers_are_enchantments():
    # Role (Aura Role) and Shard tokens are enchantment tokens, so their makers make
    # enchantments — constellation / enchantment-count fuel.
    # Cursed Courtier is a real Role maker; the other two are fictional clause
    # probes for the Shard / Aura-token wordings.
    makers = [
        _card("Cursed Courtier"),
        {
            "name": "Shard Maker",
            "type_line": "Enchantment",
            "oracle_text": "Create a Shard token.",
        },
        {
            "name": "Aura Token Maker",
            "type_line": "Enchantment",
            "oracle_text": (
                "Create a white Aura enchantment token with enchant creature and "
                "totem armor."
            ),
        },
    ]
    for card in makers:
        assert serves(card, _sig("enchantments_matter", "you")) is True, card["name"]


def test_artifact_token_makers_are_artifacts():
    # Treasure/Food/Clue/Blood/Gold/Map/Powerstone tokens ARE artifact tokens, so a
    # maker of them makes an artifact — affinity/metalcraft/artifact-count fuel.
    # Three real makers; "Powerstone Maker" is a fictional clause probe.
    makers = [
        _card("Smothering Tithe"),
        _card("Witch's Oven"),
        _card("Tireless Tracker"),
        {
            "name": "Powerstone Maker",
            "type_line": "Artifact",
            "oracle_text": "When this enters, create a tapped Powerstone token.",
        },
    ]
    for card in makers:
        assert serves(card, _sig("artifacts_matter", "you")) is True, card["name"]


def test_theme_cost_reducers_are_credited():
    # A spell-type cost reducer is prime synergy for that theme's deck.
    etherium = _card("Etherium Sculptor")
    electromancer = _card("Goblin Electromancer")
    assert serves(etherium, _sig("artifacts_matter", "you")) is True
    assert serves(electromancer, _sig("spellcast_matters", "you")) is True
    assert serves(electromancer, _sig("magecraft_matters", "you")) is True


def test_aristocrats_lane_surfaces_board_wipes():
    wrath = _card("Wrath of God")
    assert _lane_covers(wrath, _sig("death_matters", "any")) is True
    assert _lane_covers(wrath, _sig("sacrifice_outlets", "you")) is True


def test_keyword_counter_cards_surface_across_counter_lanes():
    # Keyword counters (flying/trample/deathtouch/…) are counters too — a counters
    # commander wants them (proliferate fuel, voltron protection), even with no +1/+1.
    kwc = {
        "name": "Pure Keyword Counter Card",
        "type_line": "Instant",
        "oracle_text": "Put a flying counter and a trample counter on target creature.",
    }
    for key, scope in COUNTER_LANES:
        assert _lane_covers(kwc, _sig(key, scope)), f"{key}: keyword-counter uncovered"


# --- land-creatures theme (the Jyoti case) -------------------------------------

LAND_CREATURE_PAYOFF = _card("Sylvan Advocate")
PLANT_MAKER = _card("Avenger of Zendikar")
CLONE = _card("Silent Hallcreeper")
MANLAND = _card("Mishra's Factory")
# A transform DFC whose FRONT is a Saga and BACK is a Land. Not a manland: the
# "becomes a … creature" text animates an OPPONENT's artifact (Saga chapter I),
# and "Land" appears only via the back face. The card enters as the Saga, so its
# deckbuilding type is the front face — it must not be served as a creature-land.
JURASSIC_PARK = _card("Welcome to . . . // Jurassic Park")
LIFE_AND_LIMB = _card("Life and Limb")
EMBODIMENT_OF_INSIGHT = _card("Embodiment of Insight")
QUIRION_RANGER = _card("Quirion Ranger")
SCRYB_RANGER = _card("Scryb Ranger")
OBORO_BREEZECALLER = _card("Oboro Breezecaller")
SEEKER_OF_SKYBREAK = _card("Seeker of Skybreak")
BASILISK_COLLAR = _card("Basilisk Collar")
BONESPLITTER = _card("Bonesplitter")
CRUCIBLE_OF_WORLDS = _card("Crucible of Worlds")
DINGUS_EGG = _card("Dingus Egg")
PRICE_OF_GLORY = _card("Price of Glory")
HAUNTED_CROSSROADS = _card("Haunted Crossroads")
HUA_TUO = _card("Hua Tuo, Honored Physician")
REANIMATE = _card("Reanimate")
NAVIGATORS_COMPASS = _card("Navigator's Compass")
PRISMATIC_OMEN = _card("Prismatic Omen")
REEF_SHAMAN = _card("Reef Shaman")
BLOOD_MOON = _card("Blood Moon")
VICIOUS_SHADOWS = _card("Vicious Shadows")
BLOOD_ARTIST = _card("Blood Artist")
MURDER = _card("Murder")
THE_OZOLITH = _card("The Ozolith")
RESOURCEFUL_DEFENSE = _card("Resourceful Defense")
AETHER_SNAP = _card("Aether Snap")
TAINTED_STRIKE = _card("Tainted Strike")
TEMUR_BATTLE_RAGE = _card("Temur Battle Rage")
GRAFTED_EXOSKELETON = _card("Grafted Exoskeleton")
BOROS_SWIFTBLADE = _card("Boros Swiftblade")
ORNITHOPTER = _card("Ornithopter")
WELDING_JAR = _card("Welding Jar")
SOL_RING = _card("Sol Ring")
AVEN_MINDCENSOR = _card("Aven Mindcensor")
ARCHON_OF_EMERIA = _card("Archon of Emeria")
LLANOWAR_ELVES = _card("Llanowar Elves")
PUCAS_MISCHIEF = _card("Puca's Mischief")
PERPLEXING_CHIMERA = _card("Perplexing Chimera")
SPAWNBROKER = _card("Spawnbroker")
SOWER_OF_TEMPTATION = _card("Sower of Temptation")
ROIL_ELEMENTAL = _card("Roil Elemental")
EMPRESS_GALINA = _card("Empress Galina")
ACT_OF_TREASON = _card("Act of Treason")
FIREBALL = _card("Fireball")
CRACKLE_WITH_POWER = _card("Crackle with Power")
JAYAS_INFERNO = _card("Jaya's Immolating Inferno")
LIGHTNING_BOLT = _card("Lightning Bolt")
MANA_FLARE = _card("Mana Flare")
FIELD_OF_DREAMS = _card("Field of Dreams")
WIZENED_SNITCHES = _card("Wizened Snitches")
PSYCHIC_SURGERY = _card("Psychic Surgery")
CAVERN_HARPY = _card("Cavern Harpy")
WHITEMANE_LION = _card("Whitemane Lion")
RUN_AWAY_TOGETHER = _card("Run Away Together")


def test_land_creatures_spec_exists_with_extra_avenues():
    spec = spec_for(_sig("land_creatures_matter", "you"))
    assert spec is not None
    assert spec.label
    assert spec.avenue
    # The engine offers multiple precise sub-avenues, not one generic search.
    assert spec.extras


def test_land_creatures_serve_is_precise():
    sig = _sig("land_creatures_matter", "you")
    assert serves(LAND_CREATURE_PAYOFF, sig) is True  # references "land creatures"
    assert serves(PLANT_MAKER, sig) is False  # Plant tokens aren't land creatures
    assert serves(CLONE, sig) is False  # a clone is not a land creature


def _avenue_dicts(spec):
    """Engine avenue dicts (main + extras), as build_app emits them."""
    out = [{"label": spec.label, "search": dict(spec.search)}]
    out += [{"label": sa.label, "search": dict(sa.search)} for sa in spec.extras]
    return out


def _sig_sub(key, subject, scope="you"):
    return Signal(key=key, scope=scope, subject=subject, text="", source="cmd")


def test_subject_spec_built_for_tribal_signal():
    spec = spec_for(_sig_sub("type_matters", "Goblin"))
    assert spec is not None
    assert "Goblin" in spec.label
    assert spec.search.get("card_type") == "Goblin"


def test_subject_spec_serve_matches_subject_reference():
    sig = _sig_sub("type_matters", "Goblin")
    lord = _card("Goblin Trashmaster")
    off = _card("Reach Through Mists")
    assert serves(lord, sig) is True
    assert serves(off, sig) is False


def test_token_maker_subject_spec_and_generic_fallback():
    sub = spec_for(_sig_sub("token_maker", "Construct"))
    assert sub is not None
    assert "Construct" in sub.label  # "Construct tokens"
    # searches for cards that CREATE Construct tokens (oracle), not the type line.
    assert "oracle" in sub.search
    assert "card_type" not in sub.search
    generic = spec_for(_sig_sub("token_maker", ""))  # no subject → static spec
    assert generic is not None
    assert "oracle" in generic.search


def test_every_producible_key_resolves_to_a_spec():
    """The readable twin of the import-time key-agreement gate (ADR-0014): every
    subject-less key a detector can emit must resolve to a spec, so a new detector
    without a spec can't silently produce a no-op avenue. DERIVED from the producer
    tables (replaces the old hand-typed list, which was exactly the drift this guards)."""
    from mtg_utils._analysis.signals import producible_static_keys

    for key in sorted(producible_static_keys()):
        spec = spec_for(_sig(key, "any"))
        assert spec is not None, key
        assert spec.label, key
        assert spec.search, key


def test_search_filters_for_subject_signal_inject_identity():
    filters = search_filters(
        _sig_sub("type_matters", "Goblin"), color_identity="R", fmt="commander"
    )
    assert filters["card_type"] == "Goblin"
    assert filters["color_identity"] == "R"
    assert filters["format"] == "commander"


def test_land_creature_avenue_searches_exclude_false_positives():
    """The exact bug class the user hit: a Plant-token maker and a clone must not
    be surfaced by ANY land-creature avenue, while a real creature-land is."""
    from mtg_utils._analysis.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("land_creatures_matter", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(MANLAND)  # a real creature-land is surfaced by some avenue
    assert not served(PLANT_MAKER)  # Avenger's Plant tokens — surfaced by none
    assert not served(CLONE)  # Silent Hallcreeper clone — surfaced by none
    # A transform DFC (Saga front // Land back) is NOT a creature-land: "Land"
    # comes only from the back face and "becomes a … creature" animates an
    # opponent's artifact. The card's deckbuilding type is its front (the Saga).
    assert not served(JURASSIC_PARK)


def test_animate_lands_serve_covers_mass_forest_animators():
    """Yedora's payoff: she makes Forest lands, then 'animate your lands' effects
    turn them into a creature army. Life and Limb animates ALL Forests at once
    ('All Forests ... are 1/1 ... creatures'), so the Animate-your-lands
    sub-avenue must reach it, not only the 'lands you control become' phrasing."""
    from mtg_utils._analysis.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("land_creatures_matter", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(LIFE_AND_LIMB)  # mass Forest animator — the Yedora payoff
    assert served(EMBODIMENT_OF_INSIGHT)  # "Land creatures you control" — covered


def test_land_bounce_untap_engines_served():
    """A Forest/land-animation deck (Yedora) wants the Forest-bounce untap engines
    (Quirion / Scryb Ranger) and land-untappers (Oboro Breezecaller) — the untap
    can re-tap an animated land for mana. Narrow lane: the cost must BOUNCE a
    forest/land you control, not just any untap (Seeker of Skybreak stays out)."""
    from mtg_utils._analysis.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("land_creatures_matter", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(QUIRION_RANGER)
    assert served(SCRYB_RANGER)
    assert served(OBORO_BREEZECALLER)  # untap target LAND — the mana-source case
    assert not served(SEEKER_OF_SKYBREAK)  # plain untapper, no land bounce


def test_aoe_ping_serves_deathtouch_gear():
    """A repeatable 'damage to each creature' commander (Tibor, Pestilence) wants
    deathtouch on the source so each ping kills (CR 702.2b). The aoe_ping lane
    serves deathtouch-granting gear (Basilisk Collar) and not a plain stat-only
    Equipment (Bonesplitter)."""
    from mtg_utils._analysis.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("aoe_ping", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(BASILISK_COLLAR)
    assert not served(BONESPLITTER)  # +2/+0 only — not a deathtouch enabler


def test_land_destruction_serves_ld_support_package():
    """Numot repeatedly destroys lands, so her lane serves the land-destruction
    support package: own-land recursion to survive symmetric LD (Crucible of
    Worlds) and land-loss punishers (Dingus Egg, Price of Glory). A plain stat
    Equipment (Bonesplitter) is surfaced by none."""
    from mtg_utils._analysis.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("land_destruction", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(CRUCIBLE_OF_WORLDS)  # recursion — survive your own LD
    assert served(DINGUS_EGG)  # land-to-graveyard punisher
    assert served(PRICE_OF_GLORY)  # off-turn land-tap stax
    assert not served(BONESPLITTER)  # unrelated equipment


def test_cheat_from_top_serves_graveyard_to_top():
    """A cheat-from-top commander (Vaevictis) wants to STACK its top with a bomb, so
    the lane serves graveyard-to-top (Haunted Crossroads, Hua Tuo). A reanimation
    spell that puts a creature straight onto the battlefield (Reanimate) is NOT a
    top-stacker and stays out."""
    from mtg_utils._analysis.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("cheat_from_top", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(HAUNTED_CROSSROADS)
    assert served(HUA_TUO)
    assert not served(REANIMATE)  # graveyard -> battlefield, not graveyard -> top


def test_domain_serve_credits_additive_land_type_granters():
    """A domain commander (Radha) grows X with ADDITIVE basic-land-type granters
    (Navigator's Compass: 'becomes the basic land type of your choice in addition to
    its other types'; Prismatic Omen). A replacement color-fixer (Reef Shaman:
    'becomes ... until end of turn', no 'in addition to') doesn't grow domain, and an
    anti-domain hoser (Blood Moon) actively shrinks it — both stay out."""
    sig = _sig("domain_matters", "you")
    assert serves(NAVIGATORS_COMPASS, sig) is True  # additive type-of-choice granter
    assert serves(PRISMATIC_OMEN, sig) is True  # regression: "every basic land type"
    assert serves(REEF_SHAMAN, sig) is False  # replacement fixer, not additive
    assert serves(BLOOD_MOON, sig) is False  # anti-domain hoser


def test_kill_engine_serves_death_payoffs():
    """A repeatable creature-killer (Diaochan, Visara) wants on-death payoffs that
    fire every time it kills — drain (Blood Artist) and damage (Vicious Shadows). A
    plain removal spell (Murder) is not a death payoff and stays out."""
    sig = _sig("kill_engine", "you")
    assert serves(VICIOUS_SHADOWS, sig) is True  # whenever a creature dies -> damage
    assert serves(BLOOD_ARTIST, sig) is True  # whenever a creature dies -> drain
    assert serves(MURDER, sig) is False  # removal, not a death payoff


def test_counter_resilience_served_not_counter_hate():
    """A +1/+1-counter commander (Wolverine) wants COUNTER RESILIENCE — save/relocate
    its counters when a creature leaves (The Ozolith, Resourceful Defense), protecting
    the investment. Counter REMOVAL (Aether Snap) is the opposite and stays out."""
    from mtg_utils._analysis.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("self_counter_grow", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(THE_OZOLITH)
    assert served(RESOURCEFUL_DEFENSE)
    assert not served(AETHER_SNAP)  # removes counters — anti-synergy


def test_one_punch_serves_damage_amplifiers():
    """An extreme power-for-cost beater (Lord, Yargle) wins by connecting once for
    lethal, so the one_punch lane serves damage amplifiers — grant infect (Tainted
    Strike, Grafted Exoskeleton) and grant double strike (Temur Battle Rage). A
    vanilla creature that merely HAS double strike (Boros Swiftblade) is not an
    amplifier for your commander and stays out."""
    sig = _sig("one_punch", "you")
    assert serves(TAINTED_STRIKE, sig) is True  # grant infect (power -> poison kill)
    assert serves(TEMUR_BATTLE_RAGE, sig) is True  # grant double strike (2x damage)
    assert serves(GRAFTED_EXOSKELETON, sig) is True  # equipped creature has infect
    assert serves(BOROS_SWIFTBLADE, sig) is False  # vanilla double-striker, not a grant


def test_evasive_attackers_serves_fliers_for_nonhuman_engine():
    """Winota's non-Human-attack engine wants evasive attackers — fliers reliably
    connect to fire her trigger (Ornithopter, Aven Mindcensor, Archon of Emeria), and
    flying Humans are premium cheat-into-play targets. A grounded non-flier (Llanowar
    Elves) is not an evasive attacker and stays out."""
    sig = _sig("nonhuman_attackers", "you")
    assert serves(ORNITHOPTER, sig) is True
    assert serves(AVEN_MINDCENSOR, sig) is True
    assert serves(ARCHON_OF_EMERIA, sig) is True
    assert serves(LLANOWAR_ELVES, sig) is False  # no evasion


def test_control_exchange_serves_swaps_not_theft():
    """A reclaim-owned commander (Meneldor) wants control-EXCHANGE — donate a dud, take
    their bomb, then reclaim your own dud (Puca's Mischief, Perplexing Chimera,
    Spawnbroker). Pure one-way theft (Sower of Temptation) is NOT it: you don't OWN a
    stolen creature, so the commander can't reclaim it."""
    sig = _sig("control_exchange", "you")
    assert serves(PUCAS_MISCHIEF, sig) is True
    assert serves(PERPLEXING_CHIMERA, sig) is True
    assert serves(SPAWNBROKER, sig) is True
    assert serves(SOWER_OF_TEMPTATION, sig) is False  # one-way theft, not an exchange


def test_theft_protection_serves_permanent_theft_not_temporary():
    """Kira shields your creatures from removal, so theft creatures whose steal is
    contingent (Sower, Roil — lost if the thief dies) or a repeatable engine (Empress
    Galina) keep their loot. A temporary steal (Act of Treason: 'until end of turn')
    gains nothing from protection and stays out."""
    sig = _sig("theft_protection", "you")
    assert serves(SOWER_OF_TEMPTATION, sig) is True  # contingent steal made sticky
    assert serves(ROIL_ELEMENTAL, sig) is True  # contingent steal made sticky
    assert serves(EMPRESS_GALINA, sig) is True  # repeatable theft engine, protected
    assert serves(ACT_OF_TREASON, sig) is False  # temporary — protection irrelevant


def test_big_mana_serves_x_spell_sinks():
    """A big-mana commander (Neheb, Sunastian) wants X-spell mana sinks — Fireball,
    Crackle with Power, Jaya's Immolating Inferno (deal X damage scaling with the mana
    paid). A fixed-cost burn (Lightning Bolt) and a mana GENERATOR (Mana Flare, not a
    sink) stay out."""
    sig = _sig("big_mana", "you")
    assert serves(FIREBALL, sig) is True
    assert serves(CRACKLE_WITH_POWER, sig) is True
    assert serves(JAYAS_INFERNO, sig) is True
    assert serves(LIGHTNING_BOLT, sig) is False  # fixed 3 damage, not a mana sink
    assert serves(MANA_FLARE, sig) is False  # generates mana, isn't a sink


def test_opp_top_exile_serves_top_reveal():
    """A commander that exiles/takes opponents' library tops (Circu) wants to SEE those
    tops — play-with-top-revealed (Field of Dreams, Wizened Snitches) shows what it will
    exile/steal. A shuffle-triggered graveyard peek (Psychic Surgery) isn't a top-reveal
    and stays out."""
    sig = _sig("opp_top_exile", "you")
    assert serves(FIELD_OF_DREAMS, sig) is True
    assert serves(WIZENED_SNITCHES, sig) is True
    assert serves(PSYCHIC_SURGERY, sig) is False  # shuffle peek, not a top-reveal


def test_clone_self_bounce_serves_recast_enablers():
    """A clone/recast commander (The Master, Body Thief) wants SELF-BOUNCE to return its
    own body and recast it — copying a different/better creature again. Cavern Harpy is
    the canonical enabler (Whitemane Lion too). A symmetric bounce of creatures
    controlled by DIFFERENT players (Run Away Together) isn't a clean self-bounce."""
    from mtg_utils._analysis.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("clone_makers", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(CAVERN_HARPY)
    assert served(WHITEMANE_LION)
    assert not served(
        RUN_AWAY_TOGETHER
    )  # different players' creatures, not self-bounce


def test_free_plot_serves_zero_cost_spells():
    """Fblthp makes 0-cost cards free to plot, so the lane serves cards whose mana cost
    is {0} (Ornithopter, Welding Jar — the artifact-combo / storm fuel). A 1-cost
    artifact (Sol Ring) isn't free to plot, and lands (no mana cost) aren't plottable
    nonland spells — both stay out."""
    sig = _sig("free_plot", "you")
    assert serves(ORNITHOPTER, sig) is True  # {0} artifact creature
    assert serves(WELDING_JAR, sig) is True  # {0} artifact
    assert serves(SOL_RING, sig) is False  # {1} — not a free plot


def _subj_sig(key, subject):
    return Signal(key=key, scope="you", subject=subject, text="", source="cmd")


class TestCoinFlipSpec:
    """The coin-flip avenue must fan out a Flip-fixing sub-avenue that surfaces
    Krark's-Thumb-style fixers (otherwise they sink past the package cap)."""

    def test_coin_flip_has_flip_fixing_subavenue(self):
        import re

        spec = spec_for(_sig("coin_flip", "you"))
        assert spec is not None
        assert spec.label == "Coin flips"
        fix = {e.label: e for e in spec.extras}.get("Flip fixing")
        assert fix is not None, "expected a 'Flip fixing' sub-avenue"
        # Krark's Thumb is the canonical fixer — the sub-avenue's search must surface it.
        krark = "If you would flip a coin, instead flip two coins and ignore one."
        assert re.search(fix.search["oracle"], krark, re.IGNORECASE)
        # but a plain flip payoff is NOT a fixer (stays in the main avenue only).
        plain = "Flip a coin. If you win the flip, draw a card."
        assert not re.search(fix.search["oracle"], plain, re.IGNORECASE)
        # the main avenue still recognizes generic flip payoffs.
        assert spec.serve.search(plain)

    def test_flip_fixing_catches_outcome_forcing_fixers(self):
        """Edgar, King of Figaro fixes flips by FORCING THE OUTCOME
        ('those coins come up heads and you win those flips'), not by
        re-flipping. The Krark's-Thumb-shaped regex missed this whole class —
        the sub-avenue (and the parent avenue) must surface it."""
        import re

        spec = spec_for(_sig("coin_flip", "you"))
        fix = {e.label: e for e in spec.extras}["Flip fixing"]
        edgar = (
            "The first time you flip one or more coins each turn, "
            "those coins come up heads and you win those flips."
        )
        # Edgar is a genuine fixer — the sub-avenue search must catch it.
        assert re.search(fix.search["oracle"], edgar, re.IGNORECASE)
        # …and it serves the parent coin-flip avenue (it IS a coin-flip card,
        # phrased "flip one or more coins"/"come up heads", not "flip a coin").
        assert spec.serve.search(edgar)
        # but a plain flip-resolution payoff stays out of the fixer sub-avenue.
        plain = "Flip a coin. If you win the flip, draw a card."
        assert not re.search(fix.search["oracle"], plain, re.IGNORECASE)

    def test_flip_fixing_excludes_conditional_payoffs(self):
        """The e21b7d6 broadening (bare 'come up heads' / 'you win … flip') wrongly
        caught three PAYOFFS that reference a flip result as a CONDITION rather than
        GRANTING/manipulating the flip. A regex can't separate a grant from a condition,
        so the fixer sub-avenue must pin {Krark's Thumb, Edgar} and exclude these three
        (verified against bulk: the precise matcher yields exactly the two real fixers)."""
        import re

        spec = spec_for(_sig("coin_flip", "you"))
        fix = {e.label: e for e in spec.extras}["Flip fixing"]
        rx = re.compile(fix.search["oracle"], re.IGNORECASE)

        # The two REAL fixers — must match (a grant / a re-flip).
        edgar = (
            "The first time you flip one or more coins each turn, those coins come up "
            "heads and you win those flips."
        )
        krark = "If you would flip a coin, instead flip two coins and ignore one."
        assert rx.search(edgar)
        assert rx.search(krark)

        # Three PAYOFFS that merely reference a flip result — must NOT match.
        mana_clash = (
            "You and target opponent each flip a coin. Mana Clash deals 1 damage to "
            "each player whose coin comes up tails. Repeat this process until both "
            "players' coins come up heads on the same flip."
        )
        two_headed_giant = (
            "Whenever this creature attacks, flip two coins. If both coins come up "
            "heads, this creature gains double strike until end of turn. If both coins "
            "come up tails, this creature gains menace until end of turn."
        )
        squees_revenge = (
            "Choose a number. Flip a coin that many times or until you lose a flip, "
            "whichever comes first. If you win all the flips, draw two cards for each "
            "flip."
        )
        assert not rx.search(mana_clash)
        assert not rx.search(two_headed_giant)
        assert not rx.search(squees_revenge)


class TestSpellslingerServe:
    """The canonical false-positive: 'Spellslinger' (spellcast_matters) must NOT be
    served by any value permanent that merely draws a card. A cantrip is specifically
    an Instant or Sorcery that draws (CR 601.2: casting is determined by the card's
    type), prowess marks a payoff (CR 702.108a), and magecraft is an ability word that
    lives only in oracle prose (CR 207.2c). Copies aren't cast (CR 707.10)."""

    SLINGER = _sig("spellcast_matters", "you")

    def test_value_permanent_that_draws_does_not_serve(self):
        rhystic = _card("Rhystic Study")
        assert serves(rhystic, self.SLINGER) is False

    def test_opponent_cast_drawer_does_not_serve(self):
        # Esper Sentinel: "opponent casts … noncreature spell" — the "you cast" gate
        # must reject it (it's an opponents-cast payoff, not a spellslinger enabler).
        esper = _card("Esper Sentinel")
        assert serves(esper, self.SLINGER) is False

    def test_equipment_that_draws_does_not_serve(self):
        sword = _card("Sword of Fire and Ice")
        assert serves(sword, self.SLINGER) is False

    def test_coinflip_value_creature_does_not_serve(self):
        # Zndrsplt: draws on a won coin flip, never on YOUR cast — the canonical FP.
        zndrsplt = _card("Zndrsplt, Eye of Wisdom")
        assert serves(zndrsplt, self.SLINGER) is False

    def test_instant_cantrip_serves(self):
        opt = _card("Opt")
        assert serves(opt, self.SLINGER) is True

    def test_prowess_creature_serves_via_keyword(self):
        swiftspear = _card("Monastery Swiftspear")
        assert serves(swiftspear, self.SLINGER) is True

    def test_cast_trigger_payoff_serves_via_oracle(self):
        # Young Pyromancer: a payoff with NO prowess keyword and not itself an
        # instant/sorcery — caught by the "whenever you cast an instant or sorcery"
        # oracle branch.
        pyromancer = _card("Young Pyromancer")
        assert serves(pyromancer, self.SLINGER) is True

    def test_magecraft_payoff_serves_via_oracle(self):
        storm_kiln = _card("Storm-Kiln Artist")
        assert serves(storm_kiln, self.SLINGER) is True

    def test_avenue_classifies_by_structured_serve_not_draw(self):
        """The avenue-credit path (ranking._avenue_matchers) must apply the SAME
        precise predicate the spec serves on — so exploring the Spellslinger avenue
        credits a real cantrip (matched by TYPE, whose oracle says only 'draw a card')
        and a prowess creature (matched by KEYWORD), but NOT a value permanent."""
        from mtg_utils._analysis.ranking import score_candidate

        spec = spec_for(self.SLINGER)
        avenue = {
            "label": spec.label,
            "search": dict(spec.search),
            "serve": spec.serve.as_dict(),
        }

        def served(card):
            return set(
                score_candidate(card, active_signals=[], avenues=[avenue])["served"]
            )

        opt = _card("Opt")
        swiftspear = _card("Monastery Swiftspear")
        rhystic = _card("Rhystic Study")
        assert "Spellslinger" in served(opt)  # by type
        assert "Spellslinger" in served(swiftspear)  # by keyword
        assert "Spellslinger" not in served(rhystic)  # value permanent excluded


class TestMagecraftServe:
    """magecraft_matters is the same spellslinger archetype (CR 207.2c: magecraft's
    reminder is 'whenever you cast or copy an instant or sorcery spell'). Its matcher
    must be as precise as Spellslinger's — no bare 'draw a card' search, no bare
    'instant or sorcery' serve branch that credits counterspell-shelters/value lands."""

    MAGE = _sig("magecraft_matters", "you")

    def test_protective_land_does_not_serve(self):
        # Boseiju mentions "instant or sorcery" but only to protect a spell — not a
        # spellslinger payoff. The old bare 'instant or sorcery' serve branch caught it.
        boseiju = _card("Boseiju, Who Shelters All")
        assert serves(boseiju, self.MAGE) is False

    def test_cast_trigger_payoff_serves(self):
        murmuring = _card("Murmuring Mystic")
        assert serves(murmuring, self.MAGE) is True

    def test_instant_serves_by_type(self):
        opt = _card("Opt")
        assert serves(opt, self.MAGE) is True

    def test_avenue_does_not_credit_value_permanent(self):
        from mtg_utils._analysis.ranking import score_candidate

        spec = spec_for(self.MAGE)
        avenue = engine_avenue(spec)
        rhystic = _card("Rhystic Study")
        served = set(
            score_candidate(rhystic, active_signals=[], avenues=[avenue])["served"]
        )
        assert spec.label not in served


def engine_avenue(spec):
    """An engine-emitted avenue dict for a spec (main avenue, with structured serve)."""
    from mtg_utils._deck_forge.engine import avenue_with_serve

    return avenue_with_serve(
        {"label": spec.label, "search": dict(spec.search)}, spec.serve
    )


class TestSecondSpellSearch:
    """second_spell_matters' serve is precise, but its SEARCH carried the same bare
    'draw a card' branch — so the avenue credited value permanents. The search must
    surface second-spell / storm payoffs, not every drawer."""

    SIG = _sig("second_spell_matters", "you")

    def test_avenue_excludes_value_permanent(self):
        from mtg_utils._analysis.ranking import score_candidate

        spec = spec_for(self.SIG)
        avenue = engine_avenue(spec)
        rhystic = _card("Rhystic Study")
        served = set(
            score_candidate(rhystic, active_signals=[], avenues=[avenue])["served"]
        )
        assert spec.label not in served

    def test_serve_matches_a_real_second_spell_payoff(self):
        payoff = _card("Jori En, Ruin Diver")
        assert serves(payoff, self.SIG) is True


class TestSubjectSpecs:
    """Subject-bearing avenues must match their label and stay distinct from payoffs."""

    def test_token_maker_finds_token_makers_not_the_tribe(self):
        spec = spec_for(_subj_sig("token_maker", "Dryad"))
        assert spec.label == "Dryad tokens"
        # a card that CREATES Dryad tokens serves it…
        assert spec.serve.search("Create a 1/1 green Dryad creature token.")
        # …a plain Dryad creature (no token creation) does NOT.
        assert not spec.serve.search("Dryad — this creature has reach.")
        # the search targets token creation, not the type line.
        assert "oracle" in spec.search
        assert "card_type" not in spec.search

    def test_token_maker_payoffs_are_a_distinct_sub_avenue(self):
        spec = spec_for(_subj_sig("token_maker", "Dryad"))
        extra_labels = [e.label for e in spec.extras]
        # The tribe-token payoffs come first; the flood deck also gets the audit-added
        # token-doubler and creature-ETB-payoff sub-avenues (EDHREC gap fix).
        assert extra_labels[0] == "Dryad payoffs"
        assert "Token doublers" in extra_labels
        assert "Creature-ETB payoffs" in extra_labels
        # the main avenue blurb must NOT also claim to cover payoffs (the old confusion).
        assert "payoff" not in spec.avenue.lower()

    def test_tribal_finds_the_creatures_payoffs_finds_the_lords(self):
        spec = spec_for(_subj_sig("type_matters", "Elemental"))
        assert spec.label == "Elemental tribal"
        assert spec.search == {"card_type": "Elemental"}  # the creatures
        payoff = spec.extras[0]
        assert payoff.label == "Elemental payoffs"
        assert "you control" in payoff.search["oracle"]  # the lords/anthems


class TestStructuredServeFixes:
    """Audit-driven precision fixes that convert imprecise oracle regexes to the
    proper structured characteristic (type / keyword / count gate). Each pins a
    measured false-positive AND a false-negative against real cards."""

    def test_card_draw_engine_rejects_one_shot_cantrips(self):
        """card_draw_engine's serve `draw \\w+ cards?` let \\w+ eat 'draw a card',
        so ~753 one-shot cantrips were mislabeled an 'engine'. A recurring/bulk gate
        keeps Phyrexian Arena (recurring) and Blue Sun's Zenith (X cards) but drops a
        one-shot instant draw (Remand) and a death-triggered single draw (Solemn)."""
        sig = _sig("card_draw_engine", "you")
        phyrexian_arena = _card("Phyrexian Arena")
        blue_suns = _card("Blue Sun's Zenith")
        remand = _card("Remand")
        solemn = _card("Solemn Simulacrum")
        assert serves(phyrexian_arena, sig) is True
        assert serves(blue_suns, sig) is True
        assert serves(remand, sig) is False
        assert serves(solemn, sig) is False

    def test_lifegain_uses_lifelink_keyword_not_the_bare_word(self):
        """lifegain's serve matched the bare word 'lifelink' anywhere in oracle text,
        so Crystalline Giant (which only lists lifelink among random counters) served.
        Gate on the keywords[] field instead; a card that GRANTS lifelink to the team
        still serves via an oracle grant-branch."""
        sig = _sig("lifegain_matters", "you")
        soul_warden = _card("Soul Warden")
        baneslayer = _card("Baneslayer Angel")
        whip = _card("Whip of Erebos")
        crystalline_giant = _card("Crystalline Giant")
        assert serves(soul_warden, sig) is True  # gains life
        assert serves(baneslayer, sig) is True  # lifelink keyword
        assert serves(whip, sig) is True  # grants lifelink to the team
        assert serves(crystalline_giant, sig) is False  # bare word in a counter list

    def test_dash_avenue_keys_on_equipment_type_and_dash_keyword(self):
        """has_dash' serve had `whenever[^.]*attacks` and a bare `\\bequipment\\b`
        that matched any creature mentioning equipment/attacks (~1104). The avenue is
        Equipment-for-a-dasher: gate on the Equipment TYPE and the dash KEYWORD."""
        sig = _sig("has_dash", "you")
        skullclamp = _card("Skullclamp")
        mangara = _card("Mangara, the Diplomat")
        elder_gargaroth = _card("Elder Gargaroth")
        assert serves(skullclamp, sig) is True  # Equipment type
        assert serves(mangara, sig) is False  # not equipment, no dash
        assert serves(elder_gargaroth, sig) is False  # "attacks" no longer triggers

    def test_creature_etb_opponents_matches_punisher_not_bloodthirst(self):
        """creature_etb/opponents' serve `opponent.*creature.*enters` required
        opponent BEFORE creature, so it matched Bloodthirst ('an opponent was dealt
        damage … this creature enters') and MISSED the real punisher ('a creature an
        opponent controls enters'). A near-total inversion."""
        sig = _sig("creature_etb", "opponents")
        suture_priest = _card("Suture Priest")
        authority = _card("Authority of the Consuls")
        bloodthirst = _card("Stormblood Berserker")
        assert serves(suture_priest, sig) is True
        assert serves(authority, sig) is True
        assert serves(bloodthirst, sig) is False

    def test_drain_avenue_serves_blood_artist(self):
        """lifeloss_matters/opponents (the 'Drain' avenue) required the literal word
        'opponent' next to 'loses', so it MISSED the keystone aristocrats drains that
        read 'target player loses N life' (Blood Artist, Zulaport Cutthroat)."""
        sig = _sig("lifeloss_matters", "opponents")
        blood_artist = _card("Blood Artist")
        zulaport = _card("Zulaport Cutthroat")
        assert serves(blood_artist, sig) is True
        assert serves(zulaport, sig) is True


class TestStructuredServeFixes2:
    """Second batch of audit-driven precision fixes (all SPECS-level serve)."""

    def test_aristocrats_serve_requires_creature_token_not_treasure(self):
        """sacrifice/death serves keyed on `create .*token`, which is type-blind: it
        served every Treasure/Clue/Food maker (~428 in WBR). Require the literal
        'creature token' so only real sacrifice fodder qualifies."""
        sac = _sig("sacrifice_outlets", "you")
        death = _sig("death_matters", "any")
        bitterblossom = _card("Bitterblossom")
        viscera_seer = _card("Viscera Seer")
        blood_artist = _card("Blood Artist")
        smothering_tithe = _card("Smothering Tithe")
        # Thraben Inspector, not Tireless Tracker: the Tracker's own "whenever you
        # sacrifice a Clue" reads as a sac payoff, which is not the Clue-token branch.
        thraben_inspector = _card("Thraben Inspector")
        assert serves(bitterblossom, sac) is True  # makes creature-token fodder
        assert serves(viscera_seer, sac) is True  # sac outlet
        assert serves(blood_artist, death) is True  # dies trigger
        assert serves(smothering_tithe, sac) is False  # Treasure, not creature token
        assert serves(smothering_tithe, death) is False
        assert serves(thraben_inspector, death) is False  # Clue, not creature token

    def test_landfall_serve_is_land_anchored(self):
        """landfall's bare `onto the battlefield` branch matched any cheat-into-play /
        reanimation. Anchor it to 'land card … onto the battlefield'."""
        sig = _sig("landfall", "you")
        cultivate = _card("Cultivate")
        azusa = _card("Azusa, Lost but Seeking")
        sneak_attack = _card("Sneak Attack")
        reanimate = _card("Reanimate")
        assert serves(cultivate, sig) is True
        assert serves(azusa, sig) is True
        assert serves(sneak_attack, sig) is False
        assert serves(reanimate, sig) is False

    def test_stax_serve_requires_restriction_not_bare_your_opponents(self):
        """stax/opponents had a bare `your opponents` alternative that matched any card
        naming opponents (Edric's draw trigger, Telepathy's hand reveal). Serve the
        actual tax/restriction shapes; this also recovers symmetric taxes (Thalia)."""
        sig = _sig("stax_taxes", "opponents")
        drannith = _card("Drannith Magistrate")
        thalia = _card("Thalia, Guardian of Thraben")
        edric = _card("Edric, Spymaster of Trest")
        telepathy = _card("Telepathy")
        assert serves(drannith, sig) is True  # opponents can't
        assert serves(thalia, sig) is True  # noncreature cost more
        assert serves(edric, sig) is False  # names opponents, but is a draw payoff
        assert serves(telepathy, sig) is False  # names opponents, but is hand reveal

    def test_evasion_self_excludes_menace_reminder(self):
        """evasion_self's bare `can't be blocked` matched the menace/flying REMINDER
        text 'can't be blocked except by …'. Exclude the 'except' form; keep true
        unblockable and landwalk."""
        sig = _sig("evasion_self", "you")
        invisible_stalker = _card("Invisible Stalker")
        sengir = _card("Sengir Vampire")
        assert serves(invisible_stalker, sig) is True
        assert serves(sengir, sig) is False


class TestStructuredServeFixes3:
    """Combat-damage connect avenues: drop the bare `\\bmenace\\b` word (matched every
    menace creature + reminder text) and the `can't be blocked` reminder form. Serve
    the payoff trigger + true-unblockable enablers, not every vanilla evasive body."""

    def test_combat_damage_opponents_drops_bare_menace(self):
        sig = _sig("combat_damage_matters", "opponents")
        edric = _card("Edric, Spymaster of Trest")
        coastal_piracy = _card("Coastal Piracy")
        invisible_stalker = _card("Invisible Stalker")
        vanilla_menace = _card("Boggart Brute")
        sengir = _card("Sengir Vampire")
        assert serves(edric, sig) is True  # payoff trigger
        assert serves(coastal_piracy, sig) is True  # payoff trigger
        assert serves(invisible_stalker, sig) is True  # true unblockable enabler
        assert serves(vanilla_menace, sig) is False  # bare menace word/reminder
        assert serves(sengir, sig) is False  # vanilla flier, reminder "except"

    def test_damage_to_opp_drops_bare_menace(self):
        sig = _sig("damage_to_opp_matters", "opponents")
        niv = _card("Niv-Mizzet, Visionary")
        vanilla_menace = _card("Boggart Brute")
        assert serves(niv, sig) is True  # noncombat-damage-to-opponent payoff
        assert serves(vanilla_menace, sig) is False


class TestSweepDetectorFixes:
    """Mined sweep-detector regexes whose open-ended alternations over-fire."""

    def test_self_counter_grow_is_self_only_not_distribution(self):
        """The `put … +1/+1 counter on [A-Z][a-z]+` branch matched any capitalized
        word after 'on' — so distributors (counter on target Knight / on target
        creature for each Elf) read as SELF-growth (~1072 FP). Self-growth only."""
        sig = _sig("self_counter_grow", "you")
        walking_ballista = _card("Walking Ballista")
        venerable_knight = _card("Venerable Knight")
        immaculate = _card("Immaculate Magistrate")
        assert serves(walking_ballista, sig) is True
        assert serves(venerable_knight, sig) is False
        assert serves(immaculate, sig) is False

    def test_facedown_requires_morph_vocab_not_bare_face_down(self):
        """The bare `face-down|face down` and `is turned face up` branches matched
        impulse/hideaway exile ('exile one face down'). Require the morph/manifest
        vocabulary or the 'face-down creature(s)' payoff noun (~212 FP)."""
        sig = _sig("facedown_matters", "you")
        secret_plans = _card("Secret Plans")
        morph_creature = _card("Krosan Colossus")
        gonti = _card("Gonti, Lord of Luxury")
        spinerock = _card("Spinerock Knoll")
        assert serves(secret_plans, sig) is True  # face-down creatures payoff
        assert serves(morph_creature, sig) is True  # morph vocab
        assert serves(gonti, sig) is False  # impulse exile "face down"
        assert serves(spinerock, sig) is False  # hideaway exile "face down"


class TestStructuredServeExtension:
    """fp=0 HIGH findings the audit flagged as RECALL failures: the serve named only
    the payoffs and could not express the structured enablers. Now type/keyword/cmc/
    devotion-pip dimensions recover them — the heart of the 'use the structured field'
    thesis. Each pins recovered enablers (+) and confirms non-members stay out (-)."""

    def test_superfriends_serves_planeswalkers_and_proliferate(self):
        sig = _sig("superfriends_matters", "you")
        karn = _card("Karn Liberated")
        atraxa = _card("Atraxa, Praetors' Voice")
        bolt = _card("Lightning Bolt")
        assert serves(karn, sig) is True  # planeswalker type
        assert serves(atraxa, sig) is True  # proliferate keyword
        assert serves(bolt, sig) is False

    def test_modified_serves_equipment_auras_and_counters(self):
        sig = _sig("modified_matters", "you")
        glitters = _card("All That Glitters")
        hardened_scales = _card("Hardened Scales")
        equipment = _card("Leonin Scimitar")
        sol_ring = _card("Sol Ring")
        assert serves(glitters, sig) is True  # Aura type
        assert serves(equipment, sig) is True  # Equipment type
        assert serves(hardened_scales, sig) is True  # +1/+1 counter oracle
        assert serves(sol_ring, sig) is False

    def test_voltron_serves_buff_auras_but_not_control_auras(self):
        sig = _sig("voltron_matters", "you")
        skullclamp = _card("Skullclamp")
        flight = _card("Flight")
        pacifism = _card("Pacifism")
        sol_ring = _card("Sol Ring")
        assert serves(skullclamp, sig) is True  # Equipment
        assert serves(flight, sig) is True  # buff Aura
        assert serves(pacifism, sig) is False  # control Aura — vetoed
        assert serves(sol_ring, sig) is False

    def test_devotion_serves_heavy_pip_permanents_via_structured_pips(self):
        sig = _sig("devotion_matters", "you")
        gray_merchant = _card("Gray Merchant of Asphodel")
        heavy_pip_vanilla = _card("Havoc Devils")
        llanowar = _card("Llanowar Elves")
        counterspell = _card("Counterspell")
        sol_ring = _card("Sol Ring")
        assert serves(gray_merchant, sig) is True  # devotion oracle + 2 black pips
        assert serves(heavy_pip_vanilla, sig) is True  # 2 red pips, a permanent
        assert serves(llanowar, sig) is False  # only 1 pip
        # 2 pips but an instant (not a permanent)
        assert serves(counterspell, sig) is False
        assert serves(sol_ring, sig) is False  # colorless

    def test_cost_reduction_serves_x_spells_and_expensive_bombs(self):
        sig = _sig("cost_reduction", "you")
        # X-spells by mana cost: Torment of Hailfire's text never prints {X} ("X
        # times"), so an oracle read missed it; an {X} ACTIVATED cost (Chimeric
        # Staff) is not a spell a cost reducer discounts.
        torment = _card("Torment of Hailfire")
        devils_play = _card("Devil's Play")
        chimeric_staff = _card("Chimeric Staff")
        emrakul = _card("Emrakul, the Aeons Torn")
        disdainful = _card("Disdainful Stroke")
        sun_titan = _card("Sun Titan")
        assert serves(torment, sig) is True  # X spell, no {X} in its text
        assert serves(devils_play, sig) is True  # X spell
        assert serves(chimeric_staff, sig) is False  # {X} activated ability only
        # an MDFC's {X} cost lives on its face; the top-level mana_cost is empty
        agadeem = _card("Agadeem's Awakening // Agadeem, the Undercrypt")
        assert serves(agadeem, sig) is True
        assert serves(agadeem, _sig("xspell_matters", "you")) is True
        assert serves(emrakul, sig) is True  # expensive bomb (cmc>=7)
        assert serves(disdainful, sig) is False  # "mana value 4" no longer matches
        assert serves(sun_titan, sig) is False  # cmc 6 below the bomb threshold

    def test_removal_serves_burn_to_any_target(self):
        sig = _sig("removal", "you")
        bolt = _card("Lightning Bolt")
        murder = _card("Murder")
        sol_ring = _card("Sol Ring")
        assert serves(bolt, sig) is True  # damage to any target
        assert serves(murder, sig) is True
        assert serves(sol_ring, sig) is False

    def test_counter_control_extraction_allows_adjective_gap(self):
        # ADR-0027: counter_control migrated to the Card IR — phase's `counter_spell`
        # effect category serves "Counter target creature spell" (Essence Scatter,
        # adjective gap), so the lane opens through the hybrid IR path, not the regex.

        # Real production extractor: phase's `counter_spell` effect category serves the
        # adjective-gap "Counter target creature spell".
        hybrid = {s.key for s in test_signals("Essence Scatter")}
        assert "counter_control" in hybrid


class TestStructuredServeFixes4:
    """Batch 4: remaining HIGH precision fixes."""

    def test_mana_amplifier_drops_fixing_keeps_doublers(self):
        """`add .* mana of any` captured fixing (Birds, City of Brass), not
        amplification. Serve the doublers/triplers ('tap … for mana … add/produces
        twice') + X-spell payoffs."""
        sig = _sig("mana_amplifier", "you")
        mirari = _card("Mirari's Wake")
        reflection = _card("Mana Reflection")
        birds = _card("Birds of Paradise")
        signet = _card("Manalith")
        assert serves(mirari, sig) is True
        assert serves(reflection, sig) is True
        assert serves(birds, sig) is False
        assert serves(signet, sig) is False

    def test_attack_serves_haste_keyword_and_grants_not_bare_word(self):
        sig = _sig("attack_matters", "you")
        fervor = _card("Fervor")
        haste_beater = _card("Raging Goblin")
        krenko = _card("Krenko, Mob Boss")
        # Fictional (ADR-0056 machinery): no real card strips haste, so the bare-word
        # "haste" regex shape is pinned by a made-up record.
        loses_haste = {
            "name": "Haste Stripper",
            "type_line": "Instant",
            "oracle_text": "Target creature loses haste until end of turn.",
            "keywords": [],
        }
        sol_ring = _card("Sol Ring")
        assert serves(fervor, sig) is True  # grants haste to team
        assert serves(haste_beater, sig) is True  # Haste keyword
        assert serves(krenko, sig) is True  # creature-token maker
        assert serves(loses_haste, sig) is False  # bare word "haste" (removes it)
        assert serves(sol_ring, sig) is False

    def test_play_from_top_drops_bare_reveal(self):
        """`reveal the top card of your library` is a peek (Coiling Oracle), not
        play-from-top. Keep the play/cast-from-top forms."""
        sig = _sig("play_from_top", "you")
        future_sight = _card("Future Sight")
        coiling_oracle = _card("Coiling Oracle")
        assert serves(future_sight, sig) is True
        assert serves(coiling_oracle, sig) is False

    def test_pump_matters_drops_minus_bonuses(self):
        """pump's `[+\\-]` matched -X/-X shrink (that's debuff_makers). Positive only."""
        sig = _sig("pump_makers", "you")
        giant_growth = _card("Giant Growth")
        festering_goblin = _card("Festering Goblin")
        assert serves(giant_growth, sig) is True
        assert serves(festering_goblin, sig) is False

    def test_crimes_avenue_excludes_counterspells(self):
        """crimes SEARCH `target.*spell` credited every counterspell. Drop it."""
        from mtg_utils._analysis.ranking import score_candidate

        spec = spec_for(_sig("crimes_matter", "you"))
        avenue = {"label": spec.label, "search": dict(spec.search)}
        counterspell = _card("Counterspell")
        murder = _card("Murder")
        served_cs = set(
            score_candidate(counterspell, active_signals=[], avenues=[avenue])["served"]
        )
        served_m = set(
            score_candidate(murder, active_signals=[], avenues=[avenue])["served"]
        )
        assert spec.label not in served_cs  # counterspell is not a crime enabler
        assert spec.label in served_m  # targeted removal is


class TestMediumServeFixes:
    """MEDIUM findings: recall recoveries via type/keyword/produced_mana, plus serve
    tightenings that drop a bad branch. Each pins the audit's +/- fixtures."""

    def _ck(self, key, scope, plus, minus):
        sig = _sig(key, scope)
        for card in plus:
            assert serves(card, sig) is True, (key, card.get("name"))
        for card in minus:
            assert serves(card, sig) is False, (key, card.get("name"))

    def test_historic_serves_legendary_artifact_saga_types(self):
        self._ck(
            "historic_matters",
            "you",
            [
                _card("Sol Ring"),
                _card("The Eldest Reborn"),
                _card("Urza, Lord High Artificer"),
            ],
            [_card("Llanowar Elves")],
        )

    def test_legends_serves_legendary_type(self):
        self._ck(
            "legends_matter",
            "you",
            [_card("Jodah, Archmage Eternal")],
            [_card("Island")],
        )

    def test_party_serves_party_classes_not_bare_word(self):
        self._ck(
            "party_matters",
            "you",
            [
                _card("Archpriest of Iona"),
                _card("Tazri, Beacon of Unity"),
            ],
            [_card("You Meet in a Tavern")],
        )

    def test_ramp_serves_via_produced_mana(self):
        self._ck(
            "ramp",
            "you",
            [
                _card("Birds of Paradise"),
                _card("Sol Ring"),
                _card("Cultivate"),
            ],
            [_card("Lightning Bolt")],
        )

    def test_opponent_draw_serves_payoffs_and_force_draw_enablers(self):
        # The punish-draw lane wants BOTH the payoff trigger (Bowmasters) AND the
        # enablers that make opponents draw extra so it fires — including "each opponent
        # draws" gifts (Master of the Feast), a known Nekusar staple. Dan's asymmetry
        # point: forcing opponents to draw is on-theme; a pure self-cantrip is not.
        self._ck(
            "opponent_draw_matters",
            "opponents",
            [
                _card("Orcish Bowmasters"),
                _card("Master of the Feast"),
                # "target player draws" is DUAL-USE — point it at an opponent to
                # punish (or at yourself to draw), so it belongs to the punish lane.
                _card("Inspiration"),
            ],
            # A pure self-cantrip has no target choice — it can only help you.
            [_card("Opt")],
        )

    def test_tokens_matter_anchors_token_enters(self):
        self._ck(
            "tokens_matter",
            "you",
            # Leonardo is the token-anchored Cathars' Crusade ("whenever a token you
            # control enters"); the real Crusade watches any creature, so it is not.
            [_card("Leonardo, the Balance")],
            [_card("Darksteel Splicer")],
        )

    def test_exile_removal_excludes_blink(self):
        self._ck(
            "exile_removal",
            "you",
            [_card("Swords to Plowshares")],
            [_card("Ephemerate")],
        )

    def test_bounce_tempo_constrains_object(self):
        self._ck(
            "bounce_tempo",
            "you",
            [_card("Boomerang")],
            [_card("Reprieve")],
        )

    def test_count_anthem_drops_self_scaling_branch(self):
        self._ck(
            "count_anthem",
            "you",
            [_card("Commander's Insignia")],
            [_card("Storm-Kiln Artist")],
        )

    def test_lifeloss_self_drops_painlands(self):
        self._ck(
            "lifeloss_matters",
            "you",
            [_card("K'rrik, Son of Yawgmoth")],
            [_card("Blood Crypt")],
        )

    def test_permanent_etb_recovers_etb_engines(self):
        self._ck(
            "permanent_etb",
            "you",
            [_card("Panharmonicon")],
            [],
        )

    def test_gain_control_requires_you_as_controller(self):
        self._ck(
            "gain_control",
            "you",
            [_card("Control Magic")],
            [_card("Sky Swallower")],
        )


class TestMediumServeFixes2:
    """MEDIUM batch 7b: more serve recall/precision fixes."""

    def _ck(self, key, scope, plus, minus):
        sig = _sig(key, scope)
        for card in plus:
            assert serves(card, sig) is True, (key, card.get("name"))
        for card in minus:
            assert serves(card, sig) is False, (key, card.get("name"))

    def test_opponents_graveyard_recovers_hate_payoffs(self):
        self._ck(
            "graveyard_matters",
            "opponents",
            [
                _card("Bojuka Bog"),
                _card("Ruin Crab"),
            ],
            [_card("Stitcher's Supplier")],
        )

    def test_opponent_search_requires_opponent_subject(self):
        self._ck(
            "opponent_search_matters",
            "opponents",
            [_card("Aven Mindcensor")],
            [_card("Path to Exile")],
        )

    def test_group_draw_each_drops_self_only_additional(self):
        self._ck(
            "card_draw_engine",
            "each",
            [_card("Howling Mine")],
            [_card("Heightened Awareness")],
        )

    def test_cast_from_exile_is_payoffs_not_impulse(self):
        # Cast-from-exile is now the PAYOFF lane (rewards for casting from exile).
        # A pure impulse enabler (Light Up the Stage) belongs to the separate
        # impulse_top_play avenue, not here.
        self._ck(
            "cast_from_exile",
            "you",
            [_card("Nalfeshnee")],
            [_card("Light Up the Stage")],
        )
        # A rebound self-cast (Consuming Vapors): its reminder text ("cast this card
        # from exile") is not payoff prose, so the ORACLE arm stays off it. The full
        # serve still credits it through the Rebound keyword by design (f53b0776:
        # Suspend / Foretell / Rebound all cast from exile, CR 702.88a).
        vapors = _card("Consuming Vapors")
        serve = spec_for(_sig("cast_from_exile", "you")).serve
        assert serve.oracle.search(vapors["oracle_text"]) is None
        assert serves(vapors, _sig("cast_from_exile", "you")) is True

    def test_doubling_splits_token_and_counter_doublers(self):
        # token_doubling and counter_doubling are SEPARATE lanes (inherently different
        # properties): a token doubler wants token MAKERS; a counter doubler wants
        # counter SOURCES. Doubling Season feeds both; Parallel Lives only tokens;
        # Hardened Scales only counters. Real cards, full oracle text.
        parallel_lives = _card("Parallel Lives")
        doubling_season = _card("Doubling Season")
        hardened_scales = _card("Hardened Scales")
        hangarback = _card("Hangarback Walker")
        tok = _sig("token_doubling", "you")
        cnt = _sig("counter_doubling", "you")
        # Token lane (main + extras): token doublers + token makers; a pure counter
        # doubler (Hardened Scales) is off-theme.
        assert _lane_covers(parallel_lives, tok) is True
        assert _lane_covers(doubling_season, tok) is True
        assert _lane_covers(hangarback, tok) is True
        assert _lane_covers(hardened_scales, tok) is False
        # Counter lane: counter doublers + counter sources; a pure token doubler
        # (Parallel Lives) is off-theme.
        assert _lane_covers(doubling_season, cnt) is True
        assert _lane_covers(hardened_scales, cnt) is True
        assert _lane_covers(hangarback, cnt) is True
        assert _lane_covers(parallel_lives, cnt) is False


class TestSweepHandSpecs:
    """Sweep keys that need a STRUCTURED serve (keyword/veto) the auto-registered
    oracle-only serve can't carry — given a hand-written SPECS override."""

    def test_excess_damage_serves_trample_bodies(self):
        sig = _sig("excess_damage", "you")
        pelakka = _card("Pelakka Wurm")
        payoff = _card("Flame Spill")
        vanilla = _card("Grizzly Bears")
        assert serves(pelakka, sig) is True  # trample keyword
        assert serves(payoff, sig) is True  # excess damage payoff
        assert serves(vanilla, sig) is False

    def test_anthem_static_excludes_until_end_of_turn(self):
        sig = _sig("anthem_static", "you")
        glorious = _card("Glorious Anthem")
        overcome = _card("Overrun")
        assert serves(glorious, sig) is True  # static anthem
        assert serves(overcome, sig) is False  # one-shot pump (until end of turn)

    def test_anthem_static_serves_color_conditional_anthems(self):
        # Bad Moon ("Black creatures get +1/+1") is THE iconic black anthem, but the
        # serve required "you control" / "nonblack" / "other", so a color-conditional
        # anthem was missed — and Hall of Triumph's "creatures you control of the chosen
        # color get +1/+1" too (the color phrase splits "control" from "get"). The
        # one-shot color pump stays vetoed by serve_not. Real oracle.
        sig = _sig("anthem_static", "you")
        bad_moon = _card("Bad Moon")
        hall = _card("Hall of Triumph")
        nocturnal_raid = _card("Nocturnal Raid")
        assert serves(bad_moon, sig) is True  # static color anthem
        assert serves(hall, sig) is True  # chosen-color anthem
        assert serves(nocturnal_raid, sig) is False  # one-shot pump still vetoed

    def test_ltb_matters_excludes_o_ring_removal(self):
        sig = _sig("ltb_matters", "you")
        nikara = _card("Nikara, Lair Scavenger")
        banishing = _card("Banishing Light")
        assert serves(nikara, sig) is True  # LTB payoff
        assert serves(banishing, sig) is False  # O-Ring exile-until-leaves


class TestMediumBatch8:
    """MEDIUM batch 8: sweep-regex surgeries + extraction/scope fixes."""

    def test_big_hand_excludes_stax_hand_size_refs(self):
        sig = _sig("big_hand_matters", "you")
        no_max = _card("Spellbook")
        ensnaring = _card("Ensnaring Bridge")
        assert serves(no_max, sig) is True
        assert serves(ensnaring, sig) is False

    def test_counter_manipulation_requires_plus_one_counters(self):
        sig = _sig("counter_manipulation", "you")
        # Triskelion, not Hex Parasite: the Parasite's current Oracle text removes
        # "up to X counters" of any kind, with no +1/+1 in it.
        triskelion = _card("Triskelion")
        mana_bloom = _card("Mana Bloom")
        assert serves(triskelion, sig) is True
        assert serves(mana_bloom, sig) is False

    def test_life_total_set_drops_symmetric_damage_branch(self):
        sig = _sig("life_total_set", "any")
        mirror = _card("Mirror Universe")
        price = _card("Price of Progress")
        assert serves(mirror, sig) is True
        assert serves(price, sig) is False

    def test_creature_cast_trigger_recovers_you_cast(self):
        # ADR-0027: creature_cast_trigger migrated to the Card IR — a cast_spell trigger
        # with a Creature subject opens it via the hybrid path, not the deleted regex.

        # Real production extractor: a cast_spell trigger with a Creature subject
        # opens the lane.
        keys = {s.key for s in test_signals("Beast Whisperer")}
        assert "creature_cast_trigger" in keys

    def test_win_lose_game_self_win_not_mislabeled_opponents(self):
        # ADR-0027 t2b4a-B: win_lose_game is IR-served from the win_game / lose_game
        # Effect categories (scope 'any', the behavior-neutral row scope — never
        # 'opponents', so a self-wincon is not mislabeled). Regex path no longer fires.

        # Real production extractor: the upkeep win_game Effect (scope 'you') — never
        # 'opponents', so a self-wincon is not mislabeled.
        sigs = [
            s for s in test_signals("Felidar Sovereign") if s.key == "win_lose_game"
        ]
        assert sigs
        assert all(s.scope != "opponents" for s in sigs)


class TestMediumBatch9:
    def test_counter_distribute_is_board_wide_only(self):
        sig = _sig("counter_distribute", "you")
        cathars = _card("Cathars' Crusade")
        venerable = _card("Venerable Knight")
        assert serves(cathars, sig) is True
        assert serves(venerable, sig) is False

    def test_keyword_tribe_requires_payoff_anchor(self):
        # ADR-0027: keyword_tribe migrated to the Card IR (a subject-carrying kept
        # mirror over the record's oracle_text), so assert against the real production
        # extractor — the mirror reads the record, not the IR structure.
        from mtg_utils._analysis.signals import signal_keys

        # Real production extractor for each real card (the subject-carrying kept
        # mirror over oracle_text).
        praetor_kw = {
            s.subject
            for s in test_signals("Hand of the Praetors")
            if s.key == signal_keys.KEYWORD_TRIBE
        }
        whip_kw = {
            s.subject
            for s in test_signals("Whiptongue Hydra")
            if s.key == signal_keys.KEYWORD_TRIBE
        }
        assert "Infect" in praetor_kw  # a real keyword-tribe anthem
        assert "Flying" not in whip_kw  # "destroy all creatures with flying" is removal


def test_play_from_top_is_its_own_avenue_and_excludes_look_at_top():
    """Play-from-top-of-library (Future Sight) is its own avenue — it casts from the
    LIBRARY, not exile, so it's neither impulse nor cast-from-exile. The serve requires a
    play/cast verb so look/scry/mill ("look at ... from the top", Stargaze) don't match.
    """
    top = _sig("play_from_top")
    cfe = _sig("cast_from_exile")
    stargaze = _card("Stargaze")
    future_sight = _card("Future Sight")
    # Future Sight serves play_from_top, NOT cast-from-exile (different zone).
    assert serves(future_sight, top)
    assert not serves(future_sight, cfe)
    # A look-at-top effect serves neither.
    assert not serves(stargaze, top)
    assert not serves(stargaze, cfe)


def test_cheat_into_play_credits_fat_creatures_as_payoff():
    """The PAYOFF of a cheat-into-play deck is the huge body it cheats in (Craterhoof,
    Worldspine Wurm, Emrakul) — a power-5+ creature must be on-theme for the lane, even
    though its own text never says 'onto the battlefield'."""
    sig = _sig("cheat_into_play")
    worldspine = _card("Worldspine Wurm")
    assert _lane_covers(worldspine, sig)
    # The enabler (a reanimation/cheat spell) still serves via the main serve.
    sneak = _card("Sneak Attack")
    assert _lane_covers(sneak, sig)


def test_cheat_into_play_does_not_credit_small_creatures():
    """A 2/2 bear is not the payoff of a cheat deck — power gate keeps it off-theme."""
    sig = _sig("cheat_into_play")
    bear = _card("Grizzly Bears")
    assert not _lane_covers(bear, sig)


def test_voltron_credits_aura_equipment_cost_reduction():
    """Danitha-style 'Aura and Equipment spells you cast cost {1} less' is a voltron
    payoff — it makes suiting up cheaper. EDHREC ranks it top-synergy for voltron."""
    sig = _sig("voltron_matters")
    danitha = _card("Danitha Capashen, Paragon")
    assert _lane_covers(danitha, sig)


def test_voltron_credits_equipment_aura_tutors():
    """Open the Armory / Steelshaper's Gift fetch the suit — top voltron synergy."""
    sig = _sig("voltron_matters")
    armory = _card("Open the Armory")
    gift = _card("Steelshaper's Gift")
    assert _lane_covers(armory, sig)
    assert _lane_covers(gift, sig)


def test_voltron_credits_protection_for_the_threat():
    """Protecting the one suited-up creature is THE voltron support package — Mother of
    Runes, Bastion Protector, Avacyn are top-synergy for voltron commanders."""
    sig = _sig("voltron_matters")
    mom = _card("Mother of Runes")
    bastion = _card("Bastion Protector")
    avacyn = _card("Avacyn, Angel of Hope")
    assert _lane_covers(mom, sig)
    assert _lane_covers(bastion, sig)
    assert _lane_covers(avacyn, sig)


def test_voltron_protection_does_not_credit_plain_anthems():
    """A flying/+1+1 anthem is not protection — precision guard so the protect-extra
    doesn't swallow every team buff."""
    sig = _sig("voltron_matters")
    # No real card grants flying AND +1/+1 alone: one real anthem for each half.
    assert not _lane_covers(_card("Glorious Anthem"), sig)
    assert not _lane_covers(_card("Levitation"), sig)


def test_evasion_serves_horsemanship_via_keyword():
    """A horsemanship creature feeds the evasion lane — but its 'can't be blocked
    except' text trips the serve's negative lookahead, so credit it by the keyword[]."""
    sig = _sig("evasion_self")
    shu_general = _card("Shu General")
    assert _lane_covers(shu_general, sig)


def test_power_double_credits_big_bodies():
    """A power-doubler (Rhonas / Mr. Orfeo) wants high BASE power to double — Ghalta
    (12 power) is the payoff, not a 2/2."""
    sig = _sig("power_double")
    ghalta = _card("Ghalta, Primal Hunger")
    bear = _card("Grizzly Bears")
    assert serves(ghalta, sig)
    assert not serves(bear, sig)


def test_creature_ping_credits_big_bodies():
    """A power-as-damage commander (Itzquinth) wants high power for more ping damage."""
    sig = _sig("creature_ping")
    fatty = _card("Worldspine Wurm")
    assert serves(fatty, sig)


def test_blink_serves_two_sentence_flicker():
    """Flickerwisp / Charming Prince write the flicker as two sentences ('exile … .
    Return it …'); the serve must cross the one sentence boundary, anchored to a
    return-pronoun so an unrelated exile+return-a-land doesn't match."""
    sig = _sig("blink_flicker")
    flickerwisp = _card("Flickerwisp")
    charming = _card("Charming Prince")
    assert _lane_covers(flickerwisp, sig)
    assert _lane_covers(charming, sig)


def test_blink_does_not_match_unrelated_exile_then_return_land():
    # Precision: exile-removal followed by an unrelated land-return is not flicker.
    sig = _sig("blink_flicker")
    # Fictional (ADR-0056 machinery): no real card pairs exile-removal with an
    # unrelated land return, so the regex shape is pinned by a made-up record.
    card = {
        "name": "Not Flicker",
        "type_line": "Sorcery",
        "oracle_text": "Exile target creature. Return a Forest from your graveyard to "
        "the battlefield.",
    }
    assert not _lane_covers(card, sig)


def test_graveyard_serves_cards_in_your_graveyard():
    """Victimize and many recursion spells say 'creature cards IN your graveyard' — the
    serve only had into/from, missing the very common 'in your graveyard' phrasing."""
    sig = _sig("graveyard_matters")
    victimize = _card("Victimize")
    assert _lane_covers(victimize, sig)


def test_graveyard_you_does_not_serve_opponent_graveyard():
    # Precision: an opponents'-graveyard card must NOT serve the YOUR-graveyard lane.
    sig = _sig("graveyard_matters")
    # Tormod's Crypt, not Bojuka Bog: the Bog's "when this land enters, exile
    # target ..." is an ETB-value trigger, which the lane credits on its own.
    card = _card("Tormod's Crypt")
    assert not _lane_covers(card, sig)


def test_activated_ability_serves_support_package():
    """The activated-ability engine surfaces cost reducers, untappers, haste-for-
    abilities, and ability copiers — the package that powers a {T}: commander."""
    sig = _sig("activated_ability")
    training = _card("Training Grounds")
    elixir = _card("Thousand-Year Elixir")
    rings = _card("Rings of Brighthearth")
    ioreth = _card("Ioreth of the Healing House")
    for c in (training, elixir, rings, ioreth):
        assert _lane_covers(c, sig), c["name"]


def test_activated_ability_does_not_serve_a_vanilla_bear():
    sig = _sig("activated_ability")
    bear = _card("Grizzly Bears")
    assert not _lane_covers(bear, sig)


def test_deathtouch_gear_serves_ping_and_noncombat_lanes():
    """Basilisk Collar (deathtouch gear) is top-synergy for pingers / power-as-damage /
    noncombat-damage commanders (Ghyrson, Tahngarth, Hidetsugu) — deathtouch + any ping
    kills anything. Previously only the Burn lane carried the deathtouch extra."""
    collar = _card("Basilisk Collar")
    for key in ("creature_ping", "noncombat_damage_payoff", "damage_equal_power"):
        assert _lane_covers(collar, _sig(key)), key


def test_all_counter_lanes_serve_sources_and_doublers():
    """Every +1/+1-counter lane should surface the core package — counter SOURCES
    (Forgotten Ancient: 'put a +1/+1 counter') and counter DOUBLERS (Hardened Scales) —
    no matter which fragmented counter lane the commander opened."""
    forgotten = _card("Forgotten Ancient")
    scales = _card("Hardened Scales")
    for key in (
        "counter_place_trigger",
        "keyword_counter",
        "counter_replace_bonus",
        "counter_move",
        "counter_distribute",
        "counter_manipulation",
    ):
        assert _lane_covers(forgotten, _sig(key)), f"source/{key}"
        assert _lane_covers(scales, _sig(key)), f"doubler/{key}"


def test_creature_cast_trigger_credits_cost_reducers_and_fatties():
    """Green creature-cast commanders (Gwenna, Runadi, Eshki) ramp into fatties — they
    want creature cost reducers (Goreclaw) and genuine bombs (Ghalta), the top-synergy
    cards that lane missed. power_min=6 keeps it to true fatties, not every 5/5."""
    sig = _sig("creature_cast_trigger")
    goreclaw = _card("Goreclaw, Terror of Qal Sisma")
    ghalta = _card("Ghalta, Primal Hunger")
    midsize = _card("Hill Giant")
    assert _lane_covers(goreclaw, sig)
    assert _lane_covers(ghalta, sig)
    assert not _lane_covers(midsize, sig)


def test_toughness_combat_credits_big_butts_and_walls():
    """Doran / Arcades deal damage with TOUGHNESS — they want big-toughness bodies and
    Walls (defenders), which the toughness lane previously couldn't surface."""
    sig = _sig("toughness_combat")
    wall = _card("Wall of Denial")
    big_butt = _card("Indomitable Ancients")
    small = _card("Grizzly Bears")
    assert _lane_covers(wall, sig)
    assert _lane_covers(big_butt, sig)
    assert not _lane_covers(small, sig)


def test_toughness_combat_serve_skips_base_pt_set():
    """The serve's oracle arm reads toughness as a VALUE ("deals damage equal to
    its toughness"), never a base-P/T set: Ambassador Blorpityblorpboop's "base
    toughness become equal to those stickers' total toughness" is layer 7b
    (CR 613.4b), and its 3/3 body clears neither the toughness>=4 floor nor the
    butt stat line — so it isn't served. Doran (the value read, on a 0/5)
    still is."""
    sig = _sig("toughness_combat")
    assert not _lane_covers(_card("Ambassador Blorpityblorpboop"), sig)
    assert _lane_covers(_card("Doran, the Siege Tower"), sig)


def test_clone_credits_big_creatures_worth_copying():
    """The clone blurb promises 'strong creatures worth copying' — deliver it: Etali (a
    6/6 bomb) is a top clone/token-copy target, not just the clone effects themselves."""
    sig = _sig("clone_makers")
    etali = _card("Etali, Primal Storm")
    assert _lane_covers(etali, sig)


def test_go_wide_credits_board_protection():
    """Go-wide decks want mass-indestructible to survive wraths (Selfless Spirit) — the
    protection extra now reaches the go-wide lane, not just voltron."""
    sig = _sig("creatures_matter")
    selfless = _card("Selfless Spirit")
    assert _lane_covers(selfless, sig)


def test_landfall_serves_basic_type_ramp():
    """Skyshroud Claim / Nature's Lore / Farseek search for 'Forest'/'a Plains or
    Island' — basic-type names, never the word 'land' — so the landfall ramp serve
    missed them. These put lands onto the battlefield, the bread-and-butter landfall
    fuel."""
    sig = _sig("landfall")
    skyshroud = _card("Skyshroud Claim")
    farseek = _card("Farseek")
    assert _lane_covers(skyshroud, sig)
    assert _lane_covers(farseek, sig)


def test_landfall_does_not_serve_a_nonland_tutor():
    sig = _sig("landfall")
    demonic = _card("Demonic Tutor")
    assert not _lane_covers(demonic, sig)


def test_ltb_serves_flicker_effects():
    """A leaves-the-battlefield commander (Bilbo, Genku, Lagrella) wants flicker — it
    blinks your own permanents, firing both LTB and a fresh ETB. The serve matched LTB
    triggers but not the flicker effects its own blurb ('blink fodder') promises."""
    sig = _sig("ltb_matters")
    ghostly = _card("Ghostly Flicker")
    assert _lane_covers(ghostly, sig)


def test_regenerate_lane_serves_voltron_auras():
    """A regenerate/resilience commander is a resilient beater — a voltron plan. Its
    top-synergy cards are buff/protection Auras and gear (Rancor, Bear Umbra, Alpha
    Authority) that the bare regenerate serve missed."""
    sig = _sig("regenerate_makers")
    rancor = _card("Rancor")
    alpha = _card("Alpha Authority")
    assert _lane_covers(rancor, sig)
    assert _lane_covers(alpha, sig)


def test_power_growth_lanes_serve_fling_payoffs():
    """Power-growth decks (firebreathing, variable P/T, +1/+1, power-double) want to
    convert that power into damage — Fling / Chandra's Ignition / Soul's Fire. The
    board-sweep form ('to each other creature and player') was missed by the
    single-target fling regex."""
    ignition = _card("Chandra's Ignition")
    fling = _card("Fling")
    for key in ("power_matters", "self_pump", "variable_pt", "power_double"):
        assert _lane_covers(ignition, _sig(key)), f"ignition/{key}"
        assert _lane_covers(fling, _sig(key)), f"fling/{key}"


def test_token_copy_credits_big_creatures():
    """token_copy's blurb promises 'strong creatures to copy' — deliver it: Etali (6/6
    bomb) is a top token-copy target (Cadric, Feldon), not just the copy effects."""
    sig = _sig("token_copy_makers")
    etali = _card("Etali, Primal Storm")
    assert _lane_covers(etali, sig)


def test_go_wide_credits_etb_doubler():
    """A go-wide deck full of creature ETBs wants Panharmonicon — the go-wide lane had
    ETB-value/payoff extras but not the ETB-doubler."""
    sig = _sig("creatures_matter")
    panharmonicon = _card("Panharmonicon")
    assert _lane_covers(panharmonicon, sig)


def test_stax_serves_replacement_search_hate():
    """Aven Mindcensor / Maze of Ith-style search hate uses a REPLACEMENT ('if an
    opponent would search ... top four instead'), not 'can't search' — the stax serve
    only had the prohibition form."""
    sig = _sig("stax_taxes", "opponents")
    aven = _card("Aven Mindcensor")
    assert _lane_covers(aven, sig)


def test_reanimator_credits_etb_value_targets():
    """A reanimator deck wants high-ETB creatures to reanimate — Mulldrifter (draw) and
    edict-ETB creatures (Plaguecrafter, Accursed Marauder: 'each player sacrifices').
    The reanimator lane served the spells but not the targets."""
    sig = _sig("reanimator")
    mulldrifter = _card("Mulldrifter")
    plaguecrafter = _card("Plaguecrafter")
    assert _lane_covers(mulldrifter, sig)
    assert _lane_covers(plaguecrafter, sig)


def test_ramp_credits_the_fatties_it_accelerates_into():
    """ramp promises 'accelerate into your payoffs' — deliver them: the big
    bombs (Ghalta, power 12) and creature cost reducers (Goreclaw). Only 3% of
    commanders open this 'big mana' lane, so power_min=6 is clean. A 2/2 stays off."""
    sig = _sig("ramp")
    ghalta = _card("Ghalta, Primal Hunger")
    bear = _card("Grizzly Bears")
    assert _lane_covers(ghalta, sig)
    assert not _lane_covers(bear, sig)


def test_token_anthems_serve_token_lanes():
    """Intangible Virtue / token anthems ('creature TOKENS you control get +1/+1') are
    top-synergy for token commanders — but the go-wide serve matched 'creatures you
    control get', not the 'creature tokens you control' phrasing."""
    virtue = _card("Intangible Virtue")
    assert _lane_covers(virtue, _sig("token_maker"))
    assert _lane_covers(virtue, _sig("creatures_matter"))


def test_snow_lane_serves_snow_cards():
    sig = _sig("snow_matters")
    rime = _card("Rime Tender")
    search = _card("Search for Glory")
    assert _lane_covers(rime, sig)
    assert _lane_covers(search, sig)


def test_tribal_serve_matches_members_by_type_not_just_oracle():
    """A creature is a member of its own tribe — the tribal serve must match by
    TYPE-LINE, not only oracle. Dread Shade (oracle '{B}: +1/+1', no 'Shade' word) and
    Llanowar Elves (oracle '{T}: Add {G}') are tribe members that the oracle-only serve
    silently dropped — fatal for lord-less tribes (Shade was 0/10)."""
    dread = _card("Dread Shade")
    llanowar = _card("Llanowar Elves")
    assert _lane_covers(dread, _sig_sub("type_matters", "Shade"))
    assert _lane_covers(llanowar, _sig_sub("type_matters", "Elf"))
    # Precision: a Goblin does NOT serve Elf tribal.
    goblin = _card("Raging Goblin")
    assert not _lane_covers(goblin, _sig_sub("type_matters", "Elf"))


def test_vanilla_lane_serves_vanilla_creatures_and_payoffs():
    sig = _sig("vanilla_matters")
    gigantosaurus = _card("Gigantosaurus")
    muraganda = _card("Muraganda Petroglyphs")
    bear_with_text = _card("Elvish Visionary")
    assert _lane_covers(gigantosaurus, sig)  # vanilla member
    assert _lane_covers(muraganda, sig)  # the payoff
    assert not _lane_covers(bear_with_text, sig)  # has an ability → not vanilla


def test_combat_damage_lane_serves_gear_and_pump():
    """A combat-damage-trigger commander (Benton, Ojutai, Edric) wants to CONNECT and
    survive: gear (Ring of Thune) and pump (Giant Growth). The lane served evasion but
    not the gear/pump that keeps the attacker alive and bigger."""
    sig = _sig("combat_damage_matters", "opponents")
    ring = _card("Ring of Thune")
    giant_growth = _card("Giant Growth")
    assert _lane_covers(ring, sig)
    assert _lane_covers(giant_growth, sig)


def test_toughness_lane_credits_butts_by_statline():
    """The ideal toughness-deck creature is a BUTT — toughness > power (1/5, 0/3) — which
    a flat toughness>=4 threshold misses. Detect it from the actual stat line, not
    oracle. A balanced 3/3 (not toughness-skewed, below the >=4 floor) stays off."""
    sig = _sig("toughness_combat")
    one_five = _card("Wall of Wonder")
    zero_three = _card("Wall of Wood")
    balanced = _card("Hill Giant")
    assert _lane_covers(one_five, sig)
    assert _lane_covers(zero_three, sig)
    assert not _lane_covers(balanced, sig)


def test_redirect_lane_serves_pariah_and_indestructible():
    sig = _sig("damage_redirect")
    pariah = _card("Pariah")
    shielded = _card("Shielded by Faith")
    assert _lane_covers(pariah, sig)
    assert _lane_covers(shielded, sig)


def test_opponents_mill_serves_exile_library_artifacts():
    sig = _sig("graveyard_matters", "opponents")
    pyxis = _card("Pyxis of Pandemonium")
    codex = _card("Codex Shredder")
    assert _lane_covers(pyxis, sig)
    assert _lane_covers(codex, sig)


def test_board_wipe_lane_serves_reanimation_and_resilient_bombs():
    """The 'Board wipes' blurb promises 'resilience to rebuild' — deliver it: a
    repeatable-wrath commander (Mageta) wants reanimation (Breath of Life) to rebuild
    after the sweep and indestructible bombs (Zetalpa) that survive it."""
    sig = _sig("mass_removal")
    breath = _card("Breath of Life")
    zetalpa = _card("Zetalpa, Primal Dawn")
    assert _lane_covers(breath, sig)
    assert _lane_covers(zetalpa, sig)


def test_self_blink_serves_etb_payoffs():
    """A self-blinking commander (Norin) re-enters constantly, firing 'whenever a
    creature enters' payoffs (Impact Tremors, Genesis Chamber) and doublers
    (Panharmonicon). The lane served neither."""
    sig = _sig("self_blink")
    tremors = _card("Impact Tremors")
    panharmonicon = _card("Panharmonicon")
    assert _lane_covers(tremors, sig)
    assert _lane_covers(panharmonicon, sig)


def test_untap_lanes_serve_untap_auras():
    """Tui and La (tap-for-draw / untap-for-counter) wants untap auras like Freed from
    the Real ('{U}: untap enchanted creature') — the serve only had target/all/another/
    each, missing the 'enchanted/this' forms."""
    freed = _card("Freed from the Real")
    assert _lane_covers(freed, _sig("untap_engine"))
    assert _lane_covers(freed, _sig("tap_untap_matters"))


def test_self_lifeloss_serves_life_total_manipulation():
    """Selenia pays life as a resource (lifeloss scope you) — she wants life-total
    swaps/resets (Axis of Mortality, Repay in Kind), life recovery (Children of Korlis),
    and low-life wincons (Near-Death Experience)."""
    sig = _sig("lifeloss_matters", "you")
    axis = _card("Axis of Mortality")
    children = _card("Children of Korlis")
    repay = _card("Repay in Kind")
    for c in (axis, children, repay):
        assert _lane_covers(c, sig), c["name"]


def test_burn_serves_land_enter_punishers():
    sig = _sig("direct_damage")
    ankh = _card("Ankh of Mishra")
    assert _lane_covers(ankh, sig)


def test_redirect_lane_serves_damage_prevention():
    """A redirect-to-self commander (Hazduhr, Cho-Manno) also wants damage PREVENTION —
    Battlefield Medic, Worship — to blank the damage it soaks."""
    sig = _sig("damage_redirect")
    medic = _card("Battlefield Medic")
    worship = _card("Worship")
    assert _lane_covers(medic, sig)
    assert _lane_covers(worship, sig)


def test_forced_attack_serves_extra_combat():
    sig = _sig("forced_attack")
    waw = _card("World at War")
    assert _lane_covers(waw, sig)


def test_outlaw_lane_serves_outlaws_and_anthems():
    sig = _sig("outlaw_matters")
    pirate = _card("Goblin Trailblazer")
    rogue = _card("Krovikan Scoundrel")
    anthem = _card("Hellspur Posse Boss")
    non = _card("Grizzly Bears")
    assert _lane_covers(pirate, sig)
    assert _lane_covers(rogue, sig)
    assert _lane_covers(anthem, sig)
    assert not _lane_covers(non, sig)


def test_donate_lane_serves_drawback_creatures():
    """Jon Irenicus donates creatures to opponents — he wants creatures whose DOWNSIDE
    punishes their controller (Abyssal Persecutor 'you can't win', Flesh Reaver 'deals
    damage to you', Demonic Taskmaster 'upkeep: sacrifice a creature')."""
    sig = _sig("donate_makers")
    persecutor = _card("Abyssal Persecutor")
    reaver = _card("Flesh Reaver")
    taskmaster = _card("Demonic Taskmaster")
    for c in (persecutor, reaver, taskmaster):
        assert _lane_covers(c, sig), c["name"]


def test_banding_lane_serves_banding_creatures():
    sig = _sig("has_banding")
    hero = _card("Benalish Hero")
    assert _lane_covers(hero, sig)


def test_flicker_extra_handles_two_sentence():
    """_FLICKER_EXTRA (used by ltb/creature_etb/self_blink) must also catch two-sentence
    flicker (Charming Prince / Flickerwisp 'Exile … . Return it …') — it was still
    period-blocked, so ltb commanders missed those cards."""
    sig = _sig("ltb_matters")
    charming = _card("Charming Prince")
    assert _lane_covers(charming, sig)


def test_legend_rule_off_serves_copy_effects():
    """A legend-rule-off commander (Brothers Yamazaki) wants self-copy effects — having
    multiple copies of itself (Helm of the Host, Blade of Selves, Mirror Box)."""
    sig = _sig("legend_rule_off")
    helm = _card("Helm of the Host")
    blade = _card("Blade of Selves")
    assert _lane_covers(helm, sig)
    assert _lane_covers(blade, sig)


def test_graveyard_lane_serves_etb_value_recursion_targets():
    """Graveyard/reanimator commanders (Alesha, Gisa) recur creatures with strong ETBs —
    edict-ETB (Fleshbag Marauder), value-ETB (Eternal Witness). The fuel lane served the
    mill/recursion but not the targets worth recurring."""
    sig = _sig("graveyard_matters", "you")
    fleshbag = _card("Fleshbag Marauder")
    witness = _card("Eternal Witness")
    assert _lane_covers(fleshbag, sig)
    assert _lane_covers(witness, sig)


def test_dies_recursion_and_flicker_are_separate_avenues_on_etb_lanes():
    """Dies-recursion (death→return) and flicker (exile→return) are DISTINCT mechanics
    (CR: graveyard 700.4 vs exile 400.1, both LTB per 603.6c). An ETB-reuse / LTB
    commander wants BOTH — so the ETB/blink/ltb lanes carry them as SEPARATE avenues,
    not one combined flicker serve."""
    feign = _card("Feign Death")  # dies-recursion (death-return), NOT flicker
    ephemerate = _card("Ephemerate")  # flicker (exile-return), NOT dies-recursion
    # ETB-reuse / LTB lanes are served by BOTH mechanics.
    for key in ("blink_flicker", "ltb_matters", "creature_etb", "permanent_etb"):
        assert _lane_covers(feign, _sig(key)), f"{key} should serve dies-recursion"
        assert _lane_covers(ephemerate, _sig(key)), f"{key} should serve flicker"
    # But the mechanics are categorized SEPARATELY: the flicker sub-avenue serves
    # exile-return, not death-return, and vice versa.
    flicker_serve = serve_from_dict({"oracle": signal_specs._FLICKER_ORACLE})
    dies_serve = serve_from_dict({"oracle": signal_specs._DIES_RECURSION_ORACLE})
    assert flicker_serve.matches(ephemerate) is True
    assert flicker_serve.matches(feign) is False  # death-return is not flicker
    assert dies_serve.matches(feign) is True
    assert dies_serve.matches(ephemerate) is False  # flicker is not death-return


def test_tribal_lane_serves_type_agnostic_anthems():
    """Every tribal lane should credit the type-AGNOSTIC tribal payoffs — "choose a
    creature type … of the chosen type" anthems (Vanquisher's Banner, Herald's Horn)
    and "shares a creature type" pumps (Shared Animosity, Coat of Arms) work for ANY
    tribe, so a Knight / Elf / Soldier deck wants them."""
    sig = _sig_sub("type_matters", "Knight")
    for card in (
        _card("Shared Animosity"),
        _card("Coat of Arms"),
        _card("Vanquisher's Banner"),
        _card("Herald's Horn"),
    ):
        assert _lane_covers(card, sig), card["name"]
    # Precision: a plain unrelated card is NOT credited as a tribal anthem.
    bolt = _card("Lightning Bolt")
    assert _lane_covers(bolt, sig) is False


def test_tribal_enabler_vs_payoff_and_restricted_list():
    """B1: a type-CHANGER (Xenograft) is an enabler, not a payoff; a RESTRICTED
    type-of-choice payoff (Dawn-Blessed Pennant, "choose Elf, Goblin, …") counts only for
    the tribes it names, never an unlisted one (Scarecrow); an OPEN type-of-choice payoff
    (Door of Destinies) works for any tribe."""
    scarecrow = _sig_sub("type_matters", "Scarecrow")
    goblin = _sig_sub("type_matters", "Goblin")

    def payoff_serves(card, sig):
        ex = spec_for(sig).extras[0]  # the "{s} payoffs" sub-avenue
        return (ex.serve or serve_from_dict(ex.search)).matches(card)

    def enabler_serves(card, sig):
        ex = spec_for(sig).extras[1]  # the "{s} enablers" sub-avenue
        assert ex.label.endswith("enablers")
        return (ex.serve or serve_from_dict(ex.search)).matches(card)

    xenograft = _card("Xenograft")
    dawn = _card("Dawn-Blessed Pennant")
    door = _card("Door of Destinies")
    # board-wide "every creature type" granter — a real enabler
    maskwood = _card("Maskwood Nexus")
    # a lone changeling IS every creature type, but it's a MEMBER body, not an
    # enabler that converts your OTHER creatures
    changeling = _card("Woodland Changeling")
    # Enabler: surfaced by the lane (enabler sub-avenue) but NOT as a payoff.
    assert _lane_covers(xenograft, scarecrow) is True
    assert enabler_serves(xenograft, scarecrow) is True
    assert payoff_serves(xenograft, scarecrow) is False
    # Board-wide "every creature type" granter is an enabler for any tribe.
    assert enabler_serves(maskwood, scarecrow) is True
    # A lone changeling is a tribe MEMBER (bodies lane), NOT an enabler — its "this card
    # is every creature type" reminder must not flood the enabler lane.
    assert enabler_serves(changeling, scarecrow) is False
    assert _lane_covers(changeling, scarecrow) is True  # still a Scarecrow body
    # Restricted payoff: a named tribe (Goblin) counts; an unlisted one (Scarecrow)
    # does not — pinned in the test below.
    assert payoff_serves(dawn, goblin) is True
    # Open type-of-choice payoff works for ANY tribe, including Scarecrow.
    assert payoff_serves(door, scarecrow) is True


def test_restricted_type_choice_payoff_skips_unlisted_tribes():
    """B1: a RESTRICTED type-of-choice payoff (Dawn-Blessed Pennant, "choose Elf,
    Goblin, …") never counts for an unlisted tribe (Scarecrow) — no Scarecrow hook
    at all."""
    scarecrow = _sig_sub("type_matters", "Scarecrow")
    payoffs = spec_for(scarecrow).extras[0]  # the "{s} payoffs" sub-avenue
    dawn = _card("Dawn-Blessed Pennant")
    assert (payoffs.serve or serve_from_dict(payoffs.search)).matches(dawn) is False
    assert _lane_covers(dawn, scarecrow) is False


def test_restricted_chooser_emits_its_listed_types_not_the_wildcard():
    """The chosen_type_matters lane emits a RESTRICTED chooser's printed options as
    subjects (so only those tribes' serves credit it) and the wildcard ``""`` only
    for an open choice."""
    from mtg_utils._analysis.lanes.core_makers import _chosen_type_matters
    from mtg_utils._card_ir.trees import trees_for

    def subjects(name):
        _card(name)  # seeds the concept tree from the snapshot
        trees = trees_for(test_card(name))
        trees = trees if isinstance(trees, (list, tuple)) else [trees]
        return {s.subject for t in trees for s in _chosen_type_matters(t)}

    assert subjects("Dawn-Blessed Pennant") == {
        "Elemental",
        "Elf",
        "Faerie",
        "Giant",
        "Goblin",
        "Kithkin",
        "Merfolk",
        "Treefolk",
    }
    assert subjects("Door of Destinies") == {""}
    goblin = _sig_sub("type_matters", "Goblin")
    payoffs = spec_for(goblin).extras[0]
    dawn = _card("Dawn-Blessed Pennant")
    # credited structurally for a LISTED tribe, text arm removed
    no_text = dataclasses.replace(payoffs.serve, oracle=None)
    assert no_text.matches(dawn) is True


def test_activated_ability_lane_serves_costly_activated_creatures():
    """A cost-reducer / untapper commander (Agatha, Training Grounds) wants the PAYOFF
    targets — creatures with an expensive mana-cost activated ability to exploit the
    discount/untap. The serve credited reducers but not the targets."""
    sig = _sig("activated_ability", "you")
    for card in (
        _card("Bhaal's Invoker"),
        _card("Wildheart Invoker"),
        _card("Captivating Crew"),
    ):
        assert _lane_covers(card, sig) is True, card["name"]
    # control: a {T}-only ability (no mana cost) isn't a mana-discount target
    tapper = _card("Llanowar Elves")
    assert _lane_covers(tapper, sig) is False


def test_graveyard_lane_serves_recursion_keyword_cards():
    """A self-graveyard deck wants the graveyard-recursion KEYWORD cards (Dredge,
    Flashback, Unearth, Escape, Disturb, Scavenge) whose graveyard mechanic is reminder
    text the oracle serve missed. Credit by keyword (CR 702.x)."""
    sig = _sig("graveyard_matters", "you")
    for card in (
        _card("Stinkweed Imp"),  # Dredge
        _card("Dregscape Zombie"),  # Unearth
        _card("Lingering Souls"),  # Flashback
        _card("Deadbridge Goliath"),  # Scavenge
    ):
        assert _lane_covers(card, sig) is True, card["name"]
        # The keyword arm alone: strip the oracle text (and the oracle_id the
        # structural arm keys on) so only keywords[] can credit it.
        bare = {**card, "oracle_text": ""}
        bare.pop("oracle_id", None)
        assert _lane_covers(bare, sig) is True, card["name"]
    # control: a plain Flying creature is not graveyard-relevant
    flyer = _card("Wind Drake")
    assert _lane_covers(flyer, sig) is False


def test_counters_lane_serves_counter_keyword_creatures():
    """A +1/+1-counter deck wants the counter-KEYWORD creatures (Undying, Graft, Riot,
    Bloodthirst, Fabricate) whose mechanic is reminder text the oracle serves miss.
    Credit them by the keyword (CR 702.x)."""
    sig = _sig("plus_one_matters", "you")
    cases = (
        _card("Young Wolf"),  # Undying
        _card("Cytoplast Root-Kin"),  # Graft
        _card("Stormblood Berserker"),  # Bloodthirst
        _card("Ardent Plea"),  # control: Exalted + Cascade, NOT counter keywords
    )
    results = {}
    bare_results = {}
    for card in cases:
        results[card["name"]] = _lane_covers(card, sig)
        # The keyword arm alone: strip the oracle text (and the oracle_id the
        # structural arm keys on) so only keywords[] can credit it.
        bare = {**card, "oracle_text": ""}
        bare.pop("oracle_id", None)
        bare_results[card["name"]] = _lane_covers(bare, sig)
    for got in (results, bare_results):
        assert got["Young Wolf"] is True
        assert got["Cytoplast Root-Kin"] is True
        assert got["Stormblood Berserker"] is True
        assert got["Ardent Plea"] is False  # cascade is not a counter keyword


def test_pillowfort_served_to_high_synergy_archetypes_only():
    """Pillowfort (Ghostly Prison, Propaganda, Sphere of Safety, Crawlspace) is attached
    ONLY to the archetypes whose pillowfort SYNERGY clears the ~4% background floor (Dan:
    gate on synergy, not raw inclusion): Monarch (86%), Goad/politics (44%), Superfriends
    (24%), Damage-prevention/fog (23%). Everything else — card-advantage/activated/voltron/
    spellslinger (at floor by synergy), Initiative (0%, aggressive), counterspell-control
    (0%), and go-wide/tokens — does NOT get it."""
    fort = (
        _card("Ghostly Prison"),
        _card("Sphere of Safety"),
        _card("Crawlspace"),
    )
    served = [
        ("monarch_matters", "you"),
        ("goad_makers", "opponents"),
        ("superfriends_matters", "you"),
        ("damage_prevention", "you"),
    ]
    for key, scope in served:
        sig = _sig(key, scope)
        for card in fort:
            assert _lane_covers(card, sig), f"{key}/{card['name']}"
    gp = _card("Ghostly Prison")
    for key, scope in [
        ("token_maker", "you"),
        ("activated_ability", "you"),
        ("card_draw_engine", "you"),
        ("voltron_matters", "you"),
        ("spellcast_matters", "you"),
        ("counter_control", "you"),
        ("initiative_matters", "you"),
    ]:
        assert _lane_covers(gp, _sig(key, scope)) is False, key


def test_superfriends_serves_generic_counter_doublers_via_loyalty_extra():
    """ADR-0036/0037 Stage 5 #62: a GENERIC (any-permanent) counter doubler ALSO
    doubles loyalty (CR 306.6 + 122.1), a real hook the "Loyalty doubling" SubAvenue
    serves — but as deck-level ADJACENCY (serve layer), never lane membership
    (ADR-0034 strict membership: a +1/+1-counter deck runs Doubling Season too)."""
    generic_doublers = (
        _card("Doubling Season"),
        _card("Vorinclex, Monstrous Raider"),
        _card("Gilder Bairn"),
    )
    sig = _sig("superfriends_matters", "you")
    for card in generic_doublers:
        assert _lane_covers(card, sig), card["name"]
    # A +1/+1-counter-SPECIFIC or creature/artifact/land-typed doubler never touches
    # loyalty — correctly excluded (over-fire the task explicitly warns against).
    typed_doublers = (
        _card("Winding Constrictor"),
        _card("Corpsejack Menace"),
        _card("Vorel of the Hull Clade"),
    )
    for card in typed_doublers:
        assert not _lane_covers(card, sig), card["name"]


def test_token_lanes_serve_creature_anthems():
    """A token go-wide deck's tokens ARE creatures, so symmetric creature anthems pump
    them — "creatures you control get +1/+1" (Glorious Anthem, Dictate of Heliod), not
    just token-specific ones. token_maker (incl. subject specs) and tokens_matter served
    only token anthems. These are SYMMETRIC ("creatures you control"), not "target
    creature" single pumps."""
    glorious = _card("Glorious Anthem")
    virtue = _card("Intangible Virtue")
    for sig in [
        _sig("tokens_matter", "you"),
        _sig("token_maker", "you"),
        _sig_sub("token_maker", "Spirit"),
    ]:
        label = f"{sig.key}/{sig.subject or '-'}"
        assert _lane_covers(glorious, sig), f"{label}/glorious"
        assert _lane_covers(virtue, sig), f"{label}/virtue"
    # precision: a single-TARGET pump is not a go-wide anthem.
    brute = _card("Brute Force")
    assert _lane_covers(brute, _sig("token_maker", "you")) is False


def test_targeting_heroic_serves_single_target_buffs():
    """A heroic / targeting commander triggers when YOU cast a spell that TARGETS its
    creature (CR 115), so the enablers are cheap single-TARGET pumps/protection (Gods
    Willing, Brute Force, Defiant Strike). "each creature" anthems don't target and must
    NOT count; targeted REMOVAL ("destroy target creature") isn't a buff."""
    sig = _sig("targeting_matters", "any")
    for card in (
        _card("Gods Willing"),
        _card("Brute Force"),
        _card("Temur Battle Rage"),
    ):
        assert _lane_covers(card, sig), card["name"]
    # "each creature" anthem doesn't TARGET — must not count as a heroic enabler.
    anthem = _card("Glorious Anthem")
    assert _lane_covers(anthem, sig) is False
    # targeted removal is not a buff for your own creature.
    rm = _card("Murder")
    assert _lane_covers(rm, sig) is False


def test_opponent_draw_punish_serves_group_draw_enablers():
    """A "whenever an opponent draws → punish" commander (Nekusar) wants the SYMMETRIC /
    forced group-draw enablers that make opponents draw extra (Howling Mine, Temple
    Bell, Dictate of Kruphix, Forced Fruition, Windfall) — distinct from "target player
    draws" (which could benefit only you). The serve credited only the payoff trigger."""
    sig = _sig("opponent_draw_matters", "opponents")
    for card in (
        _card("Temple Bell"),
        _card("Howling Mine"),
        _card("Forced Fruition"),
        _card("Windfall"),
    ):
        assert _lane_covers(card, sig), card["name"]
    # Precision: your OWN cantrip ("You draw a card.") is not a force-opponents-draw enabler.
    assert _lane_covers(_card("Opt"), sig) is False


def test_lands_matter_serves_land_ramp():
    """lands_matter (Molimo, Lord Windgrace — P/T or payoff scales with land count) is
    the same archetype as landfall and wants land ramp, but its serve only credited
    "number of lands" payoffs, not the ramp/fetch that grows the count."""
    sig = _sig("lands_matter", "you")
    for card in (
        _card("Skyshroud Claim"),
        _card("Cultivate"),
        _card("Crucible of Worlds"),
    ):
        assert _lane_covers(card, sig) is True, card["name"]


def test_ramp_serves_basic_land_type_fetches():
    """Ramp serve must credit the basic-land-TYPE fetches (Skyshroud Claim, Nature's
    Lore, Three Visits, Farseek) — they search for "Forest/Plains/… cards", which don't
    contain the word "land", so the bare "search … for … land" missed them."""
    sig = _sig("ramp", "you")
    for card in (
        _card("Skyshroud Claim"),
        _card("Nature's Lore"),
        _card("Farseek"),
    ):
        assert _lane_covers(card, sig) is True, card["name"]


def test_sacrifice_serves_death_value_fodder():
    """A sacrifice deck wants DEATH-VALUE fodder — permanents that replace themselves
    with a card/token/search when they die or are put into a graveyard (Ichor Wellspring,
    Filigree Familiar, Mycosynth Wellspring). The serve keyed on 'whenever … dies' and
    missed the 'put into a graveyard' (artifacts) and 'When … dies' forms. (Confirmed by
    the cross-archetype audit: Sacrifice lane, 9.2x lift.)"""
    sig = _sig("sacrifice_outlets", "you")
    for card in (
        _card("Ichor Wellspring"),
        _card("Filigree Familiar"),
        _card("Mycosynth Wellspring"),
    ):
        assert _lane_covers(card, sig), card["name"]
    # Precision: a plain cantrip with no death/graveyard trigger is not sac fodder.
    cantrip = _card("Opt")
    assert _lane_covers(cantrip, sig) is False


def test_symmetric_edict_serves_recurring_fodder():
    """A forced/symmetric-sacrifice commander (Braids — "each player sacrifices") loses
    its OWN board too, so it wants recurring fodder to survive: recurring token makers
    (Bitterblossom) and self-recurring creatures (Reassembling Skeleton)."""
    sig = _sig("edict_makers", "each")
    bb = _card("Bitterblossom")
    skel = _card("Reassembling Skeleton")
    assert _lane_covers(bb, sig) is True
    assert _lane_covers(skel, sig) is True


def test_copy_lanes_serve_etb_doublers_and_payoffs():
    """Token-copy / clone decks flood the board with creatures that ENTER, so they want
    ETB payoffs (Impact Tremors) and doublers (Panharmonicon) — every copy fires them."""
    pan = _card("Panharmonicon")
    tremors = _card("Impact Tremors")
    for key in ("token_copy_makers", "clone_makers"):
        assert _lane_covers(pan, _sig(key, "you")) is True, f"{key}/Panharmonicon"
        assert _lane_covers(tremors, _sig(key, "you")) is True, f"{key}/Impact Tremors"


def test_clone_lane_serves_token_copy_effects():
    """A clone/copy commander (Stangg, Yosei) wants the token-copy gear too — Helm of
    the Host ("a token that's a copy of equipped creature"), Blade of Selves (myriad),
    Rite of Replication. The clone serve's bare "copy of target/that" missed the
    "equipped"/"it"/myriad forms."""
    sig = _sig("clone_makers", "you")
    helm = _card("Helm of the Host")
    blade = _card("Blade of Selves")
    assert _lane_covers(helm, sig) is True
    assert _lane_covers(blade, sig) is True


def test_blocked_matters_serves_force_block_effects():
    """A 'becomes blocked' payoff (General Marhault Elsdragon: +3/+3 for each creature
    blocking it) wants force-block effects so the per-blocker bonus maxes — Lure /
    Nemesis Mask / Roar of Challenge force every able creature to block."""
    sig = _sig("blocked_matters", "you")
    lure = _card("Lure")
    roar = _card("Roar of Challenge")
    assert _lane_covers(lure, sig) is True
    assert _lane_covers(roar, sig) is True
    # A plain anthem is not a force-block effect.
    anthem = _card("Glorious Anthem")
    assert _lane_covers(anthem, sig) is False


def test_token_copy_serves_makers_and_doublers():
    """Esix converts each token she'd create into a copy of a chosen creature — so she
    wants token MAKERS (more tokens → more copies) and token DOUBLERS (double the
    copies), not just big bodies to copy."""
    sig = _sig("token_copy_makers", "you")
    hornet = _card("Hornet Queen")
    avenger = _card("Avenger of Zendikar")
    adrix = _card("Adrix and Nev, Twincasters")
    assert _lane_covers(hornet, sig) is True
    assert _lane_covers(avenger, sig) is True
    assert _lane_covers(adrix, sig) is True


# ── Long-tail coverage clusters (workflow-diagnosed, verify-before-add) ────────


def test_extra_upkeep_serves_upkeep_payoffs_not_ramp():
    sig = _sig("extra_upkeep", "you")
    as_foretold = _card("As Foretold")
    sol_ring = _card("Sol Ring")
    assert _lane_covers(as_foretold, sig) is True
    assert _lane_covers(sol_ring, sig) is False  # no upkeep trigger — not a payoff


def test_extra_end_step_serves_end_step_payoffs():
    sig = _sig("extra_end_step", "you")
    agent = _card("Agent of Treachery")
    chimil = _card("Chimil, the Inner Sun")
    assert _lane_covers(agent, sig) is True
    assert _lane_covers(chimil, sig) is True


def test_noncombat_damage_serves_player_directed_burn():
    sig = _sig("noncombat_damage_payoff", "you")
    boltwave = _card("Boltwave")
    # "deals damage … equal to" (no explicit number) must still serve a doubler.
    hidetsugu = _card("Heartless Hidetsugu")
    price = _card("Price of Progress")
    # A creature-only sweeper hits no player and must NOT serve the doubler lane.
    pyroclasm = _card("Pyroclasm")
    assert _lane_covers(boltwave, sig) is True
    assert _lane_covers(hidetsugu, sig) is True
    assert _lane_covers(price, sig) is True
    assert _lane_covers(pyroclasm, sig) is False


def test_creatures_matter_serves_board_scaling_lord():
    sig = _sig("creatures_matter", "you")
    leonardo = _card("Leonardo, Big Brother")
    assert _lane_covers(leonardo, sig) is True


def test_artifacts_matter_serves_artifact_dig():
    sig = _sig("artifacts_matter", "you")
    casey = _card("Casey Jones, Jury-Rig Justiciar")
    assert _lane_covers(casey, sig) is True


# ── Serve-gap fixes from the archetype-normalized failing-tail analysis ───────
# Real cards (full oracle_text + type_line from Scryfall bulk) that the failing
# commanders rank as top-synergy but the lanes they open were not crediting.

COMBAT_CELEBRANT = _card("Combat Celebrant")
MORAUG = _card("Moraug, Fury of Akoum")
AGGRAVATED_ASSAULT = _card("Aggravated Assault")


def test_attack_matters_serves_extra_combat_enablers():
    # An attack-trigger commander wants more combats — each extra combat is another
    # round of attack triggers. These were only credited to the narrow extra_combats
    # lane, so attack_matters commanders (Winota, Johan, Umaro) read them as off-theme.
    sig = _sig("attack_matters", "you")
    assert _lane_covers(COMBAT_CELEBRANT, sig) is True
    assert _lane_covers(MORAUG, sig) is True
    assert _lane_covers(AGGRAVATED_ASSAULT, sig) is True
    # Over-fire guard: a vanilla beater with no attack payoff is NOT served.
    grizzly = _card("Grizzly Bears")
    assert _lane_covers(grizzly, sig) is False


def test_attack_matters_serves_extra_turn_spells():
    # attack_matters already credits "additional combat phase" — another round of attack
    # triggers. An extra TURN (Time Warp) is the strict superset: a full turn, combat
    # included, so the attack happens again. Narset, Enlightened Master (free-casts
    # noncreature spells on attack) snowballs hardest off extra turns, but every
    # attack-trigger commander wants the replay. Real oracle.
    sig = _sig("attack_matters", "you")
    time_warp = _card("Time Warp")
    temporal_mastery = _card("Temporal Mastery")
    assert serves(time_warp, sig) is True
    assert serves(temporal_mastery, sig) is True
    # Over-fire guard: an "additional LAND this turn" ramp cantrip (Explore) is not an
    # extra TURN — the extra-turn clause must not leak to "additional land". Real oracle.
    explore = _card("Explore")
    assert serves(explore, sig) is False


BRIBERY = _card("Bribery")
ACQUIRE = _card("Acquire")


def test_gain_control_serves_steal_from_opponent_library():
    # Bribery/Acquire take a card from an opponent's deck and seat it under YOUR
    # control — theft, the gain_control lane's whole point — but the serve only
    # matched the literal "gain control of" phrasing.
    sig = _sig("gain_control", "you")
    assert _lane_covers(BRIBERY, sig) is True
    assert _lane_covers(ACQUIRE, sig) is True
    # Over-fire guard: self-reanimation also "put ... onto the battlefield under
    # your control" but takes from a graveyard, not an opponent's LIBRARY — not theft.
    reanimate = _card("Reanimate")
    assert _lane_covers(reanimate, sig) is False


PANHARMONICON = _card("Panharmonicon")
STRIONIC_RESONATOR = _card("Strionic Resonator")


def test_creature_etb_serves_trigger_doublers():
    # Panharmonicon literally doubles ETB triggers; Strionic copies any triggered
    # ability. An ETB-payoff commander wants both, but they name no "enters" trigger
    # of their own, so the creature_etb serve missed them.
    sig = _sig("creature_etb", "you")
    assert _lane_covers(PANHARMONICON, sig) is True
    assert _lane_covers(STRIONIC_RESONATOR, sig) is True
    # Over-fire guard: a plain vanilla creature is NOT a trigger doubler.
    grizzly = _card("Grizzly Bears")
    assert _lane_covers(grizzly, sig) is False


# ── Theft / cast-an-exiled-card cluster (Gonti / Hostage Taker / Thief of Sanity) ──
GONTI = _card("Gonti, Lord of Luxury")
HOSTAGE_TAKER = _card("Hostage Taker")
THIEF_OF_SANITY = _card("Thief of Sanity")
# Over-fire guard for theft_makers: self-impulse (your OWN library) is not theft.
VALAKUT_EXPLORATION = _card("Valakut Exploration")


def test_impulse_and_cast_from_exile_serve_exile_then_cast_engines():
    # "Exile a card, you may cast it for as long as it remains exiled" is the impulse /
    # cast-from-exile engine (Gonti, Hostage Taker, Thief of Sanity).
    for sig in (_sig("impulse_top_play"), _sig("cast_from_exile")):
        assert _lane_covers(GONTI, sig) is True, sig.key
        assert _lane_covers(HOSTAGE_TAKER, sig) is True, sig.key
        assert _lane_covers(THIEF_OF_SANITY, sig) is True, sig.key


def test_theft_makers_serves_opponent_library_theft_not_self_impulse():
    # theft_makers is steal-from-OPPONENT — Gonti/Thief dig an opponent's library;
    # Valakut Exploration impulses YOUR OWN library and must NOT register as theft.
    sig = _sig("theft_makers", "opponents")
    assert _lane_covers(GONTI, sig) is True
    assert _lane_covers(THIEF_OF_SANITY, sig) is True
    # A self-impulse near miss the steal-cast arm can't reach ("until the end of
    # your next turn", not "for as long as it remains exiled").
    assert _lane_covers(_card("Light Up the Stage"), sig) is False


def test_theft_makers_never_serves_self_impulse():
    # Valakut Exploration and Rassilon impulse YOUR OWN library ("exile the top card
    # of your library. You may play that card for as long as it remains exiled") and
    # must NOT register as theft; the self-impulse veto keeps them out while the
    # un-anchored steal-cast arm still credits Hostage Taker.
    for sig in (_sig("theft_makers", "opponents"), _sig("wants_theft", "opponents")):
        assert _lane_covers(VALAKUT_EXPLORATION, sig) is False, sig.key
        assert _lane_covers(_card("Rassilon, the War President"), sig) is False, sig.key
        assert _lane_covers(HOSTAGE_TAKER, sig) is True, sig.key


# ── creatures_matter serves creature cost-reducers + board-scaled payoffs ────────
GORECLAW = _card("Goreclaw, Terror of Qal Sisma")
GHALTA = _card("Ghalta, Primal Hunger")


def test_creatures_matter_serves_creature_cost_reducer_and_board_payoff():
    # A creatures deck wants the creature-spell cost reducers that let it deploy more
    # bodies (Goreclaw) and the board-scaled finishers it casts off a wide board
    # (Ghalta). The flip-commanders (Surrak, Maelstrom, Zilortha) open creatures_matter,
    # not power_matters, so these read as off-theme before.
    sig = _sig("creatures_matter", "you")
    assert _lane_covers(GORECLAW, sig) is True
    assert _lane_covers(GHALTA, sig) is True
    # Over-fire guard: a pure counterspell is not a creatures payoff.
    counterspell = _card("Counterspell")
    assert _lane_covers(counterspell, sig) is False


# ── mass_removal serves board-protection (asymmetric wrath) ──────────────────────
SELFLESS_SPIRIT = _card("Selfless Spirit")


def test_mass_removal_serves_board_indestructible_granters():
    # A repeatable-wrath commander (Mageta) wants to wrath one-sided — keep its own
    # board through the sweep. The lane already credits indestructible CREATURES via
    # keyword, but not the GRANTERS (Selfless Spirit) that protect the whole team.
    sig = _sig("mass_removal", "you")
    assert _lane_covers(SELFLESS_SPIRIT, sig) is True
    # Over-fire guard: a single-target protection spell is not board protection.
    gods_willing = _card("Gods Willing")
    assert _lane_covers(gods_willing, sig) is False


# ── landfall serves land-recursion-from-graveyard (puts lands onto battlefield) ──
def test_landfall_serves_return_lands_from_graveyard():
    # "Return all land cards from your graveyard to the battlefield" floods lands in =
    # a huge landfall payoff. The lands-from-grave extra only matched "play lands from
    # your graveyard", missing the direct mass-return forms (Splendid Reclamation,
    # Titania, World Shaper).
    sig = _sig("landfall", "you")
    splendid = _card("Splendid Reclamation")
    assert _lane_covers(splendid, sig) is True
    # Over-fire guard: returning a CREATURE from the graveyard is reanimation, not
    # land recursion — not a landfall enabler.
    raise_dead = _card("Raise Dead")
    assert _lane_covers(raise_dead, sig) is False


def test_gain_control_vs_theft_borrow_and_cast_are_distinct():
    # PRECISION boundary: gain_control is a BATTLEFIELD control change. Borrow-and-cast
    # engines (Gonti/Hostage Taker) exile a card and let you CAST it — playing what you
    # don't own — which is theft_makers, NOT gain_control. Bribery is the genuine
    # gain-control case: it seats a permanent onto the battlefield UNDER YOUR CONTROL.
    gc = _sig("gain_control", "you")
    theft = _sig("theft_makers", "opponents")
    assert (
        _lane_covers(BRIBERY, gc) is True
    )  # library -> battlefield under your control
    assert _lane_covers(GONTI, gc) is False  # exile + cast is not a control change
    assert _lane_covers(HOSTAGE_TAKER, gc) is False
    # Their real home is theft_makers (play-what-you-don't-own).
    assert _lane_covers(GONTI, theft) is True
    assert _lane_covers(HOSTAGE_TAKER, theft) is True


def test_impulse_top_play_serves_cast_from_exile_payoffs():
    # An impulse commander exiles cards and casts them — so it wants the payoffs that
    # reward casting from exile (Wild-Magic Sorcerer: "the first spell you cast from
    # exile each turn has cascade"). Already served by cast_from_exile; impulse decks
    # do the same thing and open impulse_top_play.
    sig = _sig("impulse_top_play", "you")
    wild_magic = _card("Wild-Magic Sorcerer")
    assert _lane_covers(wild_magic, sig) is True
    # The bare "Whenever you cast a spell from exile" trigger payoff (Passionate
    # Archaeologist, Nalfeshnee) — distinct from "spell(s) you cast from exile". An
    # impulse deck casts its exiled cards, firing these. cast_from_exile already
    # serves them; impulse_top_play must too.
    passionate_archaeologist = _card("Passionate Archaeologist")
    assert _lane_covers(passionate_archaeologist, sig) is True
    # The paradox "from anywhere other than your hand" payoff (Keeper of Secrets) —
    # casting from exile IS from-anywhere-other-than-hand, so an impulse deck fires it.
    keeper_of_secrets = _card("Keeper of Secrets")
    assert _lane_covers(keeper_of_secrets, sig) is True
    # Over-fire guard: a vanilla creature is not a cast-from-exile payoff.
    grizzly = _card("Grizzly Bears")
    assert _lane_covers(grizzly, sig) is False


def test_xspell_matters_serves_x_spells_and_doublers():
    # An X-matters commander (Zaxara, Rosheen) is built from X-spells and wants the
    # X-doublers. Serve credits cards whose PRINTED mana cost contains {X} (CR 107.3 —
    # a fixed characteristic, cf. CR 702.156a "cards with {X} in their mana cost") plus
    # oracle X-payoffs. Real oracle/cost.
    sig = _sig("xspell_matters", "you")
    stonecoil = _card("Stonecoil Serpent")
    assert _lane_covers(stonecoil, sig) is True  # {X} in mana cost
    unbound = _card("Unbound Flourishing")
    assert _lane_covers(unbound, sig) is True  # oracle X-doubler payoff
    # Over-fire guard: a fixed-cost vanilla creature is not an X-spell.
    grizzly = _card("Grizzly Bears")
    assert _lane_covers(grizzly, sig) is False


def test_unspent_mana_serves_mana_amplification():
    # An unspent-mana commander (Omnath, Locus of Mana; Kruphix) keeps mana between steps,
    # so it wants mana AMPLIFICATION — untap-all-lands (Bear Umbra) and mana-doublers
    # (Mana Reflection) — to generate more mana to keep. The sweep's bare "unspent mana"
    # serve credited none of these. Real oracle.
    sig = _sig("unspent_mana", "you")
    bear_umbra = _card("Bear Umbra")
    assert _lane_covers(bear_umbra, sig) is True
    mana_reflection = _card("Mana Reflection")
    assert _lane_covers(mana_reflection, sig) is True
    # Over-fire guard: a plain mana dork is not amplification.
    llanowar = _card("Llanowar Elves")
    assert _lane_covers(llanowar, sig) is False


def test_curse_matters_is_a_named_archetype_lane():
    # Lynde recurs/attaches Curses ("Whenever a Curse is put into your graveyard ...
    # attach a Curse ...") — it wants the Curse subtype. A named-archetype lane served
    # by the Curse TYPE (not oracle prose). ADR-0027 t2b4a-B: IR-served from a
    # trigger/effect subject Filter subtypes=='Curse' (the cares-about half) + a kept
    # word mirror; the regex path no longer fires it. Real oracle.

    # Real production extractor: a trigger/effect subject Filter with
    # subtypes=='Curse'.
    assert "curse_matters" in {s.key for s in test_signals("Lynde, Cheerful Tormentor")}
    sig = _sig("curse_matters", "you")
    curse_of_misfortunes = _card("Curse of Misfortunes")
    assert _lane_covers(curse_of_misfortunes, sig) is True
    # Over-fire guard: a non-Curse Aura is not a Curse.
    pacifism = _card("Pacifism")
    assert _lane_covers(pacifism, sig) is False


def test_opponent_discard_serves_hellbent_punishers():
    # A hand-attack commander empties opponents' hands (Myojin of Night's Reach: "Each
    # opponent discards their hand"), so it wants the empty-hand (8-Rack) punishers that
    # cash the empty hand in. Opponent-anchored so a self-hellbent / draw card stays out.
    sig = _sig("opponent_discard", "opponents")
    the_rack = _card("The Rack")
    assert _lane_covers(the_rack, sig) is True
    shrieking_affliction = _card("Shrieking Affliction")
    assert _lane_covers(shrieking_affliction, sig) is True
    # Over-fire guard: a plain draw spell ("cards in hand" in a draw context) is not a
    # hellbent punisher.
    divination = _card("Divination")
    assert _lane_covers(divination, sig) is False


def test_villainous_choice_is_a_named_mechanic_lane():
    # The Valeyard doubles every villainous choice opponents face — its whole synergy is
    # villainous-choice cards (This Is How It Ends, Ensnared by the Mara, Hunted by The
    # Family). A named mechanic, like venture / initiative, with its own lane. Real oracle.
    # ADR-0027 t2b5-C: villainous_choice migrated to the Card IR (the kept word mirror),
    # so the regex path no longer emits it — assert via the real production extractor.

    # Real production extractor (the villainous_choice kept mirror over oracle_text).
    assert "villainous_choice" in {s.key for s in test_signals("The Valeyard")}
    sig = _sig("villainous_choice", "you")
    this_is_how_it_ends = _card("This Is How It Ends")
    assert _lane_covers(this_is_how_it_ends, sig) is True


def test_low_power_matters_serves_cast_low_power_enabler():
    # low_power_matters served "creatures you control with power N or less" payoffs but
    # missed the casting-ENABLER phrasing "cast a creature spell with power N or less"
    # (Assemble the Players) that a small-creatures commander (Delney) is built around.
    # Still an enabler, not a flood of vanilla small bodies, so precise. Real oracle.
    sig = _sig("low_power_matters", "you")
    assemble = _card("Assemble the Players")
    assert _lane_covers(assemble, sig) is True
    # Over-fire guard: a vanilla small creature is not a low-power payoff/enabler.
    grizzly = _card("Grizzly Bears")
    assert _lane_covers(grizzly, sig) is False


def test_discard_outlet_serves_discard_payoffs():
    # A loot/rummage commander (Jaya Ballard, Alexi) discards a lot, so it wants the
    # payoffs that reward discarding — Containment Construct turns each discard into a
    # castable card. The auto-serve only credited other discard OUTLETS.
    sig = _sig("discard_outlet", "you")
    containment_construct = _card("Containment Construct")
    assert _lane_covers(containment_construct, sig) is True
    # Over-fire guard: a vanilla creature is not a discard payoff.
    grizzly = _card("Grizzly Bears")
    assert _lane_covers(grizzly, sig) is False


def test_mass_bounce_serves_creature_mass_bounce():
    # mass_bounce matched only "return each PERMANENT", missing "return each CREATURE
    # … to its owner's hand" (Scourge of Fleets). A mass-bounce commander (Slinn Voda)
    # wants creature mass-bounce too.
    sig = _sig("mass_bounce", "any")
    scourge = _card("Scourge of Fleets")
    assert _lane_covers(scourge, sig) is True
    # Over-fire guard: single-target bounce is tempo, not mass bounce.
    boomerang = _card("Boomerang")
    assert _lane_covers(boomerang, sig) is False


def test_dies_recursion_is_superset_of_undying_persist():
    # dies_recursion is the BROAD "creatures recur when they die" category (with or
    # without counters); has_undying_persist is the counter-bearing SUBSET (undying
    # = +1/+1 per CR 702.93a, persist = -1/-1 per CR 702.79a). So undying/persist cards
    # belong to BOTH; bare dies-return (Supernatural Stamina) only to dies_recursion.
    kitchen_finks = _card("Kitchen Finks")
    supernatural_stamina = _card("Supernatural Stamina")
    geralfs = test_card("Geralf's Messenger")
    dr = _sig("dies_recursion", "you")
    up = _sig("has_undying_persist", "you")
    # Superset: undying/persist AND bare dies-return are all dies_recursion.
    assert _lane_covers(geralfs, dr) is True
    assert _lane_covers(kitchen_finks, dr) is True
    assert _lane_covers(supernatural_stamina, dr) is True
    # Subset: undying/persist are counter-bearing; bare dies-return is NOT.
    assert _lane_covers(geralfs, up) is True
    assert _lane_covers(kitchen_finks, up) is True
    assert _lane_covers(supernatural_stamina, up) is False
    # And undying/persist cards OPEN both lanes (they are members of the superset).
    # ADR-0027: BOTH dies_recursion and has_undying_persist migrated to the Card IR —
    # the real production extractor supplies both from the intrinsic Undying keyword
    # bearer (Scryfall keyword array + _IR_KEYWORD_MAP['undying']) PLUS the
    # DIES_RECURSION_REGEX kept word mirror.
    hybrid_keys = {s.key for s in test_signals("Geralf's Messenger")}
    assert "dies_recursion" in hybrid_keys
    assert "has_undying_persist" in hybrid_keys


def test_creature_cast_and_etb_serve_self_bounce_recast_engines():
    # Self-bounce ETB creatures (Whitemane Lion, Kor Skyfisher) return your own
    # permanent on enter — recast them to re-fire creature-cast / enter triggers. A
    # creature-cast (Oketra) or ETB commander wants them.
    whitemane = _card("Whitemane Lion")
    kor = _card("Kor Skyfisher")
    for key in ("creature_cast_trigger", "creature_etb", "permanent_etb"):
        assert _lane_covers(whitemane, _sig(key)), key
        assert _lane_covers(kor, _sig(key)), key
    # Over-fire guard: bouncing an OPPONENT's permanent is tempo, not a recast engine.
    boomerang = _card("Man-o'-War")
    assert _lane_covers(boomerang, _sig("creature_cast_trigger")) is False


def test_suspend_serves_extra_upkeep_and_suspended_card_support():
    # Suspend removes a TIME counter each upkeep (CR 702.62), so a suspend commander
    # (Jhoira, Taigam) wants extra upkeeps (Paradox Haze) and counter-manipulation on
    # suspended cards (Clockspinning) — neither says "suspend"/"time counter" itself.
    sig = _sig("suspend_matters", "you")
    paradox_haze = _card("Paradox Haze")
    clockspinning = _card("Clockspinning")
    assert _lane_covers(paradox_haze, sig) is True
    assert _lane_covers(clockspinning, sig) is True
    # Over-fire guard: a generic extra-turn spell with no upkeep/suspend hook stays out.
    explore = _card("Explore")
    assert _lane_covers(explore, sig) is False


def test_stax_lanes_serve_symmetric_hatebears():
    # A stax commander wants stax PIECES regardless of its own scope. The opponent-tax
    # serve missed SYMMETRIC hatebears: global ability-shutoff (Collector Ouphe),
    # anti-cheat ETB replacement (Containment Priest), trigger-hate (Hushbringer). And a
    # symmetric-stax commander (Hokori) also wants the opponent-tax pieces (Kismet).
    collector_ouphe = _card("Collector Ouphe")
    containment_priest = _card("Containment Priest")
    hushbringer = _card("Hushbringer")
    kismet = _card("Kismet")
    stax = _sig("stax_taxes", "opponents")
    sym = _sig("symmetric_stax", "each")
    for piece in (collector_ouphe, containment_priest, hushbringer):
        assert _lane_covers(piece, stax), piece["name"]
        assert _lane_covers(piece, sym), piece["name"]
    # The symmetric-stax commander also wants opponent-tax pieces.
    assert _lane_covers(kismet, sym) is True
    # Over-fire guard: a vanilla beater is not a stax piece.
    bear = _card("Grizzly Bears")
    assert _lane_covers(bear, stax) is False
    assert _lane_covers(bear, sym) is False


def test_ninjutsu_serves_evasive_unblockable_enablers():
    # Ninjutsu (CR 702.49) returns an UNBLOCKED attacker and drops the ninja in, so a
    # ninjutsu commander (Satoru Umezawa) wants cheap unblockable/evasive creatures to
    # reliably connect — Slither Blade, Mist-Cloaked Herald, Tormented Soul. Reuses the
    # evasion classifier (no flying — that's soft/blockable).
    sig = _sig("has_ninjutsu", "you")
    slither = _card("Slither Blade")
    tormented = _card("Tormented Soul")
    shadowmage = _card("Razortooth Rats")  # keyword evasion (fear) is also an enabler
    assert _lane_covers(slither, sig) is True
    assert _lane_covers(tormented, sig) is True
    assert _lane_covers(shadowmage, sig) is True
    # Over-fire guard: a plain ground creature is not an enabler.
    bear = _card("Grizzly Bears")
    assert _lane_covers(bear, sig) is False


def test_aristocrats_graveyard_lanes_serve_self_sac_creatures():
    # Self-sacrificing creatures (Selfless Spirit, Kami of False Hope, Spore Frog) die on
    # demand and protect the board — sac-fodder a death/sacrifice/graveyard deck wants.
    selfless_spirit = _card("Selfless Spirit")
    for key in ("death_matters", "sacrifice_outlets", "graveyard_matters"):
        scope = "any" if key == "death_matters" else "you"
        assert _lane_covers(selfless_spirit, _sig(key, scope)), key
    # Over-fire guard: a vanilla creature is not sac-fodder via this extra.
    bear = _card("Grizzly Bears")
    assert _lane_covers(bear, _sig("death_matters", "any")) is False


def test_direct_damage_serves_burn_redirect():
    # Repercussion converts creature-damage into player damage — a burn payoff a
    # pinger/wipe/damage deck wants (ping or wipe + Repercussion = burn the table).
    # direct_damage served numeric burn + "double that damage" but not "that much
    # damage to that creature's controller".
    repercussion = _card("Repercussion")
    assert _lane_covers(repercussion, _sig("direct_damage", "you")) is True
    # Over-fire guard: a vanilla lifegain spell is not burn.
    healer = _card("Natural Spring")
    assert _lane_covers(healer, _sig("direct_damage", "you")) is False


def test_activated_ability_serves_haste_granters_and_untap_enablers():
    # A {T}: commander (Visara "{T}: Destroy target creature") can't tap the turn it
    # enters (CR 302.6 summoning sickness) and taps only once per turn. Haste-granters
    # (CR 702.10 / 302.6) lift the sickness so it activates immediately; untap-enablers
    # re-tap it for extra activations. Both are its support package.
    sig = _sig("activated_ability", "you")
    # Haste-granter on an equipped creature (lifts summoning sickness for the {T}:).
    sting = _card("Sting, the Glinting Dagger")
    # Repeatable untap of an enchanted creature — re-tap the {T}: commander each turn.
    freed = _card("Freed from the Real")
    # One-shot "Untap it" (plus protection) to reactivate the commander in response.
    shore_up = _card("Shore Up")
    assert _lane_covers(sting, sig) is True
    assert _lane_covers(freed, sig) is True
    assert _lane_covers(shore_up, sig) is True
    # Over-fire guard: a vanilla creature with innate haste is NOT a granter — it grants
    # nothing to the commander.
    goblin = _card("Raging Goblin")
    assert _lane_covers(goblin, sig) is False


def test_chaos_warp_no_longer_serves_a_you_scoped_cheat_spec():
    """task #91 flagship consumer check: Chaos Warp's cheat_into_play
    beneficiary is the shuffled permanent's OWNER (CR 108.3), not the
    caster — so its signal identity must stop matching a "you"-scoped
    cheat build-around's own identity (``signals.py``'s ``support`` lookup
    and ``engine.avenues``'s ``f"engine:{key}:{scope}"`` avenue id both key
    off the exact ``(key, scope, subject)`` ident) and instead carry the
    scope-'any' ident a target-dependent beneficiary needs.

    Production ``test_signals`` (the real ``extract_signals`` over
    the committed snapshot) never emits ``('cheat_into_play', 'you', '')``
    for Chaos Warp any more; ``spec_for`` on its actual ``('cheat_into_play',
    'any', '')`` signal still resolves a real spec via the (key, "any") /
    by-key fallback (the fix changes WHICH scope key is stamped — and thus
    which avenue id a "you"-scoped cheat commander's support lookup would
    match — never drops the avenue outright)."""
    sigs = test_signals("Chaos Warp")
    idents = {(s.key, s.scope) for s in sigs}
    assert ("cheat_into_play", "you") not in idents
    assert ("cheat_into_play", "any") in idents
    any_sig = next(s for s in sigs if s.key == "cheat_into_play")
    you_sig = _sig("cheat_into_play", "you")
    assert spec_for(any_sig) is not None
    # A "you"-scoped cheat commander's identity no longer matches Chaos
    # Warp's own ident — the exact support-lookup key a "cheat things into
    # play for YOURSELF" build-around's synergy check uses.
    assert (any_sig.key, any_sig.scope, any_sig.subject) != (
        you_sig.key,
        you_sig.scope,
        you_sig.subject,
    )
    assert f"engine:{any_sig.key}:{any_sig.scope}" == "engine:cheat_into_play:any"


# ── task #96: type_changers serve wiring (ADR-0040) ──────────────────────────
# The tribal main serve deliberately excludes type-granters by oracle (B1:
# they are not tribe BODIES), which left Leyline of Transformation bucketed
# filler on the Sliver benchmark — the falsely-filler build-around ADR-0040
# names. The fix is a STRUCTURAL arm: Serve gains `signal_idents`, matched
# against the card's own emitted "key|scope|subject" idents (the task-#90
# ident vocabulary), and the tribal _subject_spec enumerates the
# type_changers idents that grow the tribe ("" chosen / "all" every /
# "<Type>" fixed, scopes you+each). Bodies-by-type-line stay unchanged.


def test_serve_signal_idents_arm_matches_structurally():
    test_card_ir("Leyline of Transformation")  # seeds the crosswalk trees memo
    leyline = test_card("Leyline of Transformation")
    serve = Serve(signal_idents=frozenset({"type_changers|you|"}))
    assert serve.matches(leyline)
    # A card without the ident falls through this arm (and every other).
    test_card_ir("Murder")
    assert not serve.matches(test_card("Murder"))


def test_tribal_serve_credits_type_changers_structurally():
    test_card_ir("Leyline of Transformation")
    leyline = test_card("Leyline of Transformation")
    spec = spec_for(
        Signal(key="type_matters", scope="you", subject="Sliver", text="", source="c")
    )
    assert spec is not None
    assert spec.serve.matches(leyline)
    # A fixed-subtype changer serves ITS tribe only (Hivestone grows Slivers,
    # never Goblins) — enumerated idents, not a bare-key match.
    goblin_spec = spec_for(
        Signal(key="type_matters", scope="you", subject="Goblin", text="", source="c")
    )
    hive_idents = frozenset({"type_changers|you|Sliver"})
    assert "type_changers|you|Sliver" in (spec.serve.signal_idents or frozenset())
    assert hive_idents & (goblin_spec.serve.signal_idents or frozenset()) == frozenset()


def test_spec_for_resolves_every_type_changers_key():
    # SUBJECT_KEYS routing: all three zone-reach keys resolve through
    # _subject_spec for every subject shape, so a ranked type_changers deck
    # signal never becomes a spec-less avenue (the import-time key-agreement
    # gate skips subject keys; this pins the dynamic side).
    for key in (
        "type_changers",
        "type_changers_all_zones",
        "type_changers_graveyard",
    ):
        for subject in ("", "all", "Sliver"):
            sig = Signal(key=key, scope="you", subject=subject, text="", source="c")
            spec = spec_for(sig)
            assert spec is not None, (key, subject)
            assert spec.label, (key, subject)


def test_enabler_extra_credits_fixed_subtype_changers_structurally():
    # The "Sliver enablers" sub-avenue served by oracle regex only (chosen/
    # every-type forms), so Hivestone ("Creatures you control are Slivers in
    # addition to their other creature types") never surfaced on the Find
    # surface's enabler avenue — hidden from the interface even though its
    # type_changers|you|Sliver signal is exactly what the lane is for. The
    # extra's serve now carries the structural idents arm, so it credits any
    # type_changers emitter regardless of wording.
    test_card_ir("Hivestone")  # seeds the crosswalk trees memo
    hivestone = test_card("Hivestone")
    spec = spec_for(
        Signal(key="type_matters", scope="you", subject="Sliver", text="", source="c")
    )
    assert spec is not None
    enabler = next(e for e in spec.extras if e.label == "Sliver enablers")
    assert enabler.serve.matches(hivestone)


# ── task B-1: chosen_type_matters serve wiring ────────────────────────────────
# Wildcard tribal payoffs (Door of Destinies, Herald's Horn: choose a creature
# type as it enters — CR 614.12 — then pay off the chosen type) serve EVERY
# tribe: the per-subject tribal serve carries the chosen_type_matters idents,
# so a Sliver deck credits Herald's Horn exactly as a Goblin deck does. The
# idents are punish-gated at emission (Engineered Plague's -1/-1 chooser
# never emits), unlike the legacy choose-a-type text arm on the payoff
# sub-avenue.


def test_tribal_serve_credits_chosen_type_payoffs_for_any_tribe():
    test_card_ir("Herald's Horn")  # seeds the crosswalk trees memo
    horn = test_card("Herald's Horn")
    for tribe in ("Sliver", "Goblin"):
        spec = spec_for(
            Signal(key="type_matters", scope="you", subject=tribe, text="", source="c")
        )
        assert spec is not None
        assert spec.serve.matches(horn), tribe
        assert (spec.serve.signal_idents or frozenset()) >= _CHOSEN_TYPE_IDENTS


def test_punisher_chooser_never_serves_the_main_tribal_lane():
    # Engineered Plague chooses a type to HATE it (-1/-1): no
    # chosen_type_matters ident is emitted, and the main tribal serve's other
    # arms (bodies by type line, type-changer idents) don't match either.
    test_card_ir("Engineered Plague")
    plague = test_card("Engineered Plague")
    spec = spec_for(
        Signal(key="type_matters", scope="you", subject="Sliver", text="", source="c")
    )
    assert spec is not None
    assert not spec.serve.matches(plague)


def test_chosen_type_matters_key_resolves_and_serves_structurally():
    # The deck-side spec: a deck that already runs Door of Destinies emits
    # chosen_type_matters ("you"), which must resolve through the (key, "any")
    # entry and serve other wildcard payoffs structurally.
    test_card_ir("Door of Destinies")
    door = test_card("Door of Destinies")
    spec = spec_for(
        Signal(key="chosen_type_matters", scope="you", subject="", text="", source="c")
    )
    assert spec is not None
    assert spec.label == "Chosen-type tribal payoffs"
    assert spec.serve.matches(door)


# ── task B-6: mana_amplifier serve wiring into the X-spell lane ──────────────
# The xspell_matters avenue text always promised "the X-doublers ... an
# X-matters deck is built around", but its serve only credited X-COST cards
# — a mana doubler has neither an {X} cost nor the copy-payoff prose, so
# Mana Reflection under Zaxara ranked as filler (the adjudicated study gap).
# The structural arm delivers them: the serve carries the mana_amplifier
# ident, implementing the ledgered big_mana adjudication ("Dan: big-mana-
# generators -> X-spells" — generators serve the X lane, never the sinks
# lane).


@pytest.mark.parametrize(
    ("name", "serves"),
    [
        ("Mana Reflection", True),
        ("Zendikar Resurgent", True),
        # Plain ramp / single-land Auras never emit mana_amplifier — the
        # lane's AttachedTo/plain-producer exclusions are the precision gate.
        ("Sol Ring", False),
        ("Llanowar Elves", False),
        ("Wild Growth", False),
    ],
)
def test_xspell_serve_credits_mana_amplifiers_structurally(name, serves):
    spec = spec_for(
        Signal(key="xspell_matters", scope="you", subject="", text="", source="c")
    )
    assert spec is not None
    assert "mana_amplifier|you|" in (spec.serve.signal_idents or frozenset())
    test_card_ir(name)  # seeds the crosswalk trees memo
    assert spec.serve.matches(test_card(name)) is serves, name


def test_xspell_amplifier_serve_survives_avenue_round_trip():
    # ranking rebuilds serves from avenue dicts (serve_from_dict) — the
    # ident arm must survive the round trip.
    spec = spec_for(
        Signal(key="xspell_matters", scope="you", subject="", text="", source="c")
    )
    test_card_ir("Mana Reflection")
    rebuilt = serve_from_dict(spec.serve.as_dict())
    assert rebuilt.matches(test_card("Mana Reflection"))


# ── Verified-review F4/F5/F6/F7: spec serve/search contradictions ────────────


def test_chosen_type_serve_never_credits_punisher_choosers():
    # F5: the text arm ("choose a creature type") re-admitted every punisher
    # the lane's emission gates exclude. The serve is idents-only now.
    spec = spec_for(
        Signal(key="chosen_type_matters", scope="you", subject="", text="", source="c")
    )
    test_card_ir("Engineered Plague")
    assert not spec.serve.matches(test_card("Engineered Plague"))
    test_card_ir("Door of Destinies")
    assert spec.serve.matches(test_card("Door of Destinies"))


def test_chosen_idents_stay_out_of_count_damage_body_lanes():
    # F4: a "Dragon count damage" lane's serve promises BODIES that raise the
    # count — Herald's Horn adds zero bodies and must not serve it. It still
    # serves the type_matters tribal lane (the B-1 adjudication).
    dfe = spec_for(
        Signal(
            key="damage_for_each",
            scope="opponents",
            subject="Dragon",
            text="",
            source="c",
        )
    )
    test_card_ir("Herald's Horn")
    horn = test_card("Herald's Horn")
    assert not dfe.serve.matches(horn)
    tm = spec_for(
        Signal(key="type_matters", scope="you", subject="Dragon", text="", source="c")
    )
    assert tm.serve.matches(horn)


def test_damage_for_each_search_finds_fuel_not_more_burn():
    # F6: search must find cards that FEED the signal (token fuel), not more
    # board-count burn emitters the serve then rejects.
    spec = spec_for(
        Signal(key="damage_for_each", scope="any", subject="", text="", source="c")
    )
    oracle = spec.search.get("oracle", "")
    assert "token" in oracle, spec.search
    assert "number of" not in oracle, spec.search


def test_keep_n_wrath_serve_is_the_rebuild_package_not_the_wipe():
    # F7: the serve's primary regex WAS the wipe pattern itself, so redundant
    # wraths outranked actual rebuild cards. Serve = keyword/extras only.
    spec = spec_for(
        Signal(key="keep_n_wrath", scope="each", subject="", text="", source="c")
    )
    wipe = {
        "name": "Another Keep-N",
        "type_line": "Sorcery",
        "cmc": 4.0,
        "oracle_text": (
            "Each player chooses two creatures they control, then sacrifices the rest."
        ),
        "prices": {"usd": "1.00"},
    }
    assert not spec.serve.matches(wipe)
    protector = {
        "name": "Indestructo",
        "type_line": "Creature — Spirit",
        "cmc": 2.0,
        "oracle_text": "Your permanents are indestructible.",
        "keywords": ["Indestructible"],
        "prices": {"usd": "1.00"},
    }
    assert spec.serve.matches(protector)
