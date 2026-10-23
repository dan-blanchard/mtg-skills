"""Serve-ident pass A over ``signal_specs/data_1.py`` (docs/plans/serve-idents-
and-avenue-support.md §2).

Each converted spec's serve arm is the lanes' own structural idents, not an
oracle regex. One test per spec pins the swap: the regex arm is gone, the ident
is on the serve, a real card the regex missed now serves, and (where the regex
over-served) a real card it wrongly served no longer does. The structured dims
(power / toughness / keywords) the spec keeps are unchanged and never admit the
negative cards below.
"""

import pytest
from conftest import extra

from mtg_utils._analysis.signal_specs import Serve, avenue_spec_for, spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record for *name* (ADR-0056), with its crosswalk trees
    memo seeded first — so a serve's structural ``signal_idents`` arm reads the
    card's real idents in CI exactly as it does locally (no phase cache)."""
    test_card_ir(name)
    return test_card(name)


def _ident_serve(key: str, scope: str, *idents: str) -> Serve:
    spec = spec_for(_sig(key, scope))
    assert spec is not None
    assert spec.serve.oracle is None
    for ident in idents:
        assert ident in spec.serve.signal_idents, ident
    return spec.serve


# ── Lanes that equal the old regex: the lane is now the one source ────────────


def test_adapt_matters_serve_rides_the_lane():
    serve = _ident_serve("adapt_matters", "you", "adapt_matters|you|")
    assert serve.matches(_card("Biomancer's Familiar"))


def test_combat_choice_makers_serve_rides_the_lane():
    serve = _ident_serve(
        "combat_choice_makers", "opponents", "combat_choice_makers|opponents|"
    )
    assert serve.matches(_card("Master Warcraft"))


def test_mill_makers_serve_rides_the_lane():
    serve = _ident_serve("mill_makers", "any", "mill_makers|any|")
    assert serve.matches(_card("Ashiok, Dream Render"))


def test_copy_limit_serve_rides_the_lane():
    serve = _ident_serve("copy_limit", "you", "copy_limit|you|")
    assert serve.matches(_card("Relentless Rats"))


def test_timing_control_serve_rides_the_lane():
    serve = _ident_serve("timing_control", "any", "timing_control|any|")
    assert serve.matches(_card("Teferi, Time Raveler"))


def test_sacrifice_protection_serve_rides_the_lane():
    serve = _ident_serve("sacrifice_protection", "you", "sacrifice_protection|you|")
    assert serve.matches(_card("Sigarda, Host of Herons"))


def test_draft_spellbook_serve_rides_the_lane():
    serve = _ident_serve("draft_spellbook", "you", "draft_spellbook|you|")
    assert serve.matches(_card("Cogwork Librarian"))


def test_each_mode_player_serve_rides_the_lane():
    serve = _ident_serve("each_mode_player", "each", "each_mode_player|each|")
    assert serve.matches(_card("Vindictive Lich"))


def test_miracle_grant_serve_rides_the_lane():
    serve = _ident_serve("miracle_grant", "you", "miracle_grant|you|")
    assert serve.matches(_card("Lorehold, the Historian"))


def test_legend_rule_off_serve_rides_the_lane():
    serve = _ident_serve("legend_rule_off", "you", "legend_rule_off|you|")
    assert serve.matches(_card("Mirror Gallery"))


def test_noncombat_damage_payoff_serve_rides_the_lane():
    serve = _ident_serve(
        "noncombat_damage_payoff", "you", "noncombat_damage_payoff|you|"
    )
    assert serve.matches(_card("Boros Reckoner"))


def test_extra_combats_serve_rides_the_lane():
    serve = _ident_serve("extra_combats", "you", "extra_combats|you|")
    assert serve.matches(_card("Aggravated Assault"))


# ── Lanes that read what the regex missed (and drop what it over-served) ──────


def test_counter_hate_serve_reads_the_two_sentence_denial():
    serve = _ident_serve("counter_hate", "opponents", "counter_hate|opponents|")
    # "Target opponent loses all counters. That player can't get counters" — the
    # sentence break defeated the regex.
    assert serve.matches(_card("Suncleanser"))


def test_coin_flip_serve_reads_each_player_flips():
    serve = _ident_serve("coin_flip", "any", "coin_flip|you|")
    assert serve.matches(_card("Chance Encounter"))
    assert serve.matches(_card("Goblin Assassin"))  # "each player flips a coin"


def test_keyword_counter_serve_reads_keyword_counter_placement():
    serve = _ident_serve("keyword_counter", "you", "keyword_counter|any|")
    assert serve.matches(_card("Champions of Tyr"))
    assert serve.matches(_card("Heightened Reflexes"))  # "a first strike counter"


def test_group_hug_draw_serve_reads_the_wheel():
    serve = _ident_serve("group_hug_draw", "each", "group_hug_draw|each|")
    assert serve.matches(_card("Memory Jar"))
    assert serve.matches(_card("Dark Deal"))


def test_counter_move_serve_reads_put_its_counters_on():
    serve = _ident_serve("counter_move", "you", "counter_move|you|")
    assert serve.matches(_card("Essence Channeler"))


