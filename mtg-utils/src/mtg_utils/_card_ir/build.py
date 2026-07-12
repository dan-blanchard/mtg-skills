"""Build the crosswalk Card IR cache sidecar from phase-rs's ``card-data.json``.

Cache-only distribution (the grilled decision): each user's launch builds the
sidecar once from phase's parse, keyed by ``oracle_id``, and the runtime then
does field lookups (no Rust/mypyc at runtime). The sidecar carries the phase tag
so a phase upgrade invalidates it.

phase keys ``card-data.json`` by lowercased face name (each face a separate
entry); DFC faces share a ``scryfall_oracle_id``, so we group all records by it
and build each group into one multi-face :class:`~mtg_utils.card_ir.Card`.

ADR-0039 step 7: the legacy builder arm (``build_sidecar`` calling the deleted
``project.py``'s ``project_card``, plus its ``build-card-ir`` CLI) is gone; the
crosswalk twin (``build_crosswalk_sidecar`` / ``build-card-ir-crosswalk``) is
the only sidecar build. ``_group_by_oracle_id`` stays — it is the one grouping
seam every consumer shares (the sidecar build, ``build-card-snapshot``, and the
production ``_ir_lookup._phase_record_index``).
"""

from __future__ import annotations

import json
from pathlib import Path

from mtg_utils import _phase
from mtg_utils._card_ir.load import (
    CROSSWALK_SIDECAR_VERSION,
    crosswalk_sidecar_path,
)
from mtg_utils._sidecar import atomic_write_json


def _group_by_oracle_id(data: object) -> dict[str, list[dict]]:
    """Group phase face-records by ``scryfall_oracle_id`` (insertion order kept,
    so a DFC's front face precedes its back face as listed in card-data.json).

    Known-bad records upstream stamps with the WRONG card's oracle_id are
    dropped here (``_phase.is_impostor_record``, task #78) — this is the one
    grouping seam every consumer shares (the sidecar builder, the snapshot
    builder, and the production ``_ir_lookup._phase_record_index``), so the
    impostor's parse can never ride an oracle_id join onto the real card."""
    if isinstance(data, dict):
        records: list = list(data.values())
    elif isinstance(data, list):
        records = data
    else:
        return {}
    groups: dict[str, list[dict]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        oid = rec.get("scryfall_oracle_id")
        if isinstance(oid, str) and oid and not _phase.is_impostor_record(rec):
            groups.setdefault(oid, []).append(rec)
    return groups


def build_crosswalk_sidecar(
    card_data_path: str | Path | None = None,
    out_path: str | Path | None = None,
) -> tuple[Path, dict]:
    """Build the crosswalk-backed sidecar (ADR-0035 Stage-3a); return (path, stats).

    Historically the Stage-1 twin of the legacy ``build_sidecar`` (deleted in
    ADR-0039 step 7 with ``project_card``): it builds
    ``compat_card(build_concept_tree(strict_load_card(rec, schema)))`` per face,
    so the on-disk ``Card`` shape matches what the legacy sidecar carried but
    its fields come from the typed phase-mirror substrate + Layer-2 concept
    overlay. Writes to :func:`crosswalk_sidecar_path` with
    :data:`CROSSWALK_SIDECAR_VERSION` (the distinct path/version kept from the
    cutover era).

    ONE Card per oracle_id, but every face record contributes its own compat
    ``Face`` (ADR-0035/0038 task #74) — the emitted ``faces`` tuple concatenates
    the per-face compat faces in ``records`` order, mirroring the legacy
    multi-face ``Card`` shape ``project_card(records)`` used to build. A face
    that drifts from the committed schema is skipped and tallied
    (``MirrorDriftError``) rather than aborting the whole build; an oracle_id
    where EVERY face drifts is dropped entirely (also tallied).
    """
    from mtg_utils._card_ir.compat import CompatCoverage, compat_card_from_records
    from mtg_utils._card_ir.mirror.build import load_committed_schema

    if card_data_path:
        cdp = Path(card_data_path)
        if not cdp.exists():
            raise FileNotFoundError(f"phase card-data.json not found at {cdp}.")
    else:
        cdp = _phase.ensure_card_data()
    data = json.loads(cdp.read_text())
    groups = _group_by_oracle_id(data)
    schema = load_committed_schema()

    cov = CompatCoverage()
    cards: dict[str, dict] = {}
    drift = 0
    for oid, records in groups.items():
        card, drifted = compat_card_from_records(oid, records, schema, cov)
        drift += drifted
        if card is None:
            continue
        cards[oid] = card.to_dict()

    out = Path(out_path) if out_path else crosswalk_sidecar_path()
    atomic_write_json(
        out,
        {
            "version": CROSSWALK_SIDECAR_VERSION,
            "phase_tag": _phase.PHASE_TAG,
            "cards": cards,
        },
    )
    stats = {
        "cards": len(cards),
        "phase_tag": _phase.PHASE_TAG,
        "drift_skipped": drift,
        "coverage": cov.coverage_rows(),
    }
    return out, stats


def main_crosswalk(argv: list[str] | None = None) -> int:
    """CLI: ``build-card-ir-crosswalk [--card-data PATH] [--out PATH]`` (ADR-0035)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build the crosswalk-backed Card IR sidecar (ADR-0035 "
        "Stage-3a) — the backend ir_for reads; gated dev step, never CI."
    )
    parser.add_argument(
        "--card-data",
        default=None,
        help="Path to phase card-data.json (default: download+cache the "
        "release tarball's copy for the pinned PHASE_TAG).",
    )
    parser.add_argument(
        "--out", default=None, help="Sidecar output path (default: the cache dir)."
    )
    args = parser.parse_args(argv)

    try:
        out, stats = build_crosswalk_sidecar(args.card_data, args.out)
    except (FileNotFoundError, RuntimeError) as exc:
        print(str(exc))
        return 1

    print(
        f"Wrote {stats['cards']} cards to {out} (phase {stats['phase_tag']}); "
        f"{stats['drift_skipped']} drift-skipped."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_crosswalk())
