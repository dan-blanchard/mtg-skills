"""Tests for signal specs: how a signal maps to cards that FEED it.

Headline guard: a card that feeds an *opponents'-graveyard* signal must mill
opponents, not yourself. Self-mill must NOT register as serving it.
"""

import re

from mtg_utils._deck_forge import signal_specs
from mtg_utils._deck_forge.signal_specs import (
    Serve,
    search_filters,
    serve_from_dict,
    serves,
    spec_for,
)
from mtg_utils._deck_forge.signals import Signal, extract_signals


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


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
    kokusho = {
        "name": "Kokusho",
        "type_line": "Legendary Creature — Dragon Spirit",
        "cmc": 6.0,
        "oracle_text": "When Kokusho dies, each opponent loses 5 life.",
    }
    young_wolf = {  # has a dies trigger but cmc 1 — not a clone bomb
        "name": "Young Wolf",
        "type_line": "Creature — Wolf",
        "cmc": 1.0,
        "oracle_text": "Undying\nWhen Young Wolf dies, return it...",
    }
    big_vanilla = {  # cmc>=5 but no dies trigger
        "name": "Big Dumb",
        "type_line": "Creature — Beast",
        "cmc": 7.0,
        "oracle_text": "",
    }
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
    magus = {
        "name": "Magus of the Moon",
        "type_line": "Creature — Human Wizard",
        "oracle_text": "Nonbasic lands are Mountains.",
    }
    burning = {
        "name": "Burning Earth",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever a player taps a nonbasic land for mana, Burning Earth deals 1 "
            "damage to that player."
        ),
    }
    assert _lane_covers(magus, sig) is True
    assert _lane_covers(burning, sig) is True
    # Over-fire guard: a basic-land ramp spell is not land-denial stax.
    ramp = {
        "name": "Rampant Growth",
        "type_line": "Sorcery",
        "oracle_text": (
            "Search your library for a basic land card, put it onto the battlefield "
            "tapped, then shuffle."
        ),
    }
    assert _lane_covers(ramp, sig) is False


def test_free_creature_payoff_serves_only_zero_cost_creatures():
    # Satoru's "no mana was spent to cast" payoff wants 0-cost CREATURES (Ornithopter),
    # not 0-cost mana rocks (Lotus Petal is {0} but not a creature) and not normal-cost
    # creatures. The serve ANDs mana_cost {0} with a creature type. Real oracle.
    sig = _sig("free_creature_payoff", "you")
    ornithopter = {
        "name": "Ornithopter",
        "type_line": "Artifact Creature — Thopter",
        "mana_cost": "{0}",
        "power": "0",
        "toughness": "2",
        "oracle_text": "Flying",
    }
    lotus_petal = {
        "name": "Lotus Petal",
        "type_line": "Artifact",
        "mana_cost": "{0}",
        "oracle_text": "{T}, Sacrifice this artifact: Add one mana of any color.",
    }
    grizzly_bears = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
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
    wipes_and_reanim = [
        (
            "Wrath of God",
            "Sorcery",
            "{2}{W}{W}",
            "Destroy all creatures. They can't be regenerated.",
        ),
        (
            "Blasphemous Act",
            "Sorcery",
            "{8}{R}",
            "This spell costs {1} less to cast for each creature on the battlefield.\n"
            "Blasphemous Act deals 13 damage to each creature.",
        ),
        (
            "Storm of Souls",
            "Sorcery",
            "{4}{W}{W}",
            "Return all creature cards from your graveyard to the battlefield. Each of "
            "them is a 1/1 Spirit with flying in addition to its other types. Exile "
            "Storm of Souls.",
        ),
        (
            "Faith's Reward",
            "Instant",
            "{3}{W}",
            "Return to the battlefield all permanent cards in your graveyard that were "
            "put there from the battlefield this turn.",
        ),
    ]
    for name, tl, mc, otext in wipes_and_reanim:
        card = {"name": name, "type_line": tl, "mana_cost": mc, "oracle_text": otext}
        assert serves(card, sig) is True, name
    # NOT single-target reanimation — Raise Dead returns ONE creature to hand; that's
    # the reanimator lane, not refilling a wiped board. Real oracle.
    raise_dead = {
        "name": "Raise Dead",
        "type_line": "Sorcery",
        "mana_cost": "{B}",
        "oracle_text": "Return target creature card from your graveyard to your hand.",
    }
    assert serves(raise_dead, sig) is False


def test_land_protection_serves_indestructible_and_untargetable_lands():
    # A land-animation commander (Noyan Dar) wants its creature-lands kept alive: Terra
    # Eternal ("All lands have indestructible") and Tomik ("Lands … can't be the targets
    # of … your opponents"). A mana dork is not land protection. Real oracle.
    sig = _sig("land_protection", "you")
    terra_eternal = {
        "name": "Terra Eternal",
        "type_line": "Enchantment",
        "mana_cost": "{2}{W}",
        "oracle_text": "All lands have indestructible.",
    }
    tomik = {
        "name": "Tomik, Distinguished Advokist",
        "type_line": "Legendary Creature — Human Advisor",
        "mana_cost": "{W}{W}",
        "power": "2",
        "toughness": "3",
        "oracle_text": (
            "Flying\nLands on the battlefield and land cards in graveyards can't be the "
            "targets of spells or abilities your opponents control.\nYour opponents "
            "can't play land cards from graveyards."
        ),
    }
    assert serves(terra_eternal, sig) is True
    assert serves(tomik, sig) is True
    llanowar_elves = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "oracle_text": "{T}: Add {G}.",
    }
    assert serves(llanowar_elves, sig) is False


def test_entered_attacker_serves_etb_pump_and_haste():
    # Samut wants enter-trigger pump + haste so a freshly-entered creature swings at
    # once. Primal Forcemage (+3/+3 on enter) and Ogre Battledriver (+2/+0 and haste on
    # enter) feed it; Impact Tremors (ETB-ping, no pump/haste) does not. Real oracle.
    sig = _sig("entered_attacker", "you")
    primal_forcemage = {
        "name": "Primal Forcemage",
        "type_line": "Creature — Elf Shaman",
        "mana_cost": "{2}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": (
            "Whenever another creature you control enters, that creature gets +3/+3 "
            "until end of turn."
        ),
    }
    ogre_battledriver = {
        "name": "Ogre Battledriver",
        "type_line": "Creature — Ogre Warrior",
        "mana_cost": "{2}{R}{R}",
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "Whenever another creature you control enters, that creature gets +2/+0 and "
            "gains haste until end of turn. (It can attack and {T} this turn.)"
        ),
    }
    assert serves(primal_forcemage, sig) is True
    assert serves(ogre_battledriver, sig) is True
    impact_tremors = {
        "name": "Impact Tremors",
        "type_line": "Enchantment",
        "mana_cost": "{1}{R}",
        "oracle_text": (
            "Whenever a creature you control enters, this enchantment deals 1 damage to "
            "each opponent."
        ),
    }
    assert serves(impact_tremors, sig) is False


def test_target_redirect_serves_spell_redirect():
    # Rayne wants target-redirect: Spellskite ("change a target of target spell or
    # ability to this creature") and Misdirection ("change the target of target spell").
    # A burn spell is not. Real oracle.
    sig = _sig("target_redirect", "you")
    spellskite = {
        "name": "Spellskite",
        "type_line": "Artifact Creature — Phyrexian Horror",
        "mana_cost": "{2}",
        "power": "0",
        "toughness": "4",
        "oracle_text": (
            "{U/P}: Change a target of target spell or ability to this creature. ({U/P} "
            "can be paid with either {U} or 2 life.)"
        ),
    }
    misdirection = {
        "name": "Misdirection",
        "type_line": "Instant",
        "mana_cost": "{3}{U}{U}",
        "oracle_text": (
            "You may exile a blue card from your hand rather than pay this spell's mana "
            "cost.\nChange the target of target spell with a single target."
        ),
    }
    assert serves(spellskite, sig) is True
    assert serves(misdirection, sig) is True
    lightning_bolt = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "mana_cost": "{R}",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    }
    assert serves(lightning_bolt, sig) is False


def test_free_spell_storm_serves_zero_cost_nonland_spells():
    # Thrasta wants free spells to chain: Lotus Petal and Memnite (both {0} nonland). A
    # 1-cmc creature isn't free; a 0-mv basic land isn't a spell cast. Real oracle.
    sig = _sig("free_spell_storm", "you")
    lotus_petal = {
        "name": "Lotus Petal",
        "type_line": "Artifact",
        "mana_cost": "{0}",
        "cmc": 0.0,
        "oracle_text": "{T}, Sacrifice this artifact: Add one mana of any color.",
    }
    memnite = {
        "name": "Memnite",
        "type_line": "Artifact Creature — Construct",
        "mana_cost": "{0}",
        "cmc": 0.0,
        "power": "1",
        "toughness": "1",
        "oracle_text": "",
    }
    assert serves(lotus_petal, sig) is True
    assert serves(memnite, sig) is True
    llanowar_elves = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "cmc": 1.0,
        "power": "1",
        "toughness": "1",
        "oracle_text": "{T}: Add {G}.",
    }
    forest = {
        "name": "Forest",
        "type_line": "Basic Land — Forest",
        "mana_cost": "",
        "cmc": 0.0,
        "oracle_text": "({T}: Add {G}.)",
    }
    assert serves(llanowar_elves, sig) is False  # not free
    assert serves(forest, sig) is False  # 0-mv but a land, not a spell


def test_scavenge_fuel_serves_high_power_creatures():
    # Varolz wants high-power creatures (scavenge = +1/+1 counters equal to power). Force
    # of Savagery (8/0) feeds it; a 2/2 bear does not. Real oracle.
    sig = _sig("scavenge_fuel", "you")
    force_of_savagery = {
        "name": "Force of Savagery",
        "type_line": "Creature — Elemental",
        "mana_cost": "{G}{G}{G}",
        "power": "8",
        "toughness": "0",
        "oracle_text": "Trample",
    }
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert serves(force_of_savagery, sig) is True
    assert serves(grizzly, sig) is False


def test_land_exchange_serves_land_swap():
    # Sharkey wants land-exchange: Political Trickery and Vedalken Plotter ("exchange
    # control of target land you control and target land an opponent controls"). A plain
    # ramp spell is not. Real oracle.
    sig = _sig("land_exchange", "you")
    political_trickery = {
        "name": "Political Trickery",
        "type_line": "Sorcery",
        "mana_cost": "{2}{U}",
        "oracle_text": (
            "Exchange control of target land you control and target land an opponent "
            "controls. (This effect lasts indefinitely.)"
        ),
    }
    vedalken_plotter = {
        "name": "Vedalken Plotter",
        "type_line": "Creature — Vedalken Wizard",
        "mana_cost": "{2}{U}",
        "power": "2",
        "toughness": "2",
        "oracle_text": (
            "When this creature enters, exchange control of target land you control and "
            "target land an opponent controls."
        ),
    }
    assert serves(political_trickery, sig) is True
    assert serves(vedalken_plotter, sig) is True
    rampant_growth = {
        "name": "Rampant Growth",
        "type_line": "Sorcery",
        "mana_cost": "{1}{G}",
        "oracle_text": (
            "Search your library for a basic land card, put that card onto the "
            "battlefield tapped, then shuffle."
        ),
    }
    assert serves(rampant_growth, sig) is False


def test_life_payment_insurance_serves_dont_lose_at_zero():
    # Selenia wants life-loss insurance: Phyrexian Unlife ("don't lose the game for
    # having 0 or less life") and Angel's Grace ("you can't lose the game this turn"). A
    # mana dork is not insurance. Real oracle.
    sig = _sig("life_payment_insurance", "you")
    phyrexian_unlife = {
        "name": "Phyrexian Unlife",
        "type_line": "Enchantment",
        "mana_cost": "{2}{W}",
        "oracle_text": (
            "You don't lose the game for having 0 or less life.\nAs long as you have 0 "
            "or less life, all damage is dealt to you as though its source had infect. "
            "(Damage is dealt to you in the form of poison counters.)"
        ),
    }
    angels_grace = {
        "name": "Angel's Grace",
        "type_line": "Instant",
        "mana_cost": "{W}",
        "oracle_text": (
            "Split second (As long as this spell is on the stack, players can't cast "
            "spells or activate abilities that aren't mana abilities.)\nYou can't lose "
            "the game this turn and your opponents can't win the game this turn. Until "
            "end of turn, damage that would reduce your life total to less than 1 "
            "reduces it to 1 instead."
        ),
    }
    assert serves(phyrexian_unlife, sig) is True
    assert serves(angels_grace, sig) is True
    llanowar_elves = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "oracle_text": "{T}: Add {G}.",
    }
    assert serves(llanowar_elves, sig) is False


def test_target_own_payoff_serves_free_self_targeting():
    # Monk Gyatso wants free ways to target his own creatures: the en-Kor cycle ("{0}: …
    # dealt to target creature you control") triggers airbend on demand. A vanilla bear
    # is not a self-targeter. Real oracle.
    sig = _sig("target_own_payoff", "you")
    nomads_en_kor = {
        "name": "Nomads en-Kor",
        "type_line": "Creature — Kor Nomad Soldier",
        "mana_cost": "{W}",
        "power": "1",
        "toughness": "1",
        "oracle_text": (
            "{0}: The next 1 damage that would be dealt to this creature this turn is "
            "dealt to target creature you control instead."
        ),
    }
    warrior_en_kor = {
        "name": "Warrior en-Kor",
        "type_line": "Creature — Kor Warrior Knight",
        "mana_cost": "{W}{W}",
        "power": "2",
        "toughness": "2",
        "oracle_text": (
            "{0}: The next 1 damage that would be dealt to this creature this turn is "
            "dealt to target creature you control instead."
        ),
    }
    assert serves(nomads_en_kor, sig) is True
    assert serves(warrior_en_kor, sig) is True
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert serves(grizzly, sig) is False


def test_multicolor_matters_serves_payoffs_not_every_gold_card():
    # Niv wants multicolored PAYOFFS: General Ferrous Rokiric ("whenever you cast a
    # multicolored spell …") and Bring to Light (converge). A plain gold creature with no
    # multicolor payoff (Soulherder) is not credited — that would be the whole deck. Real
    # oracle.
    sig = _sig("multicolor_matters", "you")
    rokiric = {
        "name": "General Ferrous Rokiric",
        "type_line": "Legendary Creature — Human Soldier",
        "mana_cost": "{1}{R}{W}",
        "power": "3",
        "toughness": "1",
        "oracle_text": (
            "Hexproof from monocolored\nWhenever you cast a multicolored spell, create a "
            "4/4 red and white Golem artifact creature token."
        ),
    }
    bring_to_light = {
        "name": "Bring to Light",
        "type_line": "Sorcery",
        "mana_cost": "{3}{G}{U}",
        "oracle_text": (
            "Converge — Search your library for a creature, instant, or sorcery card "
            "with mana value less than or equal to the number of colors of mana spent "
            "to cast this spell, exile that card, then shuffle. You may cast that card "
            "without paying its mana cost."
        ),
    }
    assert serves(rokiric, sig) is True
    assert serves(bring_to_light, sig) is True
    soulherder = {
        "name": "Soulherder",
        "type_line": "Creature — Spirit",
        "mana_cost": "{1}{W}{U}",
        "power": "1",
        "toughness": "1",
        "oracle_text": (
            "Whenever a creature is exiled from the battlefield, put a +1/+1 counter on "
            "this creature.\nAt the beginning of your end step, you may exile another "
            "target creature you control, then return it to the battlefield under its "
            "owner's control."
        ),
    }
    assert serves(soulherder, sig) is False


def test_land_denial_serves_symmetric_land_punishers():
    # Taniwha wants symmetric land-bounce/sac stax: Mana Breach and Overburden ("that
    # player returns a land they control"). A mana dork is not land denial. Real oracle.
    sig = _sig("land_denial", "you")
    mana_breach = {
        "name": "Mana Breach",
        "type_line": "Enchantment",
        "mana_cost": "{2}{U}",
        "oracle_text": (
            "Whenever a player casts a spell, that player returns a land they control "
            "to its owner's hand."
        ),
    }
    overburden = {
        "name": "Overburden",
        "type_line": "Enchantment",
        "mana_cost": "{1}{U}",
        "oracle_text": (
            "Whenever a player puts a nontoken creature onto the battlefield, that "
            "player returns a land they control to its owner's hand."
        ),
    }
    assert serves(mana_breach, sig) is True
    assert serves(overburden, sig) is True
    llanowar_elves = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "oracle_text": "{T}: Add {G}.",
    }
    assert serves(llanowar_elves, sig) is False


def test_lose_unless_hand_serves_drawback_negation():
    # Phage wants to negate "you lose unless cast from hand": Netherborn Altar (commander
    # to hand), Platinum Angel ("can't lose the game"), Torpor Orb (ETBs don't trigger,
    # silencing the lose-trigger). A burn spell does not. Real oracle.
    sig = _sig("lose_unless_hand", "you")
    netherborn_altar = {
        "name": "Netherborn Altar",
        "type_line": "Artifact",
        "mana_cost": "{1}{B}",
        "oracle_text": (
            "{T}, Put a soul counter on this artifact: Put your commander into your hand "
            "from the command zone. Then you lose 3 life for each soul counter on this "
            "artifact."
        ),
    }
    platinum_angel = {
        "name": "Platinum Angel",
        "type_line": "Artifact Creature — Angel",
        "mana_cost": "{7}",
        "power": "4",
        "toughness": "4",
        "oracle_text": (
            "Flying\nYou can't lose the game and your opponents can't win the game."
        ),
    }
    torpor_orb = {
        "name": "Torpor Orb",
        "type_line": "Artifact",
        "mana_cost": "{2}",
        "oracle_text": "Creatures entering don't cause abilities to trigger.",
    }
    assert serves(netherborn_altar, sig) is True
    assert serves(platinum_angel, sig) is True
    assert serves(torpor_orb, sig) is True
    lightning_bolt = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "mana_cost": "{R}",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    }
    assert serves(lightning_bolt, sig) is False


def test_speed_matters_serves_cheap_unblockable_only():
    # Vnwxt's speed ramps when an opponent loses life, so it wants CHEAP unblockable
    # creatures that connect early (Slither Blade, {U}). The cmc_max gate excludes an
    # expensive unblockable (Bubbling Beebles, mv 5) — that's not the early-pressure
    # package. Rides a sub-avenue, so check _lane_covers. Real oracle.
    sig = _sig("speed_matters", "you")
    slither_blade = {
        "name": "Slither Blade",
        "type_line": "Creature — Snake Rogue",
        "mana_cost": "{U}",
        "cmc": 1.0,
        "power": "2",
        "toughness": "1",
        "oracle_text": "This creature can't be blocked.",
    }
    bubbling_beebles = {
        "name": "Bubbling Beebles",
        "type_line": "Creature — Beeble",
        "mana_cost": "{4}{U}",
        "cmc": 5.0,
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "Bubbling Beebles can't be blocked as long as your opponents control an "
            "artifact or enchantment."
        ),
    }
    assert _lane_covers(slither_blade, sig) is True
    # Expensive unblockable is not the cheap early-pressure package (cmc gate).
    big_unblockable = dict(bubbling_beebles)
    big_unblockable["oracle_text"] = "This creature can't be blocked."
    assert _lane_covers(big_unblockable, sig) is False


def test_timing_control_serves_cast_and_activate_lock():
    # Dosan ("Players can cast spells only during their own turns") is a timing-lock
    # commander; City of Solitude is a near-copy ("cast spells AND ACTIVATE ABILITIES
    # only during their own turns") — the timing_control regex required "spells only"
    # contiguously and missed the "and activate abilities" variant. Real oracle.
    sig = _sig("timing_control", "opponents")
    city_of_solitude = {
        "name": "City of Solitude",
        "type_line": "Enchantment",
        "mana_cost": "{2}{G}",
        "oracle_text": (
            "Players can cast spells and activate abilities only during their own turns."
        ),
    }
    assert serves(city_of_solitude, sig) is True


def test_damage_prevention_serves_block_any_number_and_redirect_soak():
    # A damage-PREVENTION commander (Oriss "{T}: prevent all damage to target creature")
    # turns a "block any number of creatures" wall (Palace Guard) or a redirect-to-one
    # soak (Pariah) into a hard lock — block/soak everything, then prevent it. These ride
    # a sub-avenue, so check _lane_covers. Real oracle.
    sig = _sig("damage_prevention", "you")
    palace_guard = {
        "name": "Palace Guard",
        "type_line": "Creature — Human Soldier",
        "mana_cost": "{2}{W}",
        "power": "1",
        "toughness": "4",
        "oracle_text": "This creature can block any number of creatures.",
    }
    pariah = {
        "name": "Pariah",
        "type_line": "Enchantment — Aura",
        "mana_cost": "{2}{W}",
        "oracle_text": (
            "Enchant creature\nAll damage that would be dealt to you is dealt to "
            "enchanted creature instead."
        ),
    }
    assert _lane_covers(palace_guard, sig) is True
    assert _lane_covers(pariah, sig) is True
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert _lane_covers(grizzly, sig) is False


def test_island_matters_serves_island_makers():
    # Zhou Yu wants opponents to control Islands. Quicksilver Fountain (flood counters →
    # Islands) and Stormtide Leviathan ("All lands are Islands") feed it; a mana dork
    # does not. Real oracle.
    sig = _sig("island_matters", "you")
    quicksilver_fountain = {
        "name": "Quicksilver Fountain",
        "type_line": "Artifact",
        "mana_cost": "{3}",
        "oracle_text": (
            "At the beginning of each player's upkeep, that player puts a flood counter "
            "on target non-Island land they control of their choice. That land is an "
            "Island for as long as it has a flood counter on it.\nAt the beginning of "
            "each end step, if all lands on the battlefield are Islands, remove all "
            "flood counters from them."
        ),
    }
    stormtide_leviathan = {
        "name": "Stormtide Leviathan",
        "type_line": "Creature — Leviathan",
        "mana_cost": "{5}{U}{U}{U}",
        "power": "8",
        "toughness": "8",
        "keywords": ["Landwalk", "Islandwalk"],
        "oracle_text": (
            "Islandwalk (This creature can't be blocked as long as defending player "
            "controls an Island.)\nAll lands are Islands in addition to their other "
            "types.\nCreatures without flying or islandwalk can't attack."
        ),
    }
    assert serves(quicksilver_fountain, sig) is True
    assert serves(stormtide_leviathan, sig) is True
    llanowar_elves = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "oracle_text": "{T}: Add {G}.",
    }
    assert serves(llanowar_elves, sig) is False


def test_tap_down_blockers_serves_opponent_tappers():
    # Tromokratis wants to tap opponents' creatures so they can't all block. Sleep ("Tap
    # all creatures target player controls") and Blustersquall ("Tap target creature you
    # don't control") feed it; a burn spell does not. Real oracle.
    sig = _sig("tap_down_blockers", "you")
    sleep = {
        "name": "Sleep",
        "type_line": "Sorcery",
        "mana_cost": "{2}{U}{U}",
        "oracle_text": (
            "Tap all creatures target player controls. Those creatures don't untap "
            "during that player's next untap step."
        ),
    }
    blustersquall = {
        "name": "Blustersquall",
        "type_line": "Instant",
        "mana_cost": "{U}",
        "oracle_text": (
            "Tap target creature you don't control.\nOverload {3}{U} (You may cast this "
            'spell for its overload cost. If you do, change "target" in its text to '
            '"each.")'
        ),
    }
    assert serves(sleep, sig) is True
    assert serves(blustersquall, sig) is True
    lightning_bolt = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "mana_cost": "{R}",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    }
    assert serves(lightning_bolt, sig) is False


def test_per_target_payoff_serves_variable_target_spells():
    # Hinata (spells cost {1} less per target) wants spells whose target COUNT scales —
    # X-target and "any number of targets" — so the discount compounds. Aurelia's Fury
    # (divided among any number of targets) and Distorting Wake (X target permanents) are
    # premium; a single-target removal (Doom Blade) gives only {1} off and isn't the
    # payoff. Real oracle.
    sig = _sig("per_target_payoff", "you")
    aurelias_fury = {
        "name": "Aurelia's Fury",
        "type_line": "Instant",
        "mana_cost": "{X}{R}{W}",
        "oracle_text": (
            "Aurelia's Fury deals X damage divided as you choose among any number of "
            "targets. Tap each creature dealt damage this way. Players dealt damage this "
            "way can't cast noncreature spells this turn."
        ),
    }
    distorting_wake = {
        "name": "Distorting Wake",
        "type_line": "Sorcery",
        "mana_cost": "{X}{U}{U}{U}",
        "oracle_text": "Return X target nonland permanents to their owners' hands.",
    }
    assert serves(aurelias_fury, sig) is True
    assert serves(distorting_wake, sig) is True
    # Single-target removal is only a {1} discount — not the multi-target payoff.
    doom_blade = {
        "name": "Doom Blade",
        "type_line": "Instant",
        "mana_cost": "{1}{B}",
        "oracle_text": "Destroy target nonblack creature.",
    }
    assert serves(doom_blade, sig) is False


def test_ability_strip_payoff_serves_big_drawback_creatures():
    # Abigale strips a target's abilities + buffs it, so she wants BIG creatures whose
    # crippling drawback she removes (Rotting Regisaur 7/6 upkeep-discard; Nyxathid 7/7
    # that shrinks). The serve ANDs a crippling-drawback clause with power >= 5: a big
    # vanilla beater (Colossal Dreadmaw — no drawback) and a small drawback creature
    # (Scarred Puma — power 2) are both excluded. Real oracle.
    sig = _sig("ability_strip_payoff", "you")
    rotting_regisaur = {
        "name": "Rotting Regisaur",
        "type_line": "Creature — Zombie Dinosaur",
        "mana_cost": "{2}{B}",
        "power": "7",
        "toughness": "6",
        "oracle_text": "At the beginning of your upkeep, discard a card.",
    }
    nyxathid = {
        "name": "Nyxathid",
        "type_line": "Creature — Elemental",
        "mana_cost": "{1}{B}{B}",
        "power": "7",
        "toughness": "7",
        "oracle_text": (
            "As this creature enters, choose an opponent.\nThis creature gets -1/-1 for "
            "each card in the chosen player's hand."
        ),
    }
    assert serves(rotting_regisaur, sig) is True
    assert serves(nyxathid, sig) is True
    # Big body, no drawback to strip → not the payoff.
    colossal_dreadmaw = {
        "name": "Colossal Dreadmaw",
        "type_line": "Creature — Dinosaur",
        "mana_cost": "{4}{G}{G}",
        "power": "6",
        "toughness": "6",
        "oracle_text": (
            "Trample (This creature can deal excess combat damage to the player or "
            "planeswalker it's attacking.)"
        ),
    }
    assert serves(colossal_dreadmaw, sig) is False
    # Crippling drawback but too small to be worth stripping + buffing.
    scarred_puma = {
        "name": "Scarred Puma",
        "type_line": "Creature — Cat",
        "mana_cost": "{B}",
        "power": "2",
        "toughness": "1",
        "oracle_text": (
            "This creature can't attack unless a black or green creature is attacking."
        ),
    }
    assert serves(scarred_puma, sig) is False


def test_arcane_matters_serves_arcane_subtype_spells():
    # An Arcane-tribal commander wants Arcane-subtype spells (CR 205.3k). Eerie
    # Procession (Sorcery — Arcane) and Psychic Puppetry (Instant — Arcane) feed it; a
    # plain non-Arcane instant (Lightning Bolt) does not. Real oracle.
    sig = _sig("arcane_matters", "you")
    eerie = {
        "name": "Eerie Procession",
        "type_line": "Sorcery — Arcane",
        "mana_cost": "{2}{U}",
        "oracle_text": (
            "Search your library for an Arcane card, reveal that card, put it into your "
            "hand, then shuffle."
        ),
    }
    psychic_puppetry = {
        "name": "Psychic Puppetry",
        "type_line": "Instant — Arcane",
        "mana_cost": "{1}{U}",
        "oracle_text": (
            "You may tap or untap target permanent.\nSplice onto Arcane {U} (As you cast "
            "an Arcane spell, you may reveal this card from your hand and pay its splice "
            "cost. If you do, add this card's effects to that spell.)"
        ),
    }
    assert serves(eerie, sig) is True
    assert serves(psychic_puppetry, sig) is True
    lightning_bolt = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "mana_cost": "{R}",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    }
    assert serves(lightning_bolt, sig) is False