def test_toughness_combat_serve_reads_total_toughness():
    serve = _ident_serve("toughness_combat", "you", "toughness_combat|you|")
    assert serve.matches(_card("Assault Formation"))
    assert serve.matches(_card("Loxodon Lifechanter"))


def test_damage_reflect_serve_reads_aura_and_global_reflectors():
    serve = _ident_serve("damage_reflect", "you", "damage_reflect|you|")
    assert serve.matches(_card("Repercussion"))
    assert serve.matches(_card("Arcbond"))


def test_power_double_serve_reads_double_target_power():
    serve = _ident_serve("power_double", "you", "power_double|you|")
    assert serve.matches(_card("Unleash Fury"))
    assert serve.matches(_card("Exponential Growth"))


def test_damage_to_you_punish_serve_reads_combat_damage_to_you():
    serve = _ident_serve(
        "damage_to_you_punish", "opponents", "damage_to_you_punish|opponents|"
    )
    assert serve.matches(_card("Norn's Decree"))


def test_extra_turns_serve_drops_the_extra_turn_haters():
    serve = _ident_serve("extra_turns", "you", "extra_turns|you|")
    assert serve.matches(_card("Nexus of Fate"))
    # "If an opponent would begin an extra turn, that player skips that turn
    # instead" names extra turns but takes none.
    assert not serve.matches(_card("Stranglehold"))


def test_global_ability_grant_serve_reads_qualified_grants():
    serve = _ident_serve("global_ability_grant", "any", "global_ability_grant|any|")
    assert serve.matches(_card("Esika, God of the Tree // The Prismatic Bridge"))
    assert serve.matches(_card("Rishkar, Peema Renegade"))


def test_counter_replace_bonus_serve_reads_the_doublers():
    serve = _ident_serve("counter_replace_bonus", "you", "counter_replace_bonus|you|")
    assert serve.matches(_card("Doubling Season"))
    assert serve.matches(_card("Vorinclex, Monstrous Raider"))


def test_donate_makers_serve_reads_optional_donates():
    serve = _ident_serve("donate_makers", "you", "donate_makers|you|")
    assert serve.matches(_card("Assault Suit"))
    assert serve.matches(_card("Coveted Jewel"))


def test_counter_manipulation_serve_reads_remove_costs():
    serve = _ident_serve("counter_manipulation", "you", "counter_manipulation|you|")
    assert serve.matches(_card("Experiment One"))
    # Rock Hydra's counter loss is damage prevention's drawback, not a payoff.
    assert not serve.matches(_card("Rock Hydra"))


def test_creature_cast_trigger_serve_reads_typed_creature_spells():
    serve = _ident_serve("creature_cast_trigger", "you", "creature_cast_trigger|any|")
    assert serve.matches(_card("Emrakul's Influence"))


def test_goad_makers_serve_reads_forced_attacks():
    serve = _ident_serve("goad_makers", "opponents", "goad_makers|opponents|")
    assert serve.matches(_card("Ghoulish Impetus"))
    assert serve.matches(_card("Alluring Siren"))


def test_tribe_damage_trigger_serve_reads_qualified_subjects():
    serve = _ident_serve("tribe_damage_trigger", "you", "tribe_damage_trigger|you|")
    assert serve.matches(_card("Fynn, the Fangbearer"))
    assert serve.matches(_card("Bred for the Hunt"))
    # "a source you control deals damage to an opponent" — no tribe, no creature.
    assert not serve.matches(_card("Quest for Pure Flame"))


def test_counter_distribute_serve_reads_typed_distributes():
    serve = _ident_serve("counter_distribute", "you", "counter_distribute|you|")
    assert serve.matches(_card("Edgar Markov"))
    # Twins of Discord grants bloodthirst; it distributes nothing.
    assert not serve.matches(_card("Twins of Discord"))


def test_creature_ping_serve_reads_tap_and_granted_bites():
    serve = _ident_serve("creature_ping", "you", "creature_ping|you|")
    assert serve.matches(_card("Abyssal Hunter"))
    assert serve.matches(_card("Burning Anger"))


def test_mass_removal_serve_drops_combat_tricks():
    serve = _ident_serve("mass_removal", "you", "mass_removal|you|")
    assert serve.matches(_card("Bile Blight"))
    assert serve.matches(_card("Blast Zone"))
    # "All creatures get -2/-0 until end of turn" kills nothing.
    assert not serve.matches(_card("Ivory Charm"))


def test_damage_equal_power_serve_reads_bite_spells():
    serve = _ident_serve(
        "damage_equal_power",
        "you",
        "creature_ping|you|",
        "damage_equal_power|you|",
    )
    assert serve.matches(_card("Chandra's Ignition"))
    assert serve.matches(_card("Betrayal at the Vault"))


def test_damage_prevention_serve_reads_prevent_and_redirect_statics():
    serve = _ident_serve(
        "damage_prevention",
        "you",
        "damage_prevention|you|",
        "damage_redirect|you|",
    )
    assert serve.matches(_card("Gisela, Blade of Goldnight"))
    assert serve.matches(_card("Carom"))


