"""Shadow ``Signal``-diff: the Layer-2 crosswalk vs the live hybrid (ADR-0035).

The Stage-2 migration gate, modeled on ``signal_diff.py::diff_corpus`` but the
seam turned the other way: instead of regex-vs-IR it diffs the **typed-substrate
crosswalk** (``crosswalk_signals.extract_crosswalk_signals`` over
``strict_load_card`` → ``build_concept_tree``) against the **live hybrid path**
(``extract_signals_hybrid``), per ``(key, scope, subject)`` over the
commander-legal corpus, restricted to the ported batch (``PORTED_KEYS``).

Gate = **adjudicated improvement**, not byte parity against the lossy old IR.
``crosswalk_only`` firings are improvement candidates (the typed read catches a
case the old projection lost); ``live_only`` firings are reproduction gaps to
adjudicate (often a kept-regex-mirror residue the structural arm does not yet
cover). The report rolls counts up per key so the reproduce ratio is legible.

Read-only / gated dev tool (joins the local phase ``card-data.json`` to the bulk
+ the old IR sidecar); never part of the live build path, never CI.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import cast

from mtg_utils._card_ir.crosswalk import build_concept_tree
from mtg_utils._card_ir.mirror import MirrorDriftError, strict_load_card
from mtg_utils._card_ir.mirror.schema import MirrorSchema
from mtg_utils._deck_forge.crosswalk_signals import (
    PORTED_KEYS,
    extract_crosswalk_signals,
)
from mtg_utils._deck_forge.signals import extract_signals_hybrid
from mtg_utils.card_ir import Card

BOTH = "both"
LIVE_ONLY = "live_only"
CROSSWALK_ONLY = "crosswalk_only"

Ident = tuple[str, str, str]  # (key, scope, subject)


def _slice(sigs: Iterable, keys: frozenset[str]) -> set[Ident]:
    return {(s.key, s.scope, s.subject) for s in sigs if s.key in keys}


def diff_corpus_crosswalk(
    phase_records: Iterable[dict],
    bulk_index: dict[str, dict],
    ir_index: dict[str, Card],
    schema: MirrorSchema,
    *,
    keys: frozenset[str] = PORTED_KEYS,
    commander_only: bool = True,
    example_cap: int = 15,
) -> dict:
    """Diff the crosswalk against the live hybrid, joined by oracle_id.

    ``phase_records`` are phase ``card-data.json`` records (the typed substrate
    source, carrying ``scryfall_oracle_id``); ``bulk_index`` maps oracle_id → the
    Scryfall bulk record (the live path's input + legality); ``ir_index`` is the
    old Card-IR sidecar. Returns a structured report: per-ident both/live_only/
    crosswalk_only with capped examples, a per-key rollup, and join/skip stats.
    """
    idents: dict[Ident, dict] = {}
    per_key: dict[str, dict] = {}
    joined = 0
    skipped = {
        "no_oracle_id": 0,
        "not_in_bulk": 0,
        "not_in_ir": 0,
        "not_commander_legal": 0,
        "same_oid_extra_faces": 0,
        "schema_drift": 0,
    }

    def tally(ident: Ident, verdict: str, name: str) -> None:
        row = idents.setdefault(
            ident, {BOTH: 0, LIVE_ONLY: 0, CROSSWALK_ONLY: 0, "examples": {}}
        )
        row[verdict] += 1
        kr = per_key.setdefault(ident[0], {BOTH: 0, LIVE_ONLY: 0, CROSSWALK_ONLY: 0})
        kr[verdict] += 1
        ex = row["examples"].setdefault(verdict, [])
        if len(ex) < example_cap and name not in ex:
            ex.append(name)

    # Group phase records by oracle_id FIRST (b10 follow-up g): a DFC carries
    # BOTH faces as separate records sharing one scryfall_oracle_id, and the
    # old first-record dedup silently dropped the second face's signals
    # (counter_control's 17 spurious diffs). The crosswalk idents are the
    # UNION across same-oid records; the live path already reads the whole
    # merged bulk record.
    grouped: dict[str, list[dict]] = {}
    for rec in phase_records:
        oid = rec.get("scryfall_oracle_id")
        if not oid:
            skipped["no_oracle_id"] += 1
            continue
        if oid in grouped:
            skipped["same_oid_extra_faces"] += 1
        grouped.setdefault(oid, []).append(rec)

    for oid, recs in grouped.items():
        bulk = bulk_index.get(oid)
        if bulk is None:
            skipped["not_in_bulk"] += 1
            continue
        ir = ir_index.get(oid)
        if ir is None:
            skipped["not_in_ir"] += 1
            continue
        if (
            commander_only
            and (bulk.get("legalities") or {}).get("commander") != "legal"
        ):
            skipped["not_commander_legal"] += 1
            continue
        name = bulk.get("name", recs[0].get("name", ""))
        # mill_makers is a Scryfall-``Mill``-keyword field-lookup (ADR-0027); the
        # keyword lives on the bulk record, not the phase substrate.
        kws = frozenset(bulk.get("keywords") or [])
        crosswalk: set[Ident] = set()
        loaded_any = False
        for rec in recs:
            try:
                root = strict_load_card(rec, schema, name=rec.get("name"))
            except MirrorDriftError:
                skipped["schema_drift"] += 1
                continue
            if root is None:  # build=True always materializes; narrow for type
                skipped["schema_drift"] += 1
                continue
            loaded_any = True
            tree = build_concept_tree(root, name=name, oracle_id=oid)
            crosswalk |= _slice(
                extract_crosswalk_signals(tree, keys=keys, keywords=kws), keys
            )
        if not loaded_any:
            continue
        joined += 1
        live = _slice(extract_signals_hybrid(bulk, ir), keys)
        for ident in crosswalk & live:
            tally(ident, BOTH, name)
        for ident in live - crosswalk:
            tally(ident, LIVE_ONLY, name)
        for ident in crosswalk - live:
            tally(ident, CROSSWALK_ONLY, name)

    return {
        "idents": idents,
        "per_key": per_key,
        "joined": joined,
        "skipped": skipped,
    }


def render_report(report: dict) -> str:
    """Markdown digest: per-key reproduce rollup, then per-ident disagreements."""
    sk = report["skipped"]
    lines = [
        "# Crosswalk ↔ live-hybrid Signal diff (ADR-0035 Stage 2)",
        "",
        f"Joined **{report['joined']}** unique commander-legal cards by oracle_id "
        f"(skipped: {sk['no_oracle_id']} no-oracle_id, {sk['not_in_bulk']} "
        f"not-in-bulk, {sk['not_in_ir']} not-in-IR, "
        f"{sk['not_commander_legal']} not-commander-legal, "
        f"{sk['same_oid_extra_faces']} same-oid faces unioned, "
        f"{sk['schema_drift']} schema-drift).",
        "",
        "## Per-key reproduce rollup",
        "",
        "| key | both | live-only | crosswalk-only | reproduce% |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key in sorted(report["per_key"]):
        r = report["per_key"][key]
        live_total = r[BOTH] + r[LIVE_ONLY]
        pct = (100.0 * r[BOTH] / live_total) if live_total else 100.0
        lines.append(
            f"| {key} | {r[BOTH]} | {r[LIVE_ONLY]} | {r[CROSSWALK_ONLY]} | {pct:.1f}% |"
        )
    lines += ["", "## Disagreement examples (the adjudication worklist)", ""]
    ordered = sorted(
        report["idents"].items(),
        key=lambda kv: (kv[1][LIVE_ONLY] + kv[1][CROSSWALK_ONLY], kv[1][BOTH]),
        reverse=True,
    )
    for (key, scope, subject), row in ordered:
        for bucket in (LIVE_ONLY, CROSSWALK_ONLY):
            names = row["examples"].get(bucket) or []
            if names:
                ident = f"{key}/{scope}" + (f"/{subject}" if subject else "")
                lines.append(f"- **{ident}** {bucket}: {', '.join(names)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m mtg_utils._deck_forge.crosswalk_diff [--all] [--json]``.

    Gated dev tool: needs the local phase ``card-data.json``, the bulk, and the
    old Card-IR sidecar. Never CI.
    """
    import argparse
    import json

    from mtg_utils import _phase
    from mtg_utils._card_ir.load import load_card_ir
    from mtg_utils._card_ir.mirror.build import load_committed_schema
    from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards

    parser = argparse.ArgumentParser(
        description="Shadow-diff the Layer-2 crosswalk against the live hybrid "
        "path over the commander-legal corpus (ADR-0035 Stage 2)."
    )
    parser.add_argument("--all", action="store_true", help="Include non-commander.")
    parser.add_argument("--json", action="store_true", help="Emit raw report JSON.")
    parser.add_argument(
        "--card-data", default=None, help="Path to phase card-data.json."
    )
    args = parser.parse_args(argv)

    bulk = default_bulk_path()
    if bulk is None:
        print("No bulk found. Run `download-mtgjson` first.")
        return 1
    try:
        ir_index = load_card_ir()
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return 1
    cdp = args.card_data or _phase.ensure_card_data()
    data = json.loads(Path(cdp).read_text())
    phase_records = cast(
        "list[dict]",
        list(data.values()) if isinstance(data, dict) else list(data),
    )

    bulk_index: dict[str, dict] = {}
    for c in load_bulk_cards(bulk):
        oid = c.get("oracle_id")
        if oid and oid not in bulk_index:
            bulk_index[oid] = c

    schema = load_committed_schema()
    report = diff_corpus_crosswalk(
        phase_records, bulk_index, ir_index, schema, commander_only=not args.all
    )
    print(json.dumps(report, indent=2) if args.json else render_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