def test_enlist_matters_serves_enlisters_and_stayback_fodder():
    # Aradesh wants the enlist creatures themselves (keyword bearers) on the main serve,
    # and big stay-back fodder to tap (the sub-avenue): Relic Golem (6/6, can't attack
    # unless an opponent has 8+ graveyard cards) is ideal — tap it for 6 power. A vanilla
    # bear is neither. Real oracle.
    sig = _sig("enlist_matters", "you")
    benalish = {
        "name": "Benalish Faithbonder",
        "type_line": "Creature — Human Cleric",
        "mana_cost": "{1}{W}",
        "power": "1",
        "toughness": "3",
        "keywords": ["Vigilance", "Enlist"],
        "oracle_text": (
            "Vigilance\nEnlist (As this creature attacks, you may tap a nonattacking "
            "creature you control without summoning sickness. When you do, add its power "
            "to this creature's until end of turn.)"
        ),
    }
    relic_golem = {
        "name": "Relic Golem",
        "type_line": "Artifact Creature — Golem",
        "mana_cost": "{3}",
        "power": "6",
        "toughness": "6",
        "oracle_text": (
            "This creature can't attack or block unless an opponent has eight or more "
            "cards in their graveyard.\n{2}, {T}: Target player mills two cards. (They "
            "put the top two cards of their library into their graveyard.)"
        ),
    }
    assert serves(benalish, sig) is True  # enlist creature (keyword)
    assert _lane_covers(relic_golem, sig) is True  # stay-back fodder (sub-avenue)
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert _lane_covers(grizzly, sig) is False


def test_power_tap_engine_serves_untap_effects():
    # A power-scaling tap engine (Mona Lisa) wants UNTAP effects to re-tap. Witch's Web
    # ("Untap it.") and Kiora's Follower ("Untap another target permanent.") feed it; a
    # burn spell (Lightning Bolt) does not. Real oracle.
    sig = _sig("power_tap_engine", "you")
    witchs_web = {
        "name": "Witch's Web",
        "type_line": "Instant",
        "mana_cost": "{1}{G}",
        "oracle_text": "Target creature gets +3/+3 and gains reach until end of turn. Untap it.",
    }
    kioras_follower = {
        "name": "Kiora's Follower",
        "type_line": "Creature — Merfolk",
        "mana_cost": "{G}{U}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "{T}: Untap another target permanent.",
    }
    assert serves(witchs_web, sig) is True
    assert serves(kioras_follower, sig) is True
    lightning_bolt = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "mana_cost": "{R}",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    }
    assert serves(lightning_bolt, sig) is False


def test_exert_matters_serves_exert_creatures():
    # A pseudo-vigilance commander (Johan) wants exert creatures — Champion of Rhonas
    # (Exert keyword). A vanilla creature is not served. Real oracle.
    sig = _sig("exert_matters", "you")
    champion = {
        "name": "Champion of Rhonas",
        "type_line": "Creature — Jackal Warrior",
        "mana_cost": "{3}{G}",
        "power": "3",
        "toughness": "3",
        "keywords": ["Exert"],
        "oracle_text": (
            "You may exert this creature as it attacks. When you do, you may put a "
            "creature card from your hand onto the battlefield. (An exerted creature "
            "won't untap during your next untap step.)"
        ),
    }
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert serves(champion, sig) is True
    assert serves(grizzly, sig) is False


def test_type_change_serves_type_changers_not_tribal_anthems():
    # A type-hoser (Gor Muldrak) wants genuine creature-type CHANGERS — Standardize
    # ("Each creature becomes that type"), Unnatural Selection ("Target creature becomes
    # that type") — so it can force opponents into the punished type. A tribal anthem
    # that merely "choose a creature type" then buffs your own board (Icon of Ancestry)
    # is NOT a changer. Real oracle.
    sig = _sig("type_change", "you")
    standardize = {
        "name": "Standardize",
        "type_line": "Instant",
        "mana_cost": "{U}{U}",
        "oracle_text": (
            "Choose a creature type other than Wall. Each creature becomes that type "
            "until end of turn."
        ),
    }
    unnatural_selection = {
        "name": "Unnatural Selection",
        "type_line": "Enchantment",
        "mana_cost": "{1}{U}",
        "oracle_text": (
            "{1}: Choose a creature type other than Wall. Target creature becomes that "
            "type until end of turn."
        ),
    }
    assert serves(standardize, sig) is True
    assert serves(unnatural_selection, sig) is True
    icon_of_ancestry = {
        "name": "Icon of Ancestry",
        "type_line": "Artifact",
        "mana_cost": "{3}",
        "oracle_text": (
            "As this artifact enters, choose a creature type.\nCreatures you control of "
            "the chosen type get +1/+1.\n{3}, {T}: Look at the top three cards of your "
            "library. You may reveal a creature card of the chosen type from among them "
            "and put it into your hand. Put the rest on the bottom of your library in a "
            "random order."
        ),
    }
    assert serves(icon_of_ancestry, sig) is False


def test_recast_etb_serves_aggressive_etb_not_activated_drain():
    # A Sneak/bounce-replay commander (Oroku Saki) recasts cheap aggressive-ETB creatures
    # to repeat the bleed. Virus Beetle ("When this creature enters, each opponent
    # discards a card") feeds it; Engine Rat's drain is an ACTIVATED ability ("{5}{B}:
    # Each opponent loses 2 life"), not an enter-trigger, so recasting it does nothing.
    # Real oracle.
    sig = _sig("recast_etb", "you")
    virus_beetle = {
        "name": "Virus Beetle",
        "type_line": "Artifact Creature — Insect",
        "mana_cost": "{1}{B}",
        "power": "1",
        "toughness": "1",
        "oracle_text": "When this creature enters, each opponent discards a card.",
    }
    engine_rat = {
        "name": "Engine Rat",
        "type_line": "Creature — Zombie Rat",
        "mana_cost": "{B}",
        "power": "1",
        "toughness": "1",
        "oracle_text": "Deathtouch\n{5}{B}: Each opponent loses 2 life.",
    }
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
    rite_of_passage = {
        "name": "Rite of Passage",
        "type_line": "Enchantment",
        "mana_cost": "{2}{G}",
        "oracle_text": (
            "Whenever a creature you control is dealt damage, put a +1/+1 counter on "
            "it. (It must survive the damage to get the counter.)"
        ),
    }
    druids_call = {
        "name": "Druid's Call",
        "type_line": "Enchantment — Aura",
        "mana_cost": "{1}{G}",
        "oracle_text": (
            "Enchant creature\nWhenever enchanted creature is dealt damage, its "
            "controller creates that many 1/1 green Squirrel creature tokens."
        ),
    }
    assert serves(rite_of_passage, sig) is True
    assert serves(druids_call, sig) is True
    # Generic enrage targets ITSELF, which never receives the redirected damage.
    siegehorn = {
        "name": "Siegehorn Ceratops",
        "type_line": "Creature — Dinosaur",
        "mana_cost": "{G}{W}",
        "power": "2",
        "toughness": "2",
        "oracle_text": (
            "Enrage — Whenever this creature is dealt damage, put two +1/+1 counters on "
            "it. (It must survive the damage to get the counters.)"
        ),
    }
    assert serves(siegehorn, sig) is False


def test_outlaw_matters_serves_token_makers_and_recursion():
    # Vial Smasher's outlaw payoff wants cards that MAKE outlaw tokens (Mercenary /
    # Pirate / Rogue / Assassin / Warlock) and outlaw RECURSION — not just creatures
    # that ARE outlaws. The serve had only the type-line gate + "outlaws you control".
    # Real oracle.
    sig = _sig("outlaw_matters", "you")
    brimstone_roundup = {
        "name": "Brimstone Roundup",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever you cast your second spell each turn, create a 1/1 red Mercenary "
            'creature token with "{T}: Target creature you control gets +1/+0 until '
            'end of turn. Activate only as a sorcery."\nPlot {2}{R} (You may pay {2}{R} '
            "and exile this card from your hand. Cast it as a sorcery on a later turn "
            "without paying its mana cost. Plot only as a sorcery.)"
        ),
    }
    back_in_town = {
        "name": "Back in Town",
        "type_line": "Sorcery",
        "oracle_text": (
            "Return X target outlaw creature cards from your graveyard to the "
            "battlefield. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are "
            "outlaws.)"
        ),
    }
    raise_the_alarm = {
        "name": "Raise the Alarm",
        "type_line": "Instant",
        "oracle_text": "Create two 1/1 white Soldier creature tokens.",
    }
    assert serves(brimstone_roundup, sig) is True  # makes Mercenary tokens
    assert serves(back_in_town, sig) is True  # returns outlaw creature cards
    assert serves(raise_the_alarm, sig) is False  # non-outlaw (Soldier) tokens


def test_opponent_exile_serves_the_exile_enablers():
    # Umbris grows per "card your opponents own in exile", so it wants the ENABLERS that
    # exile opponents' cards (Leyline of the Void, Ashiok, Bojuka Bog) — not just other
    # "opponents own in exile" counters. Real oracle.
    sig = _sig("opponent_exile_matters", "opponents")
    leyline_of_the_void = {
        "name": "Leyline of the Void",
        "type_line": "Enchantment",
        "oracle_text": (
            "If this card is in your opening hand, you may begin the game with it on "
            "the battlefield.\nIf a card would be put into an opponent's graveyard from "
            "anywhere, exile it instead."
        ),
    }
    ashiok_dream_render = {
        "name": "Ashiok, Dream Render",
        "type_line": "Legendary Planeswalker — Ashiok",
        "oracle_text": (
            "Spells and abilities your opponents control can't cause their controller "
            "to search their library.\n−1: Target player mills four cards. Then exile "
            "each opponent's graveyard."
        ),
    }
    deep_analysis = {  # flashback exiles ITSELF from YOUR graveyard — not opponents'
        "name": "Deep Analysis",
        "type_line": "Sorcery",
        "oracle_text": (
            "Target player draws two cards.\nFlashback—{1}{U}, Pay 3 life. (You may "
            "cast this card from your graveyard for its flashback cost. Then exile it.)"
        ),
    }
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
    profane_tutor = {
        "name": "Profane Tutor",
        "type_line": "Sorcery",
        "keywords": ["Suspend"],
        "oracle_text": (
            "Suspend 2—{1}{B} (Rather than cast this card from your hand, pay {1}{B} and "
            "exile it with two time counters on it. At the beginning of your upkeep, "
            "remove a time counter. When the last is removed, you may cast it without "
            "paying its mana cost.)\nSearch your library for a card, put that card into "
            "your hand, then shuffle."
        ),
    }
    behold_the_multiverse = {
        "name": "Behold the Multiverse",
        "type_line": "Instant",
        "keywords": ["Foretell", "Scry"],
        "oracle_text": (
            "Scry 2, then draw two cards.\nForetell {1}{U} (During your turn, you may "
            "pay {2} and exile this card from your hand face down. Cast it on a later "
            "turn for its foretell cost.)"
        ),
    }
    staggershock = {
        "name": "Staggershock",
        "type_line": "Instant",
        "keywords": ["Rebound"],
        "oracle_text": (
            "Staggershock deals 2 damage to any target.\nRebound (If you cast this spell "
            "from your hand, exile it as it resolves. At the beginning of your next "
            "upkeep, you may cast this card from exile without paying its mana cost.)"
        ),
    }
    lightning_bolt = {  # plain burn, no cast-from-exile keyword
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "keywords": [],
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    }
    assert serves(profane_tutor, sig) is True  # Suspend
    assert serves(behold_the_multiverse, sig) is True  # Foretell
    assert serves(staggershock, sig) is True  # Rebound
    assert serves(lightning_bolt, sig) is False  # no cast-from-exile


def test_keyword_soup_serves_keyword_dense_creatures():
    # The sweep 'keyword_soup' signal (Rayami absorbs keywords from dead creatures; Akroma
    # Vision / Indominus Rex share them) was stuck on the narrow sweep regex, not the
    # keyword-count serve that 'keyword_soup_matters' (Odric) already had — so keyword-
    # dense creatures weren't served. Real oracle.
    sig = _sig("keyword_soup", "you")
    venomthrope = {
        "name": "Venomthrope",
        "type_line": "Creature — Tyranid",
        "mana_cost": "{1}{G}{U}",
        "power": "2",
        "toughness": "2",
        "keywords": ["Deathtouch", "Flying", "Hexproof"],
        "oracle_text": "Flying, deathtouch, hexproof",
    }
    stonecoil_serpent = {
        "name": "Stonecoil Serpent",
        "type_line": "Artifact Creature — Snake",
        "mana_cost": "{X}",
        "power": "0",
        "toughness": "0",
        "keywords": ["Reach", "Protection", "Trample"],
        "oracle_text": (
            "Reach, trample, protection from multicolored\nThis creature enters with X "
            "+1/+1 counters on it."
        ),
    }
    grizzly_bears = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "keywords": [],
        "oracle_text": "",
    }
    assert serves(venomthrope, sig) is True  # 3 evergreen keywords
    assert serves(stonecoil_serpent, sig) is True  # 3 evergreen keywords
    assert serves(grizzly_bears, sig) is False  # no keywords


def test_color_hoser_serves_anti_color_hate():
    # color_hoser is opened by anti-color commanders (Major Teroh "exile all black",
    # Ascendant Evincar, Crovax, Dromar, Llawan, Jaya) but its serve matched only Painter
    # changers. Those decks want anti-color HATE — "[color] creatures can't attack",
    # "protection from [color]", "destroy all [color] creatures". Real oracle.
    sig = _sig("color_hoser", "you")
    light_of_day = {
        "name": "Light of Day",
        "type_line": "Enchantment",
        "mana_cost": "{3}{W}",
        "oracle_text": "Black creatures can't attack or block.",
    }
    absolute_grace = {
        "name": "Absolute Grace",
        "type_line": "Enchantment",
        "mana_cost": "{1}{W}",
        "oracle_text": "All creatures have protection from black.",
    }
    perish = {
        "name": "Perish",
        "type_line": "Sorcery",
        "mana_cost": "{2}{B}",
        "oracle_text": "Destroy all green creatures. They can't be regenerated.",
    }
    wrath_of_god = {  # colorless mass removal — not anti-color hate
        "name": "Wrath of God",
        "type_line": "Sorcery",
        "mana_cost": "{2}{W}{W}",
        "oracle_text": "Destroy all creatures. They can't be regenerated.",
    }
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
    hibernation = {
        "name": "Hibernation",
        "type_line": "Instant",
        "mana_cost": "{2}{U}",
        "oracle_text": "Return all green permanents to their owners' hands.",
    }
    wash_out = {
        "name": "Wash Out",
        "type_line": "Sorcery",
        "mana_cost": "{3}{U}",
        "oracle_text": (
            "Return all permanents of the color of your choice to their owners' hands."
        ),
    }
    llawan = {
        "name": "Llawan, Cephalid Empress",
        "type_line": "Legendary Creature — Octopus Noble",
        "mana_cost": "{3}{U}",
        "power": "2",
        "toughness": "3",
        "oracle_text": (
            "When Llawan enters, return all blue creatures your opponents control to "
            "their owners' hands.\nYour opponents can't cast blue creature spells."
        ),
    }
    wrath_of_god = {  # colorless mass removal — not a color-conditional payoff
        "name": "Wrath of God",
        "type_line": "Sorcery",
        "mana_cost": "{2}{W}{W}",
        "oracle_text": "Destroy all creatures. They can't be regenerated.",
    }
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
    kessig_flamebreather = {
        "name": "Kessig Flamebreather",
        "type_line": "Creature — Human Shaman",
        "mana_cost": "{1}{R}",
        "power": "1",
        "toughness": "3",
        "oracle_text": (
            "Whenever you cast a noncreature spell, this creature deals 1 damage to "
            "each opponent."
        ),
    }
    sulfuric_vortex = {  # symmetric group-slug — "deals 2 damage to that player"
        "name": "Sulfuric Vortex",
        "type_line": "Enchantment",
        "mana_cost": "{1}{R}{R}",
        "oracle_text": (
            "At the beginning of each player's upkeep, this enchantment deals 2 damage "
            "to that player.\nIf a player would gain life, that player gains no life "
            "instead."
        ),
    }
    flame_slash = {  # creature-only removal — not opponent life loss
        "name": "Flame Slash",
        "type_line": "Sorcery",
        "mana_cost": "{R}",
        "oracle_text": "Flame Slash deals 4 damage to target creature.",
    }
    assert serves(kessig_flamebreather, sig) is True  # damage to each opponent = drain
    assert serves(sulfuric_vortex, sig) is True  # group-slug "that player" = drain
    assert serves(flame_slash, sig) is False  # creature-only, no opponent life loss


def test_token_maker_serves_offspring_keyword():
    # Offspring (CR keyword) makes a 1/1 token copy of the creature — token-making that
    # lives in the reminder text deck-forge strips, so it needs the authoritative Scryfall
    # keyword. A go-wide / token deck wants the extra body. (phase_crosscheck-surfaced.)
    sig = _sig("token_maker", "you")
    prosperous_bandit = {
        "name": "Prosperous Bandit",
        "type_line": "Creature — Raccoon Rogue",
        "mana_cost": "{2}{R}",
        "power": "2",
        "toughness": "2",
        "keywords": ["Offspring", "First strike", "Treasure"],
        "oracle_text": (
            "Offspring {1} (You may pay an additional {1} as you cast this spell. If you "
            "do, when this creature enters, create a 1/1 token copy of it.)\nFirst "
            "strike\nWhenever this creature deals combat damage to a player, create that "
            "many tapped Treasure tokens."
        ),
    }
    grizzly_bears = {  # plain creature, no Offspring / token-making
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "keywords": [],
        "oracle_text": "",
    }
    assert serves(prosperous_bandit, sig) is True  # Offspring = makes a token copy
    assert serves(grizzly_bears, sig) is False


def test_discard_matters_serves_self_discard_outlets():
    # A discard-payoff commander (Rielle "whenever you discard ... draw") wants self-
    # discard OUTLETS: wheels ("discard all the cards in your hand"), "discard X cards"
    # as a cost (Turbulent Dreams, Firestorm). The serve only had loot ("discard a/two:")
    # and "draw then discard". Real oracle.
    sig = _sig("discard_matters", "you")
    tolarian = {
        "name": "Tolarian Winds",
        "type_line": "Sorcery",
        "oracle_text": "Discard all the cards in your hand, then draw that many cards.",
    }
    firestorm = {
        "name": "Firestorm",
        "type_line": "Instant",
        "oracle_text": (
            "As an additional cost to cast this spell, discard X cards.\n"
            "Firestorm deals X damage to each of X target creatures and/or players."
        ),
    }
    assert _lane_covers(tolarian, sig) is True
    assert _lane_covers(firestorm, sig) is True
    # Over-fire guard: forcing an OPPONENT to discard is hand-attack, not a self-outlet.
    opp_discard = {
        "name": "Mind Rot",
        "type_line": "Sorcery",
        "oracle_text": "Target player discards two cards.",
    }
    assert _lane_covers(opp_discard, sig) is False


SELF_MILL = {
    "name": "Self Mill",
    "oracle_text": "Put the top four cards of your library into your graveyard.",
}
OPPONENT_MILL = {
    "name": "Maddening Cacophony",
    "oracle_text": "Kicker {3}{U}\nEach opponent mills eight cards. If this spell was kicked, instead each opponent mills half their library, rounded up.",
}
TOKEN_MAKER = {
    "name": "Token Maker",
    "oracle_text": "Create three 1/1 white Soldier creature tokens.",
}
BURN = {"name": "Bolt", "oracle_text": "Bolt deals 3 damage to any target."}
LIFEGAIN = {"name": "Healer", "oracle_text": "You gain 4 life."}


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
    breach = {
        "name": "Breach the Multiverse",
        "type_line": "Sorcery",
        "oracle_text": (
            "Each player mills ten cards. For each player, choose a creature or "
            "planeswalker card in that player's graveyard. Put those cards onto the "
            "battlefield under your control. Then each creature you control becomes a "
            "Phyrexian in addition to its other types."
        ),
    }
    sepulchral = {
        "name": "Sepulchral Primordial",
        "type_line": "Creature — Avatar",
        "oracle_text": (
            "Intimidate\nWhen this creature enters, for each opponent, you may put up "
            "to one target creature card from that player's graveyard onto the "
            "battlefield under your control."
        ),
    }
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
    wound_reflection = {
        "name": "Wound Reflection",
        "type_line": "Enchantment",
        "oracle_text": (
            "At the beginning of each end step, each opponent loses life equal to the "
            "life they lost this turn. (Damage causes loss of life.)"
        ),
    }
    gratuitous = {
        "name": "Gratuitous Violence",
        "type_line": "Enchantment",
        "oracle_text": (
            "If a creature you control would deal damage to a permanent or player, it "
            "deals double that damage to that permanent or player instead."
        ),
    }
    assert _lane_covers(wound_reflection, sig) is True
    assert _lane_covers(gratuitous, sig) is True
    # Over-fire guard: a plain lifegain spell is not a damage amplifier.
    lifegain = {
        "name": "Healing Salve",
        "type_line": "Instant",
        "oracle_text": "You gain 3 life.",
    }
    assert _lane_covers(lifegain, sig) is False


def test_clone_serves_high_value_dies_trigger_creatures():
    # A clone deck (The Ever-Changing 'Dane) copies high-mana-value creatures with a
    # strong DEATH trigger — the copy re-fires the trigger when it dies (Kokusho drains,
    # Keiga steals, Junji). clone served big bodies (power>=6) but not these (power 4-5,
    # cmc 5-6). The serve needs "self-dies VALUE trigger AND mana value >= 5" — an AND
    # the flat OR-Serve couldn't express. Real oracle.
    sig = _sig("clone_matters", "you")
    kokusho = {
        "name": "Kokusho, the Evening Star",
        "type_line": "Legendary Creature — Dragon Spirit",
        "cmc": 6.0,
        "power": "5",
        "oracle_text": (
            "Flying\nWhen Kokusho, the Evening Star dies, each opponent loses 5 life "
            "and you gain life equal to the life lost this way."
        ),
    }
    junji = {
        "name": "Junji, the Midnight Sky",
        "type_line": "Legendary Creature — Dragon Spirit",
        "cmc": 5.0,
        "power": "4",
        "oracle_text": (
            "Flying, menace\nWhen Junji, the Midnight Sky dies, choose one —\n"
            "• Each opponent discards a card and loses 2 life.\n"
            "• Put target non-Dragon creature card from a graveyard onto the "
            "battlefield under your control. It's a Zombie in addition to its other "
            "types."
        ),
    }
    assert _lane_covers(kokusho, sig) is True
    assert _lane_covers(junji, sig) is True
    # Over-fire guard: a cmc-1 undying body has a dies trigger but is NOT a clone bomb.
    young_wolf = {
        "name": "Young Wolf",
        "type_line": "Creature — Wolf",
        "cmc": 1.0,
        "power": "1",
        "oracle_text": (
            "Undying (When this creature dies, if it had no +1/+1 counters on it, "
            "return it to the battlefield under its owner's control with a +1/+1 "
            "counter on it.)"
        ),
    }
    assert _lane_covers(young_wolf, sig) is False


def test_ninjutsu_lane_serves_ninja_creatures():
    # A ninjutsu deck (Yuriko, Satoru, Higure) wants the NINJA creatures themselves —
    # the ninjutsu payoff swapped in via an unblocked attacker — not just the evasion
    # carriers. The lane served evasion keywords but not the ninjutsu keyword. Real card.
    sig = _sig("ninjutsu_matters", "you")
    satoru = {
        "name": "Satoru Umezawa",
        "type_line": "Legendary Creature — Human Ninja",
        "keywords": ["Ninjutsu"],
        "oracle_text": (
            "Whenever you activate a ninjutsu ability, look at the top three cards of "
            "your library. Put one of them into your hand.\nEach creature card in your "
            "hand has ninjutsu {1}{U}{B}."
        ),
    }
    silver_fur = {
        "name": "Silver-Fur Master",
        "type_line": "Creature — Rat Ninja",
        "keywords": ["Ninjutsu"],
        "oracle_text": (
            "Ninjutsu {U}{B}\nThe first ninjutsu ability you activate each turn costs "
            '{1} less to activate.\nNinja creatures you control have "Ninjutsu {U}{B}."'
        ),
    }
    assert _lane_covers(satoru, sig) is True
    assert _lane_covers(silver_fur, sig) is True
    # Over-fire guard: a vanilla creature is not a ninjutsu card.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert _lane_covers(bear, sig) is False


def test_aristocrats_lanes_serve_death_doublers_and_dies_return_grants():
    # An aristocrats/death commander (Orca) wants death-trigger DOUBLERS (Teysa, Drivnod
    # — the deaths-Panharmonicon) and dies-return GRANTERS (Feign Death, Supernatural
    # Stamina — loop a key creature with a sac outlet). death/sacrifice served neither.
    # Real oracle.
    drivnod = {
        "name": "Drivnod, Carnage Dominus",
        "type_line": "Legendary Creature — Phyrexian Horror",
        "oracle_text": (
            "If a creature dying causes a triggered ability of a permanent you control "
            "to trigger, that ability triggers an additional time."
        ),
    }
    feign_death = {
        "name": "Feign Death",
        "type_line": "Instant",
        "oracle_text": (
            'Until end of turn, target creature gains "When this creature dies, '
            "return it to the battlefield tapped under its owner's control with a "
            '+1/+1 counter on it."'
        ),
    }
    for key, scope in (("death_matters", "any"), ("sacrifice_matters", "you")):
        sig = _sig(key, scope)
        assert _lane_covers(drivnod, sig) is True, key
        assert _lane_covers(feign_death, sig) is True, key
    # Over-fire guard: an ETB-trigger doubler (Panharmonicon) is NOT a DEATH-trigger
    # doubler — the death-doubler branch must require "creature dying", not "entering".
    panharmonicon = {
        "name": "Panharmonicon",
        "type_line": "Artifact",
        "oracle_text": (
            "If an artifact or creature entering causes a triggered ability of a "
            "permanent you control to trigger, that ability triggers an additional time."
        ),
    }
    assert _lane_covers(panharmonicon, _sig("death_matters", "any")) is False


def test_blink_serves_self_bounce_recast_engines():
    # A blink/flicker deck wants self-bounce recast engines (Whitemane Lion, Kor
    # Skyfisher) — bouncing your own ETB creature and recasting re-fires the ETB, the
    # same value blink gives. The serve missed the "you may return ANOTHER TARGET
    # creature you control" wording (Jeskai Barricade), and blink_flicker lacked the
    # self-bounce extra. Real oracle.
    sig = _sig("blink_flicker", "you")
    jeskai = {
        "name": "Jeskai Barricade",
        "type_line": "Creature — Wall",
        "oracle_text": (
            "Flash\nDefender\nWhen this creature enters, you may return another target "
            "creature you control to its owner's hand."
        ),
    }
    whitemane = {
        "name": "Whitemane Lion",
        "type_line": "Creature — Cat",
        "oracle_text": (
            "Flash\nWhen this creature enters, return a creature you control to its "
            "owner's hand."
        ),
    }
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
REANIMATION_SPELL = {
    "name": "Animate Dead-like",
    "oracle_text": "Return target creature card from your graveyard to the battlefield.",
}
ESCAPE_CREATURE = {
    "name": "Woe Strider-like",
    "type_line": "Creature — Horror",
    "oracle_text": (
        "Sacrifice another creature: Scry 1.\n"
        "Escape—{3}{B}{B}, Exile four other cards from your graveyard."
    ),
    "keywords": ["Escape"],
}
GRAVEYARD_RETURN = {
    "name": "Regrowth",
    "oracle_text": "Return target card from your graveyard to your hand.",
}


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
    persist = {
        "name": "Murderous Redcap",
        "type_line": "Creature — Goblin Assassin",
        "oracle_text": "When this creature enters, it deals damage equal to its power to any target.\nPersist (When this creature dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)",
        "keywords": ["Persist"],
    }
    undying = {
        "name": "Geralf's Messenger",
        "type_line": "Creature — Zombie",
        "oracle_text": "This creature enters tapped.\nWhen this creature enters, target opponent loses 2 life.\nUndying (When this creature dies, if it had no +1/+1 counters on it, return it to the battlefield under its owner's control with a +1/+1 counter on it.)",
        "keywords": ["Undying"],
    }
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
BLOOD_ARTIST = {
    "name": "Blood Artist",
    "type_line": "Creature — Vampire",
    "oracle_text": (
        "Whenever this creature or another creature dies, target player loses 1 life "
        "and you gain 1 life."
    ),
}
ZULAPORT = {
    "name": "Zulaport Cutthroat",
    "type_line": "Creature — Human Rogue Ally",
    "oracle_text": (
        "Whenever this creature or another creature you control dies, each opponent "
        "loses 1 life and you gain 1 life."
    ),
}


def test_death_drain_served_by_both_aristocrats_and_sacrifice_lanes():
    # The drain payoff must be on-theme for BOTH the death lane and the sacrifice lane
    # (a sac-outlet commander like Yawgmoth opens sacrifice_matters, not death_matters).
    for sig in (_sig("death_matters", "any"), _sig("sacrifice_matters", "you")):
        assert serves(BLOOD_ARTIST, sig) is True
        assert serves(ZULAPORT, sig) is True


