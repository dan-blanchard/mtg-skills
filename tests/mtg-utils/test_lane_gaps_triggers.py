"""Phase D lane gaps, the triggers slice (``lanes/triggers_damage.py`` and the
``bounce_tempo`` synthesis arm in ``tree_synthesis/mana_ramp_lands.py``).

``bounce_tempo`` answers a permanent: a spell bounce, your own permanent, the
card itself and a linked exile return stay out, a granted bounce counts.
``protection_grant`` reads every protective grant to something other than the
card — a target permanent, a typed team, a ``ChooseOneOf`` branch, and you.
Real cards only (``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import effect_back_reference, tag_of
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {k for k, _s, _su in _idents(name)}


# ── bounce_tempo ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Boomerang",
        # "Target spell or creature" names a permanent too.
        "Unsubstantiate",
        # A granted bounce: an activated ability and a damage trigger.
        "Banishing Knack",
        "Arm with Aether",
        # "Return that creature" names the creature it blocks.
        "Kaijin of the Vanishing Touch",
        # "Return those creatures": two chosen targets.
        "Run Away Together",
        # "Return that creature": the creature a target trigger watches.
        "Cowardice",
    ],
)
def test_bounce_tempo_fires(name):
    assert "bounce_tempo" in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        # A spell on the stack is no permanent (CR 112.1).
        "Reprieve",
        # A copied spell's "return it" is the spell.
        "Narset's Reversal",
        # "Target creature you control … Return it": your own permanent.
        "Dragon Mask",
        # "Return it" at your end step: the card itself.
        "Cactuar",
        # The cards another ability exiled (CR 607.2a).
        "Tidehollow Sculler",
        # A card taken from an opponent's hand, never a permanent.
        "Planeswalker's Mischief",
        # Your own blocked creature; a creature you own.
        "Cunning Evasion",
        "Saving Grasp",
    ],
)
def test_bounce_tempo_answers_a_permanent(name):
    assert "bounce_tempo" not in _keys(name)


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Dragon Mask", "chosen"),
        ("Kaijin of the Vanishing Touch", "event"),
        ("Cactuar", "self"),
        ("Tidehollow Sculler", "linked"),
    ],
)
def test_effect_back_reference_kind(name, kind):
    kinds = {
        effect_back_reference(unit, n)[0]
        for tree in trees_for(test_card(name))
        for unit in tree.units
        for n in unit.iter_typed()
        if tag_of(n) == "Bounce"
        and tag_of(getattr(n, "target", None)) in ("ParentTarget", "TrackedSet")
    }
    assert kinds == {kind}


# ── protection_grant ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        # A target permanent you control (CR 702.11b).
        "Tamiyo's Safekeeping",
        "Razor Barrier",
        "Vigorbloom Charm",
        # A ChooseOneOf branch the threaded grant walk doesn't follow.
        "Giver of Runes",
        # A typed team.
        "Brave the Elements",
        # You (CR 702.11c: "Hexproof" on a player).
        "Leyline of Sanctity",
        "Teferi's Protection",
        "Veil of Summer",
    ],
)
def test_protection_grant_reads_every_recipient(name):
    assert ("protection_grant", "you", "") in _idents(name)


def test_protection_grant_skips_a_card_granting_itself():
    """Slippery Bogle's printed hexproof (and its reminder text, which the old
    serve regex read) grants nothing."""
    assert "protection_grant" not in _keys("Slippery Bogle")


# ── keyword_grant_target subjects ────────────────────────────────────────────


def test_creature_type_target_names_the_keyword():
    """A creature-type target ("Target Vampire gains haste"): a creature type alone names a creature
    (CR 205.3m), so the keyword rides as the subject; the subject-less key keeps
    its creature-core gate."""
    idents = _idents("Olivia's Bloodsworn")
    assert ("keyword_grant_target", "you", "haste") in idents
    assert ("keyword_grant_target", "you", "") not in idents
