"""``_card_ir.shape_compat``: a renamed phase shape written back in its old form."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.shape_compat import restore_renamed_shapes
from mtg_utils._card_ir.trees import _iter_raw_dicts
from mtg_utils.testkit import test_phase_records, test_signals


def _watched(rec: dict) -> list[dict]:
    return [t["valid_card"] for t in rec.get("triggers") or () if t.get("valid_card")]


@pytest.mark.retirement_canary
def test_graveyard_owner_controller_canary():
    """Shirei, Shizo's Caretaker's "Whenever a creature with power 1 or less is put
    into your graveyard from the battlefield": phase types "your graveyard" as an
    ``Owned`` property with no controller; the stage copies the owner onto the
    controller (CR 400.3: a card goes to its owner's graveyard) and keeps the
    property."""
    (rec,) = test_phase_records("Shirei, Shizo's Caretaker")
    (before,) = _watched(rec)
    assert before.get("controller") is None, (
        "shape_compat owner-as-controller: RETIRE-READY — phase writes the "
        "graveyard trigger's controller itself again. Delete the stage and this "
        "canary."
    )
    out = restore_renamed_shapes(rec)
    (after,) = _watched(out)
    assert after["controller"] == "You"
    assert any(p.get("type") == "Owned" for p in after["properties"])
    assert before.get("controller") is None  # the input record is untouched


def test_graveyard_owner_reads_as_yours():
    idents = {(s.key, s.scope) for s in test_signals("Shirei, Shizo's Caretaker")}
    assert ("low_power_matters", "you") in idents


def test_folded_trigger_reads_each_clause_destination():
    """A folded trigger (Dreadhound) carries each zone change's destination on its
    ``zone_change_clauses``; only the graveyard clause's owner moves."""

    def owned() -> dict:
        return {
            "type": "Typed",
            "controller": None,
            "type_filters": ["Creature"],
            "properties": [{"type": "Owned", "controller": "You"}],
        }

    rec = {
        "triggers": [
            {
                "mode": "ChangesZoneAll",
                "destination": None,
                "zone_change_clauses": [
                    {"destination": "Graveyard", "valid_card": owned()},
                    {"destination": "Exile", "valid_card": owned()},
                ],
            }
        ]
    }
    out = restore_renamed_shapes(rec)
    gy, exile = out["triggers"][0]["zone_change_clauses"]
    assert gy["valid_card"]["controller"] == "You"
    assert exile["valid_card"]["controller"] is None


@pytest.mark.retirement_canary
def test_targeted_and_attached_canary():
    """Eaten by Spiders' "Destroy target creature with flying and all Equipment
    attached to that creature": phase writes a ``TargetOnly`` and one
    ``DestroyAll`` over ``Or[ParentTarget, the Equipment attached to it]``; the
    stage writes the ``Destroy`` of the target back and keeps the Equipment
    arm on the mass verb."""
    (rec,) = test_phase_records("Eaten by Spiders")
    (ability,) = rec["abilities"]
    assert ability["effect"]["type"] == "TargetOnly", (
        "shape_compat targeted-and-attached: RETIRE-READY — phase writes the "
        "targeted verb itself again. Delete the row and this canary."
    )
    out = restore_renamed_shapes(rec)
    (after,) = out["abilities"]
    assert after["effect"]["type"] == "Destroy"
    assert after["effect"]["target"] == ability["effect"]["target"]
    mass = after["sub_ability"]["effect"]
    assert mass["type"] == "DestroyAll"
    assert mass["target"]["type"] == "Typed"
    assert ability["effect"]["type"] == "TargetOnly"  # the input is untouched


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Eaten by Spiders", ("removal", "you")),
        ("Soul Nova", ("exile_removal", "you")),
        ("Silence the Believers", ("exile_removal", "you")),
        ("Word of Undoing", ("bounce_tempo", "you")),
        ("Portal of Sanctuary", ("permanent_recast", "you")),
    ],
)
def test_a_targeted_object_and_its_attachments_read_as_the_targeted_verb(name, ident):
    idents = {(s.key, s.scope) for s in test_signals(name)}
    assert ident in idents