def test_sacrifice_lane_does_not_serve_plain_lifegain():
    # A bare lifegain card is not a sacrifice/aristocrats enabler.
    assert serves(LIFEGAIN, _sig("sacrifice_matters", "you")) is False


# --- landfall: payoffs + extra lands + lands-from-graveyard ---------------------
LANDFALL_PAYOFF = {
    "name": "Lotus Cobra",
    "type_line": "Creature — Snake",
    "oracle_text": "Landfall — Whenever a land you control enters, add one mana of any color.",
}
EXTRA_LANDS = {
    "name": "Azusa, Lost but Seeking",
    "type_line": "Legendary Creature — Human Monk",
    "oracle_text": "You may play two additional lands on each of your turns.",
}
LANDS_FROM_GRAVE = {
    "name": "Ramunap Excavator",
    "type_line": "Creature — Snake Cleric",
    "oracle_text": "You may play lands from your graveyard.",
}


def test_landfall_serves_payoffs_extra_lands_and_recursion():
    sig = _sig("landfall", "you")
    assert serves(LANDFALL_PAYOFF, sig) is True  # the payoff itself (was uncovered)
    assert serves(EXTRA_LANDS, sig) is True  # extra-land enabler
    assert serves(LANDS_FROM_GRAVE, sig) is True  # land recursion (was uncovered)


def test_landfall_does_not_serve_unrelated_burn():
    assert serves(BURN, _sig("landfall", "you")) is False


# --- blink: the lane must surface ETB-value creatures + ETB-trigger doublers ----
ETB_VALUE_CREATURE = {
    "name": "Mulldrifter",
    "type_line": "Creature — Elemental",
    "oracle_text": "Flying\nWhen this creature enters, draw two cards.\nEvoke {2}{U} (You may cast this spell for its evoke cost. If you do, it's sacrificed when it enters.)",
}
ETB_DOUBLER = {
    "name": "Panharmonicon",
    "type_line": "Artifact",
    "oracle_text": (
        "If an artifact or creature entering causes a triggered ability of a permanent "
        "you control to trigger, that ability triggers an additional time."
    ),
}
FLICKER_EFFECT = {
    "name": "Ephemerate",
    "type_line": "Instant",
    "oracle_text": "Exile target creature you control, then return it to the battlefield under its owner's control.\nRebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you may cast this card from exile without paying its mana cost.)",
}


def test_blink_lane_surfaces_targets_and_doublers_not_just_flicker():
    sig = _sig("blink_flicker", "you")
    assert _lane_covers(FLICKER_EFFECT, sig) is True  # the flicker effect (existing)
    assert _lane_covers(ETB_VALUE_CREATURE, sig) is True  # the target to flicker (new)
    assert _lane_covers(ETB_DOUBLER, sig) is True  # ETB-trigger doubler (new)


def test_blink_lane_does_not_surface_vanilla_creature():
    vanilla = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert _lane_covers(vanilla, _sig("blink_flicker", "you")) is False


# --- counter doublers must surface across every counter lane -------------------
DOUBLING_SEASON = {
    "name": "Doubling Season",
    "type_line": "Enchantment",
    "oracle_text": (
        "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead."
    ),
}
HARDENED_SCALES = {
    "name": "Hardened Scales",
    "type_line": "Enchantment",
    "oracle_text": (
        "If one or more +1/+1 counters would be put on a creature you control, that "
        "many plus one +1/+1 counters are put on it instead."
    ),
}
COUNTER_LANES = [
    ("counters_matter", "any"),
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
    placement = {
        "name": "Unexpected Fangs",
        "type_line": "Instant",
        "oracle_text": "Put a +1/+1 counter and a lifelink counter on target creature.",
    }
    assert _lane_covers(placement, _sig("self_counter_grow", "you")) is True


def test_combat_lane_credits_single_creature_attack_triggers():
    sig = _sig("attack_matters", "you")
    aggro = {
        "name": "Vicious Conquistador",
        "type_line": "Creature — Vampire Soldier",
        "oracle_text": "Whenever this creature attacks, each opponent loses 1 life.",
    }
    defensive = {
        "name": "Wall of Defense",
        "type_line": "Creature — Wall",
        "oracle_text": "Whenever a creature attacks you, you gain 1 life.",
    }
    assert serves(aggro, sig) is True
    assert serves(defensive, sig) is False  # "attacks you" is not an aggro payoff


def test_etb_lane_surfaces_value_creatures_and_doublers():
    sig = _sig("creature_etb", "you")
    assert _lane_covers(ETB_VALUE_CREATURE, sig) is True  # Mulldrifter
    assert _lane_covers(ETB_DOUBLER, sig) is True  # Panharmonicon


def test_aristocrats_credits_plural_creatures_die():
    # "Whenever one or more creatures die" (Morbid Opportunist) is the same payoff as
    # "dies" — plural phrasing must not be missed.
    morbid = {
        "name": "Morbid Opportunist",
        "type_line": "Creature — Human Rogue",
        "oracle_text": "Whenever one or more other creatures die, draw a card. This "
        "ability triggers only once each turn.",
    }
    keys = {(s.key, s.scope) for s in extract_signals(morbid)}
    assert any(k == "death_matters" for k, _ in keys)
    assert serves(morbid, _sig("death_matters", "any")) is True


def test_vehicles_lane_opens_for_granter_and_credits_support():
    # A vehicle-GRANTER ("becomes a Vehicle … gains crew") must open the Vehicles lane,
    # and vehicle SUPPORT (cheat a Vehicle into play, mana to cast Vehicle spells) must
    # be credited — not just core "Vehicles you control / crew" text.
    rex = {
        "name": "Captain Rex Nebula",
        "type_line": "Legendary Creature — Human Pilot Employee",
        "oracle_text": (
            'At the beginning of combat on your turn, choose target nonland permanent you control. Until end of turn, it becomes a Vehicle artifact with base power and toughness each equal to its mana value, and it gains crew 2 and "Crash Land — Whenever this Vehicle deals damage, roll a six-sided die. If the result is equal to this Vehicle\'s mana value, sacrifice this Vehicle, then it deals that much damage to any target."'
        ),
    }
    assert any(
        k == "vehicles_matter"
        for k, _ in {(s.key, s.scope) for s in extract_signals(rex)}
    )
    oviya = {
        "name": "Oviya, Automech Artisan",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": "Each creature that's attacking one of your opponents has trample.\n{G}, {T}: You may put a creature or Vehicle card from your hand onto the battlefield. If you put an artifact onto the battlefield this way, put two +1/+1 counters on it.",
    }
    stablemaster = {
        "name": "Intrepid Stablemaster",
        "type_line": "Creature — Human Scout",
        "oracle_text": "Reach\n{T}: Add {G}.\n{T}: Add two mana of any one color. Spend this mana only to cast Mount or Vehicle spells.",
    }
    assert serves(oviya, _sig("vehicles_matter", "you")) is True
    assert serves(stablemaster, _sig("vehicles_matter", "you")) is True


def test_become_a_type_cards_match_the_type_lane():
    # "Become"/"are" TYPE granters belong in that type's deck: artifact-makers in
    # artifact decks, tribal type-granters in that tribe's deck.
    artifact_makers = [
        (
            "Mycosynth Lattice",
            "All permanents are artifacts in addition to their other types.",
        ),
        (
            "Liquimetal Coating",
            "{T}: Target nonland permanent becomes an artifact in addition to its other types.",
        ),
        (
            "March of the Machines",
            "Each noncreature artifact is an artifact creature with power and toughness each equal to its mana value.",
        ),
    ]
    for n, o in artifact_makers:
        card = {"name": n, "type_line": "Artifact", "oracle_text": o}
        assert serves(card, _sig("artifacts_matter", "you")) is True, n
    # Type-agnostic tribal enablers credit EVERY tribe (they grant the chosen type).
    goblin = Signal(
        key="type_matters", scope="you", subject="Goblin", text="", source="c"
    )
    tribal_enablers = [
        (
            "Xenograft",
            "As Xenograft enters, choose a creature type. Each creature you control is the chosen type in addition to its other types.",
        ),
        (
            "Arcane Adaptation",
            "As this enters, choose a creature type. Other creatures you control are the chosen type in addition to their other types.",
        ),
    ]
    for n, o in tribal_enablers:
        card = {"name": n, "type_line": "Enchantment", "oracle_text": o}
        assert serves(card, goblin) is True, n


def test_grant_become_credited_for_clone_enchantment_food():
    # DB-mined grant phrasings (search the DB, don't guess) — a clone ("as a copy of any
    # creature"), an enchantment-grant ("are enchantments in addition"), and a Food-grant
    # ("are Foods in addition") must hit their lanes (main serve or a sub-avenue).
    cases = [
        (
            "clone_matters",
            "Clone",
            "You may have Clone enter the battlefield as a copy of any creature on the battlefield.",
        ),
        (
            "enchantments_matter",
            "Enchanted Evening",
            "All permanents are enchantments in addition to their other types.",
        ),
        (
            "food_matters",
            "The Food Court",
            "Artifacts are Foods in addition to their other types.",
        ),
        (
            "domain_matters",
            "Prismatic Omen",
            "Lands you control are every basic land type in addition to their other types.",
        ),
        (
            "color_change",
            "Painter's Servant",
            "As this creature enters, choose a color. All cards that aren't on the battlefield, spells, and permanents are the chosen color.",
        ),
        (
            "color_change",
            "Indigo Faerie",
            "{U}: Target permanent becomes blue in addition to its other colors.",
        ),
    ]
    for key, name, oracle in cases:
        card = {"name": name, "type_line": "Enchantment", "oracle_text": oracle}
        assert _lane_covers(card, _sig(key, "you")) is True, key


def test_edicts_and_third_person_sac_feed_aristocrats():
    # Edict creatures ("each player sacrifices a creature" — Plaguecrafter, Fleshbag)
    # are the aristocrats sac package; the serve matched only "sacrifice a", not the
    # 3rd-person "sacrifices a".
    for key, scope in [("sacrifice_matters", "you"), ("death_matters", "any")]:
        for n, o in [
            (
                "Plaguecrafter",
                "When this enters, each player sacrifices a creature or planeswalker.",
            ),
            (
                "Fleshbag Marauder",
                "When this enters, each player sacrifices a creature.",
            ),
        ]:
            card = {"name": n, "type_line": "Creature", "oracle_text": o}
            assert _lane_covers(card, _sig(key, scope)), (key, n)


def test_pillowfort_and_tax_feed_stax():
    sig = _sig("stax_taxes", "opponents")
    for n, o in [
        (
            "Ghostly Prison",
            "Creatures can't attack you unless their controller pays {2} for each creature.",
        ),
        (
            "Smothering Tithe",
            "Whenever an opponent draws a card, that player may pay {2}. If they don't, you create a Treasure token.",
        ),
    ]:
        card = {"name": n, "type_line": "Enchantment", "oracle_text": o}
        assert _lane_covers(card, sig), n


def test_power_matters_credits_threshold_payoffs():
    # power_matters should credit the PAYOFFS that key on power thresholds (Garruk's
    # Uprising, ferocious dorks), not only the big bodies themselves.
    sig = _sig("power_matters", "you")
    for o in [
        "If you control a creature with power 4 or greater, draw a card.",
        "Ferocious — {T}: Add {G}{G}.",
    ]:
        assert (
            serves({"name": "x", "type_line": "Enchantment", "oracle_text": o}, sig)
            is True
        )


def test_being_an_artifact_or_enchantment_by_type_is_on_theme():
    # The big "floor" miss: a card is on-theme for an artifacts/enchantments deck by
    # BEING that type (affinity/metalcraft/constellation/count all count the card),
    # even with no "artifact"/"enchantment" oracle text. EDHREC synergy proves it —
    # artifact lands / rocks are disproportionately in artifact decks.
    art = _sig("artifacts_matter", "you")
    for n, tl, o in [
        ("Seat of the Synod", "Artifact Land", "{T}: Add {U}."),
        ("Mind Stone", "Artifact", "{T}: Add {C}. {1}, {T}, Sacrifice: Draw a card."),
        (
            "Solemn Simulacrum",
            "Artifact Creature — Golem",
            "When this enters, search your library for a basic land card.",
        ),
    ]:
        assert serves({"name": n, "type_line": tl, "oracle_text": o}, art) is True, n
    ench = _sig("enchantments_matter", "you")
    spirited = {
        "name": "Spirited Companion",
        "type_line": "Enchantment Creature — Dog",
        "oracle_text": "When this creature enters, draw a card.",
    }
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
    makers = [
        (
            "Cursed Courtier",
            "When this creature enters, create a Cursed Role token attached to it.",
        ),
        ("Shard Maker", "Create a Shard token."),
        (
            "Aura Token Maker",
            "Create a white Aura enchantment token with enchant creature and totem armor.",
        ),
    ]
    for n, o in makers:
        card = {"name": n, "type_line": "Enchantment", "oracle_text": o}
        assert serves(card, _sig("enchantments_matter", "you")) is True, n


def test_artifact_token_makers_are_artifacts():
    # Treasure/Food/Clue/Blood/Gold/Map/Powerstone tokens ARE artifact tokens, so a
    # maker of them makes an artifact — affinity/metalcraft/artifact-count fuel.
    makers = [
        (
            "Smothering Tithe",
            "Whenever an opponent draws a card, … create a Treasure token.",
        ),
        ("Witch's Oven", "{T}, Sacrifice a creature: Create a Food token …"),
        ("Tireless Tracker", "Whenever a land you control enters, investigate."),
        ("Powerstone Maker", "When this enters, create a tapped Powerstone token."),
    ]
    for n, o in makers:
        card = {"name": n, "type_line": "Artifact", "oracle_text": o}
        assert serves(card, _sig("artifacts_matter", "you")) is True, n


def test_theme_cost_reducers_are_credited():
    # A spell-type cost reducer is prime synergy for that theme's deck.
    etherium = {
        "name": "Etherium Sculptor",
        "type_line": "Artifact Creature — Vedalken Artificer",
        "oracle_text": "Artifact spells you cast cost {1} less to cast.",
    }
    electromancer = {
        "name": "Goblin Electromancer",
        "type_line": "Creature — Goblin Wizard",
        "oracle_text": "Instant and sorcery spells you cast cost {1} less to cast.",
    }
    assert serves(etherium, _sig("artifacts_matter", "you")) is True
    assert serves(electromancer, _sig("spellcast_matters", "you")) is True
    assert serves(electromancer, _sig("magecraft_matters", "you")) is True


def test_aristocrats_lane_surfaces_board_wipes():
    wrath = {
        "name": "Wrath of God",
        "type_line": "Sorcery",
        "oracle_text": "Destroy all creatures. They can't be regenerated.",
    }
    assert _lane_covers(wrath, _sig("death_matters", "any")) is True
    assert _lane_covers(wrath, _sig("sacrifice_matters", "you")) is True


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

LAND_CREATURE_PAYOFF = {
    "name": "Sylvan Advocate",
    "type_line": "Creature — Elf Druid Ally",
    "oracle_text": (
        "Vigilance\nAs long as you control six or more lands, this creature "
        "and land creatures you control get +2/+2."
    ),
}
PLANT_MAKER = {
    "name": "Avenger of Zendikar",
    "type_line": "Creature — Elemental",
    "oracle_text": (
        "When this creature enters, create a 0/1 green Plant creature token for each land you control.\nLandfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control."
    ),
}
CLONE = {
    "name": "Silent Hallcreeper",
    "type_line": "Enchantment Creature — Horror",
    "oracle_text": "This creature can't be blocked.\nWhenever this creature deals combat damage to a player, choose one that hasn't been chosen —\n• Put two +1/+1 counters on this creature.\n• Draw a card.\n• This creature becomes a copy of another target creature you control.",
}
MANLAND = {
    "name": "Mishra's Factory",
    "type_line": "Land",
    "oracle_text": (
        "{T}: Add {C}.\n{1}: This land becomes a 2/2 Assembly-Worker artifact creature until end of turn. It's still a land.\n{T}: Target Assembly-Worker creature gets +1/+1 until end of turn."
    ),
}
LIFE_AND_LIMB = {
    "name": "Life and Limb",
    "type_line": "Enchantment",
    "oracle_text": (
        "All Forests and all Saprolings are 1/1 green Saproling creatures and "
        "Forest lands in addition to their other types. (They're affected by "
        "summoning sickness.)"
    ),
}
EMBODIMENT_OF_INSIGHT = {
    "name": "Embodiment of Insight",
    "type_line": "Creature — Elemental",
    "power": "4",
    "toughness": "4",
    "keywords": ["Vigilance", "Landfall"],
    "oracle_text": (
        "Vigilance\nLand creatures you control have vigilance.\nLandfall — "
        "Whenever a land you control enters, you may have target land you "
        "control become a 3/3 Elemental creature with haste until end of turn. "
        "It's still a land."
    ),
}
QUIRION_RANGER = {
    "name": "Quirion Ranger",
    "type_line": "Creature — Elf Ranger",
    "power": "1",
    "toughness": "1",
    "keywords": [],
    "oracle_text": (
        "Return a Forest you control to its owner's hand: Untap target creature. "
        "Activate only once each turn."
    ),
}
SCRYB_RANGER = {
    "name": "Scryb Ranger",
    "type_line": "Creature — Faerie Ranger",
    "power": "1",
    "toughness": "1",
    "keywords": ["Flying", "Protection", "Flash"],
    "oracle_text": (
        "Flash\nFlying, protection from blue\nReturn a Forest you control to its "
        "owner's hand: Untap target creature. Activate only once each turn."
    ),
}
OBORO_BREEZECALLER = {
    "name": "Oboro Breezecaller",
    "type_line": "Creature — Moonfolk Wizard",
    "power": "1",
    "toughness": "1",
    "keywords": ["Flying"],
    "oracle_text": (
        "Flying\n{2}, Return a land you control to its owner's hand: Untap target land."
    ),
}
SEEKER_OF_SKYBREAK = {
    "name": "Seeker of Skybreak",
    "type_line": "Creature — Elf",
    "power": "2",
    "toughness": "1",
    "keywords": [],
    "oracle_text": "{T}: Untap target creature.",
}
BASILISK_COLLAR = {
    "name": "Basilisk Collar",
    "type_line": "Artifact — Equipment",
    "keywords": ["Equip"],
    "oracle_text": (
        "Equipped creature has deathtouch and lifelink. (Any amount of damage it "
        "deals to a creature is enough to destroy it. Damage dealt by this creature "
        "also causes you to gain that much life.)\nEquip {2} ({2}: Attach to target "
        "creature you control. Equip only as a sorcery.)"
    ),
}
BONESPLITTER = {
    "name": "Bonesplitter",
    "type_line": "Artifact — Equipment",
    "keywords": ["Equip"],
    "oracle_text": "Equipped creature gets +2/+0.\nEquip {1}",
}
CRUCIBLE_OF_WORLDS = {
    "name": "Crucible of Worlds",
    "type_line": "Artifact",
    "keywords": [],
    "oracle_text": "You may play lands from your graveyard.",
}
DINGUS_EGG = {
    "name": "Dingus Egg",
    "type_line": "Artifact",
    "keywords": [],
    "oracle_text": (
        "Whenever a land is put into a graveyard from the battlefield, this "
        "artifact deals 2 damage to that land's controller."
    ),
}
PRICE_OF_GLORY = {
    "name": "Price of Glory",
    "type_line": "Enchantment",
    "keywords": [],
    "oracle_text": (
        "Whenever a player taps a land for mana, if it's not that player's turn, "
        "destroy that land."
    ),
}
HAUNTED_CROSSROADS = {
    "name": "Haunted Crossroads",
    "type_line": "Enchantment",
    "keywords": [],
    "oracle_text": "{B}: Put target creature card from your graveyard on top of your library.",
}
HUA_TUO = {
    "name": "Hua Tuo, Honored Physician",
    "type_line": "Legendary Creature — Human",
    "power": "1",
    "toughness": "2",
    "keywords": [],
    "oracle_text": "{T}: Put target creature card from your graveyard on top of your library. Activate only during your turn, before attackers are declared.",
}
REANIMATE = {
    "name": "Reanimate",
    "type_line": "Sorcery",
    "keywords": [],
    "oracle_text": (
        "Put target creature card from a graveyard onto the battlefield under your "
        "control. You lose life equal to that card's mana value."
    ),
}
NAVIGATORS_COMPASS = {
    "name": "Navigator's Compass",
    "type_line": "Artifact",
    "keywords": [],
    "oracle_text": (
        "When this artifact enters, you gain 3 life.\n{T}: Until end of turn, "
        "target land you control becomes the basic land type of your choice in "
        "addition to its other types."
    ),
}
PRISMATIC_OMEN = {
    "name": "Prismatic Omen",
    "type_line": "Enchantment",
    "keywords": [],
    "oracle_text": (
        "Lands you control are every basic land type in addition to their other types."
    ),
}
REEF_SHAMAN = {
    "name": "Reef Shaman",
    "type_line": "Creature — Merfolk Shaman",
    "power": "0",
    "toughness": "2",
    "keywords": [],
    "oracle_text": "{T}: Target land becomes the basic land type of your choice until end of turn.",
}
BLOOD_MOON = {
    "name": "Blood Moon",
    "type_line": "Enchantment",
    "keywords": [],
    "oracle_text": "Nonbasic lands are Mountains.",
}
VICIOUS_SHADOWS = {
    "name": "Vicious Shadows",
    "type_line": "Enchantment",
    "keywords": [],
    "oracle_text": (
        "Whenever a creature dies, you may have this enchantment deal damage to "
        "target player equal to the number of cards in that player's hand."
    ),
}
BLOOD_ARTIST = {
    "name": "Blood Artist",
    "type_line": "Creature — Vampire",
    "power": "0",
    "toughness": "1",
    "keywords": [],
    "oracle_text": (
        "Whenever this creature or another creature dies, target player loses 1 "
        "life and you gain 1 life."
    ),
}
MURDER = {
    "name": "Murder",
    "type_line": "Instant",
    "keywords": [],
    "oracle_text": "Destroy target creature.",
}
THE_OZOLITH = {
    "name": "The Ozolith",
    "type_line": "Legendary Artifact",
    "keywords": [],
    "oracle_text": (
        "Whenever a creature you control leaves the battlefield, if it had counters "
        "on it, put those counters on The Ozolith.\nAt the beginning of combat on "
        "your turn, if The Ozolith has counters on it, you may move all counters "
        "from The Ozolith onto target creature."
    ),
}
RESOURCEFUL_DEFENSE = {
    "name": "Resourceful Defense",
    "type_line": "Enchantment",
    "keywords": [],
    "oracle_text": (
        "Whenever a permanent you control leaves the battlefield, if it had counters "
        "on it, put those counters on target permanent you control.\n{4}{W}: Move "
        "any number of counters from target permanent you control onto a second "
        "target permanent you control."
    ),
}
AETHER_SNAP = {
    "name": "Aether Snap",
    "type_line": "Sorcery",
    "keywords": [],
    "oracle_text": "Remove all counters from all permanents and exile all tokens.",
}
TAINTED_STRIKE = {
    "name": "Tainted Strike",
    "type_line": "Instant",
    "keywords": [],
    "oracle_text": (
        "Target creature gets +1/+0 and gains infect until end of turn. (It deals "
        "damage to creatures in the form of -1/-1 counters and to players in the "
        "form of poison counters.)"
    ),
}
TEMUR_BATTLE_RAGE = {
    "name": "Temur Battle Rage",
    "type_line": "Instant",
    "keywords": ["Ferocious"],
    "oracle_text": (
        "Target creature gains double strike until end of turn.\nFerocious — That "
        "creature also gains trample until end of turn if you control a creature "
        "with power 4 or greater."
    ),
}
GRAFTED_EXOSKELETON = {
    "name": "Grafted Exoskeleton",
    "type_line": "Artifact — Equipment",
    "keywords": ["Equip"],
    "oracle_text": (
        "Equipped creature gets +2/+2 and has infect. (It deals damage to creatures "
        "in the form of -1/-1 counters and to players in the form of poison "
        "counters.)\nEquip {2}"
    ),
}
BOROS_SWIFTBLADE = {
    "name": "Boros Swiftblade",
    "type_line": "Creature — Human Soldier",
    "power": "1",
    "toughness": "2",
    "keywords": ["Double strike"],
    "oracle_text": "Double strike",
}
ORNITHOPTER = {
    "name": "Ornithopter",
    "type_line": "Artifact Creature — Thopter",
    "power": "0",
    "toughness": "2",
    "cmc": 0.0,
    "keywords": ["Flying"],
    "oracle_text": "Flying",
}
AVEN_MINDCENSOR = {
    "name": "Aven Mindcensor",
    "type_line": "Creature — Bird Wizard",
    "power": "2",
    "toughness": "1",
    "cmc": 3.0,
    "keywords": ["Flying", "Flash"],
    "oracle_text": (
        "Flash\nFlying\nIf an opponent would search a library, that player searches "
        "the top four cards of that library instead."
    ),
}
ARCHON_OF_EMERIA = {
    "name": "Archon of Emeria",
    "type_line": "Creature — Archon",
    "power": "2",
    "toughness": "3",
    "cmc": 3.0,
    "keywords": ["Flying"],
    "oracle_text": (
        "Flying\nEach player can't cast more than one spell each turn.\nNonbasic "
        "lands your opponents control enter tapped."
    ),
}
LLANOWAR_ELVES = {
    "name": "Llanowar Elves",
    "type_line": "Creature — Elf Druid",
    "power": "1",
    "toughness": "1",
    "cmc": 1.0,
    "keywords": [],
    "oracle_text": "{T}: Add {G}.",
}
PUCAS_MISCHIEF = {
    "name": "Puca's Mischief",
    "type_line": "Enchantment",
    "keywords": [],
    "oracle_text": (
        "At the beginning of your upkeep, you may exchange control of target nonland "
        "permanent you control and target nonland permanent an opponent controls with "
        "equal or lesser mana value."
    ),
}
PERPLEXING_CHIMERA = {
    "name": "Perplexing Chimera",
    "type_line": "Enchantment Creature — Chimera",
    "power": "3",
    "toughness": "3",
    "keywords": [],
    "oracle_text": (
        "Whenever an opponent casts a spell, you may exchange control of this creature "
        "and that spell. If you do, you may choose new targets for the spell. (If the "
        "spell becomes a permanent, you control that permanent.)"
    ),
}
SPAWNBROKER = {
    "name": "Spawnbroker",
    "type_line": "Creature — Human Wizard",
    "power": "1",
    "toughness": "1",
    "keywords": [],
    "oracle_text": (
        "When this creature enters, you may exchange control of target creature you "
        "control and target creature with power less than or equal to that creature's "
        "power an opponent controls."
    ),
}
SOWER_OF_TEMPTATION = {
    "name": "Sower of Temptation",
    "type_line": "Creature — Faerie Wizard",
    "power": "2",
    "toughness": "2",
    "keywords": ["Flying"],
    "oracle_text": (
        "Flying\nWhen this creature enters, gain control of target creature for as "
        "long as this creature remains on the battlefield."
    ),
}
ROIL_ELEMENTAL = {
    "name": "Roil Elemental",
    "type_line": "Creature — Elemental",
    "power": "3",
    "toughness": "2",
    "keywords": ["Landfall", "Flying"],
    "oracle_text": (
        "Flying\nLandfall — Whenever a land you control enters, you may gain control "
        "of target creature for as long as you control this creature."
    ),
}
EMPRESS_GALINA = {
    "name": "Empress Galina",
    "type_line": "Legendary Creature — Merfolk Noble",
    "power": "1",
    "toughness": "3",
    "keywords": [],
    "oracle_text": (
        "{U}{U}, {T}: Gain control of target legendary permanent. (This effect lasts "
        "indefinitely.)"
    ),
}
ACT_OF_TREASON = {
    "name": "Act of Treason",
    "type_line": "Sorcery",
    "keywords": [],
    "oracle_text": (
        "Gain control of target creature until end of turn. Untap that creature. It "
        "gains haste until end of turn. (It can attack and {T} this turn.)"
    ),
}


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
    lord = {
        "oracle_text": "Other Goblins you control get +1/+1.",
        "type_line": "Creature — Goblin",
    }
    off = {"oracle_text": "Draw a card.", "type_line": "Sorcery"}
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
    from mtg_utils._deck_forge.signals import producible_static_keys

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
    from mtg_utils._deck_forge.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("land_creatures_matter", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(MANLAND)  # a real creature-land is surfaced by some avenue
    assert not served(PLANT_MAKER)  # Avenger's Plant tokens — surfaced by none
    assert not served(CLONE)  # Silent Hallcreeper clone — surfaced by none


def test_animate_lands_serve_covers_mass_forest_animators():
    """Yedora's payoff: she makes Forest lands, then 'animate your lands' effects
    turn them into a creature army. Life and Limb animates ALL Forests at once
    ('All Forests ... are 1/1 ... creatures'), so the Animate-your-lands
    sub-avenue must reach it, not only the 'lands you control become' phrasing."""
    from mtg_utils._deck_forge.ranking import score_candidate

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
    from mtg_utils._deck_forge.ranking import score_candidate

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
    from mtg_utils._deck_forge.ranking import score_candidate

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
    from mtg_utils._deck_forge.ranking import score_candidate

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
    from mtg_utils._deck_forge.ranking import score_candidate

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
    from mtg_utils._deck_forge.ranking import score_candidate

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
        rhystic = {
            "name": "Rhystic Study",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever an opponent casts a spell, you may draw a card unless that "
                "player pays {1}."
            ),
        }
        assert serves(rhystic, self.SLINGER) is False

    def test_opponent_cast_drawer_does_not_serve(self):
        # Esper Sentinel: "opponent casts … noncreature spell" — the "you cast" gate
        # must reject it (it's an opponents-cast payoff, not a spellslinger enabler).
        esper = {
            "name": "Esper Sentinel",
            "type_line": "Artifact Creature — Human Soldier",
            "oracle_text": (
                "Whenever an opponent casts their first noncreature spell each turn, "
                "draw a card unless that player pays {X}, where X is this creature's "
                "power."
            ),
            "keywords": [],
        }
        assert serves(esper, self.SLINGER) is False

    def test_equipment_that_draws_does_not_serve(self):
        sword = {
            "name": "Sword of Fire and Ice",
            "type_line": "Artifact — Equipment",
            "oracle_text": (
                "Equipped creature gets +2/+2 and has protection from red and from blue.\nWhenever equipped creature deals combat damage to a player, this Equipment deals 2 damage to any target and you draw a card.\nEquip {2}"
            ),
            "keywords": ["Equip"],
        }
        assert serves(sword, self.SLINGER) is False

    def test_coinflip_value_creature_does_not_serve(self):
        # Zndrsplt: draws on a won coin flip, never on YOUR cast — the canonical FP.
        zndrsplt = {
            "name": "Zndrsplt, Eye of Wisdom",
            "type_line": "Legendary Creature — Homunculus",
            "oracle_text": (
                "Partner with Okaun, Eye of Chaos (When this creature enters, target player may put Okaun into their hand from their library, then shuffle.)\nAt the beginning of combat on your turn, flip a coin until you lose a flip.\nWhenever a player wins a coin flip, draw a card."
            ),
            "keywords": ["Partner"],
        }
        assert serves(zndrsplt, self.SLINGER) is False

    def test_instant_cantrip_serves(self):
        opt = {
            "name": "Opt",
            "type_line": "Instant",
            "oracle_text": "Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nDraw a card.",
        }
        assert serves(opt, self.SLINGER) is True

    def test_prowess_creature_serves_via_keyword(self):
        swiftspear = {
            "name": "Monastery Swiftspear",
            "type_line": "Creature — Human Monk",
            "oracle_text": "Haste\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)",
            "keywords": ["Prowess", "Haste"],
        }
        assert serves(swiftspear, self.SLINGER) is True

    def test_cast_trigger_payoff_serves_via_oracle(self):
        # Young Pyromancer: a payoff with NO prowess keyword and not itself an
        # instant/sorcery — caught by the "whenever you cast an instant or sorcery"
        # oracle branch.
        pyromancer = {
            "name": "Young Pyromancer",
            "type_line": "Creature — Human Shaman",
            "oracle_text": (
                "Whenever you cast an instant or sorcery spell, create a 1/1 red "
                "Elemental creature token."
            ),
            "keywords": [],
        }
        assert serves(pyromancer, self.SLINGER) is True

    def test_magecraft_payoff_serves_via_oracle(self):
        storm_kiln = {
            "name": "Storm-Kiln Artist",
            "type_line": "Creature — Dwarf Shaman",
            "oracle_text": (
                'This creature gets +1/+0 for each artifact you control.\nMagecraft — Whenever you cast or copy an instant or sorcery spell, create a Treasure token. (It\'s an artifact with "{T}, Sacrifice this token: Add one mana of any color.")'
            ),
            "keywords": ["Treasure", "Magecraft"],
        }
        assert serves(storm_kiln, self.SLINGER) is True

    def test_avenue_classifies_by_structured_serve_not_draw(self):
        """The avenue-credit path (ranking._avenue_matchers) must apply the SAME
        precise predicate the spec serves on — so exploring the Spellslinger avenue
        credits a real cantrip (matched by TYPE, whose oracle says only 'draw a card')
        and a prowess creature (matched by KEYWORD), but NOT a value permanent."""
        from mtg_utils._deck_forge.ranking import score_candidate

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

        opt = {
            "name": "Opt",
            "type_line": "Instant",
            "oracle_text": "Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nDraw a card.",
        }
        swiftspear = {
            "name": "Monastery Swiftspear",
            "type_line": "Creature — Human Monk",
            "oracle_text": "Haste\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)",
            "keywords": ["Prowess"],
        }
        rhystic = {
            "name": "Rhystic Study",
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
        }
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
        boseiju = {
            "name": "Boseiju, Who Shelters All",
            "type_line": "Legendary Land",
            "oracle_text": (
                "Boseiju enters tapped.\n{T}, Pay 2 life: Add {C}. If that mana is "
                "spent on an instant or sorcery spell, that spell can't be countered."
            ),
            "keywords": [],
        }
        assert serves(boseiju, self.MAGE) is False

    def test_cast_trigger_payoff_serves(self):
        murmuring = {
            "name": "Murmuring Mystic",
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "Whenever you cast an instant or sorcery spell, create a 1/1 blue Bird "
                "Illusion creature token with flying."
            ),
            "keywords": [],
        }
        assert serves(murmuring, self.MAGE) is True

    def test_instant_serves_by_type(self):
        opt = {
            "name": "Opt",
            "type_line": "Instant",
            "oracle_text": "Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nDraw a card.",
        }
        assert serves(opt, self.MAGE) is True

    def test_avenue_does_not_credit_value_permanent(self):
        from mtg_utils._deck_forge.ranking import score_candidate

        spec = spec_for(self.MAGE)
        avenue = engine_avenue(spec)
        rhystic = {
            "name": "Rhystic Study",
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
        }
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
        from mtg_utils._deck_forge.ranking import score_candidate

        spec = spec_for(self.SIG)
        avenue = engine_avenue(spec)
        rhystic = {
            "name": "Rhystic Study",
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
        }
        served = set(
            score_candidate(rhystic, active_signals=[], avenues=[avenue])["served"]
        )
        assert spec.label not in served

    def test_serve_matches_a_real_second_spell_payoff(self):
        payoff = {
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "Whenever you cast your second spell each turn, draw a card."
            ),
        }
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
        phyrexian_arena = {
            "type_line": "Enchantment",
            "oracle_text": "At the beginning of your upkeep, you draw a card and you lose 1 life.",
        }
        blue_suns = {
            "type_line": "Instant",
            "oracle_text": "Draw X cards. Put Blue Sun's Zenith into its owner's library third from the top.",
        }
        remand = {
            "type_line": "Instant",
            "oracle_text": "Counter target spell. If that spell is countered this way, put it into its owner's hand instead. Draw a card.",
        }
        solemn = {
            "type_line": "Artifact Creature — Golem",
            "oracle_text": "When this creature dies, you may draw a card.",
        }
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
        soul_warden = {
            "type_line": "Creature — Human Cleric",
            "oracle_text": "Whenever another creature enters, you gain 1 life.",
            "keywords": [],
        }
        baneslayer = {
            "type_line": "Creature — Angel",
            "oracle_text": "Flying, first strike, lifelink, protection from Demons and from Dragons",
            "keywords": ["Flying", "First strike", "Lifelink"],
        }
        whip = {
            "type_line": "Legendary Enchantment Artifact",
            "oracle_text": "Creatures you control have lifelink.",
            "keywords": [],
        }
        crystalline_giant = {
            "type_line": "Artifact Creature — Giant",
            "oracle_text": (
                "At the beginning of combat on your turn, choose a kind of counter at "
                "random that this creature doesn't have on it from among flying, first "
                "strike, deathtouch, hexproof, lifelink, menace, reach, trample, and "
                "vigilance, then put a counter of that kind on this creature."
            ),
            "keywords": [],
        }
        assert serves(soul_warden, sig) is True  # gains life
        assert serves(baneslayer, sig) is True  # lifelink keyword
        assert serves(whip, sig) is True  # grants lifelink to the team
        assert serves(crystalline_giant, sig) is False  # bare word in a counter list

    def test_dash_avenue_keys_on_equipment_type_and_dash_keyword(self):
        """dash_matters' serve had `whenever[^.]*attacks` and a bare `\\bequipment\\b`
        that matched any creature mentioning equipment/attacks (~1104). The avenue is
        Equipment-for-a-dasher: gate on the Equipment TYPE and the dash KEYWORD."""
        sig = _sig("dash_matters", "you")
        skullclamp = {
            "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature gets +1/-1.\nWhenever equipped creature dies, draw two cards.\nEquip {1}",
            "keywords": ["Equip"],
        }
        mangara = {
            "type_line": "Legendary Creature — Human Cleric",
            "oracle_text": "Lifelink\nWhenever an opponent attacks with creatures, draw a card.",
            "keywords": ["Lifelink"],
        }
        elder_gargaroth = {
            "type_line": "Creature — Beast",
            "oracle_text": "Vigilance, reach, trample\nWhenever this creature attacks or blocks, choose one.",
            "keywords": ["Vigilance", "Reach", "Trample"],
        }
        assert serves(skullclamp, sig) is True  # Equipment type
        assert serves(mangara, sig) is False  # not equipment, no dash
        assert serves(elder_gargaroth, sig) is False  # "attacks" no longer triggers

    def test_creature_etb_opponents_matches_punisher_not_bloodthirst(self):
        """creature_etb/opponents' serve `opponent.*creature.*enters` required
        opponent BEFORE creature, so it matched Bloodthirst ('an opponent was dealt
        damage … this creature enters') and MISSED the real punisher ('a creature an
        opponent controls enters'). A near-total inversion."""
        sig = _sig("creature_etb", "opponents")
        suture_priest = {
            "type_line": "Creature — Phyrexian Cleric",
            "oracle_text": (
                "Whenever another creature you control enters, you may gain 1 life.\n"
                "Whenever a creature an opponent controls enters, you may have that "
                "player lose 1 life."
            ),
        }
        authority = {
            "type_line": "Enchantment",
            "oracle_text": (
                "Creatures your opponents control enter tapped.\nWhenever a creature "
                "an opponent controls enters, you gain 1 life."
            ),
        }
        bloodthirst = {
            "type_line": "Creature — Vampire Warrior",
            "oracle_text": (
                "Bloodthirst 2 (If an opponent was dealt damage this turn, this "
                "creature enters with two +1/+1 counters on it.)"
            ),
        }
        assert serves(suture_priest, sig) is True
        assert serves(authority, sig) is True
        assert serves(bloodthirst, sig) is False

    def test_drain_avenue_serves_blood_artist(self):
        """lifeloss_matters/opponents (the 'Drain' avenue) required the literal word
        'opponent' next to 'loses', so it MISSED the keystone aristocrats drains that
        read 'target player loses N life' (Blood Artist, Zulaport Cutthroat)."""
        sig = _sig("lifeloss_matters", "opponents")
        blood_artist = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.",
        }
        zulaport = {
            "type_line": "Creature — Human Cleric",
            "oracle_text": "Whenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life.",
        }
        assert serves(blood_artist, sig) is True
        assert serves(zulaport, sig) is True


