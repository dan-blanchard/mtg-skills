"""Shadow output-diff for the FOUR non-Signal IR consumers (ADR-0035 Stage 2).

The migration plan names two consumer seams over the Card IR: the ``Signal``
lanes (shadow-diffed by ``crosswalk_diff``) and the Effect/Ability/Card
dataclass API read directly by ``ranking`` / ``budgets`` / ``cut_check`` and
the tuner (``_tuner.metrics`` + ``_tuner.bracket``). This harness covers the
second seam: it joins the phase typed substrate to the bulk + the old Card-IR
sidecar by ``oracle_id`` (the ``crosswalk_diff.diff_corpus_crosswalk`` join
pattern), builds the MINIMAL compat card (``_card_ir.compat``) from the
concept overlay, and runs each consumer's IR read TWICE — old IR vs compat —
recording per-consumer agreement plus per-category coverage.

The consumer views are the production functions, called unchanged:

* ``budgets``   — ``_ir_draws`` / ``_ir_board_wipe`` / ``_ir_recursion_only``
  / ``_ir_redirect`` (the IR-driven arm of ``role_of`` / ``protects``).
* ``cut_check`` — ``detect_triggers(..., ir=...)`` rows, normalized to the
  consumer-visible decision tuple (matched_type / matches / parseable /
  fixed base_value).
* ``ranking``   — the IR-driven arm of ``score_candidate``: the per-oracle-
  clause role (``_clause_role`` over ``_ir_payoff_raws``) plus the tribal
  gate subtypes (``_ir_gate_subtypes``).
* ``metrics``   — ``_ir_wincon`` (the Tier-2 wincon flag).
* ``bracket``   — ``_ir_has_extra_turn`` (the bracket extra-turn axis).

Gate = **adjudicated improvement**, not byte parity: today's expected result
is faithful agreement on the ported categories and large, explicitly-tallied
divergence on the unported tail (the ``CompatCoverage`` buckets — the
porting worklist). Disagreements are attributed to the effect categories the
two sides do NOT share, so the per-category rollup is the Stage-3 gate as
porting proceeds.

Read-only / gated dev tool (local phase ``card-data.json`` + bulk + old IR
sidecar); never part of the live build path, never CI. The committed tests
run the same functions fixture-driven.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from mtg_utils._card_ir.compat import CompatCoverage, compat_card
from mtg_utils._card_ir.crosswalk import build_concept_tree
from mtg_utils._card_ir.mirror import MirrorDriftError, strict_load_card
from mtg_utils._deck_forge.budgets import (
    _ir_board_wipe,
    _ir_draws,
    _ir_recursion_only,
    _ir_redirect,
)
from mtg_utils._deck_forge.ranking import (
    _clause_role,
    _ir_gate_subtypes,
    _ir_payoff_raws,
)
from mtg_utils._deck_forge.signals import clauses
from mtg_utils._tuner.bracket import _ir_has_extra_turn
from mtg_utils._tuner.metrics import _ir_wincon
from mtg_utils.card_classify import get_oracle_text
from mtg_utils.cut_check import _IR_EVENT_TO_TYPE, detect_triggers

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mtg_utils._card_ir.mirror.schema import MirrorSchema
    from mtg_utils.card_ir import Card

CONSUMERS = ("ranking", "budgets", "cut_check", "metrics", "bracket")

# Every cut-check trigger type, so the diff exercises the full matched_type map.
_ALL_TRIGGER_TYPES = sorted(set(_IR_EVENT_TO_TYPE.values()))
_OPPONENTS = 3


# ── per-consumer views (the consumer-visible decision, made comparable) ───────


def budgets_view(ir: Card) -> tuple:
    """The four IR-driven budget reads of ``role_of`` / ``protects``."""
    return (
        _ir_draws(ir),
        _ir_board_wipe(ir),
        _ir_recursion_only(ir),
        _ir_redirect(ir),
    )


def cut_check_view(bulk: dict, ir: Card) -> tuple:
    """``detect_triggers`` rows as a sorted multiset of decision tuples.

    Normalized to what downstream consumes: the matched trigger type, whether
    it matched, and the parsed fixed value. The free-text ``text`` /
    unparseable ``base_value`` echo the event NAME, which differs across
    vocabularies without changing any decision — excluded so the diff stays
    on consumer-visible behavior.
    """
    rows = detect_triggers(
        bulk, trigger_types=_ALL_TRIGGER_TYPES, opponents=_OPPONENTS, ir=ir
    )
    return tuple(
        sorted(
            (
                r.get("matched_type") or "",
                bool(r.get("matches_trigger_type")),
                bool(r.get("parseable")),
                r.get("base_value") if r.get("parseable") else "",
            )
            for r in rows
        )
    )


def ranking_view(bulk: dict, ir: Card) -> tuple:
    """The IR-driven arm of ``score_candidate``: clause roles + gate tribes."""
    payoff_raws = _ir_payoff_raws(ir)
    clause_list = clauses(get_oracle_text(bulk) or "")
    roles = tuple(_clause_role(cl, ir, payoff_raws) for cl in clause_list)
    tribes: set[str] = set()
    for _, gate in _ir_gate_subtypes(ir):
        tribes |= gate
    return (roles, tuple(sorted(tribes)))


def metrics_view(ir: Card) -> bool:
    """The tuner's structural alt-win read."""
    return _ir_wincon(ir)