def _nodes(node: object) -> list[dict]:
    return list(_iter_raw_dicts(node, lambda _d: True))


def _zero_floors(rec: dict) -> list[dict]:
    return [
        n
        for n in _nodes(rec)
        if n.get("type") == "ClampMin" and (n.get("inner") or {}).get("type") == "Ref"
    ]


@pytest.mark.retirement_canary
def test_zero_floor_canary():
    """Craterhoof Behemoth's "+X/+X, where X is the number of creatures you
    control": phase wraps the count in ``ClampMin{minimum: 0}``; the stage hands
    the reads the count itself."""
    (rec,) = test_phase_records("Craterhoof Behemoth")
    assert _zero_floors(rec), (
        "shape_compat zero floor: RETIRE-READY — phase no longer wraps a counted "
        "amount in ClampMin. Delete _is_zero_floor, its arm of _node_form and "
        "this canary."
    )
    out = restore_renamed_shapes(rec)
    assert not _zero_floors(out)
    assert any(n.get("type") == "ObjectCount" for n in _nodes(out))
    assert _zero_floors(rec)  # the input is untouched


def test_a_floored_expression_keeps_its_floor():
    # synthetic: "X minus 2", floored — the form phase wrote before v0.131.0
    floor = {
        "type": "ClampMin",
        "minimum": 0,
        "inner": {"type": "Offset", "inner": {"type": "Ref"}, "offset": -2},
    }
    rec = {"abilities": [{"effect": {"type": "Draw", "count": floor}}]}
    assert restore_renamed_shapes(rec) is rec


def test_a_floored_difference_still_loads():
    """Doran, Besieged by Time's "+X/+X, where X is the difference between its
    power and toughness" floors a ``Difference``, which the pump's slot doesn't
    take bare: the floor stays and the card keeps its tree."""
    (rec,) = test_phase_records("Doran, Besieged by Time")
    assert any(
        n.get("type") == "ClampMin" and (n.get("inner") or {}).get("type") != "Ref"
        for n in _nodes(rec)
    )
    assert "toughness_combat" in {
        s.key for s in test_signals("Doran, Besieged by Time")
    }


@pytest.mark.parametrize(
    "name", ["Craterhoof Behemoth", "Bonehoard", "Aspect of Hydra"]
)
def test_floored_counts_scale(name):
    assert "scaling_pump" in {s.key for s in test_signals(name)}


def _cant_be_targeted(rec: dict) -> list[dict]:
    return [n for n in _nodes(rec) if isinstance(n.get("mode"), dict)]


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Canopy Cover", "Vines of Vastwood"])
def test_spelled_out_hexproof_canary(name):
    """ "Can't be the target of spells or abilities your opponents control" is
    what hexproof means (CR 702.11b). Phase types it as a ``CantBeTargeted``
    static mode — the static's own (Canopy Cover) or under an ``AddStaticMode``
    (Vines of Vastwood); the stage writes the keyword grant back."""
    (rec,) = test_phase_records(name)
    spelled = [
        n
        for n in _cant_be_targeted(rec)
        if n["mode"] == {"CantBeTargeted": {"who": "Opponents"}}
    ]
    assert spelled, (
        f"shape_compat spelled-out hexproof: RETIRE-READY — phase no longer types "
        f"{name}'s clause as CantBeTargeted. With both cases gone, delete the "
        "hexproof arm of _node_form and this canary."
    )
    out = restore_renamed_shapes(rec)
    assert not [
        n
        for n in _cant_be_targeted(out)
        if n["mode"] == {"CantBeTargeted": {"who": "Opponents"}}
    ]
    assert {"type": "AddKeyword", "keyword": "Hexproof"} in list(_nodes(out))
    assert ("keyword_bodies", "hexproof") in {
        (s.key, s.subject) for s in test_signals(name)
    }