def test_self_death_payoff_serve_reads_dies_return_grants():
    serve = _ident_serve("self_death_payoff", "you", "dies_recursion|you|")
    assert serve.matches(_card("False Demise"))
    assert serve.matches(_card("Resurrection Orb"))
    # "Undying Vengeance" is an ability word, not the undying keyword.
    assert not serve.matches(_card("Shadow of the Goblin"))


def test_dies_recursion_serve_reads_dies_return_grants():
    serve = _ident_serve("dies_recursion", "you", "dies_recursion|you|")
    assert serve.matches(_card("Gift of Immortality"))
    assert not serve.matches(_card("Shadow of the Goblin"))


def test_keyword_grant_target_serve_reads_untap_and_grant():
    serve = _ident_serve("keyword_grant_target", "you", "keyword_grant_target|you|*")
    assert serve.matches(_card("Aim High"))


def test_base_pt_set_serve_reads_x_valued_sets():
    serve = _ident_serve(
        "base_pt_set", "any", "base_pt_set|any|", "base_power_matters|you|"
    )
    assert serve.matches(_card("Biomass Mutation"))
    assert serve.matches(_card("Mirror Entity"))


@pytest.mark.parametrize(
    "key", ["lifegain_matters", "lifegain_makers", "wants_lifegain"]
)
def test_lifegain_serve_reads_payoffs_and_leaves_out_self_bleed(key):
    serve = _ident_serve(key, "you", "lifegain_makers|you|*", "lifegain_matters|you|*")
    assert serve.matches(_card("Ajani's Pridemate"))  # "whenever you gain life"
    assert serve.matches(_card("Baneslayer Angel"))  # lifelink
    # "X is the amount of life you've gained this turn": the regex missed it.
    assert serve.matches(_card("Voracious Wurm"))
    # A self-bleed engine wants lifegain (wants_lifegain) but supplies none, so
    # it isn't a Lifegain card.
    assert not serve.matches(_card("Dark Confidant"))
    assert not serve.matches(_card("Phyrexian Arena"))
    # The regex served lifegain hate and a gift to an opponent.
    assert not serve.matches(_card("Sulfuric Vortex"))
    assert not serve.matches(_card("Path of Peace"))


def test_wants_lifegain_shares_the_lifegain_avenue():
    # A self-bleed engine opens the same avenue its payoffs do, so focus reads
    # the two keys as one Lifegain avenue.
    wants = spec_for(_sig("wants_lifegain"))
    payoff = spec_for(_sig("lifegain_matters"))
    assert wants is not None
    assert payoff is not None
    assert wants.label == payoff.label == "Lifegain"


@pytest.mark.parametrize("key", ["graveyard_makers", "graveyard_matters"])
def test_own_graveyard_serve_reads_surveil_and_mill_costs(key):
    serve = _ident_serve(key, "you", "graveyard_makers|you|", "graveyard_matters|you|")
    # Surveil (CR 701.25a) and a mill paid as a cost fill your graveyard;
    # the lane reads both now, so the regex's "surveil" arm has a replacement.
    assert serve.matches(_card("Thought Erasure"))
    assert serve.matches(_card("Millikin"))
    assert serve.matches(_card("Sidisi, Brood Tyrant"))
    # "Target player mills three cards" never says "your graveyard".
    assert serve.matches(_card("Hedron Crab"))
    # A scry keeps every card in the library (CR 701.22a).
    assert not serve.matches(_card("Preordain"))
    # Madness's reminder text says "put it into your graveyard"; it's a
    # discard payoff, not a graveyard card.
    assert not serve.matches(_card("Fiery Temper"))


@pytest.mark.parametrize("key", ["plus_one_makers", "plus_one_matters"])
def test_plus_one_serve_reads_the_keyword_actions(key):
    serve = _ident_serve(
        key,
        "any",
        "plus_one_makers|you|",
        "plus_one_matters|you|",
        "counter_doubling|you|",
        "proliferate_makers|you|",
    )
    # plus_one_makers reads the keyword actions that put +1/+1 counters, so a
    # connive / amass printed without its reminder text now serves; the regex
    # needed the literal "+1/+1 counter".
    assert serve.matches(_card("Baron Helmut Zemo"))
    assert serve.matches(_card("Grishnákh, Brash Instigator"))
    assert serve.matches(_card("Dromoka's Gift"))  # bolster
    assert serve.matches(_card("Sheer Drop"))  # awaken
    # The regex served an energy doubler off "twice that many".
    assert not serve.matches(_card("Aether Refinery"))


def test_damage_redirect_serve_reads_the_static_redirect():
    serve = _ident_serve(
        "damage_redirect", "you", "damage_redirect|you|", "damage_prevention|you|"
    )
    # "All damage that would be dealt to you is dealt to enchanted creature
    # instead" (CR 614.9) and the one-shot redirects both serve.
    assert serve.matches(_card("Pariah"))
    assert serve.matches(_card("Palisade Giant"))
    assert serve.matches(_card("Harm's Way"))
    # A granted prevention ability (CR 615) blanks the soaked damage too.
    assert serve.matches(_card("Samite Blessing"))
    # A life floor redirects nothing: Worship's ruling says the damage is still
    # dealt. It is board protection, not this avenue.
    assert not serve.matches(_card("Worship"))
    assert not serve.matches(_card("Ali from Cairo"))


