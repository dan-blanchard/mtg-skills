"""Phase D lane gaps, the voltron_counters slice (``lanes/counters_voltron.py``
and the voltron tells of ``membership_floor.py``).

The membership floor's voltron tells carry the ``carrier`` subject, so the
bare ``voltron_matters|you|`` is the lanes' Aura / Equipment payoff alone; Role
tokens and pump gear are voltron makers; blight and granted wither / infect /
persist place -1/-1 counters; a mill that reaches another player's library is
``mill_makers|opponents|``; populate and the filters of your tokens are
``tokens_matter``. Real cards only (``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils._analysis.lanes.counters_voltron import VOLTRON_GEAR_PUMP
from mtg_utils._analysis.membership_floor import VOLTRON_CARRIER
from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {k for k, _s, _su in _idents(name)}


# ── voltron: the floor's carrier tells vs the lanes' payoff ─────────────────


@pytest.mark.parametrize("name", ["Grizzly Bears", "Isamaru, Hound of Konda"])
def test_commander_damage_tell_is_a_carrier_not_a_payoff(name):
    # CR 903.10a: a body to win with by commander damage, not a card that pays
    # off Equipment and Auras — a serve can read the bare payoff ident.
    idents = _idents(name)
    assert ("voltron_matters", "you", VOLTRON_CARRIER) in idents
    assert ("voltron_matters", "you", "") not in idents


@pytest.mark.parametrize(
    "name",
    [
        "Sram, Senior Edificer",
        # A trigger on an Equipment you control entering, and a static over the
        # Equipment you control.
        "Puresteel Paladin",
        # "Whenever an Aura or Equipment you control is put into a graveyard".
        "Tiana, Ship's Caretaker",
        # A cast permission for Aura and Equipment spells.
        "Galea, Kindler of Hope",
        # "+X/+X, where X is the number of equipped creatures you control".
        "Jor Kadeen, First Goldwarden",
    ],
)
def test_gear_payoffs_carry_the_bare_voltron_payoff(name):
    assert ("voltron_matters", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Monstrous Rage", "Royal Treatment"])
def test_role_token_attached_is_a_voltron_maker(name):
    # CR 303.7: a Role is an Aura, created attached to the creature.
    assert ("voltron_makers", "you", "") in _idents(name)


def test_cursed_role_is_no_voltron_maker():
    # CR 111.10j: the Cursed Role makes the creature a base 1/1.
    assert "voltron_makers" not in _keys("Spiteful Hexmage")


@pytest.mark.parametrize("name", ["Blanchwood Armor", "Bonesplitter"])
def test_pump_gear_is_a_voltron_maker_pump(name):
    assert ("voltron_makers", "you", VOLTRON_GEAR_PUMP) in _idents(name)


@pytest.mark.parametrize("name", ["Pacifism", "Agoraphobia"])
def test_shrinking_aura_is_no_pump_gear(name):
    assert ("voltron_makers", "you", VOLTRON_GEAR_PUMP) not in _idents(name)


# ── minus_counters_matter: blight and granted wither / infect / persist ─────


@pytest.mark.parametrize(
    "name",
    [
        # CR 701.68a blight: an effect, an opponent's blight, a cost.
        "Sourbread Auntie",
        "High Perfect Morcant",
        "Gristle Glutton",
        # CR 702.80a / 702.90c / 702.79a, granted.
        "Corrosive Mentor",
        "Tainted Strike",
        "Cauldron of Souls",
        "Carrion Call",
    ],
)
def test_minus_counter_sources(name):
    assert ("minus_counters_matter", "you", "") in _idents(name)


# ── mill_makers: an opponent scope ──────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Millstone",
        "Nemesis of Reason",
        "Countermand",
        "Sword of Body and Mind",
        "Extract from Darkness",
        # A granted "{T}: Target player mills X cards".
        "Phenax, God of Deception",
    ],
)
def test_opponent_mill(name):
    assert ("mill_makers", "opponents", "") in _idents(name)


@pytest.mark.parametrize("name", ["Stitcher's Supplier", "Combustible Gearhulk"])
def test_self_mill_has_no_opponent_scope(name):
    idents = _idents(name)
    assert ("mill_makers", "any", "") in idents
    assert ("mill_makers", "opponents", "") not in idents


# ── tokens_matter: populate and the filters of your tokens ──────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Growing Ranks",  # CR 701.36a populate
        "Jaheira, Friend of the Forest",  # tokens you control have an ability
        "Baylen, the Haymaker",  # tap untapped tokens you control
        "Curiosity Crafter",  # a creature token you control deals combat damage
        "Magnus the Red",  # costs {1} less for each creature token you control
    ],
)
def test_token_payoffs(name):
    assert ("tokens_matter", "you", "") in _idents(name)


def test_artifact_token_cost_reducer_is_artifacts_matter():
    # "Activated abilities of artifact tokens you control cost {1} less".
    idents = _idents("Mutagen Man, Living Ooze")
    assert ("artifacts_matter", "you", "") in idents
    assert ("tokens_matter", "you", "") not in idents
