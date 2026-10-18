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
