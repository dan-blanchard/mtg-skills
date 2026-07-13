"""task #93 item 4 — the missing tag gate (the #84 postmortem prescribed it).

Two committed test fixtures freeze phase's OWN parse at a specific
``_phase.PHASE_TAG`` pin:

  * ``tests/fixtures/crosswalk_fixture_cards.json`` (the Stage-2 crosswalk
    gate's raw phase records, ``test_crosswalk.py``) — carries its own
    ``phase_tag`` field, but NOTHING asserted it matched the live pin until
    this file. A phase bump silently drifting the fixture out from under
    the pin is exactly the hole that let ``creature_recursion`` die
    unnoticed at v0.20 (the #84 postmortem): the fixture kept parsing
    without error, just against a STALE phase grammar, so no test failed.
  * ``tests/fixtures/card_snapshot.json`` (the ADR-0027/#25/#39 real-card
    fixtures, ``mtg_utils.testkit``) — already self-gates on load
    (``testkit._snapshot()`` raises ``ValueError`` on a
    ``crosswalk_sidecar_version``/``phase_tag`` mismatch), but that load is
    lazy and ``lru_cache``d: the assert only fires when some test in the
    selected run actually calls ``test_card``/``test_card_ir``/
    ``test_signals`` (true for the whole suite today — 29 files use
    testkit — but NOT guaranteed for an arbitrary ``-k``/subset run). This
    module is a small, ALWAYS-collected, dependency-free gate for both
    fixtures so neither can drift silently again, regardless of what else
    a given test invocation happens to select.
"""

from __future__ import annotations

import json

from mtg_utils import testkit
from mtg_utils._card_ir.mirror.build import fixtures_dir
from mtg_utils._phase import PHASE_TAG


def test_crosswalk_fixture_cards_phase_tag_matches_pin():
    """``crosswalk_fixture_cards.json``'s ``phase_tag`` must match the live
    ``_phase.PHASE_TAG`` pin. A mismatch means the fixture's raw phase
    records were captured against a DIFFERENT phase grammar than the one
    ``_card_ir``/``_deck_forge`` code now assumes — regenerate the fixture
    (the same ``add_*_fixtures.py``-style script pattern used to grow it)
    before trusting ``test_crosswalk.py``'s pass/fail against it."""
    path = fixtures_dir() / "crosswalk_fixture_cards.json"
    fixture = json.loads(path.read_text())
    got_tag = fixture.get("phase_tag")
    assert got_tag == PHASE_TAG, (
        f"crosswalk_fixture_cards.json was captured at phase {got_tag!r}, "
        f"but the live pin is {PHASE_TAG!r} — regenerate the fixture's raw "
        "phase records against the new phase tag before trusting "
        "test_crosswalk.py's results."
    )


def test_card_snapshot_version_pins_match_live():
    """``card_snapshot.json``'s ``crosswalk_sidecar_version``/``phase_tag``
    must match the live pins. ``testkit._snapshot()`` already raises loud
    on a mismatch (and ``lru_cache`` never memoizes a raised exception, so
    any call — cached or not — is a real check, not a rubber stamp), but
    the check is LAZY: it only ever runs when something calls
    ``test_card``/``test_card_ir``/``test_signals``/``_snapshot`` directly.
    True for the whole suite today (29 files use ``testkit``), but not
    guaranteed for an arbitrary ``-k``/subset run — this dedicated,
    always-collected test makes the gate unconditional."""
    payload = testkit._snapshot()  # raises ValueError on any pin mismatch
    assert payload.get("phase_tag") == PHASE_TAG
    assert payload.get("crosswalk_sidecar_version") == testkit.CROSSWALK_SIDECAR_VERSION
