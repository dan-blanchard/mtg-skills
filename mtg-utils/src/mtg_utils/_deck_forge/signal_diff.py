"""Diff the IR-backed signal path against the regex path over the bulk.

The Milestone A migration is phased with old-vs-new comparison: ``extract_signals``
(regex) and ``extract_signals_ir`` (Card IR) must converge before the regex
detectors are retired (A4). This harness — the ``phase_crosscheck`` pattern turned
inward — joins the Scryfall bulk to the Card IR sidecar by ``oracle_id``, runs both
extractors restricted to ``IR_SLICE_KEYS``, and tallies per
``(key, scope, subject)`` whether the firing came from BOTH, REGEX_ONLY, or
IR_ONLY. The disagreement buckets are the adjudication worklist (resolved against
oracle text + CR via rules-lawyer).

Read-only; never part of the live build path.
"""

from __future__ import annotations

from collections.abc import Iterable

from mtg_utils._card_ir.load import load_card_ir
from mtg_utils._deck_forge.signals import (
    IR_SLICE_KEYS,
    extract_signals,
    extract_signals_ir,
)
from mtg_utils.card_ir import Card

BOTH = "both"
REGEX_ONLY = "regex_only"
IR_ONLY = "ir_only"

Ident = tuple[str, str, str]  # (key, scope, subject)


def _slice(sigs: Iterable, keys: frozenset[str]) -> set[Ident]:
    return {(s.key, s.scope, s.subject) for s in sigs if s.key in keys}


def diff_corpus(
    cards: Iterable[dict],
    ir_index: dict[str, Card],
    *,
    keys: frozenset[str] = IR_SLICE_KEYS,
    commander_only: bool = True,
    example_cap: int = 15,
) -> dict:
    """Join ``cards`` to ``ir_index`` by oracle_id; tally IR-vs-regex agreement.

    Returns a structured report: per-``(key, scope, subject)`` both/regex_only/
    ir_only counts with capped example card names, plus join/skip stats.
    """
    idents: dict[Ident, dict] = {}
    joined = 0
    seen_oids: set[str] = set()  # the bulk has many printings; compare each card once
    skipped = {
        "no_oracle_id": 0,
        "not_in_ir": 0,
        "not_commander_legal": 0,
        "duplicate_printing": 0,
    }

    def tally(ident: Ident, verdict: str, name: str) -> None:
        row = idents.setdefault(
            ident, {BOTH: 0, REGEX_ONLY: 0, IR_ONLY: 0, "examples": {}}
        )
        row[verdict] += 1
        ex = row["examples"].setdefault(verdict, [])
        if len(ex) < example_cap and name not in ex:
            ex.append(name)

    for card in cards:
        oid = card.get("oracle_id")
        if not oid:
            skipped["no_oracle_id"] += 1
            continue
        ir = ir_index.get(oid)
        if ir is None:
            skipped["not_in_ir"] += 1
            continue
        if (
            commander_only
            and (card.get("legalities") or {}).get("commander") != "legal"
        ):
            skipped["not_commander_legal"] += 1
            continue
        if oid in seen_oids:
            skipped["duplicate_printing"] += 1
            continue
        seen_oids.add(oid)

        joined += 1
        name = card.get("name", "")
        regex = _slice(extract_signals(card), keys)
        ir_sig = _slice(extract_signals_ir(card, ir), keys)
        for ident in regex & ir_sig:
            tally(ident, BOTH, name)
        for ident in regex - ir_sig:
            tally(ident, REGEX_ONLY, name)
        for ident in ir_sig - regex:
            tally(ident, IR_ONLY, name)

    return {"idents": idents, "joined": joined, "skipped": skipped}


def render_report(report: dict) -> str:
    """Markdown digest, idents ordered by disagreement (most actionable first)."""
    sk = report["skipped"]
    lines = [
        "# IR ↔ regex signal diff (vertical slice)",
        "",
        f"Joined **{report['joined']}** unique cards by oracle_id "
        f"(skipped: {sk['no_oracle_id']} no-oracle_id, {sk['not_in_ir']} not-in-IR, "
        f"{sk['not_commander_legal']} not-commander-legal, "
        f"{sk['duplicate_printing']} duplicate-printings).",
        "",
        "| key | scope | subject | both | regex-only | ir-only |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    ordered = sorted(
        report["idents"].items(),
        key=lambda kv: (kv[1][REGEX_ONLY] + kv[1][IR_ONLY], kv[1][BOTH]),
        reverse=True,
    )
    for (key, scope, subject), row in ordered:
        lines.append(
            f"| {key} | {scope} | {subject or '—'} | "
            f"{row[BOTH]} | {row[REGEX_ONLY]} | {row[IR_ONLY]} |"
        )
    lines.append("")
    lines.append("## Disagreement examples (the adjudication worklist)")
    lines.append("")
    for (key, scope, subject), row in ordered:
        for bucket in (REGEX_ONLY, IR_ONLY):
            names = row["examples"].get(bucket) or []
            if names:
                ident = f"{key}/{scope}" + (f"/{subject}" if subject else "")
                lines.append(f"- **{ident}** {bucket}: {', '.join(names)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m mtg_utils._deck_forge.signal_diff [--all] [--json]``."""
    import argparse
    import json

    from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards

    parser = argparse.ArgumentParser(
        description="Diff IR-backed signals against the regex path over the bulk."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include non-commander-legal cards (default: commander-legal only).",
    )
    parser.add_argument("--json", action="store_true", help="Emit the raw report JSON.")
    args = parser.parse_args(argv)

    bulk = default_bulk_path()
    if bulk is None:
        print("No Scryfall bulk found. Run `download-bulk` first.")
        return 1
    try:
        ir_index = load_card_ir()
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return 1

    report = diff_corpus(load_bulk_cards(bulk), ir_index, commander_only=not args.all)
    print(json.dumps(report, indent=2) if args.json else render_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
