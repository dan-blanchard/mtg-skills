"""Phase D lane fixes in ``lanes/board_and_ramp.py``, ``lanes/keyword_mechanics.py``
and ``tree_synthesis/combat.py`` (2026-10-23): the blink enabler subject, the
board-power thresholds, granted / printed attack-trigger keywords with exert and
enlist, and the conjure keyword action. Real cards via ``mtg_utils.testkit``."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import tag_of
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


# ── (1) blink_flicker: the enabler subject ───────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Ephemerate",
        "Conjurer's Closet",
        "Restoration Angel",
        "Flickerwisp",
        # Modal self-blinks whose "return it" phase binds to the cast trigger's
        # source (the retirement canary below).
        "Ojutai Exemplars",
        "Djinn of the Fountain",
    ],
)
def test_a_flicker_enabler_carries_the_enabler_subject(name):
    assert "blink_flicker|you|enabler" in _idents(name)


@pytest.mark.parametrize("name", ["Dragoon's Wyvern", "Mulldrifter"])
def test_an_etb_body_keeps_the_bare_blink_ident(name):
    """The membership floor's "worth blinking" ETB body is not an enabler."""
    idents = _idents(name)
    assert "blink_flicker|you|" in idents
    assert "blink_flicker|you|enabler" not in idents


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Ojutai Exemplars", "Djinn of the Fountain"])
def test_cast_trigger_self_return_is_bound_to_the_triggering_source(name):
    """Phase binds the self-blink mode's "Return it" to ``TriggeringSource`` (the
    cast spell) instead of the exiled creature. Once phase binds it to the card
    itself for both, the ``TriggeringSource`` arm of ``_blink_flicker`` can go."""
    tags = {
        tag_of(getattr(c.node, "target", None))
        for tree in trees_for(test_card(name))
        for unit in tree.units
        for c in unit.effects
        if c.concept == "change_zone"
    }
    assert "TriggeringSource" in tags


# ── (2) power_matters: board-power thresholds ────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Gnoll Hunter",  # pack tactics: the attackers' total power
        "Werewolf Pack Leader",
        "Owlbear Shepherd",  # "creatures you control have total power 8 or greater"
        "Mosswort Bridge",  # the hideaway gate
        "Leafkin Avenger",  # a mana ability's count of power-4 creatures
        "Temur Battlecrier",  # a ModifyCost count
        "Gwenna, Eyes of Gaea",  # "whenever you cast a creature spell with power 5"
    ],
)
def test_a_power_threshold_payoff_is_power_matters(name):
    assert "power_matters|you|" in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Vulpine Harvester",  # total power compared to a mana value: a scaler
        "Carrion Grub",  # greatest power in your graveyard
        "Big Game Hunter",  # removal of a power-4 creature
        "MacCready, Lamplight Mayor",  # "a creature with power 4 or greater attacks you"
    ],
)
def test_a_power_reference_that_is_not_your_board_is_not_power_matters(name):
    assert "power_matters|you|" not in _idents(name)


# ── (3) attack_matters: attack-trigger keywords, exert, enlist ───────────────


@pytest.mark.parametrize(
    "name",
    [
        "Legion Loyalty",  # "creatures you control have myriad"
        "Sozin's Comet",  # "each creature you control gains firebending 5"
        "Fire Nation Attacks",  # tokens "with firebending 1"
        "Frenzy Sliver",  # "all Sliver creatures have frenzy 1"
        "Fire Sages",  # printed firebending, which phase drops
        "Ahn-Crop Crasher",  # "you may exert this creature as it attacks"
        "Argivian Cavalier",  # enlist
    ],
)
def test_an_attack_trigger_keyword_is_attack_matters(name):
    assert "attack_matters|you|" in _idents(name)


@pytest.mark.retirement_canary
def test_phase_drops_printed_firebending():
    """Phase carries no trigger for printed firebending (CR 702.189a: "Whenever
    this creature attacks, add N {R}"), so the bulk keyword array is the lane's
    read. Once phase types it, the keyword arm is redundant."""
    events = {
        unit.trigger_event
        for tree in trees_for(test_card("Fire Sages"))
        for unit in tree.units
    }
    assert "attacks" not in events


def test_a_granted_block_trigger_keyword_is_not_attack_matters():
    """Flanking triggers on blocks (CR 702.25a): ``blocked_matters``' turf."""
    assert "attack_matters|you|" not in _idents("Agility")


# ── (4) conjure_makers ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Tome of the Infinite",  # DraftFromSpellbook with ``random`` set
        "Clone Crafter",  # a conjure clause phase parks as Unimplemented
    ],
)
def test_a_conjure_card_is_a_conjure_maker(name):
    assert "conjure_makers|you|" in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Silvanus's Invoker",  # an ability NAMED "Conjure Elemental"
        "Big Spender",  # drafts from a spellbook: no conjure
    ],
)
def test_a_non_conjure_card_is_not_a_conjure_maker(name):
    assert "conjure_makers|you|" not in _idents(name)


def test_recovered_conjure_clause_is_a_conjure_not_a_token():
    """A conjured card is a real card, "not a token and not a copy" (the digital
    supplement's DD2.1): Clone Crafter's recovered conjure clause reads as the
    conjure concept, never make_token."""
    test_signals("Clone Crafter")  # seeds the snapshot's trees (CI-safe)
    trees = trees_for(test_card("Clone Crafter"))
    assert any(
        c.recovered_by == "conjure" for t in trees for c in t.effect_concepts("conjure")
    )
    assert not any(
        "onjure" in (c.raw or "")
        for t in trees
        for c in t.effect_concepts("make_token")
    )


# ── (5) sacrifice_outlets|you|self: a creature that sacrifices itself ────────


@pytest.mark.parametrize(
    "name",
    [
        "Spore Frog",  # "Sacrifice this creature: Prevent all combat damage …"
        "Sakura-Tribe Elder",
        "Hajar, Loyal Bodyguard",  # "Sacrifice Hajar: …" — by name
    ],
)
def test_a_self_sacrificing_creature_is_the_self_subject(name):
    idents = _idents(name)
    assert "sacrifice_outlets|you|self" in idents
    assert "sacrifice_outlets|you|" not in idents


def test_a_real_outlet_keeps_the_bare_ident_only():
    idents = _idents("Viscera Seer")
    assert "sacrifice_outlets|you|" in idents
    assert "sacrifice_outlets|you|self" not in idents


def test_a_noncreature_that_sacrifices_itself_is_not_the_self_subject():
    """Mind Stone's "{1}, {T}, Sacrifice this artifact: Draw a card" is no
    creature for a recursion engine to loop."""
    assert "sacrifice_outlets|you|self" not in _idents("Mind Stone")