def test_counter_place_trigger_serve_is_the_lane():
    serve = _ident_serve("counter_place_trigger", "you", "counter_place_trigger|you|")
    # A granted "whenever counters are put on this" trigger (CR 122.6).
    assert serve.matches(_card("Cursed Wombat"))
    assert serve.matches(_card("Danny Pink"))
    # You putting counters on a creature you don't control is your payoff.
    assert serve.matches(_card("Kros, Defense Contractor"))
    assert serve.matches(_card("Generous Patron"))
    assert serve.matches(_card("Fathom Mage"))
    # An opponent's placement, and a countdown on the card itself.
    assert not serve.matches(_card("Bold Plagiarist"))
    assert not serve.matches(_card("Midnight Clock"))
    # A doubler places nothing to trigger on.
    assert not serve.matches(_card("Doubling Season"))


def test_debuff_serve_reads_variable_one_sided_and_granted_shrinks():
    serve = _ident_serve(
        "debuff_makers", "any", "debuff_makers|any|", "debuff_makers|you|"
    )
    assert serve.matches(_card("Dead Weight"))
    assert serve.matches(_card("Disfigure"))
    # A static "-X/-X, where X is …" (CR 613.4c, layer 7c); phase writes the
    # dynamic amount as a negated quantity.
    assert serve.matches(_card("Kagemaro's Clutch"))
    assert serve.matches(_card("Meishin, the Mind Cage"))  # "-X/-0", all creatures
    # One-sided: "Creatures your opponents control get -X/-0".
    assert serve.matches(_card("Roilmage's Trick"))
    # A granted "{B}, {T}: Put a -1/-1 counter on target creature" (CR 113.1a).
    assert serve.matches(_card("Sadistic Obsession"))
    # A one-shot base 0/1 on the opponents' creatures (CR 613.4b, layer 7b).
    assert serve.matches(_card("Flatline"))
    # "Each opponent blights 1": -1/-1 counters on their creature (CR 701.68a).
    assert serve.matches(_card("High Perfect Morcant"))
    # A whole board turned into 1/1 Frogs: retyping creatures animates nothing.
    assert serve.matches(_card("Polymorphist's Jest"))
    # A delayed "it gets -1/-0" on an attacker: phase stamps it SelfRef, the
    # overlay's anaphoric_pump arm re-reads it as the attacking creature.
    assert serve.matches(_card("Jace, Architect of Thought"))
    # The regex served a creature shrinking itself, blight (-1/-1 counters on
    # a creature you control, CR 701.68a) and an animation's 1/1 (the
    # animation is a CR 613.1d type change; the P/T it sets, 613.4b, is the
    # new creature's).
    assert not serve.matches(_card("Flowstone Giant"))
    assert not serve.matches(_card("Blighted Blackthorn"))
    assert not serve.matches(_card("Living Lands"))
    # A single-target base-P/T set is a neutralize, not a -1/-1 enabler.
    assert not serve.matches(_card("Turn to Frog"))
    assert not serve.matches(_card("Diminish"))
    assert not serve.matches(_card("Metamorphic Blast"))


def test_tapper_serve_reads_granted_tap_abilities():
    serve = _ident_serve("tapper_engine", "any", "tapper_engine|any|")
    assert serve.matches(_card("Gideon's Lawkeeper"))
    assert serve.matches(_card("Niblis of Frost"))
    # An Aura's / Equipment's granted "{T}: Tap target creature" (CR 113.1a).
    assert serve.matches(_card("Debtor's Pulpit"))
    assert serve.matches(_card("Siren Song Lyre"))
    # "This creature doesn't untap during your untap step" is a drawback on
    # itself, not a lock.
    assert not serve.matches(_card("Brass Gnat"))


def test_damage_received_matters_serve_is_the_lane():
    serve = _ident_serve(
        "damage_received_matters",
        "you",
        "damage_received_matters|you|",
        "damage_redirect|you|",
    )
    assert serve.matches(_card("Rite of Passage"))
    assert serve.matches(_card("Pariah"))
    assert not serve.matches(_card("Boros Reckoner"))


def test_damage_redirect_soak_payoffs_ride_the_lane():
    spec = spec_for(_sig("damage_redirect"))
    assert spec is not None
    soak = extra(spec, "Profit from the soaked damage")
    assert soak.serve is not None
    assert soak.serve.oracle is None
    assert soak.serve.matches(_card("Druid's Call"))
    assert soak.serve.matches(_card("Spiteful Shadows"))
    assert not soak.serve.matches(_card("Brash Taunter"))


# ── Serve-ident pass 3 (2026-10-20): the partial and blocked specs ────────────


@pytest.mark.parametrize(
    ("key", "scope"), [("sacrifice_outlets", "you"), ("death_matters", "any")]
)
def test_aristocrats_serve_reads_death_value_fodder(key, scope):
    serve = _ident_serve(
        key,
        scope,
        "sacrifice_outlets|you|",
        "death_matters|any|",
        "self_death_payoff|you|",
    )
    assert serve.matches(_card("Blood Artist"))
    # A permanent whose own death trigger pays you back is fodder; the regex
    # wanted a value verb within 45 characters of "dies".
    assert serve.matches(_card("Kokusho, the Evening Star"))
    # "Sacrifice after III" is a Saga's reminder text, not an outlet.
    assert not serve.matches(_card("Invasion of the Giants"))


