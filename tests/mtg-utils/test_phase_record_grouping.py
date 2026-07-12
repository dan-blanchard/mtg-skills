"""Tests for the shared phase-record grouping seam (``_card_ir.build._group_by_oracle_id``
+ ``_phase.is_impostor_record``).

``_group_by_oracle_id`` is the ONE grouping seam every sidecar consumer shares —
``build_sidecar`` (legacy), ``build_crosswalk_sidecar``, and
``_deck_forge._ir_lookup._phase_record_index`` (production ``trees_for``) all call it,
and ``build_card_snapshot`` calls it too to capture the raw records the committed
snapshot stores (ADR-0039 task #80 step 5). Tested directly against the grouping
function rather than through either sidecar builder — builder-agnostic, so this
coverage survives whichever builder(s) exist after ADR-0039 finishes.

Harvested from the retired ``test_card_ir.py`` (ADR-0039 task #80 step 5): these were
the only two tests in that file exercising SHARED infrastructure rather than
``project.py``'s own private recovery internals; every other test in that file pinned
legacy-only vocabulary (Effect/Quantity/Filter shapes and category strings specific to
``project_card``) with no crosswalk equivalent, so the rest was deleted rather than
ported — see the ADR-0039 step 5 report for the full accounting.
"""

from __future__ import annotations

from mtg_utils._card_ir.build import _group_by_oracle_id
from mtg_utils._phase import is_impostor_record


def test_dfc_faces_grouped_by_oracle_id():
    """Two phase face-records sharing an oracle_id group together, front-face-first
    (insertion order), so a DFC/split card's faces are never silently dropped."""
    front = {
        "name": "Front",
        "scryfall_oracle_id": "dfc-1",
        "card_type": {},
        "keywords": ["Flying"],
    }
    back = {
        "name": "Back",
        "scryfall_oracle_id": "dfc-1",
        "card_type": {},
        "keywords": ["Haste"],
    }
    groups = _group_by_oracle_id({"front": front, "back": back})
    assert [r["name"] for r in groups["dfc-1"]] == ["Front", "Back"]


def test_impostor_record_dropped_at_the_grouping_seam():
    """Task #78: phase's v0.20.0 card-data stamps the PLAYTEST "Fast // Furious"
    card's "Fast" half with the commander-LEGAL card's oracle_id (bulk holds two
    distinct cards with that name), so a naive oracle_id join would serve the
    impostor's haste/unblockable parse off the real discard-draw card.
    ``_group_by_oracle_id`` must drop the known impostor record (keyed by oracle_id
    + exact oracle_text, so the entry self-retires when upstream fixes the join)
    while keeping the real half untouched."""
    oid = "62411ced-843e-4b63-bdf6-dafb2ac27047"
    real = {
        "name": "Fast",
        "scryfall_oracle_id": oid,
        "card_type": {},
        "oracle_text": "Discard a card, then draw two cards.",
    }
    impostor = {
        "name": "Fast",
        "scryfall_oracle_id": oid,
        "card_type": {},
        "oracle_text": (
            "Target creature gains haste until end of turn. It can't be "
            "blocked this turn except by Vehicles or by creatures with "
            "haste.\nFuse (You may cast one or both halves of this card "
            "from your hand.)"
        ),
    }
    groups = _group_by_oracle_id({"fast": real, "fast-impostor": impostor})
    assert [r["name"] for r in groups[oid]] == ["Fast"]  # the impostor never joins
    assert groups[oid][0]["oracle_text"] == real["oracle_text"]
    # the same text under a DIFFERENT oracle_id is NOT an impostor — the key
    # is the (oid, text) pair, never the text alone
    assert is_impostor_record(impostor)
    assert not is_impostor_record(real)
    assert not is_impostor_record({**impostor, "scryfall_oracle_id": "other"})
