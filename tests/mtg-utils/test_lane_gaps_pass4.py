"""The lane gaps and false positives the 2026-11-01 fourth pass closed
(``docs/plans/backlog.md``: "Lane gaps still open" and the bump's policy
questions). Real cards only (ADR-0056): each closed gap, and the near miss that
stays out."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_phase_records, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keyed(name: str, *keys: str) -> set[tuple[str, str, str]]:
    return {i for i in _idents(name) if i[0] in keys}


# ── edict_makers: a granted sacrifice is its holder's controller's ───────────


@pytest.mark.parametrize(
    ("name", "edicts"),
    [
        # "Enchanted creature has 'At the beginning of your upkeep, sacrifice a
        # creature.'" — the enchanted creature's controller sacrifices (CR
        # 603.3a); an any-creature Aura with a drawback is cast on an opponent's.
        ("Inevitable End", {("edict_makers", "opponents", "")}),
        # "sacrifice this creature": the holder itself, removal — no edict.
        ("Necrotic Plague", set()),
        # "Commander creatures you own have '… sacrifice a creature'": yours.
        ("Cultist of the Absolute", set()),
    ],
)
def test_granted_sacrifice_is_the_holders_controllers(name, edicts):
    assert _keyed(name, "edict_makers") == edicts


# ── "that player" after combat damage from your creature is an opponent ─────


@pytest.mark.parametrize(
    ("name", "edicts"),
    [
        # "Whenever ~ deals combat damage to a player, that player sacrifices a
        # creature of their choice": it attacked an opponent (CR 506.2, 802.2).
        ("Demon of Loathing", {("edict_makers", "opponents", "")}),
        ("Wasitora, Nekoru Queen", {("edict_makers", "opponents", "")}),
        # "… each player sacrifices a creature" stays every player's.
        ("Rankle, Master of Pranks", {("edict_makers", "each", "")}),
    ],
)
def test_combat_damaged_player_is_an_opponent(name, edicts):
    assert _keyed(name, "edict_makers") == edicts


# ── sacrifice_outlets: an opponent's sacrifice is no outlet of yours ─────────


@pytest.mark.parametrize(
    ("name", "outlet"),
    [
        # "Whenever an opponent sacrifices a creature, you create a Treasure
        # token": an edict payoff, not a sacrifice of yours.
        ("Malik, Grim Manipulator", False),
        ("Legate Lanius, Caesar's Ace", False),
        # "Whenever you sacrifice a creature, draw a card."
        ("Smothering Abomination", True),
        # "Whenever a player sacrifices a creature" counts yours too.
        ("Mortician Beetle", True),
    ],
)
def test_opponents_sacrifice_trigger_is_no_outlet(name, outlet):
    assert bool(_keyed(name, "sacrifice_outlets")) is outlet


# ── debuff_makers: granted flanking, back-referenced -1/-1 counters ──────────


@pytest.mark.parametrize(
    "name",
    [
        # "Enchanted creature gets +1/+1 and has flanking" (CR 702.25a: the
        # blocker without flanking gets -1/-1).
        "Agility",
        "Sidewinder Sliver",
        "Jabari's Banner",
        # "Choose two target creatures controlled by the same opponent. …
        # Put a -1/-1 counter on the other."
        "Retribution",
        # "Whenever this creature deals combat damage to a creature, put a -1/-1
        # counter on that creature" — the creature it fought is an opponent's.
        "Obelisk Spider",
    ],
)
def test_debuff_reaches_granted_flanking_and_back_referenced_counters(name):
    assert ("debuff_makers", "any", "") in _idents(name)


def test_own_minus_counter_stays_off_debuff():
    """Matopi Golem's -1/-1 counter on itself is a cost, not a debuff."""
    assert not _keyed("Matopi Golem", "debuff_makers")


# ── damage_prevention: a granted absorb ──────────────────────────────────────


def test_granted_absorb_is_damage_prevention():
    # "All Sliver creatures have absorb 1" (CR 702.64a: prevent 1 of the damage).
    assert ("damage_prevention", "you", "") in _idents("Lymph Sliver")


# ── graveyard_matters / graveyard_makers: the own-graveyard remainder ───────


@pytest.mark.parametrize(
    "name",
    [
        # collect evidence (CR 701.59a): a cost, an effect, an additional and
        # an alternative cost
        "Tenth District Hero",
        "Surveillance Monitor",
        "Crimestopper Sprite",
        "Conspiracy Unraveler",
        # forage (CR 701.61a): an effect, a PayCost, an additional cost
        "Corpseberry Cultivator",
        "Bushy Bodyguard",
        "Feed the Cycle",
        # descended this turn (CR 700.11): a trigger condition, a modal gate
        "Ruin-Lurker Bat",
        "Molten Collapse",
        # "Spells you cast have delve" (CR 702.66a)
        "Teval, Arbiter of Virtue",
    ],
)
def test_graveyard_fuel_and_descend_are_graveyard_matters(name):
    assert ("graveyard_matters", "you", "") in _idents(name)


