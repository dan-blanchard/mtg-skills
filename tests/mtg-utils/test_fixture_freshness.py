"""task #93 item 4 — the missing tag gate (the #84 postmortem prescribed it).

The committed card snapshot (``tests/fixtures/card_snapshot.json``, the
ADR-0027/#25/#39 real-card fixtures served by ``mtg_utils.testkit``) freezes
phase's OWN parse at a specific ``_phase.PHASE_TAG`` pin. A phase bump silently
drifting stored records out from under the pin is exactly the hole that let
``creature_recursion`` die unnoticed at v0.20 (the #84 postmortem): the records
kept parsing without error, just against a STALE phase grammar, so no test
failed. (The crosswalk suites' own ``crosswalk_fixture_cards.json`` had its own
tag gate here; ADR-0056 merged it into the snapshot.)

``testkit._snapshot()`` already self-gates on load (it raises ``ValueError`` on a
``crosswalk_sidecar_version``/``phase_tag`` mismatch), but that load is lazy and
``lru_cache``d: the assert only fires when some test in the selected run actually
calls a testkit helper (true for the whole suite today, but NOT guaranteed for an
arbitrary ``-k``/subset run). This module is a small, ALWAYS-collected,
dependency-free gate so the snapshot can't drift silently, regardless of what
else a given test invocation happens to select.
"""

from __future__ import annotations

from mtg_utils import testkit
from mtg_utils._phase import PHASE_TAG


def test_card_snapshot_version_pins_match_live():
    """``card_snapshot.json``'s ``crosswalk_sidecar_version``/``phase_tag``
    must match the live pins. ``testkit._snapshot()`` already raises loud
    on a mismatch (and ``lru_cache`` never memoizes a raised exception, so
    any call — cached or not — is a real check, not a rubber stamp), but
    the check is LAZY: it only ever runs when something calls a testkit
    helper or ``_snapshot`` directly. True for the whole suite today, but
    not guaranteed for an arbitrary ``-k``/subset run — this dedicated,
    always-collected test makes the gate unconditional."""
    payload = testkit._snapshot()  # raises ValueError on any pin mismatch
    assert payload.get("phase_tag") == PHASE_TAG
    assert payload.get("crosswalk_sidecar_version") == testkit.CROSSWALK_SIDECAR_VERSION
