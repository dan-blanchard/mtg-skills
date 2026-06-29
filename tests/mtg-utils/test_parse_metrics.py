"""CI tripwire for the ADR-0032 parse-completeness metric.

``parse_metrics.json`` (committed, regenerated in the gated ``build-card-snapshot``
step) holds two cuts: a ``full_corpus`` block (the review-time drift-watch — a human
notices a diff) and a ``snapshot`` block this test RECOMPUTES offline from the committed
``card_snapshot.json`` and asserts byte-equal. So a change to the snapshot's real IR (or
to the metric) that isn't reflected in ``parse_metrics.json`` trips here, with no
sidecar / bulk / network — the same offline contract as ``test_migrated_keys``.
"""

from __future__ import annotations

import json
from pathlib import Path

from mtg_utils._card_ir.metrics import compute_parse_metrics
from mtg_utils.card_ir import Card
from mtg_utils.testkit import _snapshot, snapshot_path


def _parse_metrics() -> dict:
    path = snapshot_path().parent / "parse_metrics.json"
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _snapshot_cards() -> dict[str, Card]:
    # Rebuild every snapshot card's real IR (the verbatim sidecar slice) the same way
    # production deserializes it — Card.from_dict over the committed snapshot.
    return {
        name: Card.from_dict(entry["ir"])
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
    # The metric is projection-version-bound, exactly like the snapshot itself.
    pm = _parse_metrics()
    assert pm["sidecar_version"] == _snapshot()["sidecar_version"]
    assert pm["phase_tag"] == _snapshot()["phase_tag"]


def test_no_bucket_a_masking_recoveries():
    # Direction guard (ADR-0032): every surviving raw-regex recovery must be a curated
    # bucket-B genuine phase gap. A bucket-A count > 0 means a recovery landed in an
    # UNRECOGNIZED category — i.e. someone masked a node phase actually has instead of
    # reading it natively. Promote it (with justification) into _BUCKET_B_CATEGORIES or
    # convert it to a native read.
    snap = _parse_metrics()["snapshot"]["feed_phase_readiness"]
    assert snap["bucket_a_masking"] == 0, snap["recovered_by_category"]