def test_free_cast_serve_drops_self_recast_reminders():
    serve = _ident_serve(
        "free_cast",
        "you",
        "free_cast|you|",
        "cascade_matters|you|",
    )
    assert serve.matches(_card("Aetherworks Marvel"))  # casts a spell free
    # Suspend's and plot's reminders cast the card itself free on a later turn
    # (suspend CR 702.62a, plot 702.170d): a self-recast, not a bomb cast for free.
    assert not serve.matches(_card("Restore Balance"))
    assert not serve.matches(_card("Beastbond Outcaster"))


@pytest.mark.parametrize("key", ["proliferate_matters", "proliferate_makers"])
def test_proliferate_serve_reads_any_counter_sources(key):
    serve = _ident_serve(
        key,
        "you",
        "proliferate_matters|you|",
        "plus_one_makers|you|",
        "poison_makers|opponents|",
    )
    # A strife counter is a counter proliferate grows; the regex named five kinds.
    assert serve.matches(_card("Crescendo of War"))
    # Tribute: an opponent chooses whether the counters go on.
    assert not serve.matches(_card("Snake of the Golden Grove"))


def test_ability_copy_serve_drops_demonstrate():
    serve = _ident_serve("ability_copy", "you", "ability_copy|you|")
    assert serve.matches(_card("Strionic Resonator"))
    # Demonstrate copies the spell (CR 702.144a), not an ability.
    assert not serve.matches(_card("Incarnation Technique"))


def test_self_counter_grow_serve_reads_named_self_counters():
    serve = _ident_serve(
        "self_counter_grow", "you", "self_counter_grow|you|", "explore_makers|you|"
    )
    # "Put a +1/+1 counter on Yahenni": the regex wanted "on it / this creature".
    assert serve.matches(_card("Yahenni, Undying Partisan"))
    assert not serve.matches(_card("Snake of the Golden Grove"))


@pytest.mark.parametrize("key", ["any_counter_matters", "any_counter_makers"])
def test_any_counter_serve_drops_devour(key):
    serve = _ident_serve(
        key,
        "you",
        "any_counter_matters|you|",
        "any_counter_makers|you|",
        "counter_doubling|you|",
    )
    assert serve.matches(_card("Rishkar, Peema Renegade"))  # "with a counter on it"
    # Devour's "twice that many +1/+1 counters" (CR 702.82a) doubles nothing.
    assert not serve.matches(_card("Mycoloth"))


def test_variable_pt_serve_reads_one_sided_cdas():
    serve = _ident_serve("variable_pt", "you", "variable_pt|any|")
    assert serve.matches(_card("Nighthawk Scavenger"))  # power only
    # Damage equal to the cards in a hand sets no power or toughness.
    assert not serve.matches(_card("Khorvath's Fury"))


def test_draw_matters_serve_reads_wheels():
    serve = _ident_serve(
        "draw_matters", "you", "draw_matters|you|", "card_draw_engine|each|"
    )
    assert serve.matches(_card("Wheel of Fortune"))
    assert serve.matches(_card("Burning Inquiry"))
    # "Draw an additional card" in a loyalty ability is not a draw payoff.
    assert not serve.matches(_card("Lord Windgrace"))


def test_outlaw_serve_reads_outlaw_payoffs():
    serve = _ident_serve(
        "outlaw_matters", "you", "outlaw_matters|you|", "token_maker|you|Pirate"
    )
    assert serve.matches(_card("Double Down"))  # "whenever you cast an outlaw spell"


def test_snow_serve_reads_nonsnow_payoffs():
    serve = _ident_serve("snow_matters", "you", "snow_matters|you|")
    # A sorcery that digs for snow permanents: no snow supertype of its own.
    assert serve.matches(_card("Glacial Revelation"))


def test_targeting_serve_drops_ward_reminders():
    serve = _ident_serve("targeting_matters", "any", "targeting_matters|any|")
    assert serve.matches(_card("Akroan Crusader"))  # heroic
    # Ward's reminder (CR 702.21a) is an opponent's targeting, not a payoff.
    assert not serve.matches(_card("Adrix and Nev, Twincasters"))


def test_self_pump_serve_drops_target_pumps():
    serve = _ident_serve("self_pump", "you", "self_pump|you|")
    assert serve.matches(_card("Flowstone Giant"))  # "+2/-2", the regex wanted +N/+N
    # "Put a +1/+1 counter on target artifact creature" pumps another creature.
    assert not serve.matches(_card("Steel Overseer"))


def test_forced_attack_serve_reads_goad():
    serve = _ident_serve(
        "forced_attack", "you", "forced_attack|any|", "goad_makers|opponents|"
    )
    assert serve.matches(_card("Goblin Diplomats"))  # "attacks this turn if able"
    assert serve.matches(_card("Disrupt Decorum"))


