"""Phase D lane gaps, protection slice: the feeder subjects four payoff lanes
were missing. ``life_payment_insurance|you|cant_lose`` reads a "can't lose the
game" static that covers you (CR 104.3b / 119.6: 0 or less life loses only as a
state-based action); ``lose_unless_hand`` reads your commander put into your
hand from the command zone (``command_to_hand`` — CR 903.8, Phage's ruling) and
a static that stops entering creatures from triggering abilities
(``etb_silencer``); ``per_target_payoff|you|variable`` reads an instant or
sorcery whose number of targets is variable (CR 601.2c / 601.2d);
``secret_writedown|you|learn`` reads learn (CR 701.48a);
``target_own_payoff|you|free_target`` reads a {0} activation that targets your
own creature (the en-Kor cycle, equip {0} — CR 702.6a).

Every card is a real one, read through the production ``extract_signals``
(``mtg_utils.testkit.test_signals``, ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import (
    filter_controller,
    filter_core_types,
    iter_static_defs,
    static_mode_tag,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _of(name: str, key: str) -> set[tuple[str, str]]:
    return {(scope, subj) for k, scope, subj in _idents(name) if k == key}


# ── life_payment_insurance: the can't-lose insurance ────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Platinum Angel",  # "You can't lose the game"
        "Phyrexian Unlife",  # "don't lose the game for having 0 or less life"
        "Angel's Grace",  # a one-shot "can't lose the game this turn"
        "Gideon of the Trials",  # the emblem's static
        "The Book of Exalted Deeds",  # granted inside "It gains '…'"
        "Everybody Lives!",  # "players can't lose the game" covers you
        "Cloudsteel Kirin",  # the equipped creature's quoted grant
    ],
)
def test_cant_lose_statics_insure_life_payments(name):
    assert ("you", "cant_lose") in _of(name, "life_payment_insurance")


@pytest.mark.parametrize(
    "name",
    [
        "Abyssal Persecutor",  # your OPPONENTS can't lose
        "Platinum Emperion",  # can't lose life: can't pay life either (CR 119.8)
        "Teferi's Protection",
    ],
)
def test_no_insurance_from_opponents_or_frozen_life(name):
    assert ("you", "cant_lose") not in _of(name, "life_payment_insurance")


def test_payer_keeps_the_bare_ident():
    assert _of("Selenia, Dark Angel", "life_payment_insurance") == {("you", "")}
    assert _of("Platinum Angel", "life_payment_insurance") == {("you", "cant_lose")}


# ── lose_unless_hand: command zone to hand, ETB silencers ───────────────────


@pytest.mark.parametrize(
    ("name", "subject"),
    [
        ("Command Beacon", "command_to_hand"),
        ("Campfire", "command_to_hand"),  # "from the command zone and graveyard"
        ("Road of Return", "command_to_hand"),  # a mode
        ("Torpor Orb", "etb_silencer"),
        ("Karn, Argent Defender", "etb_silencer"),  # "artifacts and creatures"
    ],
)
def test_drawback_negators(name, subject):
    assert _of(name, "lose_unless_hand") == {("you", subject)}


@pytest.mark.parametrize(
    "name",
    [
        "Elesh Norn, Mother of Machines",  # silences only opponents' triggers
        "Derevi, Empyrial Tactician",  # onto the battlefield: not cast at all
    ],
)
def test_not_drawback_negators(name):
    assert not _of(name, "lose_unless_hand")


def test_phage_keeps_the_bare_ident():
    assert _of("Phage the Untouchable", "lose_unless_hand") == {("you", "")}


# ── per_target_payoff: a variable number of targets ─────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Aurelia's Fury",  # X damage divided among any number of targets
        "Distorting Wake",  # X target nonland permanents
        "Descent of the Dragons",  # any number of target creatures
        "Flames of the Firebrand",  # one, two, or three targets
        "Lead Astray",  # up to two target creatures
    ],
)
def test_variable_target_spells(name):
    assert ("you", "variable") in _of(name, "per_target_payoff")


@pytest.mark.parametrize(
    "name",
    [
        "Doom Blade",  # one target
        "Frantic Search",  # "untap up to three lands": chosen on resolution
        "Plow Through Reito",  # "return any number of Plains": no target
        "Destined Confrontation",  # each player chooses, then sacrifices
        "Dimir Machinations",  # "exile any number of those cards"
        "Gang of Devils",  # a permanent's trigger, not a spell's targets
    ],
)
def test_not_variable_target_spells(name):
    assert ("you", "variable") not in _of(name, "per_target_payoff")


def test_hinata_keeps_the_bare_ident():
    assert _of("Hinata, Dawn-Crowned", "per_target_payoff") == {("you", "")}


# ── secret_writedown: learn ─────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["Eyetwitch", "Pop Quiz", "Overgrown Arch"])
def test_learn_fetches_from_outside_the_game(name):
    assert ("you", "learn") in _of(name, "secret_writedown")


def test_wish_keeps_the_bare_ident_and_companion_stays_out():
    assert _of("Burning Wish", "secret_writedown") == {("you", "")}
    # A companion's reminder text names "outside the game"; it is no wish.
    assert not _of("Lurrus of the Dream-Den", "secret_writedown")


# ── target_own_payoff: free targeting of your own creature ──────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Nomads en-Kor",  # {0}: … dealt to target creature you control
        "Shuko",  # equip {0}
        "Lightning Greaves",
        "Puresteel Paladin",  # equip {0} granted to your Equipment
        "Nahiri, the Lithomancer",  # a token with equip {0}
        "Reconnaissance",  # {0}: remove target attacking creature you control
    ],
)
def test_free_own_target_activations(name):
    assert ("you", "free_target") in _of(name, "target_own_payoff")


@pytest.mark.parametrize(
    "name",
    [
        "Lazav, the Multifarious",  # {X}: counts 0 but is not free
        "Mavinda, Students' Advocate",  # a card in your graveyard
        "Gaea's Touch",  # no target
        "Auriok Steelshaper",  # an equip reducer, not an equip {0}
    ],
)
def test_not_free_own_target_activations(name):
    assert ("you", "free_target") not in _of(name, "target_own_payoff")


def test_becomes_target_payoff_keeps_the_bare_ident():
    assert _of("Monk Gyatso", "target_own_payoff") == {("you", "")}


@pytest.mark.retirement_canary
def test_auriok_steelshaper_equip_reducer_misparse_canary():
    """Retirement canary for ``free_own_target_activations``' equip-on-a-non-
    Equipment skip: phase v0.104.0 writes Auriok Steelshaper's "Equip costs you
    pay cost {1} less" as an equip {0} ability of its own."""
    equips = [
        ability.get("cost")
        for record in test_phase_records("Auriok Steelshaper")
        for ability in record.get("abilities") or ()
        if (ability.get("ability_tag") or {}).get("type") == "Equip"
    ]
    assert equips, (
        "Auriok Steelshaper: RETIRE-READY — phase no longer gives it an equip "
        "ability. The non-Equipment equip skip in "
        "crosswalk.reads.free_own_target_activations (and this canary) can go."
    )