class TestStructuredServeFixes2:
    """Second batch of audit-driven precision fixes (all SPECS-level serve)."""

    def test_aristocrats_serve_requires_creature_token_not_treasure(self):
        """sacrifice/death serves keyed on `create .*token`, which is type-blind: it
        served every Treasure/Clue/Food maker (~428 in WBR). Require the literal
        'creature token' so only real sacrifice fodder qualifies."""
        sac = _sig("sacrifice_matters", "you")
        death = _sig("death_matters", "any")
        bitterblossom = {
            "type_line": "Kindred Enchantment — Faerie",
            "oracle_text": "At the beginning of your upkeep, you lose 1 life and create a 1/1 black Faerie Rogue creature token with flying.",
        }
        viscera_seer = {
            "type_line": "Creature — Vampire Wizard",
            "oracle_text": "Sacrifice a creature: Scry 1.",
        }
        blood_artist = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.",
        }
        smothering_tithe = {
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent draws a card, that player may pay {2}. If the player doesn't, you create a Treasure token.",
        }
        tireless_tracker = {
            "type_line": "Creature — Human Scout",
            "oracle_text": "Whenever a land you control enters, investigate. Create a Clue token.",
        }
        assert serves(bitterblossom, sac) is True  # makes creature-token fodder
        assert serves(viscera_seer, sac) is True  # sac outlet
        assert serves(blood_artist, death) is True  # dies trigger
        assert serves(smothering_tithe, sac) is False  # Treasure, not creature token
        assert serves(smothering_tithe, death) is False
        assert serves(tireless_tracker, death) is False  # Clue, not creature token

    def test_landfall_serve_is_land_anchored(self):
        """landfall's bare `onto the battlefield` branch matched any cheat-into-play /
        reanimation. Anchor it to 'land card … onto the battlefield'."""
        sig = _sig("landfall", "you")
        cultivate = {
            "type_line": "Sorcery",
            "oracle_text": "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
        }
        azusa = {
            "type_line": "Legendary Creature — Human Monk",
            "oracle_text": "You may play two additional lands on each of your turns.",
        }
        sneak_attack = {
            "type_line": "Enchantment",
            "oracle_text": "{R}: You may put a creature card from your hand onto the battlefield. That creature gains haste. Sacrifice the creature at the beginning of the next end step.",
        }
        reanimate = {
            "type_line": "Sorcery",
            "oracle_text": "Put target creature card from a graveyard onto the battlefield under your control. You lose life equal to that card's mana value.",
        }
        assert serves(cultivate, sig) is True
        assert serves(azusa, sig) is True
        assert serves(sneak_attack, sig) is False
        assert serves(reanimate, sig) is False

    def test_stax_serve_requires_restriction_not_bare_your_opponents(self):
        """stax/opponents had a bare `your opponents` alternative that matched any card
        naming opponents (Edric's draw trigger, Telepathy's hand reveal). Serve the
        actual tax/restriction shapes; this also recovers symmetric taxes (Thalia)."""
        sig = _sig("stax_taxes", "opponents")
        drannith = {
            "type_line": "Creature — Human Wizard",
            "oracle_text": "Your opponents can't cast spells from anywhere other than their hands.",
        }
        thalia = {
            "type_line": "Legendary Creature — Human Soldier",
            "oracle_text": "First strike\nNoncreature spells cost {1} more to cast.",
        }
        edric = {
            "type_line": "Legendary Creature — Elf Advisor",
            "oracle_text": "Whenever a creature deals combat damage to one of your opponents, its controller may draw a card.",
        }
        telepathy = {
            "type_line": "Enchantment",
            "oracle_text": "Your opponents play with their hands revealed.",
        }
        assert serves(drannith, sig) is True  # opponents can't
        assert serves(thalia, sig) is True  # noncreature cost more
        assert serves(edric, sig) is False  # names opponents, but is a draw payoff
        assert serves(telepathy, sig) is False  # names opponents, but is hand reveal

    def test_evasion_self_excludes_menace_reminder(self):
        """evasion_self's bare `can't be blocked` matched the menace/flying REMINDER
        text 'can't be blocked except by …'. Exclude the 'except' form; keep true
        unblockable and landwalk."""
        sig = _sig("evasion_self", "you")
        invisible_stalker = {
            "type_line": "Creature — Human Rogue",
            "oracle_text": "Hexproof (This creature can't be the target of spells or abilities your opponents control.)\nThis creature can't be blocked.",
            "keywords": ["Hexproof"],
        }
        sengir = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Flying (This creature can't be blocked except by creatures with flying or reach.)\nWhenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature.",
            "keywords": ["Flying"],
        }
        assert serves(invisible_stalker, sig) is True
        assert serves(sengir, sig) is False


class TestStructuredServeFixes3:
    """Combat-damage connect avenues: drop the bare `\\bmenace\\b` word (matched every
    menace creature + reminder text) and the `can't be blocked` reminder form. Serve
    the payoff trigger + true-unblockable enablers, not every vanilla evasive body."""

    def test_combat_damage_opponents_drops_bare_menace(self):
        sig = _sig("combat_damage_matters", "opponents")
        edric = {
            "type_line": "Legendary Creature — Elf Advisor",
            "oracle_text": "Whenever a creature deals combat damage to one of your opponents, its controller may draw a card.",
            "keywords": [],
        }
        coastal_piracy = {
            "type_line": "Enchantment",
            "oracle_text": "Whenever a creature you control deals combat damage to an opponent, you may draw a card.",
            "keywords": [],
        }
        invisible_stalker = {
            "type_line": "Creature — Human Rogue",
            "oracle_text": "Hexproof\nThis creature can't be blocked.",
            "keywords": ["Hexproof"],
        }
        vanilla_menace = {
            "type_line": "Creature — Orc Warrior",
            "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)",
            "keywords": ["Menace"],
        }
        sengir = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Flying (This creature can't be blocked except by creatures with flying or reach.)",
            "keywords": ["Flying"],
        }
        assert serves(edric, sig) is True  # payoff trigger
        assert serves(coastal_piracy, sig) is True  # payoff trigger
        assert serves(invisible_stalker, sig) is True  # true unblockable enabler
        assert serves(vanilla_menace, sig) is False  # bare menace word/reminder
        assert serves(sengir, sig) is False  # vanilla flier, reminder "except"

    def test_damage_to_opp_drops_bare_menace(self):
        sig = _sig("damage_to_opp_matters", "opponents")
        niv = {
            "type_line": "Legendary Creature — Dragon Avatar",
            "oracle_text": "Flying\nWhenever a source you control deals noncombat damage to an opponent, you draw that many cards.",
            "keywords": ["Flying"],
        }
        vanilla_menace = {
            "type_line": "Creature — Orc Warrior",
            "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)",
            "keywords": ["Menace"],
        }
        assert serves(niv, sig) is True  # noncombat-damage-to-opponent payoff
        assert serves(vanilla_menace, sig) is False


class TestSweepDetectorFixes:
    """Mined sweep-detector regexes whose open-ended alternations over-fire."""

    def test_self_counter_grow_is_self_only_not_distribution(self):
        """The `put … +1/+1 counter on [A-Z][a-z]+` branch matched any capitalized
        word after 'on' — so distributors (counter on target Knight / on target
        creature for each Elf) read as SELF-growth (~1072 FP). Self-growth only."""
        sig = _sig("self_counter_grow", "you")
        walking_ballista = {
            "type_line": "Artifact Creature — Construct",
            "oracle_text": "This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.",
        }
        venerable_knight = {
            "type_line": "Creature — Human Knight",
            "oracle_text": "When this creature dies, put a +1/+1 counter on target Knight you control.",
        }
        immaculate = {
            "type_line": "Creature — Elf Shaman",
            "oracle_text": "{T}: Put a +1/+1 counter on target creature for each Elf you control.",
        }
        assert serves(walking_ballista, sig) is True
        assert serves(venerable_knight, sig) is False
        assert serves(immaculate, sig) is False

    def test_facedown_requires_morph_vocab_not_bare_face_down(self):
        """The bare `face-down|face down` and `is turned face up` branches matched
        impulse/hideaway exile ('exile one face down'). Require the morph/manifest
        vocabulary or the 'face-down creature(s)' payoff noun (~212 FP)."""
        sig = _sig("facedown_matters", "you")
        secret_plans = {
            "type_line": "Enchantment",
            "oracle_text": "Face-down creatures you control get +0/+1.\nWhenever a permanent you control is turned face up, draw a card.",
        }
        morph_creature = {
            "type_line": "Creature — Beast",
            "oracle_text": "Morph {2}{G} (You may cast this card face down as a 2/2 creature for {3}.)",
            "keywords": ["Morph"],
        }
        gonti = {
            "type_line": "Legendary Creature — Aetherborn Rogue",
            "oracle_text": "Deathtouch\nWhen Gonti enters, look at the top four cards of target opponent's library, exile one of them face down, then put the rest on the bottom.",
            "keywords": ["Deathtouch"],
        }
        spinerock = {
            "type_line": "Land",
            "oracle_text": "Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom.)",
            "keywords": ["Hideaway"],
        }
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
        karn = {
            "type_line": "Legendary Planeswalker — Karn",
            "oracle_text": "...",
            "keywords": [],
        }
        atraxa = {
            "type_line": "Legendary Creature — Phyrexian Angel Horror",
            "oracle_text": "Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate.",
            "keywords": [
                "Flying",
                "Vigilance",
                "Deathtouch",
                "Lifelink",
                "Proliferate",
            ],
        }
        bolt = {
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "keywords": [],
        }
        assert serves(karn, sig) is True  # planeswalker type
        assert serves(atraxa, sig) is True  # proliferate keyword
        assert serves(bolt, sig) is False

    def test_modified_serves_equipment_auras_and_counters(self):
        sig = _sig("modified_matters", "you")
        glitters = {
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nEnchanted creature gets +1/+1 for each artifact and enchantment you control.",
        }
        hardened_scales = {
            "type_line": "Enchantment",
            "oracle_text": "If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.",
        }
        equipment = {
            "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature gets +1/+1.\nEquip {1}",
            "keywords": ["Equip"],
        }
        sol_ring = {"type_line": "Artifact", "oracle_text": "{T}: Add {C}{C}."}
        assert serves(glitters, sig) is True  # Aura type
        assert serves(equipment, sig) is True  # Equipment type
        assert serves(hardened_scales, sig) is True  # +1/+1 counter oracle
        assert serves(sol_ring, sig) is False

    def test_voltron_serves_buff_auras_but_not_control_auras(self):
        sig = _sig("voltron_matters", "you")
        skullclamp = {
            "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature gets +1/-1.\nEquip {1}",
            "keywords": ["Equip"],
        }
        flight = {
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nEnchanted creature has flying.",
        }
        pacifism = {
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nEnchanted creature can't attack or block.",
        }
        sol_ring = {"type_line": "Artifact", "oracle_text": "{T}: Add {C}{C}."}
        assert serves(skullclamp, sig) is True  # Equipment
        assert serves(flight, sig) is True  # buff Aura
        assert serves(pacifism, sig) is False  # control Aura — vetoed
        assert serves(sol_ring, sig) is False

    def test_devotion_serves_heavy_pip_permanents_via_structured_pips(self):
        sig = _sig("devotion_matters", "you")
        gray_merchant = {
            "type_line": "Creature — Zombie",
            "mana_cost": "{3}{B}{B}",
            "cmc": 5.0,
            "oracle_text": "When this creature enters, each opponent loses life equal to your devotion to black.",
        }
        heavy_pip_vanilla = {
            "type_line": "Creature — Elemental",
            "mana_cost": "{2}{R}{R}",
            "cmc": 4.0,
            "oracle_text": "Trample",
        }
        llanowar = {
            "type_line": "Creature — Elf Druid",
            "mana_cost": "{G}",
            "cmc": 1.0,
            "oracle_text": "{T}: Add {G}.",
        }
        bolt = {
            "type_line": "Instant",
            "mana_cost": "{R}",
            "cmc": 1.0,
            "oracle_text": "deals 3 damage to any target.",
        }
        sol_ring = {
            "type_line": "Artifact",
            "mana_cost": "{1}",
            "cmc": 1.0,
            "oracle_text": "{T}: Add {C}{C}.",
        }
        assert serves(gray_merchant, sig) is True  # devotion oracle + 2 black pips
        assert serves(heavy_pip_vanilla, sig) is True  # 2 red pips, a permanent
        assert serves(llanowar, sig) is False  # only 1 pip
        assert serves(bolt, sig) is False  # 2 pips but an instant (not a permanent)
        assert serves(sol_ring, sig) is False  # colorless

    def test_cost_reduction_serves_x_spells_and_expensive_bombs(self):
        sig = _sig("cost_reduction", "you")
        torment = {
            "type_line": "Sorcery",
            "mana_cost": "{X}{B}{B}",
            "cmc": 2.0,
            "oracle_text": "Each opponent loses life and discards a card for each {X}.",
        }
        emrakul = {
            "type_line": "Legendary Creature — Eldrazi",
            "mana_cost": "{15}",
            "cmc": 15.0,
            "oracle_text": "...",
        }
        disdainful = {
            "type_line": "Instant",
            "mana_cost": "{1}{U}",
            "cmc": 2.0,
            "oracle_text": "Counter target spell with mana value 4 or greater.",
        }
        sun_titan = {
            "type_line": "Creature — Giant",
            "mana_cost": "{4}{W}{W}",
            "cmc": 6.0,
            "oracle_text": "...",
        }
        assert serves(torment, sig) is True  # X spell
        assert serves(emrakul, sig) is True  # expensive bomb (cmc>=7)
        assert serves(disdainful, sig) is False  # "mana value 4" no longer matches
        assert serves(sun_titan, sig) is False  # cmc 6 below the bomb threshold

    def test_removal_serves_burn_to_any_target(self):
        sig = _sig("removal_matters", "you")
        bolt = {
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        }
        murder = {"type_line": "Instant", "oracle_text": "Destroy target creature."}
        sol_ring = {"type_line": "Artifact", "oracle_text": "{T}: Add {C}{C}."}
        assert serves(bolt, sig) is True  # damage to any target
        assert serves(murder, sig) is True
        assert serves(sol_ring, sig) is False

    def test_counter_control_extraction_allows_adjective_gap(self):
        from mtg_utils._deck_forge.signals import extract_signals

        essence_scatter = {
            "name": "Essence Scatter",
            "type_line": "Instant",
            "oracle_text": "Counter target creature spell.",
        }
        keys = {s.key for s in extract_signals(essence_scatter)}
        assert "counter_control" in keys