def test_creature_etb_opponents_serve_drops_enter_tapped_stax():
    serve = _ident_serve("creature_etb", "opponents", "creature_etb|opponents|")
    assert serve.matches(_card("Suture Priest"))
    # "Creatures your opponents control enter tapped" is a stax replacement.
    assert not serve.matches(_card("Imposing Sovereign"))


def test_noncreature_cast_punish_serve_reads_first_spell_punishers():
    serve = _ident_serve(
        "noncreature_cast_punish", "any", "noncreature_cast_punish|any|"
    )
    assert serve.matches(_card("Esper Sentinel"))
    # A symmetric copy / reward trigger punishes nobody.
    assert not serve.matches(_card("Niv-Mizzet, Parun"))


def test_symmetric_damage_serve_moves_group_burn_to_an_extra():
    serve = _ident_serve("symmetric_damage_each", "each", "symmetric_damage_each|each|")
    assert serve.matches(_card("Price of Progress"))
    # Burn to each opponent is the avenue's adjacency, served by its extra.
    assert not serve.matches(_card("Sizzle"))
    spec = spec_for(_sig("symmetric_damage_each", "each"))
    assert spec is not None
    burn = extra(spec, "Group burn")
    assert burn.serve is not None
    assert burn.serve.matches(_card("Sizzle"))


def test_land_creatures_serve_reads_animators():
    serve = _ident_serve("land_creatures_matter", "you", "land_creatures_matter|you|")
    assert serve.matches(_card("Avalanche Caller"))
    # Exiling an opponent's land creature is removal.
    assert not serve.matches(_card("Consuming Sinkhole"))


def test_named_synergy_serve_reads_for_each_named():
    serve = _ident_serve("named_synergy", "you", "named_synergy|you|")
    assert serve.matches(_card("Plague Rats"))


def test_combat_buff_engine_serve_drops_block_self_pumps():
    serve = _ident_serve("combat_buff_engine", "you", "combat_buff_engine|you|")
    assert serve.matches(_card("Marchesa, the Black Rose"))
    # Bushido (a block / becomes-blocked self pump) is no beginning-of-combat buff.
    assert not serve.matches(_card("Fumiko the Lowblood"))


@pytest.mark.parametrize(
    ("key", "card"),
    [
        ("tribal_etb_multi", "Marwyn, the Nurturer"),
        ("typed_enters_punish", "Impact Tremors"),
        ("spell_keyword_grant", "Maelstrom Nexus"),
        ("pump_makers", "Shared Animosity"),
        ("scaling_pump", "Might of the Masses"),
        ("vanilla_matters", "Ruxa, Patient Professor"),
        ("topdeck_stack", "Future Sight"),
        ("count_anthem", "Craterhoof Behemoth"),
        ("flip_self", "Faithful Squire // Kaiso, Memory of Loyalty"),
    ],
)
def test_lane_serves_what_its_regex_missed(key, card):
    serve = _ident_serve(key, "you", f"{key}|you|")
    assert serve.matches(_card(card))


def test_target_player_draws_serve_reads_draw_x():
    serve = _ident_serve("target_player_draws", "any", "target_player_draws|any|")
    assert serve.matches(_card("Braingeyser"))  # "draws X cards"


def test_opponent_counter_grant_serve_reads_stun_counters():
    serve = _ident_serve(
        "opponent_counter_grant", "opponents", "opponent_counter_grant|opponents|"
    )
    assert serve.matches(_card("Freeze in Place"))


def test_topdeck_stack_serve_drops_surveil_reminders():
    serve = _ident_serve("topdeck_stack", "you", "topdeck_stack|you|")
    assert not serve.matches(_card("Contingency Plan"))


def test_aoe_ping_serve_is_the_pingers_and_the_gear_an_extra():
    serve = _ident_serve("aoe_ping", "you", "aoe_ping|you|")
    assert serve.matches(_card("Crypt Rats"))
    assert not serve.matches(_card("Basilisk Collar"))
    spec = spec_for(_sig("aoe_ping"))
    assert spec is not None
    gear = extra(spec, "Deathtouch enablers")
    assert gear.serve is not None
    assert gear.serve.matches(_card("Basilisk Collar"))


# ── Pass C: lane fixes freed these serves from their oracle regexes ───────────


@pytest.mark.parametrize("key", ["spellcast_matters", "magecraft_matters"])
def test_spellslinger_serve_rides_the_lanes(key):
    serve = _ident_serve(
        key,
        "you",
        "spellcast_matters|you|instant_sorcery",
        "spellcast_matters|you|noncreature",
        "spellcast_matters|you|second_spell",
        "magecraft_matters|you|",
        "cost_reduction|you|instant_sorcery",
        "cost_reduction|you|noncreature",
    )
    assert serve.matches(_card("Guttersnipe"))
    assert serve.matches(_card("Goblin Electromancer"))
    # A symmetric/opponent-facing cast tax is not a spellslinger payoff of yours.
    assert not serve.matches(_card("Eidolon of the Great Revel"))
    # The type and prowess dims stay.
    assert "instant" in serve.types
    assert "prowess" in serve.keywords


