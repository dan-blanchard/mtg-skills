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

from mtg_utils._analysis.signal_specs import Serve, spec_for
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
    serve = _ident_serve("keyword_grant_target", "you", "keyword_grant_target|you|")
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
    # A delayed "it gets -1/-0" on an attacker; on a noncreature card phase's
    # SelfRef is the attacking creature.
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
    (soak,) = [ex for ex in spec.extras if ex.label == "Profit from the soaked damage"]
    assert soak.serve is not None
    assert soak.serve.oracle is None
    assert soak.serve.matches(_card("Druid's Call"))
    assert soak.serve.matches(_card("Spiteful Shadows"))
    assert not soak.serve.matches(_card("Brash Taunter"))