class TestStructuredServeFixes4:
    """Batch 4: remaining HIGH precision fixes."""

    def test_mana_amplifier_drops_fixing_keeps_doublers(self):
        """`add .* mana of any` captured fixing (Birds, City of Brass), not
        amplification. Serve the doublers/triplers ('tap … for mana … add/produces
        twice') + X-spell payoffs."""
        sig = _sig("mana_amplifier", "you")
        mirari = {
            "type_line": "Enchantment",
            "oracle_text": "Creatures you control get +1/+1.\nWhenever you tap a land for mana, add one mana of any type that land produced.",
        }
        reflection = {
            "type_line": "Enchantment",
            "oracle_text": "If you tap a permanent for mana, it produces twice as much of that mana instead.",
        }
        birds = {
            "type_line": "Creature — Bird",
            "oracle_text": "Flying\n{T}: Add one mana of any color.",
            "keywords": ["Flying"],
        }
        signet = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Add one mana of any color.",
        }
        assert serves(mirari, sig) is True
        assert serves(reflection, sig) is True
        assert serves(birds, sig) is False
        assert serves(signet, sig) is False

    def test_attack_serves_haste_keyword_and_grants_not_bare_word(self):
        sig = _sig("attack_matters", "you")
        fervor = {
            "type_line": "Enchantment",
            "oracle_text": "Creatures you control have haste.",
            "keywords": [],
        }
        haste_beater = {
            "type_line": "Creature — Goblin",
            "oracle_text": "Haste",
            "keywords": ["Haste"],
        }
        krenko = {
            "type_line": "Legendary Creature — Goblin",
            "oracle_text": "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
            "keywords": [],
        }
        loses_haste = {
            "type_line": "Instant",
            "oracle_text": "Target creature loses haste until end of turn.",
            "keywords": [],
        }
        sol_ring = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}{C}.",
            "keywords": [],
        }
        assert serves(fervor, sig) is True  # grants haste to team
        assert serves(haste_beater, sig) is True  # Haste keyword
        assert serves(krenko, sig) is True  # creature-token maker
        assert serves(loses_haste, sig) is False  # bare word "haste" (removes it)
        assert serves(sol_ring, sig) is False

    def test_play_from_top_drops_bare_reveal(self):
        """`reveal the top card of your library` is a peek (Coiling Oracle), not
        play-from-top. Keep the play/cast-from-top forms."""
        sig = _sig("play_from_top", "you")
        future_sight = {
            "type_line": "Enchantment",
            "oracle_text": "Play with the top card of your library revealed.\nYou may play lands and cast spells from the top of your library.",
        }
        coiling_oracle = {
            "type_line": "Creature — Snake Elf",
            "oracle_text": "When this creature enters, reveal the top card of your library. If it's a land card, put it onto the battlefield.",
        }
        assert serves(future_sight, sig) is True
        assert serves(coiling_oracle, sig) is False

    def test_pump_matters_drops_minus_bonuses(self):
        """pump's `[+\\-]` matched -X/-X shrink (that's debuff_matters). Positive only."""
        sig = _sig("pump_matters", "you")
        giant_growth = {
            "type_line": "Instant",
            "oracle_text": "Target creature gets +3/+3 until end of turn.",
        }
        festering_goblin = {
            "type_line": "Creature — Zombie Goblin",
            "oracle_text": "When this creature dies, target creature gets -1/-1 until end of turn.",
        }
        assert serves(giant_growth, sig) is True
        assert serves(festering_goblin, sig) is False

    def test_crimes_avenue_excludes_counterspells(self):
        """crimes SEARCH `target.*spell` credited every counterspell. Drop it."""
        from mtg_utils._deck_forge.ranking import score_candidate

        spec = spec_for(_sig("crimes_matter", "you"))
        avenue = {"label": spec.label, "search": dict(spec.search)}
        counterspell = {"type_line": "Instant", "oracle_text": "Counter target spell."}
        murder = {"type_line": "Instant", "oracle_text": "Destroy target creature."}
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
                {
                    "name": "Sol Ring",
                    "type_line": "Artifact",
                    "oracle_text": "{T}: Add {C}{C}.",
                },
                {
                    "name": "The Eldest Reborn",
                    "type_line": "Enchantment — Saga",
                    "oracle_text": "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Each opponent sacrifices a creature or planeswalker of their choice.\nII — Each opponent discards a card.\nIII — Put target creature or planeswalker card from a graveyard onto the battlefield under your control.",
                },
                {
                    "name": "Urza, Lord High Artificer",
                    "type_line": "Legendary Creature — Human Artificer",
                    "oracle_text": 'When Urza enters, create a 0/0 colorless Construct artifact creature token with "This token gets +1/+1 for each artifact you control."\nTap an untapped artifact you control: Add {U}.\n{5}: Shuffle your library, then exile the top card. Until end of turn, you may play that card without paying its mana cost.',
                },
            ],
            [
                {
                    "name": "Llanowar Elves",
                    "type_line": "Creature — Elf Druid",
                    "oracle_text": "{T}: Add {G}.",
                }
            ],
        )

    def test_legends_serves_legendary_type(self):
        self._ck(
            "legends_matter",
            "you",
            [
                {
                    "name": "Jodah",
                    "type_line": "Legendary Creature — Human Wizard",
                    "oracle_text": "...",
                }
            ],
            [
                {
                    "name": "Island",
                    "type_line": "Basic Land — Island",
                    "oracle_text": "({T}: Add {U}.)",
                }
            ],
        )

    def test_party_serves_party_classes_not_bare_word(self):
        self._ck(
            "party_matters",
            "you",
            [
                {
                    "name": "Archpriest",
                    "type_line": "Creature — Human Cleric",
                    "oracle_text": "...",
                },
                {
                    "name": "Tazri",
                    "type_line": "Legendary Creature — Human Warrior",
                    "oracle_text": "Your party...",
                },
            ],
            [
                {
                    "name": "Tavern",
                    "type_line": "Sorcery",
                    "oracle_text": "You meet in a tavern. The party gathers.",
                }
            ],
        )

    def test_ramp_serves_via_produced_mana(self):
        self._ck(
            "ramp_matters",
            "you",
            [
                {
                    "name": "Birds",
                    "type_line": "Creature — Bird",
                    "oracle_text": "Flying\n{T}: Add one mana of any color.",
                    "produced_mana": ["W", "U", "B", "R", "G"],
                },
                {
                    "name": "Sol Ring",
                    "type_line": "Artifact",
                    "oracle_text": "{T}: Add {C}{C}.",
                    "produced_mana": ["C"],
                },
                {
                    "name": "Cultivate",
                    "type_line": "Sorcery",
                    "oracle_text": "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
                },
            ],
            [
                {
                    "name": "Bolt",
                    "type_line": "Instant",
                    "oracle_text": "deals 3 damage to any target.",
                }
            ],
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
                {
                    "name": "Bowmasters",
                    "type_line": "Creature — Orc Archer",
                    "oracle_text": "Whenever an opponent draws a card except the first one they draw in each of their draw steps, this creature deals 1 damage to any target.",
                },
                {
                    "name": "Master of the Feast",
                    "type_line": "Enchantment Creature — Demon",
                    "oracle_text": "Flying\nAt the beginning of your upkeep, each opponent draws a card.",
                },
                {
                    # "target player draws" is DUAL-USE — point it at an opponent to
                    # punish (or at yourself to draw), so it belongs to the punish lane.
                    "name": "Prosperity-like",
                    "type_line": "Sorcery",
                    "oracle_text": "Target player draws two cards.",
                },
            ],
            [
                {
                    # A pure self-cantrip has no target choice — it can only help you.
                    "name": "Cantrip",
                    "type_line": "Instant",
                    "oracle_text": "You draw a card.",
                }
            ],
        )

    def test_tokens_matter_anchors_token_enters(self):
        self._ck(
            "tokens_matter",
            "you",
            [
                {
                    "name": "Cathars Crusade",
                    "type_line": "Enchantment",
                    "oracle_text": "Whenever a creature you control enters, put a +1/+1 counter on each creature you control.\nTokens you control...",
                }
            ],
            [
                {
                    "name": "Darksteel Splicer",
                    "type_line": "Creature — Phyrexian Artificer",
                    "oracle_text": "Whenever this creature or another nontoken Phyrexian you control enters, create X 3/3 colorless Phyrexian Golem artifact creature tokens, where X is the number of opponents you have.\nGolems you control have indestructible.",
                }
            ],
        )

    def test_exile_removal_excludes_blink(self):
        self._ck(
            "exile_removal",
            "you",
            [
                {
                    "name": "Swords",
                    "type_line": "Instant",
                    "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
                }
            ],
            [
                {
                    "name": "Ephemerate",
                    "type_line": "Instant",
                    "oracle_text": "Exile target creature you control, then return it to the battlefield under its owner's control.\nRebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you may cast this card from exile without paying its mana cost.)",
                }
            ],
        )

    def test_bounce_tempo_constrains_object(self):
        self._ck(
            "bounce_tempo",
            "you",
            [
                {
                    "name": "Boomerang",
                    "type_line": "Instant",
                    "oracle_text": "Return target permanent to its owner's hand.",
                }
            ],
            [
                {
                    "name": "Reprieve",
                    "type_line": "Instant",
                    "oracle_text": "Return target spell to its owner's hand.\nDraw a card.",
                }
            ],
        )

    def test_count_anthem_drops_self_scaling_branch(self):
        self._ck(
            "count_anthem",
            "you",
            [
                {
                    "name": "Commander's Insignia",
                    "type_line": "Enchantment",
                    "oracle_text": "Creatures you control get +1/+1 for each time you've cast your commander from the command zone this game.",
                }
            ],
            [
                {
                    "name": "Storm-Kiln Artist",
                    "type_line": "Creature — Dwarf Shaman",
                    "oracle_text": 'This creature gets +1/+0 for each artifact you control.\nMagecraft — Whenever you cast or copy an instant or sorcery spell, create a Treasure token. (It\'s an artifact with "{T}, Sacrifice this token: Add one mana of any color.")',
                }
            ],
        )

    def test_lifeloss_self_drops_painlands(self):
        self._ck(
            "lifeloss_matters",
            "you",
            [
                {
                    "name": "K'rrik",
                    "type_line": "Legendary Creature — Phyrexian Horror",
                    "oracle_text": "Whenever you lose life, ...\nBlack spells you cast cost {2} less and {2} life more.",
                }
            ],
            [
                {
                    "name": "Blood Crypt",
                    "type_line": "Land — Swamp Mountain",
                    "oracle_text": "({T}: Add {B} or {R}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
                }
            ],
        )

    def test_permanent_etb_recovers_etb_engines(self):
        self._ck(
            "permanent_etb",
            "you",
            [
                {
                    "name": "Panharmonicon",
                    "type_line": "Artifact",
                    "oracle_text": "If an artifact or creature entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
                }
            ],
            [],
        )

    def test_gain_control_requires_you_as_controller(self):
        self._ck(
            "gain_control",
            "you",
            [
                {
                    "name": "Control Magic",
                    "type_line": "Enchantment — Aura",
                    "oracle_text": "Enchant creature\nYou control enchanted creature.",
                }
            ],
            [
                {
                    "name": "Sky Swallower",
                    "type_line": "Creature — Leviathan",
                    "oracle_text": "Flying\nWhen this creature enters, target opponent gains control of all other permanents you control.",
                }
            ],
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
                {
                    "name": "Bojuka Bog",
                    "oracle_text": "This land enters tapped.\nWhen this land enters, exile target player's graveyard.\n{T}: Add {B}.",
                },
                {
                    "name": "Ruin Crab",
                    "oracle_text": "Landfall — Whenever a land you control enters, each opponent mills three cards. (To mill a card, a player puts the top card of their library into their graveyard.)",
                },
            ],
            [
                {
                    "name": "Stitcher's Supplier",
                    "oracle_text": "When this creature enters or dies, mill three cards. (Put the top three cards of your library into your graveyard.)",
                }
            ],
        )

    def test_opponent_search_requires_opponent_subject(self):
        self._ck(
            "opponent_search_matters",
            "opponents",
            [
                {
                    "name": "Aven Mindcensor",
                    "oracle_text": "Flash\nFlying\nIf an opponent would search a library, that player searches the top four cards of that library instead.",
                }
            ],
            [
                {
                    "name": "Path to Exile",
                    "oracle_text": "Exile target creature. Its controller may search their library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
                }
            ],
        )

    def test_group_draw_each_drops_self_only_additional(self):
        self._ck(
            "card_draw_engine",
            "each",
            [
                {
                    "name": "Howling Mine",
                    "oracle_text": "At the beginning of each player's draw step, if this artifact is untapped, that player draws an additional card.",
                }
            ],
            [
                {
                    "name": "Heightened Awareness",
                    "oracle_text": "As this enchantment enters, discard your hand.\nAt the beginning of your draw step, draw an additional card.",
                }
            ],
        )

    def test_cast_from_exile_is_payoffs_not_impulse(self):
        # Cast-from-exile is now the PAYOFF lane (rewards for casting from exile).
        # A rebound self-cast (Consuming Vapors) isn't an engine; and a pure impulse
        # enabler (Light Up the Stage) belongs to the separate impulse_top_play avenue,
        # not here.
        self._ck(
            "cast_from_exile",
            "you",
            [
                {
                    "name": "Exile Payoff",
                    "oracle_text": "Whenever you cast a spell from exile, draw a card.",
                }
            ],
            [
                {
                    "name": "Consuming Vapors",
                    "oracle_text": "Target player sacrifices a creature of their choice. You gain life equal to that creature's toughness.\nRebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you may cast this card from exile without paying its mana cost.)",
                },
                {
                    "name": "Light Up the Stage",
                    "oracle_text": "Spectacle {R} (You may cast this spell for its spectacle cost rather than its mana cost if an opponent lost life this turn.)\nExile the top two cards of your library. Until the end of your next turn, you may play those cards.",
                },
            ],
        )

    def test_doubling_splits_token_and_counter_doublers(self):
        # token_doubling and counter_doubling are SEPARATE lanes (inherently different
        # properties): a token doubler wants token MAKERS; a counter doubler wants
        # counter SOURCES. Doubling Season feeds both; Parallel Lives only tokens;
        # Hardened Scales only counters. Real cards, full oracle text.
        parallel_lives = {
            "name": "Parallel Lives",
            "type_line": "Enchantment",
            "oracle_text": "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.",
        }
        doubling_season = {
            "name": "Doubling Season",
            "type_line": "Enchantment",
            "oracle_text": "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.",
        }
        hardened_scales = {
            "name": "Hardened Scales",
            "type_line": "Enchantment",
            "oracle_text": "If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.",
        }
        hangarback = {
            "name": "Hangarback Walker",
            "type_line": "Artifact Creature — Construct",
            "oracle_text": "This creature enters with X +1/+1 counters on it.\nWhen this creature dies, create a 1/1 colorless Thopter artifact creature token with flying for each +1/+1 counter on this creature.\n{1}, {T}: Put a +1/+1 counter on this creature.",
        }
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
        pelakka = {
            "type_line": "Creature — Wurm",
            "oracle_text": "Trample\nWhen this creature enters, you gain 7 life.",
            "keywords": ["Trample"],
        }
        payoff = {
            "type_line": "Enchantment — Saga",
            "oracle_text": "If a creature you control would deal excess damage to a creature, deal that excess damage to its controller instead.",
        }
        vanilla = {"type_line": "Creature — Bear", "oracle_text": "", "keywords": []}
        assert serves(pelakka, sig) is True  # trample keyword
        assert serves(payoff, sig) is True  # excess damage payoff
        assert serves(vanilla, sig) is False

    def test_anthem_static_excludes_until_end_of_turn(self):
        sig = _sig("anthem_static", "you")
        glorious = {
            "type_line": "Enchantment",
            "oracle_text": "Creatures you control get +1/+1.",
        }
        overcome = {
            "type_line": "Sorcery",
            "oracle_text": "Creatures you control get +2/+2 and gain trample until end of turn.",
        }
        assert serves(glorious, sig) is True  # static anthem
        assert serves(overcome, sig) is False  # one-shot pump (until end of turn)

    def test_anthem_static_serves_color_conditional_anthems(self):
        # Bad Moon ("Black creatures get +1/+1") is THE iconic black anthem, but the
        # serve required "you control" / "nonblack" / "other", so a color-conditional
        # anthem was missed — and Hall of Triumph's "creatures you control of the chosen
        # color get +1/+1" too (the color phrase splits "control" from "get"). The
        # one-shot color pump stays vetoed by serve_not. Real oracle.
        sig = _sig("anthem_static", "you")
        bad_moon = {
            "name": "Bad Moon",
            "type_line": "Enchantment",
            "oracle_text": "Black creatures get +1/+1.",
        }
        hall = {
            "name": "Hall of Triumph",
            "type_line": "Legendary Artifact",
            "oracle_text": (
                "As Hall of Triumph enters, choose a color.\n"
                "Creatures you control of the chosen color get +1/+1."
            ),
        }
        nocturnal_raid = {
            "name": "Nocturnal Raid",
            "type_line": "Instant",
            "oracle_text": "Black creatures get +2/+0 until end of turn.",
        }
        assert serves(bad_moon, sig) is True  # static color anthem
        assert serves(hall, sig) is True  # chosen-color anthem
        assert serves(nocturnal_raid, sig) is False  # one-shot pump still vetoed

    def test_ltb_matters_excludes_o_ring_removal(self):
        sig = _sig("ltb_matters", "you")
        nikara = {
            "type_line": "Legendary Creature — Snake Cleric",
            "oracle_text": "Whenever another creature you control leaves the battlefield, target player loses 1 life and you gain 1 life.",
        }
        banishing = {
            "type_line": "Enchantment",
            "oracle_text": "When Banishing Light enters, exile target nonland permanent an opponent controls until Banishing Light leaves the battlefield.",
        }
        assert serves(nikara, sig) is True  # LTB payoff
        assert serves(banishing, sig) is False  # O-Ring exile-until-leaves


class TestMediumBatch8:
    """MEDIUM batch 8: sweep-regex surgeries + extraction/scope fixes."""

    def test_big_hand_excludes_stax_hand_size_refs(self):
        sig = _sig("big_hand_matters", "you")
        no_max = {
            "type_line": "Creature",
            "oracle_text": "You have no maximum hand size.",
        }
        ensnaring = {
            "type_line": "Artifact",
            "oracle_text": "Creatures with power greater than the number of cards in your hand can't attack.",
        }
        assert serves(no_max, sig) is True
        assert serves(ensnaring, sig) is False

    def test_counter_manipulation_requires_plus_one_counters(self):
        sig = _sig("counter_manipulation", "you")
        hex_parasite = {
            "type_line": "Artifact Creature — Insect",
            "oracle_text": "{X}, {T}: Remove X +1/+1 counters or X loyalty counters from target permanent.",
        }
        mana_bloom = {
            "type_line": "Enchantment",
            "oracle_text": "At the beginning of your upkeep, remove a charge counter from this enchantment. If you can't, sacrifice it.",
        }
        assert serves(hex_parasite, sig) is True
        assert serves(mana_bloom, sig) is False

    def test_life_total_set_drops_symmetric_damage_branch(self):
        sig = _sig("life_total_set", "any")
        mirror = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Exchange your life total with target opponent's life total.",
        }
        price = {
            "type_line": "Sorcery",
            "oracle_text": "Price of Progress deals damage to each player equal to twice the number of nonbasic lands that player controls.",
        }
        assert serves(mirror, sig) is True
        assert serves(price, sig) is False

    def test_creature_cast_trigger_recovers_you_cast(self):
        from mtg_utils._deck_forge.signals import extract_signals

        beast_whisperer = {
            "name": "Beast Whisperer",
            "type_line": "Creature — Elf Druid",
            "oracle_text": "Whenever you cast a creature spell, draw a card.",
        }
        keys = {s.key for s in extract_signals(beast_whisperer)}
        assert "creature_cast_trigger" in keys

    def test_win_lose_game_self_win_not_mislabeled_opponents(self):
        from mtg_utils._deck_forge.signals import extract_signals

        felidar = {
            "name": "Felidar Sovereign",
            "type_line": "Creature — Cat Beast",
            "oracle_text": "Vigilance (Attacking doesn't cause this creature to tap.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)\nAt the beginning of your upkeep, if you have 40 or more life, you win the game.",
        }
        sigs = [s for s in extract_signals(felidar) if s.key == "win_lose_game"]
        assert sigs
        assert all(s.scope != "opponents" for s in sigs)