def bracket_view(ir: Card) -> bool:
    """The bracket's structural extra-turn read."""
    return _ir_has_extra_turn(ir)


def _effect_categories(ir: Card) -> set[str]:
    """The distinct effect categories a card's IR carries (for attribution)."""
    return {e.category for ab in ir.all_abilities() for e in ab.effects}


# ── the corpus diff ───────────────────────────────────────────────────────────


def diff_corpus_consumers(
    phase_records: Iterable[dict],
    bulk_index: dict[str, dict],
    ir_index: dict[str, Card],
    schema: MirrorSchema,
    *,
    commander_only: bool = True,
    example_cap: int = 15,
) -> dict:
    """Diff the four consumers' IR reads (old IR vs compat), joined by oracle_id.

    Returns a structured report: join/skip stats, the aggregated
    ``CompatCoverage`` rows, and per-consumer agreement with per-category
    disagreement attribution (categories present on one side's IR but not the
    other's, for each disagreeing card) plus capped examples.
    """
    cov = CompatCoverage()
    per_consumer: dict[str, dict] = {
        name: {"cards": 0, "agree": 0, "per_category": {}, "examples": []}
        for name in CONSUMERS
    }
    joined = 0
    seen_oids: set[str] = set()
    skipped = {
        "no_oracle_id": 0,
        "not_in_bulk": 0,
        "not_in_ir": 0,
        "not_commander_legal": 0,
        "duplicate_printing": 0,
        "schema_drift": 0,
    }

    def record_diff(
        name: str, card_name: str, *, agree: bool, cats: set[str], detail: str
    ) -> None:
        row = per_consumer[name]
        row["cards"] += 1
        if agree:
            row["agree"] += 1
            return
        for cat in sorted(cats) or ["(none)"]:
            row["per_category"][cat] = row["per_category"].get(cat, 0) + 1
        if len(row["examples"]) < example_cap:
            row["examples"].append({"name": card_name, "detail": detail})

    for rec in phase_records:
        oid = rec.get("scryfall_oracle_id")
        if not oid:
            skipped["no_oracle_id"] += 1
            continue
        if oid in seen_oids:
            skipped["duplicate_printing"] += 1
            continue
        bulk = bulk_index.get(oid)
        if bulk is None:
            skipped["not_in_bulk"] += 1
            continue
        old = ir_index.get(oid)
        if old is None:
            skipped["not_in_ir"] += 1
            continue
        if (
            commander_only
            and (bulk.get("legalities") or {}).get("commander") != "legal"
        ):
            skipped["not_commander_legal"] += 1
            continue
        try:
            root = strict_load_card(rec, schema, name=rec.get("name"))
        except MirrorDriftError:
            skipped["schema_drift"] += 1
            continue
        if root is None:
            skipped["schema_drift"] += 1
            continue
        seen_oids.add(oid)
        joined += 1

        name = bulk.get("name", rec.get("name", ""))
        tree = build_concept_tree(root, name=name, oracle_id=oid)
        new = compat_card(tree, cov)
        # The disagreement-attribution key: categories one IR carries and the
        # other does not (the mechanic whose port status explains the diff).
        cats = _effect_categories(old) ^ _effect_categories(new)

        views = {
            "ranking": (ranking_view(bulk, old), ranking_view(bulk, new)),
            "budgets": (budgets_view(old), budgets_view(new)),
            "cut_check": (cut_check_view(bulk, old), cut_check_view(bulk, new)),
            "metrics": (metrics_view(old), metrics_view(new)),
            "bracket": (bracket_view(old), bracket_view(new)),
        }
        for consumer, (v_old, v_new) in views.items():
            record_diff(
                consumer,
                name,
                agree=v_old == v_new,
                cats=cats,
                detail=f"old={v_old!r} compat={v_new!r}",
            )

    return {
        "joined": joined,
        "skipped": skipped,
        "coverage": cov.coverage_rows(),
        "consumers": per_consumer,
    }