def test_blocked_matters_serve_rides_the_lane():
    serve = _ident_serve("blocked_matters", "you", "blocked_matters|you|")
    assert serve.matches(_card("General Marhault Elsdragon"))
    spec = spec_for(_sig("blocked_matters"))
    (lure,) = [e for e in spec.extras if e.label == "Force blocks (Lure)"]
    assert lure.serve.matches(_card("Lure"))


def test_artifacts_matter_serve_rides_the_lanes():
    serve = _ident_serve(
        "artifacts_matter",
        "you",
        "artifacts_matter|you|*",
        "treasure_makers|you|",
        "clue_makers|you|",
        "food_makers|you|",
        "blood_makers|you|",
        "incubate_makers|you|",
    )
    assert "artifact" in serve.types
    assert serve.matches(_card("Thraben Inspector"))  # Clue maker
    assert serve.matches(_card("Bake into a Pie"))  # Food maker
    assert serve.matches(_card("Smothering Tithe"))  # Treasure maker
    assert not serve.matches(_card("Tezzeret's Gambit"))


def test_enchantments_matter_serve_rides_the_lane():
    serve = _ident_serve("enchantments_matter", "you", "enchantments_matter|you|*")
    assert "enchantment" in serve.types
    assert serve.matches(_card("Eidolon of Blossoms"))
    assert serve.matches(_card("Sythis, Harvest's Hand"))
    assert not serve.matches(_card("Wolf's Quarry"))


def test_landfall_serve_rides_the_lanes():
    serve = _ident_serve(
        "landfall",
        "you",
        "landfall|you|",
        "extra_land_drop|you|",
        "ramp|you|land",
    )
    assert serve.matches(_card("Lotus Cobra"))
    assert serve.matches(_card("Azusa, Lost but Seeking"))
    assert serve.matches(_card("Rampant Growth"))
    spec = spec_for(_sig("landfall"))
    assert any(e.serve.matches(_card("Crucible of Worlds")) for e in spec.extras)


def test_reanimator_serve_rides_the_lanes():
    serve = _ident_serve(
        "reanimator",
        "you",
        "reanimator|you|",
        "creature_recursion|you|battlefield",
    )
    assert serve.matches(_card("Zombify"))
    assert serve.matches(_card("Unburial Rites"))
    # A return to hand is not a reanimation.
    assert not serve.matches(_card("Raise Dead"))
    assert not serve.matches(_card("Regrowth"))
    assert {"escape", "persist", "undying"} <= serve.keywords


@pytest.mark.parametrize("key", ["creature_etb", "damage_for_each"])
def test_creature_entering_serves_cover_battlefield_recursion(key):
    scope = "you" if key == "creature_etb" else "any"
    serve = _ident_serve(key, scope, "creature_recursion|you|battlefield")
    assert serve.matches(_card("Zombify"))
    assert serve.matches(_card("Raise the Alarm"))
    assert not serve.matches(_card("Raise Dead"))


def test_flash_grant_serve_rides_the_lane():
    serve = _ident_serve("flash_grant", "you", "flash_grant|you|")
    assert serve.matches(_card("Vedalken Orrery"))
    assert serve.matches(_card("Leyline of Anticipation"))


# ── Pass E: Phase D lane fixes freed these serves from their oracle regexes ───


def test_blink_serve_rides_the_enabler_ident():
    serve = _ident_serve("blink_flicker", "you", "blink_flicker|you|enabler")
    # A delayed return at the next end step was invisible to the regex.
    assert serve.matches(_card("Astral Slide"))
    assert serve.matches(_card("Restoration Angel"))
    # Earthbend's reminder text returns a land; it isn't a flicker.
    assert not serve.matches(_card("Badgermole"))


def test_self_blink_serve_adds_the_blink_enablers():
    serve = _ident_serve(
        "self_blink", "you", "self_blink|you|", "blink_flicker|you|enabler"
    )
    assert serve.matches(_card("Aetherling"))
    assert serve.matches(_card("Astral Slide"))
    assert not serve.matches(_card("Badgermole"))


def test_power_matters_serve_drops_costs_that_merely_name_a_power():
    serve = _ident_serve("power_matters", "you", "power_matters|you|")
    assert serve.power_min == 4
    # "the greatest power among creatures you control" is the lane's payoff.
    assert serve.matches(_card("Essence Harvest"))
    # Casualty names a power to sacrifice; it rewards nothing about big creatures.
    assert not serve.matches(_card("A Little Chat"))


def test_protection_grant_serve_drops_self_shroud():
    serve = _ident_serve("protection_grant", "you", "protection_grant|you|")
    assert serve.matches(_card("Adept Watershaper"))
    # A creature granting itself shroud is no grant to your board.
    assert not serve.matches(_card("Advanced Hoverguard"))


def test_secret_writedown_serve_rides_the_lane():
    serve = _ident_serve(
        "secret_writedown",
        "you",
        "secret_writedown|you|",
        "secret_writedown|you|learn",
    )
    assert serve.matches(_card("Eyetwitch"))
    assert serve.matches(_card("A Killer Among Us"))