class TestMediumBatch9:
    def test_counter_distribute_is_board_wide_only(self):
        sig = _sig("counter_distribute", "you")
        cathars = {
            "type_line": "Enchantment",
            "oracle_text": "Whenever a creature you control enters, put a +1/+1 counter on each creature you control.",
        }
        venerable = {
            "type_line": "Creature — Human Knight",
            "oracle_text": "When this creature dies, put a +1/+1 counter on target Knight you control.",
        }
        assert serves(cathars, sig) is True
        assert serves(venerable, sig) is False

    def test_keyword_tribe_requires_payoff_anchor(self):
        from mtg_utils._deck_forge.signals import extract_signals, signal_keys

        praetors = {
            "name": "Hand of the Praetors",
            "type_line": "Creature — Phyrexian Zombie",
            "oracle_text": "Infect (This creature deals damage to creatures in the form of -1/-1 counters and to players in the form of poison counters.)\nOther creatures you control with infect get +1/+1.\nWhenever you cast a creature spell with infect, target player gets a poison counter.",
        }
        whiptongue = {
            "name": "Whiptongue Hydra",
            "type_line": "Creature — Lizard Hydra",
            "oracle_text": "Reach\nWhen this creature enters, destroy all creatures with flying. Put a +1/+1 counter on this creature for each creature destroyed this way.",
        }
        praetor_kw = {
            s.subject
            for s in extract_signals(praetors)
            if s.key == signal_keys.KEYWORD_TRIBE
        }
        whip_kw = {
            s.subject
            for s in extract_signals(whiptongue)
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
    stargaze = {
        "name": "Stargaze",
        "type_line": "Sorcery",
        "oracle_text": (
            "Look at twice X cards from the top of your library. Put X cards from "
            "among them into your hand and the rest into your graveyard. You lose X life."
        ),
    }
    future_sight = {
        "name": "Future Sight",
        "type_line": "Enchantment",
        "oracle_text": (
            "Play with the top card of your library revealed. You may play lands and "
            "cast spells from the top of your library."
        ),
    }
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
    worldspine = {
        "name": "Worldspine Wurm",
        "type_line": "Creature — Wurm",
        "power": "15",
        "toughness": "15",
        "oracle_text": "Trample\nWhen this creature dies, create three 5/5 green Wurm creature tokens with trample.\nWhen Worldspine Wurm is put into a graveyard from anywhere, shuffle it into its owner's library.",
    }
    assert _lane_covers(worldspine, sig)
    # The enabler (a reanimation/cheat spell) still serves via the main serve.
    sneak = {
        "name": "Sneak Attack",
        "type_line": "Enchantment",
        "oracle_text": "{R}: You may put a creature card from your hand onto the battlefield. That creature gains haste. Sacrifice the creature at the beginning of the next end step.",
    }
    assert _lane_covers(sneak, sig)


def test_cheat_into_play_does_not_credit_small_creatures():
    """A 2/2 bear is not the payoff of a cheat deck — power gate keeps it off-theme."""
    sig = _sig("cheat_into_play")
    bear = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert not _lane_covers(bear, sig)


def test_voltron_credits_aura_equipment_cost_reduction():
    """Danitha-style 'Aura and Equipment spells you cast cost {1} less' is a voltron
    payoff — it makes suiting up cheaper. EDHREC ranks it top-synergy for voltron."""
    sig = _sig("voltron_matters")
    danitha = {
        "name": "Danitha Capashen, Paragon",
        "type_line": "Legendary Creature — Human Knight",
        "oracle_text": "First strike, vigilance, lifelink\nAura and Equipment spells "
        "you cast cost {1} less to cast.",
    }
    assert _lane_covers(danitha, sig)


def test_voltron_credits_equipment_aura_tutors():
    """Open the Armory / Steelshaper's Gift fetch the suit — top voltron synergy."""
    sig = _sig("voltron_matters")
    armory = {
        "name": "Open the Armory",
        "type_line": "Sorcery",
        "oracle_text": "Search your library for an Aura or Equipment card, reveal it, "
        "put it into your hand, then shuffle.",
    }
    gift = {
        "name": "Steelshaper's Gift",
        "type_line": "Sorcery",
        "oracle_text": "Search your library for an Equipment card, reveal that card, "
        "put it into your hand, then shuffle.",
    }
    assert _lane_covers(armory, sig)
    assert _lane_covers(gift, sig)


def test_voltron_credits_protection_for_the_threat():
    """Protecting the one suited-up creature is THE voltron support package — Mother of
    Runes, Bastion Protector, Avacyn are top-synergy for voltron commanders."""
    sig = _sig("voltron_matters")
    mom = {
        "name": "Mother of Runes",
        "type_line": "Creature — Human Cleric",
        "oracle_text": "{T}: Target creature you control gains protection from the "
        "color of your choice until end of turn.",
    }
    bastion = {
        "name": "Bastion Protector",
        "type_line": "Creature — Human Soldier",
        "oracle_text": "Commander creatures you control get +2/+2 and have indestructible.",
    }
    avacyn = {
        "name": "Avacyn, Angel of Hope",
        "type_line": "Legendary Creature — Angel",
        "oracle_text": "Flying, vigilance, indestructible\nOther permanents you control "
        "have indestructible.",
    }
    assert _lane_covers(mom, sig)
    assert _lane_covers(bastion, sig)
    assert _lane_covers(avacyn, sig)


def test_voltron_protection_does_not_credit_plain_anthems():
    """A flying/+1+1 anthem is not protection — precision guard so the protect-extra
    doesn't swallow every team buff."""
    sig = _sig("voltron_matters")
    anthem = {
        "name": "Flying Anthem",
        "type_line": "Enchantment",
        "oracle_text": "Creatures you control have flying and get +1/+1.",
    }
    assert not _lane_covers(anthem, sig)


def test_evasion_serves_horsemanship_via_keyword():
    """A horsemanship creature feeds the evasion lane — but its 'can't be blocked
    except' text trips the serve's negative lookahead, so credit it by the keyword[]."""
    sig = _sig("evasion_self")
    shu_general = {
        "name": "Shu General",
        "type_line": "Creature — Human Soldier",
        "oracle_text": "Vigilance; horsemanship (This creature can't be blocked except "
        "by creatures with horsemanship.)",
        "keywords": ["Vigilance", "Horsemanship"],
    }
    assert _lane_covers(shu_general, sig)


def test_power_double_credits_big_bodies():
    """A power-doubler (Rhonas / Mr. Orfeo) wants high BASE power to double — Ghalta
    (12 power) is the payoff, not a 2/2."""
    sig = _sig("power_double")
    ghalta = {
        "name": "Ghalta, Primal Hunger",
        "type_line": "Legendary Creature — Elder Dinosaur",
        "power": "12",
        "toughness": "12",
        "oracle_text": "This spell costs {X} less to cast, where X is the total power of creatures you control.\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
    }
    bear = {
        "name": "Bear",
        "type_line": "Token Creature — Bear",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert serves(ghalta, sig)
    assert not serves(bear, sig)


def test_creature_ping_credits_big_bodies():
    """A power-as-damage commander (Itzquinth) wants high power for more ping damage."""
    sig = _sig("creature_ping")
    fatty = {
        "name": "Worldspine Wurm",
        "type_line": "Creature — Wurm",
        "power": "15",
        "toughness": "15",
        "oracle_text": "Trample\nWhen this creature dies, create three 5/5 green Wurm creature tokens with trample.\nWhen Worldspine Wurm is put into a graveyard from anywhere, shuffle it into its owner's library.",
    }
    assert serves(fatty, sig)


def test_blink_serves_two_sentence_flicker():
    """Flickerwisp / Charming Prince write the flicker as two sentences ('exile … .
    Return it …'); the serve must cross the one sentence boundary, anchored to a
    return-pronoun so an unrelated exile+return-a-land doesn't match."""
    sig = _sig("blink_flicker")
    flickerwisp = {
        "name": "Flickerwisp",
        "type_line": "Creature — Elemental",
        "oracle_text": "Flying\nWhen this creature enters, exile another target "
        "permanent. Return that card to the battlefield under its owner's control at "
        "the beginning of the next end step.",
    }
    charming = {
        "name": "Charming Prince",
        "type_line": "Creature — Human Noble",
        "oracle_text": "When this creature enters, choose one —\n• Scry 2.\n• You gain "
        "3 life.\n• Exile another target creature you own. Return it to the battlefield "
        "under your control at the beginning of the next end step.",
    }
    assert _lane_covers(flickerwisp, sig)
    assert _lane_covers(charming, sig)


def test_blink_does_not_match_unrelated_exile_then_return_land():
    # Precision: exile-removal followed by an unrelated land-return is not flicker.
    sig = _sig("blink_flicker")
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
    victimize = {
        "name": "Victimize",
        "type_line": "Sorcery",
        "oracle_text": "Choose two target creature cards in your graveyard. Sacrifice a creature. If you do, return the chosen cards to the battlefield tapped.",
    }
    assert _lane_covers(victimize, sig)


def test_graveyard_you_does_not_serve_opponent_graveyard():
    # Precision: an opponents'-graveyard card must NOT serve the YOUR-graveyard lane.
    sig = _sig("graveyard_matters")
    card = {
        "name": "Bojuka Bog-like",
        "type_line": "Instant",
        "oracle_text": "Exile target opponent's graveyard.",
    }
    assert not _lane_covers(card, sig)


def test_activated_ability_serves_support_package():
    """The activated-ability engine surfaces cost reducers, untappers, haste-for-
    abilities, and ability copiers — the package that powers a {T}: commander."""
    sig = _sig("activated_ability")
    training = {
        "name": "Training Grounds",
        "type_line": "Enchantment",
        "oracle_text": "Activated abilities of creatures you control cost {2} less to "
        "activate. This effect can't reduce the mana in that cost to less than one mana.",
    }
    elixir = {
        "name": "Thousand-Year Elixir",
        "type_line": "Artifact",
        "oracle_text": "You may activate abilities of creatures you control as though "
        "those creatures had haste.\n{1}, {T}: Untap target creature.",
    }
    rings = {
        "name": "Rings of Brighthearth",
        "type_line": "Artifact",
        "oracle_text": "Whenever you activate an ability, if it isn't a mana ability, you may pay {2}. If you do, copy that ability. You may choose new targets for the copy.",
    }
    ioreth = {
        "name": "Ioreth of the Healing House",
        "type_line": "Legendary Creature — Human Cleric",
        "oracle_text": "{T}: Untap another target permanent.\n{T}: Untap two other target legendary creatures.",
    }
    for c in (training, elixir, rings, ioreth):
        assert _lane_covers(c, sig), c["name"]


def test_activated_ability_does_not_serve_a_vanilla_bear():
    sig = _sig("activated_ability")
    bear = {"name": "Bear", "type_line": "Token Creature — Bear", "oracle_text": ""}
    assert not _lane_covers(bear, sig)


def test_deathtouch_gear_serves_ping_and_noncombat_lanes():
    """Basilisk Collar (deathtouch gear) is top-synergy for pingers / power-as-damage /
    noncombat-damage commanders (Ghyrson, Tahngarth, Hidetsugu) — deathtouch + any ping
    kills anything. Previously only the Burn lane carried the deathtouch extra."""
    collar = {
        "name": "Basilisk Collar",
        "type_line": "Artifact — Equipment",
        "oracle_text": "Equipped creature has deathtouch and lifelink. (Any amount of damage it deals to a creature is enough to destroy it. Damage dealt by this creature also causes you to gain that much life.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    }
    for key in ("creature_ping", "noncombat_damage_payoff", "damage_equal_power"):
        assert _lane_covers(collar, _sig(key)), key


def test_all_counter_lanes_serve_sources_and_doublers():
    """Every +1/+1-counter lane should surface the core package — counter SOURCES
    (Forgotten Ancient: 'put a +1/+1 counter') and counter DOUBLERS (Hardened Scales) —
    no matter which fragmented counter lane the commander opened."""
    forgotten = {
        "name": "Forgotten Ancient",
        "type_line": "Creature — Elemental",
        "oracle_text": "Whenever a player casts a spell, you may put a +1/+1 counter on this creature.\nAt the beginning of your upkeep, you may move any number of +1/+1 counters from this creature onto other creatures.",
    }
    scales = {
        "name": "Hardened Scales",
        "type_line": "Enchantment",
        "oracle_text": "If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.",
    }
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
    goreclaw = {
        "name": "Goreclaw, Terror of Qal Sisma",
        "type_line": "Legendary Creature — Bear",
        "power": "4",
        "toughness": "6",
        "oracle_text": "Creature spells you cast with power 4 or greater cost {2} less to cast.\nWhenever Goreclaw attacks, each creature you control with power 4 or greater gets +1/+1 and gains trample until end of turn.",
    }
    ghalta = {
        "name": "Ghalta, Primal Hunger",
        "type_line": "Legendary Creature — Elder Dinosaur",
        "power": "12",
        "toughness": "12",
        "oracle_text": "This spell costs {X} less to cast, where X is the total power of creatures you control.\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
    }
    midsize = {
        "name": "Hill Giant",
        "type_line": "Creature — Giant",
        "power": "3",
        "toughness": "3",
        "oracle_text": "",
    }
    assert _lane_covers(goreclaw, sig)
    assert _lane_covers(ghalta, sig)
    assert not _lane_covers(midsize, sig)


def test_toughness_combat_credits_big_butts_and_walls():
    """Doran / Arcades deal damage with TOUGHNESS — they want big-toughness bodies and
    Walls (defenders), which the toughness lane previously couldn't surface."""
    sig = _sig("toughness_combat")
    wall = {
        "name": "Wall of Denial",
        "type_line": "Creature — Wall",
        "power": "0",
        "toughness": "4",
        "keywords": ["Defender"],
        "oracle_text": "Defender, flying\nShroud (This creature can't be the target of spells or abilities.)",
    }
    big_butt = {
        "name": "Indomitable Ancients",
        "type_line": "Creature — Treefolk Warrior",
        "power": "2",
        "toughness": "10",
        "oracle_text": "",
    }
    small = {
        "name": "Bear",
        "type_line": "Token Creature — Bear",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert _lane_covers(wall, sig)
    assert _lane_covers(big_butt, sig)
    assert not _lane_covers(small, sig)


def test_clone_credits_big_creatures_worth_copying():
    """The clone blurb promises 'strong creatures worth copying' — deliver it: Etali (a
    6/6 bomb) is a top clone/token-copy target, not just the clone effects themselves."""
    sig = _sig("clone_matters")
    etali = {
        "name": "Etali, Primal Storm",
        "type_line": "Legendary Creature — Elder Dinosaur",
        "power": "6",
        "toughness": "6",
        "oracle_text": "Whenever Etali attacks, exile the top card of each player's library, then you may cast any number of spells from among those cards without paying their mana costs.",
    }
    assert _lane_covers(etali, sig)


def test_go_wide_credits_board_protection():
    """Go-wide decks want mass-indestructible to survive wraths (Selfless Spirit) — the
    protection extra now reaches the go-wide lane, not just voltron."""
    sig = _sig("creatures_matter")
    selfless = {
        "name": "Selfless Spirit",
        "type_line": "Creature — Spirit Cleric",
        "oracle_text": "Flying\nSacrifice this creature: Creatures you control gain "
        "indestructible until end of turn.",
    }
    assert _lane_covers(selfless, sig)


def test_landfall_serves_basic_type_ramp():
    """Skyshroud Claim / Nature's Lore / Farseek search for 'Forest'/'a Plains or
    Island' — basic-type names, never the word 'land' — so the landfall ramp serve
    missed them. These put lands onto the battlefield, the bread-and-butter landfall
    fuel."""
    sig = _sig("landfall")
    skyshroud = {
        "name": "Skyshroud Claim",
        "type_line": "Sorcery",
        "oracle_text": "Search your library for up to two Forest cards, put them onto "
        "the battlefield, then shuffle.",
    }
    farseek = {
        "name": "Farseek",
        "type_line": "Sorcery",
        "oracle_text": "Search your library for a Plains, Island, Swamp, or Mountain "
        "card, put it onto the battlefield tapped, then shuffle.",
    }
    assert _lane_covers(skyshroud, sig)
    assert _lane_covers(farseek, sig)


def test_landfall_does_not_serve_a_nonland_tutor():
    sig = _sig("landfall")
    demonic = {
        "name": "Demonic Tutor",
        "type_line": "Sorcery",
        "oracle_text": "Search your library for a card, put that card into your hand, then shuffle.",
    }
    assert not _lane_covers(demonic, sig)


def test_ltb_serves_flicker_effects():
    """A leaves-the-battlefield commander (Bilbo, Genku, Lagrella) wants flicker — it
    blinks your own permanents, firing both LTB and a fresh ETB. The serve matched LTB
    triggers but not the flicker effects its own blurb ('blink fodder') promises."""
    sig = _sig("ltb_matters")
    ghostly = {
        "name": "Ghostly Flicker",
        "type_line": "Instant",
        "oracle_text": "Exile two target artifacts, creatures, and/or lands you control, then return those cards to the battlefield under your control.",
    }
    assert _lane_covers(ghostly, sig)


def test_regenerate_lane_serves_voltron_auras():
    """A regenerate/resilience commander is a resilient beater — a voltron plan. Its
    top-synergy cards are buff/protection Auras and gear (Rancor, Bear Umbra, Alpha
    Authority) that the bare regenerate serve missed."""
    sig = _sig("regenerate_matters")
    rancor = {
        "name": "Rancor",
        "type_line": "Enchantment — Aura",
        "oracle_text": "Enchant creature\nEnchanted creature gets +2/+0 and has trample.\nWhen this Aura is put into a graveyard from the battlefield, return it to its owner's hand.",
    }
    alpha = {
        "name": "Alpha Authority",
        "type_line": "Enchantment — Aura",
        "oracle_text": "Enchant creature\nEnchanted creature has hexproof and can't be "
        "blocked by more than one creature.",
    }
    assert _lane_covers(rancor, sig)
    assert _lane_covers(alpha, sig)


def test_power_growth_lanes_serve_fling_payoffs():
    """Power-growth decks (firebreathing, variable P/T, +1/+1, power-double) want to
    convert that power into damage — Fling / Chandra's Ignition / Soul's Fire. The
    board-sweep form ('to each other creature and player') was missed by the
    single-target fling regex."""
    ignition = {
        "name": "Chandra's Ignition",
        "type_line": "Sorcery",
        "oracle_text": "Target creature you control deals damage equal to its power to each other creature and each opponent.",
    }
    fling = {
        "name": "Fling",
        "type_line": "Instant",
        "oracle_text": "As an additional cost to cast this spell, sacrifice a creature.\n"
        "Fling deals damage equal to the sacrificed creature's power to any target.",
    }
    for key in ("power_matters", "self_pump", "variable_pt", "power_double"):
        assert _lane_covers(ignition, _sig(key)), f"ignition/{key}"
        assert _lane_covers(fling, _sig(key)), f"fling/{key}"


def test_token_copy_credits_big_creatures():
    """token_copy's blurb promises 'strong creatures to copy' — deliver it: Etali (6/6
    bomb) is a top token-copy target (Cadric, Feldon), not just the copy effects."""
    sig = _sig("token_copy_matters")
    etali = {
        "name": "Etali, Primal Storm",
        "type_line": "Legendary Creature — Elder Dinosaur",
        "power": "6",
        "toughness": "6",
        "oracle_text": "Whenever Etali attacks, exile the top card of each player's library, then you may cast any number of spells from among those cards without paying their mana costs.",
    }
    assert _lane_covers(etali, sig)


def test_go_wide_credits_etb_doubler():
    """A go-wide deck full of creature ETBs wants Panharmonicon — the go-wide lane had
    ETB-value/payoff extras but not the ETB-doubler."""
    sig = _sig("creatures_matter")
    panharmonicon = {
        "name": "Panharmonicon",
        "type_line": "Artifact",
        "oracle_text": "If an artifact or creature entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
    }
    assert _lane_covers(panharmonicon, sig)


def test_stax_serves_replacement_search_hate():
    """Aven Mindcensor / Maze of Ith-style search hate uses a REPLACEMENT ('if an
    opponent would search ... top four instead'), not 'can't search' — the stax serve
    only had the prohibition form."""
    sig = _sig("stax_taxes", "opponents")
    aven = {
        "name": "Aven Mindcensor",
        "type_line": "Creature — Bird Wizard",
        "oracle_text": "Flash\nFlying\nIf an opponent would search a library, that "
        "player searches the top four cards of that library instead.",
    }
    assert _lane_covers(aven, sig)


def test_reanimator_credits_etb_value_targets():
    """A reanimator deck wants high-ETB creatures to reanimate — Mulldrifter (draw) and
    edict-ETB creatures (Plaguecrafter, Accursed Marauder: 'each player sacrifices').
    The reanimator lane served the spells but not the targets."""
    sig = _sig("reanimator")
    mulldrifter = {
        "name": "Mulldrifter",
        "type_line": "Creature — Elemental",
        "oracle_text": "Flying\nWhen this creature enters, draw two cards.\nEvoke {2}{U} (You may cast this spell for its evoke cost. If you do, it's sacrificed when it enters.)",
    }
    plaguecrafter = {
        "name": "Plaguecrafter",
        "type_line": "Creature — Human Shaman",
        "oracle_text": "When this creature enters, each player sacrifices a creature or planeswalker of their choice. Each player who can't discards a card.",
    }
    assert _lane_covers(mulldrifter, sig)
    assert _lane_covers(plaguecrafter, sig)


def test_ramp_credits_the_fatties_it_accelerates_into():
    """ramp_matters promises 'accelerate into your payoffs' — deliver them: the big
    bombs (Ghalta, power 12) and creature cost reducers (Goreclaw). Only 3% of
    commanders open this 'big mana' lane, so power_min=6 is clean. A 2/2 stays off."""
    sig = _sig("ramp_matters")
    ghalta = {
        "name": "Ghalta, Primal Hunger",
        "type_line": "Legendary Creature — Elder Dinosaur",
        "power": "12",
        "toughness": "12",
        "oracle_text": "This spell costs {X} less to cast, where X is the total power of creatures you control.\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
    }
    bear = {
        "name": "Bear",
        "type_line": "Token Creature — Bear",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert _lane_covers(ghalta, sig)
    assert not _lane_covers(bear, sig)


def test_token_anthems_serve_token_lanes():
    """Intangible Virtue / token anthems ('creature TOKENS you control get +1/+1') are
    top-synergy for token commanders — but the go-wide serve matched 'creatures you
    control get', not the 'creature tokens you control' phrasing."""
    virtue = {
        "name": "Intangible Virtue",
        "type_line": "Enchantment",
        "oracle_text": "Creature tokens you control get +1/+1 and have vigilance.",
    }
    assert _lane_covers(virtue, _sig("token_maker"))
    assert _lane_covers(virtue, _sig("creatures_matter"))


def test_snow_lane_serves_snow_cards():
    sig = _sig("snow_matters")
    rime = {
        "name": "Rime Tender",
        "type_line": "Snow Creature — Human Druid",
        "oracle_text": "{T}: Untap another target snow permanent.",
    }
    search = {
        "name": "Search for Glory",
        "type_line": "Snow Sorcery",
        "oracle_text": "Search your library for a snow permanent card, a legendary card, or a Saga card, reveal it, put it into your hand, then shuffle. You gain 1 life for each {S} spent to cast this spell. ({S} is mana from a snow source.)",
    }
    assert _lane_covers(rime, sig)
    assert _lane_covers(search, sig)


def test_tribal_serve_matches_members_by_type_not_just_oracle():
    """A creature is a member of its own tribe — the tribal serve must match by
    TYPE-LINE, not only oracle. Dread Shade (oracle '{B}: +1/+1', no 'Shade' word) and
    Llanowar Elves (oracle '{T}: Add {G}') are tribe members that the oracle-only serve
    silently dropped — fatal for lord-less tribes (Shade was 0/10)."""
    dread = {
        "name": "Dread Shade",
        "type_line": "Creature — Shade",
        "oracle_text": "{B}: This creature gets +1/+1 until end of turn.",
    }
    llanowar = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "oracle_text": "{T}: Add {G}.",
    }
    assert _lane_covers(dread, _sig_sub("type_matters", "Shade"))
    assert _lane_covers(llanowar, _sig_sub("type_matters", "Elf"))
    # Precision: a Goblin does NOT serve Elf tribal.
    goblin = {
        "name": "Goblin",
        "type_line": "Token Creature — Goblin",
        "oracle_text": "",
    }
    assert not _lane_covers(goblin, _sig_sub("type_matters", "Elf"))


def test_vanilla_lane_serves_vanilla_creatures_and_payoffs():
    sig = _sig("vanilla_matters")
    gigantosaurus = {
        "name": "Gigantosaurus",
        "type_line": "Creature — Dinosaur",
        "power": "10",
        "toughness": "10",
        "oracle_text": "",
    }
    muraganda = {
        "name": "Muraganda Petroglyphs",
        "type_line": "Enchantment",
        "oracle_text": "Creatures with no abilities get +2/+2.",
    }
    bear_with_text = {
        "name": "Ability Bear",
        "type_line": "Creature — Bear",
        "oracle_text": "When this creature enters, draw a card.",
    }
    assert _lane_covers(gigantosaurus, sig)  # vanilla member
    assert _lane_covers(muraganda, sig)  # the payoff
    assert not _lane_covers(bear_with_text, sig)  # has an ability → not vanilla


def test_combat_damage_lane_serves_gear_and_pump():
    """A combat-damage-trigger commander (Benton, Ojutai, Edric) wants to CONNECT and
    survive: gear (Ring of Thune) and pump (Giant Growth). The lane served evasion but
    not the gear/pump that keeps the attacker alive and bigger."""
    sig = _sig("combat_damage_matters", "opponents")
    ring = {
        "name": "Ring of Thune",
        "type_line": "Artifact — Equipment",
        "oracle_text": "Equipped creature has vigilance. (Attacking doesn't cause it to tap.)\nAt the beginning of your upkeep, put a +1/+1 counter on equipped creature if it's white.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    }
    giant_growth = {
        "name": "Giant Growth",
        "type_line": "Instant",
        "oracle_text": "Target creature gets +3/+3 until end of turn.",
    }
    assert _lane_covers(ring, sig)
    assert _lane_covers(giant_growth, sig)


def test_toughness_lane_credits_butts_by_statline():
    """The ideal toughness-deck creature is a BUTT — toughness > power (1/5, 0/3) — which
    a flat toughness>=4 threshold misses. Detect it from the actual stat line, not
    oracle. A balanced 3/3 (not toughness-skewed, below the >=4 floor) stays off."""
    sig = _sig("toughness_combat")
    one_five = {
        "name": "Wall-ish",
        "type_line": "Creature — Wall",
        "power": "1",
        "toughness": "5",
        "oracle_text": "Defender",
    }
    zero_three = {
        "name": "Small Wall",
        "type_line": "Creature — Wall",
        "power": "0",
        "toughness": "3",
        "oracle_text": "",
    }
    balanced = {
        "name": "Bear",
        "type_line": "Token Creature — Bear",
        "power": "3",
        "toughness": "3",
        "oracle_text": "",
    }
    assert _lane_covers(one_five, sig)
    assert _lane_covers(zero_three, sig)
    assert not _lane_covers(balanced, sig)


def test_redirect_lane_serves_pariah_and_indestructible():
    sig = _sig("damage_redirect")
    pariah = {
        "name": "Pariah",
        "type_line": "Enchantment — Aura",
        "oracle_text": "Enchant creature\nAll damage that would be dealt to you is "
        "dealt to enchanted creature instead.",
    }
    shielded = {
        "name": "Shielded by Faith",
        "type_line": "Enchantment — Aura",
        "oracle_text": "Enchant creature\nEnchanted creature has indestructible.\nWhenever a creature enters, you may attach this Aura to that creature.",
    }
    assert _lane_covers(pariah, sig)
    assert _lane_covers(shielded, sig)


def test_opponents_mill_serves_exile_library_artifacts():
    sig = _sig("graveyard_matters", "opponents")
    pyxis = {
        "name": "Pyxis of Pandemonium",
        "type_line": "Artifact",
        "oracle_text": "{T}: Each player exiles the top card of their library face down.\n{7}, {T}, Sacrifice this artifact: Each player turns face up all cards they own exiled with this artifact, then puts all permanent cards among them onto the battlefield.",
    }
    codex = {
        "name": "Codex Shredder",
        "type_line": "Artifact",
        "oracle_text": "{T}: Target player mills a card. (They put the top card of their library into their graveyard.)\n{5}, {T}, Sacrifice this artifact: Return target card from your graveyard to your hand.",
    }
    assert _lane_covers(pyxis, sig)
    assert _lane_covers(codex, sig)


def test_board_wipe_lane_serves_reanimation_and_resilient_bombs():
    """The 'Board wipes' blurb promises 'resilience to rebuild' — deliver it: a
    repeatable-wrath commander (Mageta) wants reanimation (Breath of Life) to rebuild
    after the sweep and indestructible bombs (Zetalpa) that survive it."""
    sig = _sig("mass_removal")
    breath = {
        "name": "Breath of Life",
        "type_line": "Sorcery",
        "oracle_text": "Return target creature card from your graveyard to the battlefield.",
    }
    zetalpa = {
        "name": "Zetalpa, Primal Dawn",
        "type_line": "Legendary Creature — Elder Dinosaur",
        "keywords": [
            "Flying",
            "Double strike",
            "Vigilance",
            "Trample",
            "Indestructible",
        ],
        "oracle_text": "Flying, double strike, vigilance, trample, indestructible",
    }
    assert _lane_covers(breath, sig)
    assert _lane_covers(zetalpa, sig)


def test_self_blink_serves_etb_payoffs():
    """A self-blinking commander (Norin) re-enters constantly, firing 'whenever a
    creature enters' payoffs (Impact Tremors, Genesis Chamber) and doublers
    (Panharmonicon). The lane served neither."""
    sig = _sig("self_blink")
    tremors = {
        "name": "Impact Tremors",
        "type_line": "Enchantment",
        "oracle_text": "Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.",
    }
    panharmonicon = {
        "name": "Panharmonicon",
        "type_line": "Artifact",
        "oracle_text": "If an artifact or creature entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
    }
    assert _lane_covers(tremors, sig)
    assert _lane_covers(panharmonicon, sig)


def test_untap_lanes_serve_untap_auras():
    """Tui and La (tap-for-draw / untap-for-counter) wants untap auras like Freed from
    the Real ('{U}: untap enchanted creature') — the serve only had target/all/another/
    each, missing the 'enchanted/this' forms."""
    freed = {
        "name": "Freed from the Real",
        "type_line": "Enchantment — Aura",
        "oracle_text": "Enchant creature\n{U}: Tap enchanted creature.\n{U}: Untap "
        "enchanted creature.",
    }
    assert _lane_covers(freed, _sig("untap_engine"))
    assert _lane_covers(freed, _sig("tap_untap_matters"))


def test_self_lifeloss_serves_life_total_manipulation():
    """Selenia pays life as a resource (lifeloss scope you) — she wants life-total
    swaps/resets (Axis of Mortality, Repay in Kind), life recovery (Children of Korlis),
    and low-life wincons (Near-Death Experience)."""
    sig = _sig("lifeloss_matters", "you")
    axis = {
        "name": "Axis of Mortality",
        "type_line": "Enchantment",
        "oracle_text": "At the beginning of your upkeep, you may have two target players "
        "exchange life totals.",
    }
    children = {
        "name": "Children of Korlis",
        "type_line": "Creature — Human Rebel Cleric",
        "oracle_text": "Sacrifice this creature: You gain life equal to the life you've lost this turn. (Damage causes loss of life.)",
    }
    repay = {
        "name": "Repay in Kind",
        "type_line": "Sorcery",
        "oracle_text": "Each player's life total becomes the lowest life total among all players.",
    }
    for c in (axis, children, repay):
        assert _lane_covers(c, sig), c["name"]


def test_burn_serves_land_enter_punishers():
    sig = _sig("direct_damage")
    ankh = {
        "name": "Ankh of Mishra",
        "type_line": "Artifact",
        "oracle_text": "Whenever a land enters, this artifact deals 2 damage to that "
        "land's controller.",
    }
    assert _lane_covers(ankh, sig)


def test_redirect_lane_serves_damage_prevention():
    """A redirect-to-self commander (Hazduhr, Cho-Manno) also wants damage PREVENTION —
    Battlefield Medic, Worship — to blank the damage it soaks."""
    sig = _sig("damage_redirect")
    medic = {
        "name": "Battlefield Medic",
        "type_line": "Creature — Human Cleric",
        "oracle_text": "{T}: Prevent the next X damage that would be dealt to target creature this turn, where X is the number of Clerics on the battlefield.",
    }
    worship = {
        "name": "Worship",
        "type_line": "Enchantment",
        "oracle_text": "If you control a creature, damage that would reduce your life "
        "total to less than 1 reduces it to 1 instead.",
    }
    assert _lane_covers(medic, sig)
    assert _lane_covers(worship, sig)


def test_forced_attack_serves_extra_combat():
    sig = _sig("forced_attack")
    waw = {
        "name": "World at War",
        "type_line": "Sorcery",
        "oracle_text": "After the second main phase this turn, there's an additional combat phase followed by an additional main phase. At the beginning of that combat, untap all creatures that attacked this turn.\nRebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you may cast this card from exile without paying its mana cost.)",
    }
    assert _lane_covers(waw, sig)


def test_outlaw_lane_serves_outlaws_and_anthems():
    sig = _sig("outlaw_matters")
    pirate = {
        "name": "Some Pirate",
        "type_line": "Creature — Human Pirate",
        "oracle_text": "Menace",
    }
    rogue = {
        "name": "A Rogue",
        "type_line": "Creature — Merfolk Rogue",
        "oracle_text": "",
    }
    anthem = {
        "name": "Hellspur Posse Boss",
        "type_line": "Creature — Lizard Rogue",
        "oracle_text": 'Other outlaws you control have haste. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nWhen this creature enters, create two 1/1 red Mercenary creature tokens with "{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery."',
    }
    non = {"name": "Bear", "type_line": "Token Creature — Bear", "oracle_text": ""}
    assert _lane_covers(pirate, sig)
    assert _lane_covers(rogue, sig)
    assert _lane_covers(anthem, sig)
    assert not _lane_covers(non, sig)


def test_donate_lane_serves_drawback_creatures():
    """Jon Irenicus donates creatures to opponents — he wants creatures whose DOWNSIDE
    punishes their controller (Abyssal Persecutor 'you can't win', Flesh Reaver 'deals
    damage to you', Demonic Taskmaster 'upkeep: sacrifice a creature')."""
    sig = _sig("donate_matters")
    persecutor = {
        "name": "Abyssal Persecutor",
        "type_line": "Creature — Demon",
        "oracle_text": "Flying, trample\nYou can't win the game and your opponents "
        "can't lose the game.",
    }
    reaver = {
        "name": "Flesh Reaver",
        "type_line": "Creature — Phyrexian Horror",
        "oracle_text": "Whenever this creature deals damage to a creature or opponent, "
        "this creature deals that much damage to you.",
    }
    taskmaster = {
        "name": "Demonic Taskmaster",
        "type_line": "Creature — Demon",
        "oracle_text": "Flying\nAt the beginning of your upkeep, sacrifice a creature "
        "other than this creature.",
    }
    for c in (persecutor, reaver, taskmaster):
        assert _lane_covers(c, sig), c["name"]


def test_banding_lane_serves_banding_creatures():
    sig = _sig("banding_matters")
    hero = {
        "name": "Benalish Hero",
        "type_line": "Creature — Human Soldier",
        "keywords": ["Banding"],
        "oracle_text": "Banding (Any creatures with banding, and up to one without, can attack in a band. Bands are blocked as a group. If any creatures with banding you control are blocking or being blocked by a creature, you divide that creature's combat damage, not its controller, among any of the creatures it's being blocked by or is blocking.)",
    }
    assert _lane_covers(hero, sig)


def test_flicker_extra_handles_two_sentence():
    """_FLICKER_EXTRA (used by ltb/creature_etb/self_blink) must also catch two-sentence
    flicker (Charming Prince / Flickerwisp 'Exile … . Return it …') — it was still
    period-blocked, so ltb commanders missed those cards."""
    sig = _sig("ltb_matters")
    charming = {
        "name": "Charming Prince",
        "type_line": "Creature — Human Noble",
        "oracle_text": "When this creature enters, choose one —\n• Scry 2.\n• You gain "
        "3 life.\n• Exile another target creature you own. Return it to the battlefield "
        "under your control at the beginning of the next end step.",
    }
    assert _lane_covers(charming, sig)


def test_legend_rule_off_serves_copy_effects():
    """A legend-rule-off commander (Brothers Yamazaki) wants self-copy effects — having
    multiple copies of itself (Helm of the Host, Blade of Selves, Mirror Box)."""
    sig = _sig("legend_rule_off")
    helm = {
        "name": "Helm of the Host",
        "type_line": "Legendary Artifact — Equipment",
        "oracle_text": "At the beginning of combat on your turn, create a token that's a copy of equipped creature, except the token isn't legendary. That token gains haste.\nEquip {5}",
    }
    blade = {
        "name": "Blade of Selves",
        "type_line": "Artifact — Equipment",
        "oracle_text": "Equipped creature has myriad. (Whenever it attacks, for each opponent other than defending player, you may create a token copy that's tapped and attacking that player or a planeswalker they control. Exile the tokens at end of combat.)\nEquip {4}",
    }
    assert _lane_covers(helm, sig)
    assert _lane_covers(blade, sig)


def test_graveyard_lane_serves_etb_value_recursion_targets():
    """Graveyard/reanimator commanders (Alesha, Gisa) recur creatures with strong ETBs —
    edict-ETB (Fleshbag Marauder), value-ETB (Eternal Witness). The fuel lane served the
    mill/recursion but not the targets worth recurring."""
    sig = _sig("graveyard_matters", "you")
    fleshbag = {
        "name": "Fleshbag Marauder",
        "type_line": "Creature — Zombie Warrior",
        "oracle_text": "When this creature enters, each player sacrifices a creature of "
        "their choice.",
    }
    witness = {
        "name": "Eternal Witness",
        "type_line": "Creature — Human Shaman",
        "oracle_text": "When this creature enters, you may return target card from your graveyard to your hand.",
    }
    assert _lane_covers(fleshbag, sig)
    assert _lane_covers(witness, sig)


def test_dies_recursion_and_flicker_are_separate_avenues_on_etb_lanes():
    """Dies-recursion (death→return) and flicker (exile→return) are DISTINCT mechanics
    (CR: graveyard 700.4 vs exile 400.1, both LTB per 603.6c). An ETB-reuse / LTB
    commander wants BOTH — so the ETB/blink/ltb lanes carry them as SEPARATE avenues,
    not one combined flicker serve."""
    feign = {  # dies-recursion (death-return), NOT flicker
        "name": "Feign Death",
        "type_line": "Instant",
        "oracle_text": 'Until end of turn, target creature gains "When this creature dies, return it to the battlefield tapped under its owner\'s control with a +1/+1 counter on it."',
    }
    ephemerate = {  # flicker (exile-return), NOT dies-recursion
        "name": "Ephemerate",
        "type_line": "Instant",
        "oracle_text": "Exile target creature you control, then return it to the battlefield under its owner's control.\nRebound",
    }
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
    cards = {
        "Shared Animosity": "Whenever a creature you control attacks, it gets +1/+0 "
        "until end of turn for each other attacking creature that shares a creature "
        "type with it.",
        "Coat of Arms": "Each creature gets +1/+1 for each other creature on the "
        "battlefield that shares at least one creature type with it.",
        "Vanquisher's Banner": "As this artifact enters, choose a creature type.\n"
        "Creatures you control of the chosen type get +1/+1.",
        "Herald's Horn": "As this artifact enters, choose a creature type.\nCreature "
        "spells you cast of the chosen type cost {1} less to cast.",
    }
    for name, oracle in cards.items():
        assert _lane_covers({"name": name, "oracle_text": oracle}, sig), name
    # Precision: a plain unrelated card is NOT credited as a tribal anthem.
    bolt = {
        "name": "Lightning Bolt",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    }
    assert _lane_covers(bolt, sig) is False


def test_activated_ability_lane_serves_costly_activated_creatures():
    """A cost-reducer / untapper commander (Agatha, Training Grounds) wants the PAYOFF
    targets — creatures with an expensive mana-cost activated ability to exploit the
    discount/untap. The serve credited reducers but not the targets."""
    sig = _sig("activated_ability", "you")
    for name, oracle in [
        ("Bhaal's Invoker", "{8}: This creature deals 4 damage to each opponent."),
        ("Wildheart Invoker", "{8}: Target creature gets +5/+5 and gains trample."),
        (
            "Captivating Crew",
            "{3}{R}: Gain control of target creature you don't control.",
        ),
    ]:
        card = {"name": name, "type_line": "Creature", "oracle_text": oracle}
        assert _lane_covers(card, sig) is True, name
    # control: a {T}-only ability (no mana cost) isn't a mana-discount target
    tapper = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "oracle_text": "{T}: Add {G}.",
    }
    assert _lane_covers(tapper, sig) is False


def test_graveyard_lane_serves_recursion_keyword_cards():
    """A self-graveyard deck wants the graveyard-recursion KEYWORD cards (Dredge,
    Flashback, Unearth, Escape, Disturb, Scavenge) whose graveyard mechanic is reminder
    text the oracle serve missed. Credit by keyword (CR 702.x)."""
    sig = _sig("graveyard_matters", "you")
    for name, kws in [
        ("Stinkweed Imp", ["Dredge"]),
        ("Gravedigger?", ["Unearth"]),
        ("Lingering Souls?", ["Flashback"]),
        ("Scrounging Bandar?", ["Scavenge"]),
    ]:
        card = {
            "name": name,
            "type_line": "Creature",
            "keywords": kws,
            "oracle_text": "",
        }
        assert _lane_covers(card, sig) is True, name
    # control: a plain Flying creature is not graveyard-relevant
    flyer = {
        "name": "Bird",
        "type_line": "Token Creature — Bird",
        "keywords": ["Flying"],
        "oracle_text": "Flying",
    }
    assert _lane_covers(flyer, sig) is False


def test_counters_lane_serves_counter_keyword_creatures():
    """A +1/+1-counter deck wants the counter-KEYWORD creatures (Undying, Graft, Riot,
    Bloodthirst, Fabricate) whose mechanic is reminder text the oracle serves miss.
    Credit them by the keyword (CR 702.x)."""
    sig = _sig("counters_matter", "you")
    cases = [
        ("Young Wolf", ["Undying"]),
        ("Cytoplast Root-Kin", ["Graft"]),
        ("Zhur-Taa Swine", ["Bloodthirst"]),
        ("Ardent Plea", ["Cascade"]),  # control: NOT a counter keyword
    ]
    results = {}
    for name, kws in cases:
        card = {
            "name": name,
            "type_line": "Creature",
            "keywords": kws,
            "oracle_text": "",
        }
        results[name] = _lane_covers(card, sig)
    assert results["Young Wolf"] is True
    assert results["Cytoplast Root-Kin"] is True
    assert results["Zhur-Taa Swine"] is True
    assert results["Ardent Plea"] is False  # cascade is not a counter keyword


def test_pillowfort_served_to_high_synergy_archetypes_only():
    """Pillowfort (Ghostly Prison, Propaganda, Sphere of Safety, Crawlspace) is attached
    ONLY to the archetypes whose pillowfort SYNERGY clears the ~4% background floor (Dan:
    gate on synergy, not raw inclusion): Monarch (86%), Goad/politics (44%), Superfriends
    (24%), Damage-prevention/fog (23%). Everything else — card-advantage/activated/voltron/
    spellslinger (at floor by synergy), Initiative (0%, aggressive), counterspell-control
    (0%), and go-wide/tokens — does NOT get it."""
    fort = [
        (
            "Ghostly Prison",
            "Creatures can't attack you unless their controller pays {2} "
            "for each creature they control that's attacking you.",
        ),
        (
            "Sphere of Safety",
            "Creatures can't attack you or a planeswalker you control "
            "unless their controller pays {X} for each of those creatures.",
        ),
        ("Crawlspace", "No more than two creatures can attack you each combat."),
    ]
    served = [
        ("monarch_matters", "you"),
        ("goad_matters", "opponents"),
        ("superfriends_matters", "you"),
        ("damage_prevention", "you"),
    ]
    for key, scope in served:
        sig = _sig(key, scope)
        for name, oracle in fort:
            assert _lane_covers(
                {"name": name, "type_line": "Enchantment", "oracle_text": oracle}, sig
            ), f"{key}/{name}"
    gp = {
        "name": "Ghostly Prison",
        "type_line": "Enchantment",
        "oracle_text": "Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.",
    }
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


def test_token_lanes_serve_creature_anthems():
    """A token go-wide deck's tokens ARE creatures, so symmetric creature anthems pump
    them — "creatures you control get +1/+1" (Glorious Anthem, Dictate of Heliod), not
    just token-specific ones. token_maker (incl. subject specs) and tokens_matter served
    only token anthems. These are SYMMETRIC ("creatures you control"), not "target
    creature" single pumps."""
    glorious = {
        "name": "Glorious Anthem",
        "type_line": "Enchantment",
        "oracle_text": "Creatures you control get +1/+1.",
    }
    virtue = {
        "name": "Intangible Virtue",
        "type_line": "Enchantment",
        "oracle_text": "Creature tokens you control get +1/+1 and have vigilance.",
    }
    for sig in [
        _sig("tokens_matter", "you"),
        _sig("token_maker", "you"),
        _sig_sub("token_maker", "Spirit"),
    ]:
        label = f"{sig.key}/{sig.subject or '-'}"
        assert _lane_covers(glorious, sig), f"{label}/glorious"
        assert _lane_covers(virtue, sig), f"{label}/virtue"
    # precision: a single-TARGET pump is not a go-wide anthem.
    brute = {
        "name": "Brute Force",
        "type_line": "Instant",
        "oracle_text": "Target creature gets +3/+3 until end of turn.",
    }
    assert _lane_covers(brute, _sig("token_maker", "you")) is False


def test_targeting_heroic_serves_single_target_buffs():
    """A heroic / targeting commander triggers when YOU cast a spell that TARGETS its
    creature (CR 115), so the enablers are cheap single-TARGET pumps/protection (Gods
    Willing, Brute Force, Defiant Strike). "each creature" anthems don't target and must
    NOT count; targeted REMOVAL ("destroy target creature") isn't a buff."""
    sig = _sig("targeting_matters", "any")
    for name, oracle in [
        (
            "Gods Willing",
            "Target creature you control gains protection from the color "
            "of your choice until end of turn.",
        ),
        ("Brute Force", "Target creature gets +3/+3 until end of turn."),
        ("Temur Battle Rage", "Target creature gains double strike until end of turn."),
    ]:
        assert _lane_covers(
            {"name": name, "type_line": "Instant", "oracle_text": oracle}, sig
        ), name
    # "each creature" anthem doesn't TARGET — must not count as a heroic enabler.
    anthem = {
        "name": "Glorious Anthem",
        "type_line": "Enchantment",
        "oracle_text": "Creatures you control get +1/+1.",
    }
    assert _lane_covers(anthem, sig) is False
    # targeted removal is not a buff for your own creature.
    rm = {
        "name": "Murder",
        "type_line": "Instant",
        "oracle_text": "Destroy target creature.",
    }
    assert _lane_covers(rm, sig) is False


def test_opponent_draw_punish_serves_group_draw_enablers():
    """A "whenever an opponent draws → punish" commander (Nekusar) wants the SYMMETRIC /
    forced group-draw enablers that make opponents draw extra (Howling Mine, Temple
    Bell, Dictate of Kruphix, Forced Fruition, Windfall) — distinct from "target player
    draws" (which could benefit only you). The serve credited only the payoff trigger."""
    sig = _sig("opponent_draw_matters", "opponents")
    cards = {
        "Temple Bell": "{T}: Each player draws a card.",
        "Howling Mine": "At the beginning of each player's draw step, if Howling Mine is "
        "untapped, that player draws an additional card.",
        "Forced Fruition": "Whenever an opponent casts a spell, that player draws seven "
        "cards.",
        "Windfall": "Each player discards their hand, then draws cards equal to the "
        "greatest number of cards a player discarded this way.",
    }
    for name, oracle in cards.items():
        assert _lane_covers(
            {"name": name, "type_line": "Artifact", "oracle_text": oracle}, sig
        ), name
    # Precision: your OWN cantrip ("You draw a card.") is not a force-opponents-draw enabler.
    assert (
        _lane_covers(
            {
                "name": "Cantrip",
                "type_line": "Instant",
                "oracle_text": "You draw a card.",
            },
            sig,
        )
        is False
    )


def test_lands_matter_serves_land_ramp():
    """lands_matter (Molimo, Lord Windgrace — P/T or payoff scales with land count) is
    the same archetype as landfall and wants land ramp, but its serve only credited
    "number of lands" payoffs, not the ramp/fetch that grows the count."""
    sig = _sig("lands_matter", "you")
    for name, oracle in [
        (
            "Skyshroud Claim",
            "Search your library for up to two Forest cards, put them "
            "onto the battlefield tapped, then shuffle.",
        ),
        (
            "Cultivate",
            "Search your library for up to two basic land cards, reveal them, "
            "put one onto the battlefield tapped and the other into your hand.",
        ),
        ("Crucible of Worlds", "You may play lands from your graveyard."),
    ]:
        card = {"name": name, "type_line": "Sorcery", "oracle_text": oracle}
        assert _lane_covers(card, sig) is True, name


def test_ramp_serves_basic_land_type_fetches():
    """Ramp serve must credit the basic-land-TYPE fetches (Skyshroud Claim, Nature's
    Lore, Three Visits, Farseek) — they search for "Forest/Plains/… cards", which don't
    contain the word "land", so the bare "search … for … land" missed them."""
    sig = _sig("ramp_matters", "you")
    for name, oracle in [
        (
            "Skyshroud Claim",
            "Search your library for up to two Forest cards, put them "
            "onto the battlefield tapped, then shuffle.",
        ),
        (
            "Nature's Lore",
            "Search your library for a Forest card, put that card onto "
            "the battlefield, then shuffle.",
        ),
        (
            "Farseek",
            "Search your library for a Plains, Island, Swamp, or Mountain card, "
            "put it onto the battlefield tapped, then shuffle.",
        ),
    ]:
        card = {"name": name, "type_line": "Sorcery", "oracle_text": oracle}
        assert _lane_covers(card, sig) is True, name


def test_sacrifice_serves_death_value_fodder():
    """A sacrifice deck wants DEATH-VALUE fodder — permanents that replace themselves
    with a card/token/search when they die or are put into a graveyard (Ichor Wellspring,
    Filigree Familiar, Mycosynth Wellspring). The serve keyed on 'whenever … dies' and
    missed the 'put into a graveyard' (artifacts) and 'When … dies' forms. (Confirmed by
    the cross-archetype audit: Sacrifice lane, 9.2x lift.)"""
    sig = _sig("sacrifice_matters", "you")
    for name, oracle in [
        (
            "Ichor Wellspring",
            "When this artifact enters or is put into a graveyard from "
            "the battlefield, draw a card.",
        ),
        (
            "Filigree Familiar",
            "When this creature enters, you gain 2 life.\nWhen this "
            "creature dies, draw a card.",
        ),
        (
            "Mycosynth Wellspring",
            "When this artifact enters or is put into a graveyard "
            "from the battlefield, you may search your library for a basic land card.",
        ),
    ]:
        assert _lane_covers(
            {"name": name, "type_line": "Artifact", "oracle_text": oracle}, sig
        ), name
    # Precision: a plain cantrip with no death/graveyard trigger is not sac fodder.
    cantrip = {
        "name": "Opt",
        "type_line": "Instant",
        "oracle_text": "Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nDraw a card.",
    }
    assert _lane_covers(cantrip, sig) is False


def test_symmetric_edict_serves_recurring_fodder():
    """A forced/symmetric-sacrifice commander (Braids — "each player sacrifices") loses
    its OWN board too, so it wants recurring fodder to survive: recurring token makers
    (Bitterblossom) and self-recurring creatures (Reassembling Skeleton)."""
    sig = _sig("edict_matters", "each")
    bb = {
        "name": "Bitterblossom",
        "type_line": "Kindred Enchantment — Faerie",
        "oracle_text": "At the beginning of your upkeep, you lose 1 life and create a "
        "1/1 black Faerie Rogue creature token with flying.",
    }
    skel = {
        "name": "Reassembling Skeleton",
        "type_line": "Creature — Skeleton Warrior",
        "oracle_text": "{1}{B}: Return this card from your graveyard to the battlefield "
        "tapped.",
    }
    assert _lane_covers(bb, sig) is True
    assert _lane_covers(skel, sig) is True


def test_copy_lanes_serve_etb_doublers_and_payoffs():
    """Token-copy / clone decks flood the board with creatures that ENTER, so they want
    ETB payoffs (Impact Tremors) and doublers (Panharmonicon) — every copy fires them."""
    pan = {
        "name": "Panharmonicon",
        "type_line": "Artifact",
        "oracle_text": "If an artifact or creature entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
    }
    tremors = {
        "name": "Impact Tremors",
        "type_line": "Enchantment",
        "oracle_text": "Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.",
    }
    for key in ("token_copy_matters", "clone_matters"):
        assert _lane_covers(pan, _sig(key, "you")) is True, f"{key}/Panharmonicon"
        assert _lane_covers(tremors, _sig(key, "you")) is True, f"{key}/Impact Tremors"


def test_clone_lane_serves_token_copy_effects():
    """A clone/copy commander (Stangg, Yosei) wants the token-copy gear too — Helm of
    the Host ("a token that's a copy of equipped creature"), Blade of Selves (myriad),
    Rite of Replication. The clone serve's bare "copy of target/that" missed the
    "equipped"/"it"/myriad forms."""
    sig = _sig("clone_matters", "you")
    helm = {
        "name": "Helm of the Host",
        "type_line": "Legendary Artifact — Equipment",
        "oracle_text": "At the beginning of combat on your turn, create a token that's a copy of equipped creature, except the token isn't legendary. That token gains haste.\nEquip {5}",
    }
    blade = {
        "name": "Blade of Selves",
        "type_line": "Artifact — Equipment",
        "oracle_text": "Equipped creature has myriad. (Whenever it attacks, for each opponent other than defending player, you may create a token copy that's tapped and attacking that player or a planeswalker they control. Exile the tokens at end of combat.)\nEquip {4}",
    }
    assert _lane_covers(helm, sig) is True
    assert _lane_covers(blade, sig) is True


def test_blocked_matters_serves_force_block_effects():
    """A 'becomes blocked' payoff (General Marhault Elsdragon: +3/+3 for each creature
    blocking it) wants force-block effects so the per-blocker bonus maxes — Lure /
    Nemesis Mask / Roar of Challenge force every able creature to block."""
    sig = _sig("blocked_matters", "you")
    lure = {
        "name": "Lure",
        "type_line": "Enchantment — Aura",
        "oracle_text": "Enchant creature\nAll creatures able to block enchanted "
        "creature do so.",
    }
    roar = {
        "name": "Roar of Challenge",
        "type_line": "Sorcery",
        "oracle_text": "All creatures able to block target creature this turn do so.\nFerocious — That creature gains indestructible until end of turn if you control a creature with power 4 or greater.",
    }
    assert _lane_covers(lure, sig) is True
    assert _lane_covers(roar, sig) is True
    # A plain anthem is not a force-block effect.
    anthem = {
        "name": "Glorious Anthem",
        "type_line": "Enchantment",
        "oracle_text": "Creatures you control get +1/+1.",
    }
    assert _lane_covers(anthem, sig) is False


def test_token_copy_serves_makers_and_doublers():
    """Esix converts each token she'd create into a copy of a chosen creature — so she
    wants token MAKERS (more tokens → more copies) and token DOUBLERS (double the
    copies), not just big bodies to copy."""
    sig = _sig("token_copy_matters", "you")
    hornet = {
        "name": "Hornet Queen",
        "type_line": "Creature — Insect",
        "oracle_text": "Flying, deathtouch\nWhen this creature enters, create four 1/1 "
        "green Insect creature tokens with flying and deathtouch.",
    }
    avenger = {
        "name": "Avenger of Zendikar",
        "type_line": "Creature — Elemental",
        "oracle_text": "When this creature enters, create a 0/1 green Plant creature token for each land you control.\nLandfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control.",
    }
    adrix = {
        "name": "Adrix and Nev, Twincasters",
        "type_line": "Legendary Creature — Merfolk Wizard",
        "oracle_text": "Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nIf one or more tokens would be created under your control, twice that many of those tokens are created instead.",
    }
    assert _lane_covers(hornet, sig) is True
    assert _lane_covers(avenger, sig) is True
    assert _lane_covers(adrix, sig) is True


# ── Long-tail coverage clusters (workflow-diagnosed, verify-before-add) ────────


def test_extra_upkeep_serves_upkeep_payoffs_not_ramp():
    sig = _sig("extra_upkeep", "you")
    as_foretold = {
        "name": "As Foretold",
        "type_line": "Enchantment",
        "oracle_text": (
            "At the beginning of your upkeep, put a time counter on this "
            "enchantment.\nOnce each turn, you may pay {0} rather than pay the "
            "mana cost for a spell you cast with mana value X or less, where X is "
            "the number of time counters on this enchantment."
        ),
    }
    sol_ring = {
        "name": "Sol Ring",
        "type_line": "Artifact",
        "oracle_text": "{T}: Add {C}{C}.",
    }
    assert _lane_covers(as_foretold, sig) is True
    assert _lane_covers(sol_ring, sig) is False  # no upkeep trigger — not a payoff


def test_extra_end_step_serves_end_step_payoffs():
    sig = _sig("extra_end_step", "you")
    agent = {
        "name": "Agent of Treachery",
        "type_line": "Creature — Human Rogue",
        "oracle_text": (
            "When this creature enters, gain control of target permanent.\n"
            "At the beginning of your end step, if you control three or more "
            "permanents you don't own, draw three cards."
        ),
    }
    chimil = {
        "name": "Chimil, the Inner Sun",
        "type_line": "Legendary Artifact",
        "oracle_text": (
            "Spells you control can't be countered.\n"
            "At the beginning of your end step, discover 5. (Exile cards from the "
            "top of your library until you exile a nonland card with mana value 5 "
            "or less. Cast it without paying its mana cost or put it into your "
            "hand. Put the rest on the bottom in a random order.)"
        ),
    }
    assert _lane_covers(agent, sig) is True
    assert _lane_covers(chimil, sig) is True


def test_noncombat_damage_serves_player_directed_burn():
    sig = _sig("noncombat_damage_payoff", "you")
    boltwave = {
        "name": "Boltwave",
        "type_line": "Sorcery",
        "oracle_text": "Boltwave deals 3 damage to each opponent.",
    }
    # "deals damage … equal to" (no explicit number) must still serve a doubler.
    hidetsugu = {
        "name": "Heartless Hidetsugu",
        "type_line": "Legendary Creature — Ogre Shaman",
        "oracle_text": (
            "{T}: Heartless Hidetsugu deals damage to each player equal to half "
            "that player's life total, rounded down."
        ),
    }
    price = {
        "name": "Price of Progress",
        "type_line": "Instant",
        "oracle_text": (
            "Price of Progress deals damage to each player equal to twice the "
            "number of nonbasic lands that player controls."
        ),
    }
    # A creature-only sweeper hits no player and must NOT serve the doubler lane.
    pyroclasm = {
        "name": "Pyroclasm",
        "type_line": "Sorcery",
        "oracle_text": "Pyroclasm deals 2 damage to each creature.",
    }
    assert _lane_covers(boltwave, sig) is True
    assert _lane_covers(hidetsugu, sig) is True
    assert _lane_covers(price, sig) is True
    assert _lane_covers(pyroclasm, sig) is False


def test_creatures_matter_serves_board_scaling_lord():
    sig = _sig("creatures_matter", "you")
    leonardo = {
        "name": "Leonardo, Big Brother",
        "type_line": "Legendary Creature — Mutant Ninja Turtle",
        "oracle_text": (
            "Sneak {W} (You may cast this spell for {W} if you also return an "
            "unblocked attacker you control to hand during the declare blockers "
            "step. He enters tapped and attacking.)\n"
            "Leonardo gets +1/+0 for each other creature you control."
        ),
    }
    assert _lane_covers(leonardo, sig) is True


def test_artifacts_matter_serves_artifact_dig():
    sig = _sig("artifacts_matter", "you")
    casey = {
        "name": "Casey Jones, Jury-Rig Justiciar",
        "type_line": "Legendary Creature — Human Berserker",
        "oracle_text": (
            "Haste\n"
            "When Casey Jones enters, look at the top four cards of your library. "
            "You may reveal an artifact card from among them and put it into your "
            "hand. Put the rest on the bottom of your library in a random order."
        ),
    }
    assert _lane_covers(casey, sig) is True


# ── Serve-gap fixes from the archetype-normalized failing-tail analysis ───────
# Real cards (full oracle_text + type_line from Scryfall bulk) that the failing
# commanders rank as top-synergy but the lanes they open were not crediting.

COMBAT_CELEBRANT = {
    "name": "Combat Celebrant",
    "type_line": "Creature — Human Warrior",
    "oracle_text": (
        "If this creature hasn't been exerted this turn, you may exert it as it "
        "attacks. When you do, untap all other creatures you control and after "
        "this phase, there is an additional combat phase. (An exerted creature "
        "won't untap during your next untap step.)"
    ),
}
MORAUG = {
    "name": "Moraug, Fury of Akoum",
    "type_line": "Legendary Creature — Minotaur Warrior",
    "oracle_text": (
        "Each creature you control gets +1/+0 for each time it has attacked this "
        "turn.\nLandfall — Whenever a land you control enters, if it's your main "
        "phase, there's an additional combat phase after this phase. At the "
        "beginning of that combat, untap all creatures you control."
    ),
}
AGGRAVATED_ASSAULT = {
    "name": "Aggravated Assault",
    "type_line": "Enchantment",
    "oracle_text": (
        "{3}{R}{R}: Untap all creatures you control. After this main phase, there "
        "is an additional combat phase followed by an additional main phase. "
        "Activate only as a sorcery."
    ),
}


def test_attack_matters_serves_extra_combat_enablers():
    # An attack-trigger commander wants more combats — each extra combat is another
    # round of attack triggers. These were only credited to the narrow extra_combats
    # lane, so attack_matters commanders (Winota, Johan, Umaro) read them as off-theme.
    sig = _sig("attack_matters", "you")
    assert _lane_covers(COMBAT_CELEBRANT, sig) is True
    assert _lane_covers(MORAUG, sig) is True
    assert _lane_covers(AGGRAVATED_ASSAULT, sig) is True
    # Over-fire guard: a vanilla beater with no attack payoff is NOT served.
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert _lane_covers(grizzly, sig) is False


def test_attack_matters_serves_extra_turn_spells():
    # attack_matters already credits "additional combat phase" — another round of attack
    # triggers. An extra TURN (Time Warp) is the strict superset: a full turn, combat
    # included, so the attack happens again. Narset, Enlightened Master (free-casts
    # noncreature spells on attack) snowballs hardest off extra turns, but every
    # attack-trigger commander wants the replay. Real oracle.
    sig = _sig("attack_matters", "you")
    time_warp = {
        "name": "Time Warp",
        "type_line": "Sorcery",
        "mana_cost": "{3}{U}{U}",
        "oracle_text": "Target player takes an extra turn after this one.",
    }
    temporal_mastery = {
        "name": "Temporal Mastery",
        "type_line": "Sorcery",
        "mana_cost": "{5}{U}{U}",
        "oracle_text": (
            "Take an extra turn after this one. Exile Temporal Mastery.\n"
            "Miracle {1}{U} (You may cast this card for its miracle cost when you draw "
            "it if it's the first card you drew this turn.)"
        ),
    }
    assert serves(time_warp, sig) is True
    assert serves(temporal_mastery, sig) is True
    # Over-fire guard: an "additional LAND this turn" ramp cantrip (Explore) is not an
    # extra TURN — the extra-turn clause must not leak to "additional land". Real oracle.
    explore = {
        "name": "Explore",
        "type_line": "Sorcery",
        "mana_cost": "{1}{G}",
        "oracle_text": "You may play an additional land this turn.\nDraw a card.",
    }
    assert serves(explore, sig) is False


BRIBERY = {
    "name": "Bribery",
    "type_line": "Sorcery",
    "oracle_text": (
        "Search target opponent's library for a creature card and put that card "
        "onto the battlefield under your control. Then that player shuffles."
    ),
}
ACQUIRE = {
    "name": "Acquire",
    "type_line": "Sorcery",
    "oracle_text": (
        "Search target opponent's library for an artifact card and put that card "
        "onto the battlefield under your control. Then that player shuffles."
    ),
}


def test_gain_control_serves_steal_from_opponent_library():
    # Bribery/Acquire take a card from an opponent's deck and seat it under YOUR
    # control — theft, the gain_control lane's whole point — but the serve only
    # matched the literal "gain control of" phrasing.
    sig = _sig("gain_control", "you")
    assert _lane_covers(BRIBERY, sig) is True
    assert _lane_covers(ACQUIRE, sig) is True
    # Over-fire guard: self-reanimation also "put ... onto the battlefield under
    # your control" but takes from a graveyard, not an opponent's LIBRARY — not theft.
    reanimate = {
        "name": "Reanimate",
        "type_line": "Sorcery",
        "oracle_text": (
            "Put target creature card from a graveyard onto the battlefield under "
            "your control. You lose life equal to its mana value."
        ),
    }
    assert _lane_covers(reanimate, sig) is False


PANHARMONICON = {
    "name": "Panharmonicon",
    "type_line": "Artifact",
    "oracle_text": (
        "If an artifact or creature entering causes a triggered ability of a "
        "permanent you control to trigger, that ability triggers an additional time."
    ),
}
STRIONIC_RESONATOR = {
    "name": "Strionic Resonator",
    "type_line": "Artifact",
    "oracle_text": (
        "{2}, {T}: Copy target triggered ability you control. You may choose new "
        'targets for the copy. (A triggered ability uses the words "when," '
        '"whenever," or "at.")'
    ),
}


def test_creature_etb_serves_trigger_doublers():
    # Panharmonicon literally doubles ETB triggers; Strionic copies any triggered
    # ability. An ETB-payoff commander wants both, but they name no "enters" trigger
    # of their own, so the creature_etb serve missed them.
    sig = _sig("creature_etb", "you")
    assert _lane_covers(PANHARMONICON, sig) is True
    assert _lane_covers(STRIONIC_RESONATOR, sig) is True
    # Over-fire guard: a plain vanilla creature is NOT a trigger doubler.
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert _lane_covers(grizzly, sig) is False


# ── Theft / cast-an-exiled-card cluster (Gonti / Hostage Taker / Thief of Sanity) ──
GONTI = {
    "name": "Gonti, Lord of Luxury",
    "type_line": "Legendary Creature — Aetherborn Rogue",
    "oracle_text": (
        "Deathtouch\n"
        "When Gonti enters, look at the top four cards of target opponent's "
        "library, exile one of them face down, then put the rest on the bottom of "
        "that library in a random order. You may cast that card for as long as it "
        "remains exiled, and you may spend mana as though it were mana of any "
        "color to cast it."
    ),
}
HOSTAGE_TAKER = {
    "name": "Hostage Taker",
    "type_line": "Creature — Aetherborn Pirate",
    "oracle_text": (
        "When Hostage Taker enters, exile another target artifact or creature "
        "until Hostage Taker leaves the battlefield. You may cast that card for "
        "as long as it remains exiled, and you may spend mana as though it were "
        "mana of any color to cast it."
    ),
}
THIEF_OF_SANITY = {
    "name": "Thief of Sanity",
    "type_line": "Creature — Specter",
    "oracle_text": (
        "Flying\n"
        "Whenever Thief of Sanity deals combat damage to a player, look at the "
        "top three cards of that player's library, exile one of them face down, "
        "then put the rest into that player's graveyard. You may look at and play "
        "that card for as long as it remains exiled, and you may spend mana as "
        "though it were mana of any color to cast it."
    ),
}
# Over-fire guard for theft_matters: self-impulse (your OWN library) is not theft.
VALAKUT_EXPLORATION = {
    "name": "Valakut Exploration",
    "type_line": "Enchantment",
    "oracle_text": (
        "At the beginning of your end step, exile the top card of your library "
        "for each land that entered the battlefield under your control this turn. "
        "You may play those cards until the end of your next turn. At the "
        "beginning of your next end step, Valakut Exploration deals damage to "
        "each opponent equal to the number of those cards that remain exiled."
    ),
}


def test_impulse_and_cast_from_exile_serve_exile_then_cast_engines():
    # "Exile a card, you may cast it for as long as it remains exiled" is the impulse /
    # cast-from-exile engine (Gonti, Hostage Taker, Thief of Sanity).
    for sig in (_sig("impulse_top_play"), _sig("cast_from_exile")):
        assert _lane_covers(GONTI, sig) is True, sig.key
        assert _lane_covers(HOSTAGE_TAKER, sig) is True, sig.key
        assert _lane_covers(THIEF_OF_SANITY, sig) is True, sig.key


def test_theft_matters_serves_opponent_library_theft_not_self_impulse():
    # theft_matters is steal-from-OPPONENT — Gonti/Thief dig an opponent's library;
    # Valakut Exploration impulses YOUR OWN library and must NOT register as theft.
    sig = _sig("theft_matters", "opponents")
    assert _lane_covers(GONTI, sig) is True
    assert _lane_covers(THIEF_OF_SANITY, sig) is True
    assert _lane_covers(VALAKUT_EXPLORATION, sig) is False


# ── creatures_matter serves creature cost-reducers + board-scaled payoffs ────────
GORECLAW = {
    "name": "Goreclaw, Terror of Qal Sisma",
    "type_line": "Legendary Creature — Bear",
    "oracle_text": (
        "Creature spells you cast with power 4 or greater cost {2} less to cast.\n"
        "Whenever Goreclaw attacks, each creature you control with power 4 or "
        "greater gets +1/+1 and gains trample until end of turn."
    ),
}
GHALTA = {
    "name": "Ghalta, Primal Hunger",
    "type_line": "Legendary Creature — Elder Dinosaur",
    "oracle_text": (
        "This spell costs {X} less to cast, where X is the total power of "
        "creatures you control.\n"
        "Trample (This creature can deal excess combat damage to the player or "
        "planeswalker it's attacking.)"
    ),
}


def test_creatures_matter_serves_creature_cost_reducer_and_board_payoff():
    # A creatures deck wants the creature-spell cost reducers that let it deploy more
    # bodies (Goreclaw) and the board-scaled finishers it casts off a wide board
    # (Ghalta). The flip-commanders (Surrak, Maelstrom, Zilortha) open creatures_matter,
    # not power_matters, so these read as off-theme before.
    sig = _sig("creatures_matter", "you")
    assert _lane_covers(GORECLAW, sig) is True
    assert _lane_covers(GHALTA, sig) is True
    # Over-fire guard: a pure counterspell is not a creatures payoff.
    counterspell = {
        "name": "Counterspell",
        "type_line": "Instant",
        "oracle_text": "Counter target spell.",
    }
    assert _lane_covers(counterspell, sig) is False


# ── mass_removal serves board-protection (asymmetric wrath) ──────────────────────
SELFLESS_SPIRIT = {
    "name": "Selfless Spirit",
    "type_line": "Creature — Spirit Cleric",
    "oracle_text": (
        "Flying\n"
        "Sacrifice this creature: Creatures you control gain indestructible until "
        "end of turn."
    ),
}


def test_mass_removal_serves_board_indestructible_granters():
    # A repeatable-wrath commander (Mageta) wants to wrath one-sided — keep its own
    # board through the sweep. The lane already credits indestructible CREATURES via
    # keyword, but not the GRANTERS (Selfless Spirit) that protect the whole team.
    sig = _sig("mass_removal", "you")
    assert _lane_covers(SELFLESS_SPIRIT, sig) is True
    # Over-fire guard: a single-target protection spell is not board protection.
    gods_willing = {
        "name": "Gods Willing",
        "type_line": "Instant",
        "oracle_text": (
            "Target creature you control gains protection from the color of your "
            "choice until end of turn. Scry 1."
        ),
    }
    assert _lane_covers(gods_willing, sig) is False


# ── landfall serves land-recursion-from-graveyard (puts lands onto battlefield) ──
def test_landfall_serves_return_lands_from_graveyard():
    # "Return all land cards from your graveyard to the battlefield" floods lands in =
    # a huge landfall payoff. The lands-from-grave extra only matched "play lands from
    # your graveyard", missing the direct mass-return forms (Splendid Reclamation,
    # Titania, World Shaper).
    sig = _sig("landfall", "you")
    splendid = {
        "name": "Splendid Reclamation",
        "type_line": "Sorcery",
        "oracle_text": "Return all land cards from your graveyard to the battlefield tapped.",
    }
    assert _lane_covers(splendid, sig) is True
    # Over-fire guard: returning a CREATURE from the graveyard is reanimation, not
    # land recursion — not a landfall enabler.
    raise_dead = {
        "name": "Raise Dead",
        "type_line": "Sorcery",
        "oracle_text": "Return target creature card from your graveyard to your hand.",
    }
    assert _lane_covers(raise_dead, sig) is False


def test_gain_control_vs_theft_borrow_and_cast_are_distinct():
    # PRECISION boundary: gain_control is a BATTLEFIELD control change. Borrow-and-cast
    # engines (Gonti/Hostage Taker) exile a card and let you CAST it — playing what you
    # don't own — which is theft_matters, NOT gain_control. Bribery is the genuine
    # gain-control case: it seats a permanent onto the battlefield UNDER YOUR CONTROL.
    gc = _sig("gain_control", "you")
    theft = _sig("theft_matters", "opponents")
    assert (
        _lane_covers(BRIBERY, gc) is True
    )  # library -> battlefield under your control
    assert _lane_covers(GONTI, gc) is False  # exile + cast is not a control change
    assert _lane_covers(HOSTAGE_TAKER, gc) is False
    # Their real home is theft_matters (play-what-you-don't-own).
    assert _lane_covers(GONTI, theft) is True
    assert _lane_covers(HOSTAGE_TAKER, theft) is True


def test_impulse_top_play_serves_cast_from_exile_payoffs():
    # An impulse commander exiles cards and casts them — so it wants the payoffs that
    # reward casting from exile (Wild-Magic Sorcerer: "the first spell you cast from
    # exile each turn has cascade"). Already served by cast_from_exile; impulse decks
    # do the same thing and open impulse_top_play.
    sig = _sig("impulse_top_play", "you")
    wild_magic = {
        "name": "Wild-Magic Sorcerer",
        "type_line": "Creature — Human Wizard",
        "oracle_text": (
            "The first spell you cast from exile each turn has cascade. (When you "
            "cast your first spell from exile, exile cards from the top of your "
            "library until you exile a nonland card that costs less. You may cast it "
            "without paying its mana cost. Put the exiled cards on the bottom in a "
            "random order.)"
        ),
    }
    assert _lane_covers(wild_magic, sig) is True
    # The bare "Whenever you cast a spell from exile" trigger payoff (Passionate
    # Archaeologist, Nalfeshnee) — distinct from "spell(s) you cast from exile". An
    # impulse deck casts its exiled cards, firing these. cast_from_exile already
    # serves them; impulse_top_play must too.
    passionate_archaeologist = {
        "name": "Passionate Archaeologist",
        "type_line": "Legendary Enchantment — Background",
        "oracle_text": (
            'Commander creatures you own have "Whenever you cast a spell from '
            "exile, this creature deals damage equal to that spell's mana value "
            'to target opponent."'
        ),
    }
    assert _lane_covers(passionate_archaeologist, sig) is True
    # The paradox "from anywhere other than your hand" payoff (Keeper of Secrets) —
    # casting from exile IS from-anywhere-other-than-hand, so an impulse deck fires it.
    keeper_of_secrets = {
        "name": "Keeper of Secrets",
        "type_line": "Creature — Demon",
        "oracle_text": (
            "First strike, haste\nSymphony of Pain — Whenever you cast a spell "
            "from anywhere other than your hand, this creature deals damage equal "
            "to that spell's mana value to target opponent."
        ),
    }
    assert _lane_covers(keeper_of_secrets, sig) is True
    # Over-fire guard: a vanilla creature is not a cast-from-exile payoff.
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert _lane_covers(grizzly, sig) is False


def test_xspell_matters_serves_x_spells_and_doublers():
    # An X-matters commander (Zaxara, Rosheen) is built from X-spells and wants the
    # X-doublers. Serve credits cards whose PRINTED mana cost contains {X} (CR 107.3 —
    # a fixed characteristic, cf. CR 702.156a "cards with {X} in their mana cost") plus
    # oracle X-payoffs. Real oracle/cost.
    sig = _sig("xspell_matters", "you")
    stonecoil = {
        "name": "Stonecoil Serpent",
        "type_line": "Artifact Creature — Snake",
        "mana_cost": "{X}",
        "oracle_text": (
            "Reach, trample, protection from multicolored\nThis creature enters with "
            "X +1/+1 counters on it."
        ),
    }
    assert _lane_covers(stonecoil, sig) is True  # {X} in mana cost
    unbound = {
        "name": "Unbound Flourishing",
        "type_line": "Enchantment",
        "mana_cost": "{2}{G}",
        "oracle_text": (
            "Whenever you cast a permanent spell with a mana cost that contains {X}, "
            "double the value of X.\nWhenever you cast an instant or sorcery spell or "
            "activate an ability, if that spell's mana cost or that ability's "
            "activation cost contains {X}, copy that spell or ability. You may choose "
            "new targets for the copy."
        ),
    }
    assert _lane_covers(unbound, sig) is True  # oracle X-doubler payoff
    # Over-fire guard: a fixed-cost vanilla creature is not an X-spell.
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "oracle_text": "",
    }
    assert _lane_covers(grizzly, sig) is False


def test_unspent_mana_serves_mana_amplification():
    # An unspent-mana commander (Omnath, Locus of Mana; Kruphix) keeps mana between steps,
    # so it wants mana AMPLIFICATION — untap-all-lands (Bear Umbra) and mana-doublers
    # (Mana Reflection) — to generate more mana to keep. The sweep's bare "unspent mana"
    # serve credited none of these. Real oracle.
    sig = _sig("unspent_mana", "you")
    bear_umbra = {
        "name": "Bear Umbra",
        "type_line": "Enchantment — Aura",
        "oracle_text": (
            'Enchant creature\nEnchanted creature gets +2/+2 and has "Whenever this '
            'creature attacks, untap all lands you control."\nUmbra armor (If enchanted '
            "creature would be destroyed, instead remove all damage from it and destroy "
            "this Aura.)"
        ),
    }
    assert _lane_covers(bear_umbra, sig) is True
    mana_reflection = {
        "name": "Mana Reflection",
        "type_line": "Enchantment",
        "oracle_text": (
            "If you tap a permanent for mana, it produces twice as much of that mana "
            "instead."
        ),
    }
    assert _lane_covers(mana_reflection, sig) is True
    # Over-fire guard: a plain mana dork is not amplification.
    llanowar = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "oracle_text": "{T}: Add {G}.",
    }
    assert _lane_covers(llanowar, sig) is False


def test_curse_matters_is_a_named_archetype_lane():
    # Lynde recurs/attaches Curses ("Whenever a Curse is put into your graveyard ...
    # attach a Curse ...") — it wants the Curse subtype. A named-archetype lane served
    # by the Curse TYPE (not oracle prose). Real oracle.
    lynde = {
        "name": "Lynde, Cheerful Tormentor",
        "type_line": "Legendary Creature — Human Warlock",
        "oracle_text": (
            "Deathtouch\nWhenever a Curse is put into your graveyard from the "
            "battlefield, return it to the battlefield attached to you at the "
            "beginning of the next end step.\nAt the beginning of your upkeep, you may "
            "attach a Curse attached to you to one of your opponents. If you do, draw "
            "two cards."
        ),
    }
    assert "curse_matters" in {s.key for s in extract_signals(lynde)}
    sig = _sig("curse_matters", "you")
    curse_of_misfortunes = {
        "name": "Curse of Misfortunes",
        "type_line": "Enchantment — Aura Curse",
        "oracle_text": (
            "Enchant player\nAt the beginning of your upkeep, you may search your "
            "library for a Curse card that doesn't have the same name as a Curse "
            "attached to enchanted player, put it onto the battlefield attached to "
            "that player, then shuffle."
        ),
    }
    assert _lane_covers(curse_of_misfortunes, sig) is True
    # Over-fire guard: a non-Curse Aura is not a Curse.
    pacifism = {
        "name": "Pacifism",
        "type_line": "Enchantment — Aura",
        "oracle_text": "Enchant creature\nEnchanted creature can't attack or block.",
    }
    assert _lane_covers(pacifism, sig) is False


def test_opponent_discard_serves_hellbent_punishers():
    # A hand-attack commander empties opponents' hands (Myojin of Night's Reach: "Each
    # opponent discards their hand"), so it wants the empty-hand (8-Rack) punishers that
    # cash the empty hand in. Opponent-anchored so a self-hellbent / draw card stays out.
    sig = _sig("opponent_discard", "opponents")
    the_rack = {
        "name": "The Rack",
        "type_line": "Artifact",
        "oracle_text": (
            "As this artifact enters, choose an opponent.\nAt the beginning of the "
            "chosen player's upkeep, this artifact deals X damage to that player, "
            "where X is 3 minus the number of cards in their hand."
        ),
    }
    assert _lane_covers(the_rack, sig) is True
    shrieking_affliction = {
        "name": "Shrieking Affliction",
        "type_line": "Enchantment",
        "oracle_text": (
            "At the beginning of each opponent's upkeep, if that player has one or "
            "fewer cards in hand, they lose 3 life."
        ),
    }
    assert _lane_covers(shrieking_affliction, sig) is True
    # Over-fire guard: a plain draw spell ("cards in hand" in a draw context) is not a
    # hellbent punisher.
    divination = {
        "name": "Divination",
        "type_line": "Sorcery",
        "oracle_text": "Draw two cards.",
    }
    assert _lane_covers(divination, sig) is False


def test_villainous_choice_is_a_named_mechanic_lane():
    # The Valeyard doubles every villainous choice opponents face — its whole synergy is
    # villainous-choice cards (This Is How It Ends, Ensnared by the Mara, Hunted by The
    # Family). A named mechanic, like venture / initiative, with its own lane. Real oracle.
    valeyard = {
        "name": "The Valeyard",
        "type_line": "Legendary Creature — Time Lord Noble",
        "oracle_text": (
            "If an opponent would face a villainous choice, they face that choice an "
            "additional time. (They can make the same or different choices.)\nWhile "
            "voting, you may vote an additional time."
        ),
    }
    assert "villainous_choice" in {s.key for s in extract_signals(valeyard)}
    sig = _sig("villainous_choice", "you")
    this_is_how_it_ends = {
        "name": "This Is How It Ends",
        "type_line": "Instant",
        "oracle_text": (
            "Target creature's owner shuffles it into their library, then faces a "
            "villainous choice — They lose 5 life, or they shuffle another creature "
            "they own into their library."
        ),
    }
    assert _lane_covers(this_is_how_it_ends, sig) is True


def test_low_power_matters_serves_cast_low_power_enabler():
    # low_power_matters served "creatures you control with power N or less" payoffs but
    # missed the casting-ENABLER phrasing "cast a creature spell with power N or less"
    # (Assemble the Players) that a small-creatures commander (Delney) is built around.
    # Still an enabler, not a flood of vanilla small bodies, so precise. Real oracle.
    sig = _sig("low_power_matters", "you")
    assemble = {
        "name": "Assemble the Players",
        "type_line": "Enchantment",
        "oracle_text": (
            "You may look at the top card of your library any time.\nOnce each turn, "
            "you may cast a creature spell with power 2 or less from the top of your "
            "library."
        ),
    }
    assert _lane_covers(assemble, sig) is True
    # Over-fire guard: a vanilla small creature is not a low-power payoff/enabler.
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert _lane_covers(grizzly, sig) is False


def test_discard_outlet_serves_discard_payoffs():
    # A loot/rummage commander (Jaya Ballard, Alexi) discards a lot, so it wants the
    # payoffs that reward discarding — Containment Construct turns each discard into a
    # castable card. The auto-serve only credited other discard OUTLETS.
    sig = _sig("discard_outlet", "you")
    containment_construct = {
        "name": "Containment Construct",
        "type_line": "Artifact",
        "oracle_text": (
            "Whenever you discard a card, you may exile that card from your "
            "graveyard. If you do, you may play that card this turn."
        ),
    }
    assert _lane_covers(containment_construct, sig) is True
    # Over-fire guard: a vanilla creature is not a discard payoff.
    grizzly = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert _lane_covers(grizzly, sig) is False


def test_mass_bounce_serves_creature_mass_bounce():
    # mass_bounce matched only "return each PERMANENT", missing "return each CREATURE
    # … to its owner's hand" (Scourge of Fleets). A mass-bounce commander (Slinn Voda)
    # wants creature mass-bounce too.
    sig = _sig("mass_bounce", "any")
    scourge = {
        "name": "Scourge of Fleets",
        "type_line": "Creature — Kraken",
        "oracle_text": (
            "When this creature enters, return each creature your opponents control "
            "with toughness X or less to its owner's hand, where X is the number of "
            "Islands you control."
        ),
    }
    assert _lane_covers(scourge, sig) is True
    # Over-fire guard: single-target bounce is tempo, not mass bounce.
    boomerang = {
        "name": "Boomerang",
        "type_line": "Instant",
        "oracle_text": "Return target permanent to its owner's hand.",
    }
    assert _lane_covers(boomerang, sig) is False


def test_dies_recursion_is_superset_of_undying_persist():
    # dies_recursion is the BROAD "creatures recur when they die" category (with or
    # without counters); undying_persist_matters is the counter-bearing SUBSET (undying
    # = +1/+1 per CR 702.93a, persist = -1/-1 per CR 702.79a). So undying/persist cards
    # belong to BOTH; bare dies-return (Supernatural Stamina) only to dies_recursion.
    geralfs = {
        "name": "Geralf's Messenger",
        "type_line": "Creature — Zombie",
        "oracle_text": (
            "This creature enters tapped.\n"
            "When this creature enters, target opponent loses 2 life.\n"
            "Undying (When this creature dies, if it had no +1/+1 counters on it, "
            "return it to the battlefield under its owner's control with a +1/+1 "
            "counter on it.)"
        ),
    }
    kitchen_finks = {
        "name": "Kitchen Finks",
        "type_line": "Creature — Ouphe",
        "oracle_text": (
            "When this creature enters, you gain 2 life.\n"
            "Persist (When this creature dies, if it had no -1/-1 counters on it, "
            "return it to the battlefield under its owner's control with a -1/-1 "
            "counter on it.)"
        ),
    }
    supernatural_stamina = {
        "name": "Supernatural Stamina",
        "type_line": "Instant",
        "oracle_text": (
            'Until end of turn, target creature gets +2/+0 and gains "When this '
            "creature dies, return it to the battlefield tapped under its owner's "
            'control."'
        ),
    }
    dr = _sig("dies_recursion", "you")
    up = _sig("undying_persist_matters", "you")
    # Superset: undying/persist AND bare dies-return are all dies_recursion.
    assert _lane_covers(geralfs, dr) is True
    assert _lane_covers(kitchen_finks, dr) is True
    assert _lane_covers(supernatural_stamina, dr) is True
    # Subset: undying/persist are counter-bearing; bare dies-return is NOT.
    assert _lane_covers(geralfs, up) is True
    assert _lane_covers(kitchen_finks, up) is True
    assert _lane_covers(supernatural_stamina, up) is False
    # And undying/persist cards OPEN both lanes (they are members of the superset).
    gk = {s.key for s in extract_signals(geralfs)}
    assert "dies_recursion" in gk
    assert "undying_persist_matters" in gk


def test_creature_cast_and_etb_serve_self_bounce_recast_engines():
    # Self-bounce ETB creatures (Whitemane Lion, Kor Skyfisher) return your own
    # permanent on enter — recast them to re-fire creature-cast / enter triggers. A
    # creature-cast (Oketra) or ETB commander wants them.
    whitemane = {
        "name": "Whitemane Lion",
        "type_line": "Creature — Cat",
        "oracle_text": (
            "Flash\n"
            "When this creature enters, return a creature you control to its owner's "
            "hand."
        ),
    }
    kor = {
        "name": "Kor Skyfisher",
        "type_line": "Creature — Kor Soldier",
        "oracle_text": (
            "Flying\n"
            "When this creature enters, return a permanent you control to its owner's "
            "hand."
        ),
    }
    for key in ("creature_cast_trigger", "creature_etb", "permanent_etb"):
        assert _lane_covers(whitemane, _sig(key)), key
        assert _lane_covers(kor, _sig(key)), key
    # Over-fire guard: bouncing an OPPONENT's permanent is tempo, not a recast engine.
    boomerang = {
        "name": "Man-o'-War-ish",
        "type_line": "Creature — Jellyfish",
        "oracle_text": "When this creature enters, return target creature to its owner's hand.",
    }
    assert _lane_covers(boomerang, _sig("creature_cast_trigger")) is False


def test_suspend_serves_extra_upkeep_and_suspended_card_support():
    # Suspend removes a TIME counter each upkeep (CR 702.62), so a suspend commander
    # (Jhoira, Taigam) wants extra upkeeps (Paradox Haze) and counter-manipulation on
    # suspended cards (Clockspinning) — neither says "suspend"/"time counter" itself.
    sig = _sig("suspend_matters", "you")
    paradox_haze = {
        "name": "Paradox Haze",
        "type_line": "Enchantment — Aura",
        "oracle_text": (
            "Enchant player\n"
            "At the beginning of enchanted player's first upkeep each turn, that "
            "player gets an additional upkeep step after this step."
        ),
    }
    clockspinning = {
        "name": "Clockspinning",
        "type_line": "Instant",
        "oracle_text": (
            "Buyback {3}\nChoose a counter on target permanent or suspended card. "
            "Remove that counter or put another of those counters on that permanent "
            "or card."
        ),
    }
    assert _lane_covers(paradox_haze, sig) is True
    assert _lane_covers(clockspinning, sig) is True
    # Over-fire guard: a generic extra-turn spell with no upkeep/suspend hook stays out.
    explore = {
        "name": "Explore",
        "type_line": "Sorcery",
        "oracle_text": "You may play an additional land this turn.\nDraw a card.",
    }
    assert _lane_covers(explore, sig) is False


def test_stax_lanes_serve_symmetric_hatebears():
    # A stax commander wants stax PIECES regardless of its own scope. The opponent-tax
    # serve missed SYMMETRIC hatebears: global ability-shutoff (Collector Ouphe),
    # anti-cheat ETB replacement (Containment Priest), trigger-hate (Hushbringer). And a
    # symmetric-stax commander (Hokori) also wants the opponent-tax pieces (Kismet).
    collector_ouphe = {
        "name": "Collector Ouphe",
        "type_line": "Creature — Ouphe",
        "oracle_text": "Activated abilities of artifacts can't be activated.",
    }
    containment_priest = {
        "name": "Containment Priest",
        "type_line": "Creature — Cleric",
        "oracle_text": (
            "Flash\n"
            "If a nontoken creature would enter the battlefield and it wasn't cast, "
            "exile it instead."
        ),
    }
    hushbringer = {
        "name": "Hushbringer",
        "type_line": "Creature — Faerie",
        "oracle_text": (
            "Flying, lifelink\n"
            "Creatures entering the battlefield and dying don't cause triggered "
            "abilities to trigger."
        ),
    }
    kismet = {
        "name": "Kismet",
        "type_line": "Enchantment",
        "oracle_text": "Artifacts, creatures, and lands your opponents control enter tapped.",
    }
    stax = _sig("stax_taxes", "opponents")
    sym = _sig("symmetric_stax", "each")
    for piece in (collector_ouphe, containment_priest, hushbringer):
        assert _lane_covers(piece, stax), piece["name"]
        assert _lane_covers(piece, sym), piece["name"]
    # The symmetric-stax commander also wants opponent-tax pieces.
    assert _lane_covers(kismet, sym) is True
    # Over-fire guard: a vanilla beater is not a stax piece.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert _lane_covers(bear, stax) is False
    assert _lane_covers(bear, sym) is False


def test_ninjutsu_serves_evasive_unblockable_enablers():
    # Ninjutsu (CR 702.49) returns an UNBLOCKED attacker and drops the ninja in, so a
    # ninjutsu commander (Satoru Umezawa) wants cheap unblockable/evasive creatures to
    # reliably connect — Slither Blade, Mist-Cloaked Herald, Tormented Soul. Reuses the
    # evasion classifier (no flying — that's soft/blockable).
    sig = _sig("ninjutsu_matters", "you")
    slither = {
        "name": "Slither Blade",
        "type_line": "Creature — Snake Rogue",
        "oracle_text": "This creature can't be blocked.",
    }
    tormented = {
        "name": "Tormented Soul",
        "type_line": "Creature — Spirit",
        "oracle_text": "This creature can't block and can't be blocked.",
    }
    shadowmage = {  # keyword evasion (fear) is also an enabler
        "name": "Skulk Test",
        "type_line": "Creature — Rat",
        "oracle_text": "Fear",
        "keywords": ["Fear"],
    }
    assert _lane_covers(slither, sig) is True
    assert _lane_covers(tormented, sig) is True
    assert _lane_covers(shadowmage, sig) is True
    # Over-fire guard: a plain ground creature is not an enabler.
    bear = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
        "keywords": [],
    }
    assert _lane_covers(bear, sig) is False


def test_aristocrats_graveyard_lanes_serve_self_sac_creatures():
    # Self-sacrificing creatures (Selfless Spirit, Kami of False Hope, Spore Frog) die on
    # demand and protect the board — sac-fodder a death/sacrifice/graveyard deck wants.
    selfless_spirit = {
        "name": "Selfless Spirit",
        "type_line": "Creature — Spirit Cleric",
        "oracle_text": (
            "Flying\nSacrifice this creature: Creatures you control gain "
            "indestructible until end of turn."
        ),
    }
    for key in ("death_matters", "sacrifice_matters", "graveyard_matters"):
        scope = "any" if key == "death_matters" else "you"
        assert _lane_covers(selfless_spirit, _sig(key, scope)), key
    # Over-fire guard: a vanilla creature is not sac-fodder via this extra.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert _lane_covers(bear, _sig("death_matters", "any")) is False


def test_direct_damage_serves_burn_redirect():
    # Repercussion converts creature-damage into player damage — a burn payoff a
    # pinger/wipe/damage deck wants (ping or wipe + Repercussion = burn the table).
    # direct_damage served numeric burn + "double that damage" but not "that much
    # damage to that creature's controller".
    repercussion = {
        "name": "Repercussion",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever a creature is dealt damage, this enchantment deals that much "
            "damage to that creature's controller."
        ),
    }
    assert _lane_covers(repercussion, _sig("direct_damage", "you")) is True
    # Over-fire guard: a vanilla lifegain spell is not burn.
    healer = {
        "name": "Healer",
        "type_line": "Sorcery",
        "oracle_text": "You gain 5 life.",
    }
    assert _lane_covers(healer, _sig("direct_damage", "you")) is False


