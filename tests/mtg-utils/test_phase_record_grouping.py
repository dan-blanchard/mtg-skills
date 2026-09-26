"""Tests for the shared phase-record grouping seam (``_card_ir.build._group_by_oracle_id``
+ ``_phase.is_impostor_record``).

``_group_by_oracle_id`` is the ONE grouping seam every sidecar consumer shares —
``build_crosswalk_sidecar`` (the legacy ``build_sidecar`` died in step 7) and
``_card_ir.trees._phase_record_index`` (production ``trees_for``) call it,
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
    """Task #78: bulk holds two distinct cards named "Fast // Furious" (the
    commander-LEGAL discard-draw J21/MH2 card, 62411ced, and a not_legal
    PLAYTEST haste/unblockable Fuse card, 298a6369) and phase's name-keyed
    corpus mis-joins them. The direction has flipped across pins (see
    ``_phase._IMPOSTOR_RECORDS``); at v0.94.0 the legal card's own "Fast"
    record is correct and a SECOND record stamped with the legal oracle_id
    carries the PLAYTEST card's text. A naive oracle_id join would serve the
    playtest parse off the legal card. ``_group_by_oracle_id`` must drop the
    known impostor (keyed by oracle_id + exact oracle_text, so the entry
    self-retires when upstream fixes the join) while keeping the real half
    untouched. The texts are the impostor KEY itself — a fact about phase's
    records, which the snapshot never stores (the seam drops it) — so they
    are written here, not taken from testkit."""
    legal = "62411ced-843e-4b63-bdf6-dafb2ac27047"
    playtest = "298a6369-1c1f-4d75-aa97-69c56323c122"
    real = {
        "name": "Fast",
        "scryfall_oracle_id": legal,
        "card_type": {},
        "oracle_text": "Discard a card, then draw two cards.",
    }
    impostor = {  # the PLAYTEST card's half, mis-stamped with the legal oid
        "name": "Fast",
        "scryfall_oracle_id": legal,
        "card_type": {},
        "oracle_text": (
            "Target creature gains haste until end of turn. It can't be "
            "blocked this turn except by Vehicles or by creatures with "
            "haste.\nFuse (You may cast one or both halves of this card "
            "from your hand.)"
        ),
    }
    groups = _group_by_oracle_id(
        {"fast": real, "fast [62411ced-843e-4b63-bdf6-dafb2ac27047]": impostor}
    )
    assert [r["oracle_text"] for r in groups[legal]] == [real["oracle_text"]]
    # the same text under its OWN oracle_id is NOT an impostor — the key is
    # the (oid, text) pair, never the text alone (the playtest card carrying
    # its own text is exactly the fixed join)
    assert is_impostor_record(impostor)
    assert not is_impostor_record(real)
    assert not is_impostor_record({**impostor, "scryfall_oracle_id": playtest})