@pytest.mark.parametrize("key", ["graveyard_makers", "graveyard_matters"])
def test_opponent_graveyard_serves_ride_the_lanes_and_opponent_mill(key):
    serve = _ident_serve(
        key,
        "opponents",
        "graveyard_makers|opponents|",
        "graveyard_matters|opponents|",
        "mill_makers|opponents|",
    )
    assert serve.matches(_card("Codex Shredder"))
    assert serve.matches(_card("Bojuka Bog"))
    # Ingest and impulse-theft text exile an opponent's library, not a graveyard.
    assert not serve.matches(_card("Nightveil Specter"))


def test_tokens_matter_serve_rides_the_lane_and_amass():
    serve = _ident_serve(
        "tokens_matter", "you", "tokens_matter|you|*", "amass_makers|you|"
    )
    assert "mobilize" in serve.keywords
    assert serve.matches(_card("Anointed Procession"))
    assert serve.matches(_card("Commence the Endgame"))
    # A token copy of a graveyard card is a maker, not a payoff for tokens.
    assert not serve.matches(_card("Abyssal Harvester"))


def test_color_hoser_serve_drops_printed_protection():
    serve = _ident_serve("color_hoser", "you", "color_hoser|you|", "color_change|you|")
    assert serve.matches(_card("Blue Elemental Blast"))
    assert serve.matches(_card("Light of Day"))
    assert not serve.matches(_card("Abbey Gargoyles"))


def test_has_banding_serve_keeps_the_keyword_and_the_lane():
    serve = _ident_serve("has_banding", "you", "has_banding|you|")
    assert "banding" in serve.keywords
    assert serve.matches(_card("Timber Wolves"))
    # A one-shot banding grant is no banding creature.
    assert not serve.matches(_card("Nature's Blessing"))


@pytest.mark.parametrize(
    ("key", "scope"), [("stax_taxes", "opponents"), ("symmetric_stax", "each")]
)
def test_stax_serves_ride_the_two_stax_lanes(key, scope):
    serve = _ident_serve(key, scope, "stax_taxes|opponents|", "symmetric_stax|each|")
    for name in ("Magus of the Moon", "Burning Earth", "Fatespinner"):
        assert serve.matches(_card(name)), name
    # A ramp spell and a life-for-cards engine are not stax.
    assert not serve.matches(_card("Rampant Growth"))
    assert not serve.matches(_card("Necropotence"))


def test_creature_recursion_serve_is_the_self_sacrifice_outlets():
    serve = _ident_serve("creature_recursion", "you", "sacrifice_outlets|you|self")
    assert serve.matches(_card("Spore Frog"))
    assert serve.matches(_card("Sakura-Tribe Elder"))
    assert not serve.matches(_card("Aboroth"))


@pytest.mark.parametrize(
    ("key", "payoff_key", "maker", "payoff", "drawback"),
    [
        (
            "extra_upkeep",
            "upkeep_triggers",
            "Sphinx of the Second Sun",
            "Asylum Visitor",
            "Juzám Djinn",
        ),
        (
            "extra_end_step",
            "end_step_triggers",
            "Y'shtola Rhul",
            "Abiding Grace",
            "Blitz Hellion",
        ),
        (
            "extra_draw_step",
            "draw_step_triggers",
            "Sphinx of the Second Sun",
            "Omen Machine",
            "Mana Vault",
        ),
    ],
)
def test_extra_step_serve_is_the_makers_and_the_payoffs(
    key, payoff_key, maker, payoff, drawback
):
    serve = _ident_serve(key, "you", f"{key}|you|", f"{payoff_key}|you|")
    assert serve.matches(_card(maker))
    assert serve.matches(_card(payoff))
    # A step trigger that only costs you is no payoff: an added step repeats it.
    assert not serve.matches(_card(drawback))
    spec = spec_for(_sig(key))
    # The payoff key resolves to the same spec but opens no avenue of its own:
    # hundreds of commanders carry a step trigger.
    assert spec_for(_sig(payoff_key)) == spec
    assert avenue_spec_for(_sig(payoff_key)) is None
    assert avenue_spec_for(_sig(key)) == spec


def test_attack_matters_serve_rides_the_combat_lanes():
    serve = _ident_serve(
        "attack_matters",
        "you",
        "attack_matters|you|",
        "token_maker|you|*",
        "combat_damage_matters|opponents|",
        "extra_turns|you|",
        "team_buff|you|haste",
        "team_evasion_grant|you|*",
    )
    assert "haste" in serve.keywords
    assert serve.matches(_card("Hellrider"))
    # Cipher is a combat-damage payoff, served by that lane.
    assert serve.matches(_card("Hidden Strings"))
    assert serve.matches(_card("Time Warp"))
    # Dash's reminder text grants haste; the card is no haste enabler.
    assert not serve.matches(_card("Alesha's Vanguard"))
    # A shrinking Aura is removal, not gear for the attacker.
    assert not serve.matches(_card("Aether Meltdown"))


def test_attack_matters_equipment_extra_suits_up_the_attacker():
    spec = spec_for(_sig("attack_matters"))
    assert spec is not None
    gear = extra(spec, "Equipment and Auras that suit up the attacker")
    assert gear.serve is not None
    assert gear.serve.matches(_card("Bonesplitter"))
    assert not gear.serve.matches(_card("Aether Meltdown"))
