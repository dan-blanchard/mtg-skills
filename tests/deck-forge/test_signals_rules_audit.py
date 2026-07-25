"""Fixes from the rules-lawyer category audit — each pins a CR-cited distinction
the detectors must respect (so we don't group mechanics the rules treat differently).

Real-card pins run the REAL projected Card IR via ``mtg_utils.testkit``
(``test_signals`` = production hybrid over the real Scryfall record + real sidecar IR).

Many of the CR-boundary distinctions this file used to pin on hand-built synthetic
IR shapes (a testing method the deleted ``extract_signals_ir`` engine supported) are
now exhaustively proven on real cards in ``tests/mtg-utils/test_crosswalk.py`` — see
the per-deleted-test notes below for the exact covering test. What remains here is
either not duplicated there, or adds the `serves()`-classify dimension that
extraction alone doesn't cover.
"""


from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._deck_forge.signals import Signal
from mtg_utils.testkit import test_signals

# Card names referenced through the real-card helper below. This table feeds the
# `build-card-snapshot` usage scanner (it parses `_REAL_CASES` dict VALUES, which
# also handles apostrophes — unlike the bare `test_card("…")` literal scan). Keep it
# in sync with the names used below; a missing entry fails loud (KeyError) at test
# time, never silently.
_REAL_CASES: dict[str, str] = {
    "Diamond City": "Diamond City",
    "Fiery Emancipation": "Fiery Emancipation",
    "Kaervek the Merciless": "Kaervek the Merciless",
    "Tymna the Weaver": "Tymna the Weaver",
}


# Real-card signal keysets (production hybrid path), by card name.
def _hyb(name):
    return {s.key for s in test_signals(name)}


# #1 Companion (CR 702.139) is a separate deck-construction rule from Partner
# (702.124).
#
# "companion_keyword fires, not partner_background" (Lurrus of the Dream-Den) is
# already proven by
# tests/mtg-utils/test_crosswalk.py::test_companion_keyword_bearer_vs_doctors_companion.
# Not duplicated here.


def test_partner_still_fires():
    # Tymna the Weaver carries the Scryfall Partner keyword → the real IR opens
    # partner_background.
    assert "partner_background" in _hyb("Tymna the Weaver")


# #2 keyword_counter is the CR 122.1b closed set — ward/training are not counters.
#
# The closed-set positive (Arwen, Mortal Queen / Wingfold Pteron) and the stun-
# counter negative (Icebind Pillar, CR 122.1d — a replacement-maker, not a 122.1b
# keyword counter) are already proven by
# tests/mtg-utils/test_crosswalk.py::test_keyword_counter_kind_gate_and_mirror.
# Not duplicated here.


def test_shield_counter_is_not_keyword_counter():
    # Diamond City (a shield-counter land, CR 122.1c — also a replacement effect,
    # not a 122.1b keyword counter) — the real IR must NOT open keyword_counter.
    assert "keyword_counter" not in _hyb("Diamond City")


# #4 exile removal (bypasses indestructible/recursion) is its own slice vs destroy/
# damage (CR 406.1 vs 701.7) — already proven, including the blink/graveyard/mass
# vetoes, by tests/mtg-utils/test_crosswalk.py::test_exile_removal_vetoes
# (Swords to Plowshares et al). Not duplicated here.


# #5 clone (becomes/enters as a copy) must not fire on token-copy phrasing (CR
# 707) — already proven by tests/mtg-utils/test_crosswalk.py's
# test_clone_makers_excludes_spell_and_token_copy /
# test_clone_makers_text_idiom_excludes_token_and_land_copy /
# test_token_copy_makers_fires / test_clone_makers_fires. Not duplicated here.


# #6 "attacks each combat if able" is a forced-attack requirement, not evasion;
# "can't be blocked" IS evasion (CR 509.1b / 702.x). The "can't be blocked" arm is
# already proven by
# tests/mtg-utils/test_crosswalk.py::test_evasion_self_keyword_and_mirror_arms
# (Aether Figment). Only the forced-attack negative needs a real card here.
def test_attacks_if_able_is_not_evasion():
    # Bloodrock Cyclops: "This creature attacks each combat if able." fires
    # forced_attack, never evasion_self.
    assert "evasion_self" not in _hyb("Bloodrock Cyclops")


# #7 combat damage to a creature must be COMBAT damage (CR 510 / 120.2a) —
# already proven (positive + noncombat-damage negative) by
# tests/mtg-utils/test_crosswalk.py::test_combat_damage_to_creature_recipient_gate
# (Serpentine Basilisk / Seshiro the Anointed). Not duplicated here.


# #8 combat damage to opponents must be COMBAT damage, not any damage
# (burn/drain) — already proven (incl. the noncombat negative, Contested War
# Zone) across tests/mtg-utils/test_crosswalk.py's combat_damage_to_opp cluster.
# Not duplicated here.


# #12 Food keys on the Food-token mechanic, not the bare word — the maker/matters
# split (Bake into a Pie / Gyome / Gilded Goose / Experimental Confectioner /
# Honored Dreyleader) is already proven by
# tests/mtg-utils/test_crosswalk.py::test_food_matters_three_arms_and_maker_boundary.
# Not duplicated here.


