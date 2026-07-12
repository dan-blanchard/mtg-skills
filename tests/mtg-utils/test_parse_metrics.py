"""CI tripwire for the ADR-0032 parse-completeness metric.

``parse_metrics.json`` (committed, regenerated in the gated ``build-card-snapshot``
step) holds two cuts, BOTH still LEGACY (``project_card``) — ADR-0032's bucket-A/
bucket-B masking-recovery classification is intrinsic to the ``project.py`` /
``supplement.py`` recovery bookkeeping, so this stays the flag-OFF revert path's own
drift-watch (ADR-0039 step 5 repoints the *snapshot's storage shape*, not this
metric's subject): a ``full_corpus`` block (the review-time drift-watch — a human
notices a diff) and a ``snapshot`` block this test RECOMPUTES offline as
``project_card`` over each snapshotted card's OWN stored ``phase_records`` (a pure
function — no sidecar / bulk / network) and asserts byte-equal to the committed cut.
So a change to a snapshotted card's stored records (or to the metric) that isn't
reflected in ``parse_metrics.json`` trips here — the same offline contract as
``test_migrated_keys``.
"""

from __future__ import annotations

import json
from pathlib import Path

from mtg_utils._card_ir.load import SIDECAR_VERSION
from mtg_utils._card_ir.metrics import compute_parse_metrics
from mtg_utils._card_ir.project import project_card
from mtg_utils.card_ir import Card
from mtg_utils.testkit import _snapshot, snapshot_path


def _parse_metrics() -> dict:
    path = snapshot_path().parent / "parse_metrics.json"
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _snapshot_cards() -> dict[str, Card]:
    # Rebuild every snapshotted card's LEGACY IR the same pure way
    # `build-card-snapshot` computed the committed "snapshot" cut — project_card
    # over the card's OWN stored raw phase face records, offline.
    return {
        name: project_card(entry["phase_records"])
        for name, entry in _snapshot()["cards"].items()
    }


def test_snapshot_field_coverage_matches_committed():
    recomputed = compute_parse_metrics(_snapshot_cards())
    committed = _parse_metrics()["snapshot"]
    assert recomputed == committed, (
        "parse_metrics.json snapshot block is stale — regenerate with "
        "`build-card-snapshot` after any snapshot/projection change."
    )


def test_parse_metrics_pins_versions():
    # The metric is phase-tag-bound, exactly like the snapshot itself, plus its
    # OWN legacy SIDECAR_VERSION pin (the full_corpus cut's projection version —
    # unaffected by the snapshot's crosswalk_sidecar_version storage-shape guard).
    pm = _parse_metrics()
    assert pm["phase_tag"] == _snapshot()["phase_tag"]
    assert pm["sidecar_version"] == SIDECAR_VERSION


def test_no_bucket_a_masking_recoveries():
    # Direction guard (ADR-0032): every surviving raw-regex recovery must be a curated
    # bucket-B genuine phase gap. A bucket-A count > 0 means a recovery landed in an
    # UNRECOGNIZED category — i.e. someone masked a node phase actually has instead of
    # reading it natively. Promote it (with justification) into _BUCKET_B_CATEGORIES or
    # convert it to a native read.
    snap = _parse_metrics()["snapshot"]["feed_phase_readiness"]
    assert snap["bucket_a_masking"] == 0, snap["recovered_by_category"]