@pytest.mark.retirement_canary
def test_owner_shuffles_target_canary():
    """Oblation's "The owner of target nonland permanent shuffles it into their
    library, then draws two cards": phase writes a ``TargetOnly``, a
    ``ChangeZoneAll`` of the ``ParentTarget`` and an owner-scoped shuffle and
    draw; the stage writes the targeted move and the ``ParentTargetOwner``
    player back."""
    (rec,) = test_phase_records("Oblation")
    (ability,) = rec["abilities"]
    assert ability["effect"]["type"] == "TargetOnly", (
        "shape_compat owner shuffles: RETIRE-READY — phase writes the targeted "
        "move itself again. Delete _owner_shuffle, _write_owner_shuffle and "
        "this canary."
    )
    out = restore_renamed_shapes(rec)
    (after,) = out["abilities"]
    move = after["effect"]
    assert (move["type"], move["destination"]) == ("ChangeZone", "Library")
    assert move["owner_library"] is True
    assert move["target"] == ability["effect"]["target"]
    shuffle = after["sub_ability"]
    assert shuffle["effect"] == {
        "type": "Shuffle",
        "target": {"type": "ParentTargetOwner"},
    }
    assert "player_scope" not in shuffle
    draw = shuffle["sub_ability"]
    assert draw["effect"]["target"] == {"type": "ParentTargetOwner"}
    assert draw["condition"] is None
    assert ability["effect"]["type"] == "TargetOnly"  # the input is untouched


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Oblation", ("removal", "you")),
        ("Oblation", ("target_player_draws", "any")),
        ("Chaos Warp", ("removal", "you")),
        ("Chaos Warp", ("cheat_into_play", "any")),
    ],
)
def test_owner_shuffles_reads_as_the_targeted_move(name, ident):
    assert ident in {(s.key, s.scope) for s in test_signals(name)}


@pytest.mark.retirement_canary
def test_single_clause_arrival_canary():
    """Disa the Restless's "Whenever a Lhurgoyf permanent card is put into your
    graveyard from anywhere other than the battlefield": phase names the watched
    card on the trigger's one zone-change clause; the stage copies it onto the
    trigger."""
    (rec,) = test_phase_records("Disa the Restless")
    before = rec["triggers"][0]
    assert before["valid_card"] is None, (
        "shape_compat single-clause arrival: RETIRE-READY — phase writes Disa the "
        "Restless's watched card on the trigger. Delete _single_clause_arrival, "
        "its use in restore_renamed_shapes and this canary."
    )
    after = restore_renamed_shapes(rec)["triggers"][0]
    assert {"Subtype": "Lhurgoyf"} in after["valid_card"]["type_filters"]
    assert after["valid_card"]["controller"] == "You"  # the owner, copied
    assert after["origin"] is None
    assert before["valid_card"] is None  # the input is untouched
    assert {"subtype_ref|you|Lhurgoyf"} <= {
        f"{s.key}|{s.scope}|{s.subject}" for s in test_signals("Disa the Restless")
    }


@pytest.mark.retirement_canary
def test_self_owned_by_you_canary():
    """Zodiac Dragon's "When this creature is put into your graveyard from the
    battlefield": phase types the watched card as ``And[SelfRef, a card you
    own]``; the stage writes the bare ``SelfRef`` back."""
    (rec,) = test_phase_records("Zodiac Dragon")
    (before,) = _watched(rec)
    assert before["type"] == "And", (
        "shape_compat self owned by you: RETIRE-READY — phase writes Zodiac "
        "Dragon's watched card as SelfRef again. Delete _is_self_owned_by_you, "
        "its arm of _node_form and this canary."
    )
    (after,) = _watched(restore_renamed_shapes(rec))
    assert after == {"type": "SelfRef"}
    assert before["type"] == "And"  # the input is untouched
    assert "self_recurring" in {s.key for s in test_signals("Zodiac Dragon")}