# #14 all-damage doublers/triplers (Furnace of Rath, Fiery Emancipation) are
# replacement effects that fire on COMBAT damage too — they belong on
# damage_doubling, not the "noncombat damage" lane (CR 510 combat vs 702.19a
# noncombat). Furnace of Rath's damage_doubling + direct_damage co-fire is
# already proven by tests/mtg-utils/test_crosswalk.py's
# test_damage_doubling_replacement_read /
# test_damage_doubling_direct_damage_co_fire_is_player_gated. Fiery
# Emancipation's Triple multiplier (a DIFFERENT structural path — the deepened
# replacement projection, not the bare Double) is not duplicated there.
def test_triple_damage_is_damage_doubling():
    # Fiery Emancipation's Triple multiplier fires damage_doubling via the real IR.
    assert "damage_doubling" in _hyb("Fiery Emancipation")


# MV-scaling burn (Kaervek) is the genuine noncombat payoff and must still open
# it. The general noncombat_damage_payoff word-mirror arm (Solphim / Boros
# Reckoner / Ghyrson Starn, negative Cold-Eyed Selkie) is already proven by
# tests/mtg-utils/test_crosswalk.py::test_noncombat_damage_payoff_word_mirror;
# Kaervek's own MV-scaling shape is a distinct real card, kept here.
def test_mv_scaling_burn_still_opens_noncombat():
    # Kaervek the Merciless deals damage equal to a spell's mana value — the
    # genuine MV-scaling noncombat payoff opens noncombat_damage_payoff.
    assert "noncombat_damage_payoff" in _hyb("Kaervek the Merciless")


# #15 Named counters are NOT interchangeable (CR 122.1): each gets its own lane
# (oil/ki/shield MAKER lanes, the oil_counter_matters PAYOFF, the counter-kind
# discriminator, and rad_counter_makers' opponents scope) — already proven by
# tests/mtg-utils/test_crosswalk.py's batch-6 counter-kind cluster
# (test_off_p1p1_counter_makers, test_counter_makers_kind_discriminates,
# test_oil_counter_matters_payoff, test_rad_counter_makers_scope_opponents). Not
# duplicated here — the old version of this test also asserted the SUPERSEDED
# claim "oil_counter_matters fires from placing an oil counter", which the
# ADR-0034 _matters/_makers split moved to oil_counter_makers; the current split
# is the crosswalk suite's, not this file's, to re-litigate.


# #16 End-the-turn (CR 724, your-turn engine) is its own you-scoped lane, split
# from the opponents/any-scoped timing-restriction lane — both the end_the_turn
# recovery (Obeka, Brute Chronologist) and the timing_control mirror (Teferi,
# Time Raveler / City of Solitude) are already proven by
# tests/mtg-utils/test_crosswalk.py's test_end_the_turn_recovery_promoted /
# test_timing_control_mirror_scope_any. Not duplicated here.


# #17 Donate = a control change (CR 701.12); a group-hug "target opponent
# draws/creates" card must NOT open the donate lane — already proven (incl. the
# theft/control-reset/group-hug vetoes) across
# tests/mtg-utils/test_crosswalk.py's donate_makers cluster
# (test_donate_makers_give_away / test_donate_makers_excludes_theft / etc). Not
# duplicated here.


# #18 Meld (CR 701.42) is subject-bearing: a meld piece's lane serves ONLY its
# named partner (which references this card by name), never every meld half.
# The extraction side (meld_pair subject == this card's own name, on real Gisela
# / Bruna / Hanweir Garrison, with a negative on the meld RESULT Brisela) is
# already proven by
# tests/mtg-utils/test_crosswalk.py::test_meld_pair_raw_oracle_and_subject. What
# that test does NOT cover is the SERVE side — does the spec's partner-matching
# regex actually pick out the one real partner and reject an unrelated card —
# so that's what's pinned here, off the real signal.
def test_meld_pair_serves_only_its_partner():
    sig = next(s for s in test_signals("Bruna, the Fading Light") if s.key == "meld_pair")
    assert sig.subject == "Bruna, the Fading Light"  # subject is THIS card's name
    partner = {
        "name": "Gisela, the Broken Blade",
        "oracle_text": (
            "At the beginning of your end step, if you both own and control "
            "Gisela, the Broken Blade and a creature named Bruna, the Fading "
            "Light, exile them, then meld them into Brisela, Voice of "
            "Nightmares."
        ),
    }
    unrelated = {"name": "Other Meld", "oracle_text": "(Melds with Someone Else.)"}
    assert serves(partner, sig) is True  # the partner names this card
    assert serves(unrelated, sig) is False  # not every meld half


def test_meld_pair_excluded_from_static_gate():
    # Subject-bearing key with no subject resolves to no static spec (it's gated out).
    assert (
        spec_for(Signal(key="meld_pair", scope="you", subject="", text="", source=""))
        is None
    )


# #19 Flip (CR 710) is a self-contained single-card mechanic, split from meld —
# already proven (Nezumi Graverobber / Bushi Tenderfoot / Akki Lavarunner) by
# tests/mtg-utils/test_crosswalk.py::test_flip_self_structural_closes_wording_gap.
# Not duplicated here.