# ── report rendering ──────────────────────────────────────────────────────────


def render_consumer_report(report: dict) -> str:
    """Markdown digest: join stats, per-consumer agreement, coverage, worklist."""
    sk = report["skipped"]
    lines = [
        "# Consumer output-diff: compat crosswalk vs old Card IR (ADR-0035 Stage 2)",
        "",
        f"Joined **{report['joined']}** unique commander-legal cards by "
        f"oracle_id (skipped: {sk['no_oracle_id']} no-oracle_id, "
        f"{sk['not_in_bulk']} not-in-bulk, {sk['not_in_ir']} not-in-IR, "
        f"{sk['not_commander_legal']} not-commander-legal, "
        f"{sk['duplicate_printing']} dup-printings, "
        f"{sk['schema_drift']} schema-drift).",
        "",
        "## Per-consumer agreement",
        "",
        "| consumer | cards | agree | disagree | agree% |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in CONSUMERS:
        row = report["consumers"][name]
        cards, agree = row["cards"], row["agree"]
        pct = (100.0 * agree / cards) if cards else 100.0
        lines.append(f"| {name} | {cards} | {agree} | {cards - agree} | {pct:.1f}% |")
    lines += [
        "",
        "## Compat coverage (effect nodes: ported category vs explicit miss)",
        "",
        "| bucket | ported | unported |",
        "| --- | ---: | ---: |",
    ]
    rows = sorted(report["coverage"], key=lambda r: r[1] + r[2], reverse=True)
    for bucket, ported, unported in rows:
        lines.append(f"| {bucket} | {ported} | {unported} |")
    lines += ["", "## Disagreement attribution (the adjudication worklist)", ""]
    for name in CONSUMERS:
        row = report["consumers"][name]
        cats = sorted(row["per_category"].items(), key=lambda kv: kv[1], reverse=True)
        if not cats:
            continue
        lines.append(f"### {name}")
        lines.append("")
        for cat, n in cats[:20]:
            lines.append(f"- **{cat}**: {n}")
        ex = row["examples"]
        if ex:
            names = ", ".join(e["name"] for e in ex)
            lines.append(f"- examples: {names}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m mtg_utils._deck_forge.crosswalk_consumer_diff``.

    Gated dev tool: needs the local phase ``card-data.json``, the bulk, and
    the old Card-IR sidecar. Never CI.
    """
    import argparse
    import json
    from pathlib import Path

    from mtg_utils import _phase
    from mtg_utils._card_ir.load import load_card_ir
    from mtg_utils._card_ir.mirror.build import load_committed_schema
    from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards

    parser = argparse.ArgumentParser(
        description="Shadow-diff the four non-Signal IR consumers (ranking / "
        "budgets / cut_check / tuner) over old-IR vs the crosswalk compat "
        "card (ADR-0035 Stage 2)."
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
    report = diff_corpus_consumers(
        phase_records, bulk_index, ir_index, schema, commander_only=not args.all
    )
    print(json.dumps(report, indent=2) if args.json else render_consumer_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
