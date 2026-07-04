"""ADR-0035 Stage-3b (c) — the INPUT-SIDE convergence check for dropped clauses.

The ADR's named deliverable: a standing mechanism that tells a FUTURE phase-pin
bump which bucket-(c) dropped-clause arms have CONVERGED — i.e. phase now parses
the clause the arm synthesizes, so the synthesis would duplicate a real node and
the arm is retire-ready.

**Grounded on the strict mirror, not a regex.** For each applied arm the check
asks: does the arm still FIRE (change the compat Card) on any corpus card? An arm
fires only when its structural idempotence guard — a read of the compat Card built
from the strict phase mirror — finds the structure ABSENT. When a pin bump teaches
phase to parse the clause, that structure appears in the mirror-built card, the
guard trips, and the arm stops firing everywhere: firings drop to 0 = CONVERGED.
So the firing count over the mirror-built corpus IS the input-side convergence
signal (the same detector the Stage-3b measure phase used), read off the strict
mirror rather than a fresh regex.

This module ships two forms (per the ADR):

* a **report harness** — :func:`scan_arm_firings` + the ``card-ir-convergence``
  CLI — a gated dev tool (needs the local phase ``card-data.json`` + the bulk)
  that prints a per-arm ``{arm, firings, verdict}`` table over the corpus.
* a **committed pytest** (``tests/mtg-utils/test_dropped_clauses.py``): a CI-safe
  mechanism test (an arm fires on a synthetic gap card, no-ops when the structure
  is already present = convergence) plus a gated corpus test asserting every
  currently-applied arm is still LIVE (finds a gap) and NAMING any that converged.

**Retirement scope at v0.15.0 (why ``retired=[]`` is CORRECT, not unfinished).**
The Stage-3b Measure phase proved all 49 BUILT supplement ``_recover_*`` arms are
still LIVE at phase v0.15.0 — ``obsolete_count == 0`` among the built arms — so
NOTHING is deleted from ``supplement.py``: an empty retired set is the RIGHT answer
at this pin, not a TODO. Convergence is the STANDING mechanism for FUTURE pin bumps
— when a later phase parses a clause, its arm drops to 0 firings and this check
NAMES it retire-ready. Only three QUEUED (never-built) supplement items were fixed
upstream and are queue cleanup, not supplement deletions: [P24] Hama Pashar typed
room-static, [P46] playtest self-removed, [P52] Aminatou Miracle variant. Two
QUEUED items remain REAL gaps and are kept: [P51] Tromokratis, [P43] Agency
Coroner. The per-card convergence GATES (:func:`dropped_clauses.convergence_gated_arms`)
are a DIFFERENT axis — a compat-seam SUPERSET guard for still-LIVE arms — not
retirement; a gated arm stays LIVE (fires on non-converged cards).

Read-only / never part of the live build path, never CI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtg_utils._card_ir.compat import compat_card_base
from mtg_utils._card_ir.crosswalk import build_concept_tree
from mtg_utils._card_ir.dropped_clauses import (
    ARM_NAMES,
    convergence_gated_arms,
    synthesize_with_trace,
)
from mtg_utils._card_ir.mirror import MirrorDriftError, strict_load_card

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mtg_utils._card_ir.mirror.schema import MirrorSchema

LIVE = "LIVE"
CONVERGED = "CONVERGED"


def scan_arm_firings(
    phase_records: Iterable[dict],
    bulk_index: dict[str, dict],
    schema: MirrorSchema,
    *,
    commander_only: bool = True,
) -> tuple[dict[str, int], int]:
    """``(firings, scanned)``: firing count per applied (c) arm + cards scanned.

    Joins each phase record to the bulk by ``oracle_id`` (legality + name),
    strict-loads it, builds the compat base Card (pre-synthesis), and tallies
    which arms fire (:func:`synthesize_with_trace`). Every applied arm starts at 0
    so a fully-converged arm is reported explicitly.
    """
    firings: dict[str, int] = dict.fromkeys(ARM_NAMES, 0)
    seen: set[str] = set()
    for rec in phase_records:
        oid = rec.get("scryfall_oracle_id")
        if not oid or oid in seen:
            continue
        bulk = bulk_index.get(oid)
        if bulk is None:
            continue
        if (
            commander_only
            and (bulk.get("legalities") or {}).get("commander") != "legal"
        ):
            continue
        try:
            root = strict_load_card(rec, schema, name=rec.get("name"))
        except MirrorDriftError:
            continue
        if root is None:
            continue
        seen.add(oid)
        tree = build_concept_tree(
            root, name=bulk.get("name", rec.get("name", "")), oracle_id=oid
        )
        base = compat_card_base(tree)
        skip = convergence_gated_arms(tree, base)
        _card, fired = synthesize_with_trace(base, tree.oracle, skip=skip)
        for arm in fired:
            firings[arm] = firings.get(arm, 0) + 1
    return firings, len(seen)


def convergence_verdicts(firings: dict[str, int]) -> dict[str, str]:
    """``{arm: LIVE|CONVERGED}`` — CONVERGED when the arm fires on 0 corpus cards."""
    return {arm: (CONVERGED if firings.get(arm, 0) == 0 else LIVE) for arm in ARM_NAMES}


def render_report(firings: dict[str, int], scanned: int) -> str:
    """Markdown digest: per-arm firing count + convergence verdict."""
    verdicts = convergence_verdicts(firings)
    converged = [a for a in ARM_NAMES if verdicts[a] == CONVERGED]
    lines = [
        "# Dropped-clause convergence check (ADR-0035 Stage-3b c)",
        "",
        f"Scanned **{scanned}** unique mirror-built cards. "
        f"Applied arms: {len(ARM_NAMES)}; converged (retire-ready): "
        f"{len(converged)}.",
        "",
        "| arm | firings | verdict |",
        "| --- | ---: | --- |",
    ]
    for arm in sorted(ARM_NAMES, key=lambda a: firings.get(a, 0), reverse=True):
        lines.append(f"| {arm} | {firings.get(arm, 0)} | {verdicts[arm]} |")
    if converged:
        lines += [
            "",
            "## CONVERGED — retire-ready at this pin",
            "",
            "These arms fire on NO corpus card: phase now parses the clause "
            "(the mirror-built card already carries the structure), so the "
            "synthesis is dead. Retire them from `dropped_clauses.SYNTHESIS_ARMS`.",
            "",
        ]
        lines += [f"- {a}" for a in converged]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m mtg_utils._card_ir.card_ir_convergence``.

    Gated dev tool: needs the local phase ``card-data.json`` + the bulk. Never CI.
    """
    import argparse
    import json
    from pathlib import Path
    from typing import cast

    from mtg_utils import _phase
    from mtg_utils._card_ir.mirror.build import load_committed_schema
    from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards

    parser = argparse.ArgumentParser(
        description="Input-side convergence check for the Stage-3b (c) "
        "dropped-clause arms (ADR-0035): per-arm firing over the mirror-built "
        "corpus; an arm firing on 0 cards has CONVERGED (retire-ready)."
    )
    parser.add_argument("--all", action="store_true", help="Include non-commander.")
    parser.add_argument("--json", action="store_true", help="Emit raw firings JSON.")
    parser.add_argument(
        "--card-data", default=None, help="Path to phase card-data.json."
    )
    args = parser.parse_args(argv)

    bulk = default_bulk_path()
    if bulk is None:
        print("No bulk found. Run `download-mtgjson` first.")
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
    firings, scanned = scan_arm_firings(
        phase_records, bulk_index, schema, commander_only=not args.all
    )
    if args.json:
        print(
            json.dumps(
                {
                    "scanned": scanned,
                    "firings": firings,
                    "verdicts": convergence_verdicts(firings),
                },
                indent=2,
            )
        )
    else:
        print(render_report(firings, scanned=scanned))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
