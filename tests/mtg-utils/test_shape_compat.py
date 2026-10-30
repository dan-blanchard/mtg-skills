"""``_card_ir.shape_compat``: a renamed phase shape written back in its old form."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.shape_compat import restore_renamed_shapes
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
