"""Convergence hook for the ledgered bridges (ADR-0039).

A ledgered bridge is a gap-gated, corpus-bounded, self-retiring text read
(``mtg_utils._deck_forge.bridge_ledger``). This suite is the mechanism that
keeps every bridge visible until it retires:

* ``gap`` goes False on a pinned card → the typed substrate now carries the
  structure → the test fails RETIRE-READY: delete the ledger row + its lane
  call, rewrite the mechanism pin structural, keep the membership pin (the
  graduation rule).
* ``match`` goes False while ``gap`` still holds → the diagnostic/text shape
  changed under the pattern (pattern rot) → fix the read, don't widen it.

Runs CI-safe off the committed ``crosswalk_fixture_cards.json`` slice, like
``test_crosswalk.py``. A pin whose face has no phase record at all (a
``missing_face`` bridge) lives in the fixture's ``text_only_faces`` section
instead of ``cards`` (ADR-0039 W7) — see :func:`_tree`.
"""

import json
from functools import lru_cache
from pathlib import Path

import pytest

from mtg_utils._card_ir.crosswalk import ConceptTree, build_concept_tree
from mtg_utils._card_ir.mirror import strict_load_card
from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema
from mtg_utils._deck_forge.bridge_ledger import BRIDGE_KINDS, BRIDGES

FIXTURE = "crosswalk_fixture_cards.json"


@lru_cache(maxsize=1)
def _fixture() -> dict:
    path = fixtures_dir() / FIXTURE
    if not path.exists():
        pytest.skip(f"{FIXTURE} not present")
    return json.loads(Path(path).read_text())


@lru_cache(maxsize=1)
def _schema():
    return load_committed_schema()


def _tree(name: str) -> ConceptTree:
    # ADR-0039 W7: a bridge pin whose face has NO phase record at all (the
    # missing_face kind — Insult // Injury's Aftermath back half) lives in
    # the fixture's separate ``text_only_faces`` section instead of
    # ``cards`` (a real ``strict_load_card``-able record would misrepresent
    # the shape — there is nothing for phase to have emitted). Build it via
    # the SAME W2c text-only path production uses.
    text_only_faces = _fixture().get("text_only_faces", {})
    if name in text_only_faces:
        from mtg_utils._deck_forge._ir_lookup import _text_only_tree

        entry = text_only_faces[name]
        tree = _text_only_tree(
            entry["_text_only_face"], {}, oracle_id=entry["_oracle_id"]
        )
        assert tree is not None
        return tree
    rec = _fixture()["cards"][name]
    root = strict_load_card(rec, _schema(), name=name)
    return build_concept_tree(root, name=name)


_PIN_CASES = [(b, pin) for b in BRIDGES.values() for pin in b.pins]


@pytest.mark.parametrize(
    ("bridge", "pin"), _PIN_CASES, ids=[f"{b.bridge_id}:{p}" for b, p in _PIN_CASES]
)
def test_bridge_still_needed_and_serving(bridge, pin):
    tree = _tree(pin)
    assert bridge.gap(tree), (
        f"{bridge.bridge_id}: RETIRE-READY — the typed substrate now carries "
        f"the structure for {pin!r}. Delete the ledger row and its lane call, "
        f"rewrite the mechanism pin structural, keep the membership pin (the "
        f"graduation rule). Retirement path was: {bridge.todo}"
    )
    assert bridge.match(tree), (
        f"{bridge.bridge_id}: pattern rot — the gap still holds for {pin!r} "
        f"but the bounded read no longer matches; fix the read (do not widen "
        f"it past its census: {bridge.census})"
    )
    assert bridge.fires(tree)


def test_ledger_hygiene():
    """Every row is complete: a named retirement path, an authored census,
    at least one fixture-resident pin, a known kind, and an id key that
    matches the row."""
    cards = _fixture()["cards"]
    text_only_faces = _fixture().get("text_only_faces", {})
    for bridge_id, b in BRIDGES.items():
        assert bridge_id == b.bridge_id
        assert b.kind in BRIDGE_KINDS, f"{bridge_id}: unknown kind {b.kind!r}"
        assert b.todo.strip(), f"{bridge_id}: empty retirement TODO"
        assert b.census.strip(), f"{bridge_id}: empty census"
        assert b.pins, f"{bridge_id}: no convergence pins"
        for pin in b.pins:
            assert pin in cards or pin in text_only_faces, (
                f"{bridge_id}: pin {pin!r} not in fixture"
            )