# ── cipher: the encoded creature's combat-damage trigger ────────────────────


@pytest.mark.parametrize("name", ["Hidden Strings", "Last Thoughts"])
def test_cipher_is_a_combat_damage_payoff(name):
    # CR 702.99a: the encoded creature has "Whenever this creature deals combat
    # damage to a player, you may copy the encoded card …".
    assert ("opponents", "") in _of(name, "combat_damage_matters")


@pytest.mark.retirement_canary
def test_cloudsteel_kirin_cant_lose_still_unscoped_canary():
    """Retirement canary for ``crosswalk.reads._player_static_side``'s
    unscoped-``Typed`` arm (no controller, no type → every player): phase
    v0.104.0 leaves Cloudsteel Kirin's quoted "You can't lose the game" with
    neither, where the opponents' half of the same grant is typed Opponent."""
    test_signals("Cloudsteel Kirin")  # seeds the snapshot's trees (CI-safe)
    unscoped = [
        sdef
        for tree in trees_for(test_card("Cloudsteel Kirin"))
        for unit in tree.units
        for sdef in iter_static_defs(unit.node, granted=True)
        if static_mode_tag(sdef) == "CantLoseTheGame"
        and filter_controller(sdef.affected) is None
        and not filter_core_types(sdef.affected)
    ]
    assert unscoped, (
        "crosswalk.reads._player_static_side: RETIRE-READY — phase now scopes "
        "Cloudsteel Kirin's 'You can't lose the game'. Drop the unscoped-Typed "
        "'each' arm if no other card still needs it."
    )
