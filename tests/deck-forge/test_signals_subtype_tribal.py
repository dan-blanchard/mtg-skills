"""Own-subtype tribal: a creature's own creature type is a deterministic
characteristic (CR 109.3) that tribal cards key off (CR 205.3 / 702.38a) — so a
Giant commander is a viable Giants build even with no tribal *oracle* text. Verified
with rules-lawyer that subtype, not rules text, is the tribal anchor.

Marked LOW confidence (membership ≠ a tribal payoff) and gated to supported RACE
tribes (``_subtypes.TRIBAL_SUBTYPES``) or, for CLASS tribes (``_subtypes.CLASS_TRIBES``
— Soldier, Wizard, Warrior, …), only behind a go-wide-shaped ability; generic class
types with no such gate only matter with explicit oracle support, which already
fires a high-confidence ``type_matters``.

All extraction assertions run the production ``extract_signals`` over the
committed real-card snapshot (``mtg_utils.testkit``); the word-level precision
guards (basic land types / articles / counter-noise never minting a false tribal
subject) call ``_resolve_subject`` directly — the exact vocabulary gate that used
to be probed indirectly through a synthetic no-oracle_id dict (which, post ADR-0039,
resolves to no concept trees and can't reach this logic at all)."""

from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge.signal_base import _resolve_subject
from mtg_utils._deck_forge.signals import coverage_gate
from mtg_utils.testkit import test_card, test_signals


def _subjects(name: str) -> set[str]:
    return {s.subject for s in test_signals(name) if s.key == "type_matters"}


# ── race-tribe members are recovered from their subtype, no oracle needed ──
def test_giant_commander_gets_giant_tribal():
    assert "Giant" in _subjects("Sun Titan")


def test_elder_dragon_gets_dragon_not_elder():
    subs = _subjects("Dragonlord Dromoka")  # Legendary Creature — Elder Dragon
    assert "Dragon" in subs
    assert "Elder" not in subs  # Elder has no tribal support → excluded


def test_bird_knight_gets_both():
    subs = _subjects("Syr Cadian, Knight Owl")  # Legendary Creature — Bird Knight
    assert {"Bird", "Knight"} <= subs


# ── generic class types are NOT offered (avoid flooding every Human/Soldier) ──
def test_giant_soldier_class_type_excluded():
    # Oloro, Ageless Ascetic: Legendary Creature — Giant Soldier, no go-wide ability.
    # Giant (a race) is offered, Soldier (a class with no go-wide gate here) is not.
    subs = _subjects("Oloro, Ageless Ascetic")
    assert "Giant" in subs
    assert "Soldier" not in subs


def test_human_soldier_gets_no_subtype_tribal():
    # Zhou Yu, Chief Commander: Legendary Creature — Human Soldier, no go-wide ability
    # (Human is never a tribe at all; this Soldier has no go-wide gate either).
    assert _subjects("Zhou Yu, Chief Commander") == set()


def test_avatar_is_not_a_supported_tribe():
    # Aeon Chronicler: Creature — Avatar (in the broad subtype vocab for oracle-text
    # capture, but not in TRIBAL_SUBTYPES/CLASS_TRIBES, so own-membership never fires).
    assert _subjects("Aeon Chronicler") == set()


# ── non-creatures never emit creature-tribal ──
def test_noncreature_no_tribal():
    assert _subjects("Aegis of the Legion") == set()  # Artifact — Equipment


# ── confidence: membership is LOW; an oracle payoff stays HIGH ──
def test_own_subtype_tribal_is_low_confidence():
    sig = next(
        s
        for s in test_signals("Grizzly Bears")  # Creature — Bear, vanilla
        if s.key == "type_matters" and s.subject == "Bear"
    )
    assert sig.confidence == "low"


def test_oracle_payoff_stays_high_confidence():
    # Goblin King rewards Goblins in its own oracle text: the oracle signal (high)
    # wins.
    sig = next(
        s
        for s in test_signals("Goblin King")
        if s.key == "type_matters" and s.subject == "Goblin"
    )
    assert sig.confidence == "high"


# ── coverage gate: a bare race-member is surfaced but flagged for agent confirmation ──
def test_bare_tribe_member_routes_to_agent_low_confidence():
    # Grizzly Bears' only signals are the own-subtype tribal + voltron_matters, both
    # low confidence.
    c = test_card("Grizzly Bears")
    sigs = test_signals("Grizzly Bears")
    needs, reason = coverage_gate(c, sigs)
    assert needs is True
    assert reason == "low_confidence"


# ── precision gate: non-creature-type nouns must NEVER mint a tribal subject ──
# (Audit: 'the' (article), basic land types, and 'time' polluted CREATURE_SUBTYPES;
#  'the' alone served ~11,458 cards via its \bThes?\b serve. CR 205.3m: these are not
#  creature types — 'the' is an article, forest/island/mountain are basic LAND types
#  (CR 305.6), and the only two-word creature type is 'Time Lord', not bare 'Time'.)
# ``_resolve_subject`` (moved to ``signal_base``, unchanged) is the exact gate every
# subject-bearing lane runs a capture through — called directly here since these are
# probes of the vocabulary gate itself, not of any one card's extraction.
def test_basic_land_type_is_not_a_creature_tribe():
    assert _resolve_subject("Forest", CREATURE_SUBTYPES) == ""
    assert _resolve_subject("Plains", CREATURE_SUBTYPES) == ""


def test_article_is_not_a_typed_spellcast_subject():
    assert _resolve_subject("the", CREATURE_SUBTYPES) == ""


def test_time_counter_reference_is_not_a_creature_tribe():
    assert _resolve_subject("time", CREATURE_SUBTYPES) == ""


def test_real_tribe_still_minted_after_vocab_prune():
    # the prune must not remove a genuine creature tribe.
    assert "Goblin" in _subjects("Goblin King")
    assert _resolve_subject("Goblin", CREATURE_SUBTYPES) == "Goblin"


def test_orcish_lumberjack_forest_cost_does_not_leak_a_forest_tribe():
    # end-to-end companion to the unit-level guard above: a creature whose ability
    # references "a Forest" (as a sacrifice cost, not a tribal payoff) must not mint
    # a Forest subject through the full extraction path.
    assert "Forest" not in _subjects("Orcish Lumberjack")