def test_ward_collect_evidence_is_the_opponents_cost():
    # "Ward—Collect evidence 4": the opponent who targets it pays (CR 702.21a).
    assert ("graveyard_matters", "you", "") not in _idents("Axebane Ferox")


def test_granted_soulshift_is_a_graveyard_maker():
    # "~ has soulshift X" (CR 702.46a: return a Spirit card from your graveyard).
    assert ("graveyard_makers", "you", "") in _idents("Kodama of the Center Tree")


# ── a coin flip's losing outcome that undoes the winning one ────────────────


@pytest.mark.retirement_canary
def test_flip_outcome_anaphor_stamped_selfref_canary():
    """Orcish Captain's "If you lose the flip, it gets -0/-2": "it" is the Orc the
    winning outcome targets, but phase stamps the losing ``Pump`` ``SelfRef``.
    ``crosswalk.reads._FLIP_ANAPHOR_TAGS`` takes ``SelfRef`` for it."""
    (rec,) = test_phase_records("Orcish Captain")
    flip = rec["abilities"][0]["effect"]
    assert flip["lose_effect"]["effect"]["target"] == {"type": "SelfRef"}, (
        "Orcish Captain: RETIRE-READY — phase binds the losing flip's 'it' to the "
        "target; drop SelfRef from crosswalk.reads._FLIP_ANAPHOR_TAGS."
    )


@pytest.mark.parametrize(
    ("name", "ident", "fires"),
    [
        # lifegain_matters is YOUR lifegain's payoff: "Whenever an opponent gains
        # life" rewards theirs.
        ("Kavu Predator", ("lifegain_matters", "you", ""), False),
        ("Punishing Fire", ("lifegain_matters", "you", ""), False),
        ("Ajani's Pridemate", ("lifegain_matters", "you", ""), True),
        # commander damage is combat damage (CR 903.10a): a creature that can't
        # attack (CR 702.3b) or dies the first time it does is no carrier.
        ("Cinder Wall", ("voltron_matters", "you", "carrier"), False),
        ("Ceremonial Guard", ("voltron_matters", "you", "carrier"), False),
        ("Novice Knight", ("voltron_matters", "you", "carrier"), True),
        # a defender that loses defender by its own ability attacks then:
        # Torpid Moloch's typed RemoveKeyword, Guardian of the Ages' parked
        # trigger (ledger row loses_defender_trigger_parked)
        ("Torpid Moloch", ("voltron_matters", "you", "carrier"), True),
        ("Guardian of the Ages", ("voltron_matters", "you", "carrier"), True),
        # Enchant restricts what an Aura enchants (CR 702.5a): no keyword body.
        ("Scriv, the Obligator", ("keyword_bodies", "you", "enchant"), False),
        # the white Auras attached to one creature are no colour-keyed board
        ("Word of Undoing", ("color_change", "you", "payoff"), False),
        ("Perish", ("color_change", "you", "payoff"), True),
        # a parked draw the discard pays for is a loot; a conditional one isn't
        ("Messenger Jays", ("self_drawback", "you", "restriction"), False),
        ("Mindstorm Crown", ("self_drawback", "you", "harm"), True),
        # a trigger that exiles the card from its graveyard fires once
        ("Council's Deliberation", ("card_draw_engine", "you", ""), False),
        ("Rhystic Study", ("card_draw_engine", "you", ""), True),
    ],
)
def test_bump_policy_questions(name, ident, fires):
    assert (ident in _idents(name)) is fires


@pytest.mark.parametrize(
    "name",
    [
        # "that player can't attack you or permanents you control during their
        # next turn" — the opponent it dealt combat damage to (CR 510.1c-d)
        "Willie Lumpkin, Postman",
        # "defending player can't cast spells this turn" (CR 506.2)
        "Xantid Swarm",
        # "choose target opponent. This turn, that player can't cast spells …"
        "Sen Triplets",
        # "Target player can't cast creature spells this turn."
        "Cease-Fire",
    ],
)
def test_lock_on_one_player_is_stax_not_symmetric(name):
    keys = _keyed(name, "stax_taxes", "symmetric_stax")
    assert ("stax_taxes", "opponents", "") in keys
    assert not any(k[0] == "symmetric_stax" for k in keys)


def test_losing_flip_that_shrinks_the_pumped_target_is_a_drawback():
    """The -0/-2 lands on the creature you chose for +2/+0: no self pump, no
    debuff — the pump on the target stays."""
    assert ("pump_makers", "you", "target") in _idents("Orcish Captain")
    assert not _keyed("Orcish Captain", "self_pump", "debuff_makers")
