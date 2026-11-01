"""``_card_ir.misparsed_shapes``: a shape phase misparses, rewritten on the raw record
before strict load."""

from __future__ import annotations

import pytest

from mtg_utils._analysis.roles import is_board_wipe, role_of
from mtg_utils._card_ir.misparsed_shapes import correct_misparsed_shapes
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _effects(rec: dict) -> list[dict]:
    """Each head ability's effect: the face's abilities and its triggers' bodies."""
    bodies = [*(rec.get("abilities") or ()), *(t["execute"] for t in rec["triggers"])]
    return [b["effect"] for b in bodies]


def _keys(name: str) -> set[str]:
    return {s.key for s in test_signals(name)}


@pytest.mark.retirement_canary
def test_self_damage_sweep_canary():
    """Solar Blaze's "Each creature deals damage to itself equal to its power":
    phase types the targeted form's ``DealDamage`` with the target dropped, so it
    heads the ability with a ``ParentTarget`` that names nothing. The stage
    rewrites it to a ``DamageAll`` over every creature."""
    (rec,) = test_phase_records("Solar Blaze")
    (before,) = _effects(rec)
    assert before["type"] == "DealDamage", (
        "misparsed_shapes self-damage sweep: RETIRE-READY — phase types Solar "
        "Blaze's population itself. Delete the sweep row of misparsed_shapes (the "
        "module, once it holds no row) and this canary."
    )
    assert before["target"] == {"type": "ParentTarget"}
    (after,) = _effects(correct_misparsed_shapes(rec))
    assert after["type"] == "DamageAll"
    assert after["target"]["type_filters"] == ["Creature"]
    assert after["amount"] == before["amount"]
    assert after["damage_source"] == "Target"
    assert _effects(rec)[0]["type"] == "DealDamage"  # the input is untouched


@pytest.mark.parametrize("name", ["Solar Blaze", "Wave of Reckoning", "The Akroan War"])
def test_self_damage_sweep_is_a_board_wipe(name):
    """Each creature is dealt damage equal to its power (CR 120.3e) and one whose
    toughness is no greater dies (704.5g). No creature of yours sizes the
    damage, so it is no power-as-damage payoff (``crosswalk.power_is_yours``)."""
    assert "mass_removal" in _keys(name)
    assert "damage_equal_power" not in _keys(name)
    assert is_board_wipe(test_card(name))
    assert "board_wipe" in role_of(test_card(name))


@pytest.mark.parametrize(
    "name",
    [
        "Repentance",  # "Target creature deals damage to itself …": after a target
        "Stuffy Doll",  # "This creature deals 1 damage to itself": a fixed amount
    ],
)
def test_one_creature_damaging_itself_is_no_sweep(name):
    (rec,) = test_phase_records(name)
    assert correct_misparsed_shapes(rec) is rec
    assert "mass_removal" not in _keys(name)


@pytest.mark.retirement_canary
def test_graveyard_arrival_unknown_mode_canary():
    """Disa the Restless's "Whenever a Lhurgoyf permanent card is put into your
    graveyard from anywhere other than the battlefield": phase leaves the trigger
    mode ``Unknown`` with no zone fields. The stage rewrites it to the
    ``ChangesZone`` → Graveyard form of every other "from anywhere" arrival."""
    (rec,) = test_phase_records("Disa the Restless")
    before = rec["triggers"][0]
    assert isinstance(before["mode"], dict), (
        "misparsed_shapes graveyard arrival: RETIRE-READY — phase types Disa the "
        "Restless's Lhurgoyf graveyard trigger. Delete the arrival row of "
        "misparsed_shapes and this canary."
    )
    assert "Unknown" in before["mode"]
    assert before["destination"] is None
    after = correct_misparsed_shapes(rec)["triggers"][0]
    assert after["mode"] == "ChangesZone"
    assert after["destination"] == "Graveyard"
    assert after["origin"] is None  # phase has no "other than the battlefield"
    assert {"Subtype": "Lhurgoyf"} in after["valid_card"]["type_filters"]
    assert after["valid_card"]["properties"] == [{"type": "Owned", "controller": "You"}]
    assert after["execute"] == before["execute"]  # the typed body is kept
    assert isinstance(rec["triggers"][0]["mode"], dict)  # the input is untouched
    assert {"subtype_ref|you|Lhurgoyf"} <= {
        f"{s.key}|{s.scope}|{s.subject}" for s in test_signals("Disa the Restless")
    }


def test_other_unknown_mode_returns_are_not_graveyard_arrivals():
    # "When target creature dies this turn, return that card to the battlefield"
    # (Graceful Reprieve) has the same typed body under an Unknown mode: a death.
    (rec,) = test_phase_records("Graceful Reprieve")
    assert correct_misparsed_shapes(rec) is rec
