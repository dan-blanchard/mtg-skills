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
    toughness is no greater dies (704.5g)."""
    assert {"mass_removal", "damage_equal_power"} <= _keys(name)
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