def test_activated_ability_serves_haste_granters_and_untap_enablers():
    # A {T}: commander (Visara "{T}: Destroy target creature") can't tap the turn it
    # enters (CR 302.6 summoning sickness) and taps only once per turn. Haste-granters
    # (CR 702.10 / 302.6) lift the sickness so it activates immediately; untap-enablers
    # re-tap it for extra activations. Both are its support package.
    sig = _sig("activated_ability", "you")
    # Haste-granter on an equipped creature (lifts summoning sickness for the {T}:).
    sting = {
        "name": "Sting, the Glinting Dagger",
        "type_line": "Legendary Artifact — Equipment",
        "oracle_text": (
            "Equipped creature gets +1/+1 and has haste.\n"
            "At the beginning of each combat, untap equipped creature.\n"
            "Equipped creature has first strike as long as it's blocking or blocked "
            "by a Goblin or Orc.\nEquip {2}"
        ),
    }
    # Repeatable untap of an enchanted creature — re-tap the {T}: commander each turn.
    freed = {
        "name": "Freed from the Real",
        "type_line": "Enchantment — Aura",
        "oracle_text": (
            "Enchant creature\n{U}: Tap enchanted creature.\n"
            "{U}: Untap enchanted creature."
        ),
    }
    # One-shot "Untap it" (plus protection) to reactivate the commander in response.
    shore_up = {
        "name": "Shore Up",
        "type_line": "Instant",
        "oracle_text": (
            "Target creature you control gets +1/+1 and gains hexproof until end of "
            "turn. Untap it. (It can't be the target of spells or abilities your "
            "opponents control.)"
        ),
    }
    assert _lane_covers(sting, sig) is True
    assert _lane_covers(freed, sig) is True
    assert _lane_covers(shore_up, sig) is True
    # Over-fire guard: a vanilla creature with innate haste is NOT a granter — it grants
    # nothing to the commander.
    goblin = {
        "name": "Raging Goblin",
        "type_line": "Creature — Goblin Berserker",
        "oracle_text": "Haste",
    }
    assert _lane_covers(goblin, sig) is False
