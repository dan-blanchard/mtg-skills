"""Build the committed test snapshot (``tests/fixtures/card_snapshot.json``).

Gated like ``download-bulk`` / ``build-card-ir``: needs the local Scryfall bulk AND a
built Card IR sidecar, and is NEVER run in CI (CI consumes the committed snapshot
offline). It collects the card names the tests reference via the ``mtg_utils.testkit``
helpers, resolves each to its GAMEPLAY printing, and emits, per card, a minimal
Scryfall record plus the REAL projected IR (a verbatim sidecar slice).

Self-validation (the field-completeness guard): for every card it asserts the signals
of the MINIMAL record equal the signals of the FULL bulk record (both over the same
real IR). A mismatch fails loudly with the card + the differing signals so the minimal
field list is expanded rather than a lossy slice silently shipped.

Modes:
  * default — AST-scan the test tree for ``test_card`` / ``test_card_ir`` /
    ``test_signals`` usage: direct string-literal calls, parametrize columns that
    feed such a call through a bare variable, and ``_REAL_CASES`` name tables
    (usage-derived; the snapshot only holds cards a test actually asks for).
  * ``--names "A,B"`` / ``--names-file PATH`` — an explicit name list (additive to the
    scan unless ``--no-scan``).
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from pathlib import Path

from mtg_utils._card_ir.load import SIDECAR_VERSION, load_card_ir
from mtg_utils._card_ir.metrics import compute_parse_metrics
from mtg_utils._deck_forge.signals import extract_signals_hybrid
from mtg_utils._phase import PHASE_TAG
from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards
from mtg_utils.names import normalize_card_name
from mtg_utils.testkit import SCHEMA_VERSION, snapshot_path

# The minimal Scryfall fields project_card + the signal/serve path read. Validated by
# the per-card signals(minimal) == signals(full) assertion below; expand this (not a
# silent fallback) if that assertion ever fires. ``all_parts`` carries token subtypes
# the tribal type_matters subject reads (Flourishing Defenses → Elf).
_SCRY_FIELDS = (
    "oracle_id",
    "name",
    "oracle_text",
    "type_line",
    "keywords",
    "mana_cost",
    "cmc",
    "power",
    "toughness",
    "produced_mana",
    "color_identity",
    "colors",
    "legalities",
    "layout",
    "card_faces",
    "all_parts",
)
_FACE_FIELDS = (
    "name",
    "oracle_text",
    "type_line",
    "mana_cost",
    "power",
    "toughness",
    "keywords",
    "colors",
)

# The snapshot-feeding helper family: the testkit helpers themselves plus the
# per-suite real-card wrappers that forward a name into them (``_ks_real("Atraxa,
# …")``, ``_keys_real_regex(…)`` — the name literal sits on the wrapper, not on
# ``test_signals``). The scan is AST-based (see ``_scan_module``), so apostrophes
# in names, comments mentioning ``test_card("…")``, and parametrize tables all
# behave correctly — a regex scan mis-handled all three.
_HELPER_NAMES = frozenset(
    {
        "test_card",
        "test_card_ir",
        "test_signals",
        "_keys_real",
        "_ks_real",
        "_ksub_real",
        "_by_key_real",
        "_keys_real_regex",
        "_ks_real_regex",
        "_ksub_real_regex",
        "_by_key_real_regex",
        "_real_full",
        "_real",
    }
)


def _helper_call_name(call: ast.Call) -> str | None:
    """The called helper's bare name, when the call targets the helper family."""
    func = call.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    return name if name in _HELPER_NAMES else None


def _parametrize_argnames(node: ast.expr) -> list[str]:
    """The argname list of a ``pytest.mark.parametrize`` first argument — either
    the comma-string form (``"name,wanted"``) or a tuple/list of strings."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [a.strip() for a in node.value.split(",")]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [
            e.value
            for e in node.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    return []


def _parametrize_rows(node: ast.expr) -> list[tuple]:
    """The literal rows of a ``parametrize`` argvalues list, each normalized to a
    tuple (scalars become 1-tuples; ``pytest.param(...)`` rows contribute their
    positional args; non-literal rows are skipped)."""
    if not isinstance(node, (ast.Tuple, ast.List)):
        return []
    rows: list[tuple] = []
    for elt in node.elts:
        target = elt
        if (
            isinstance(elt, ast.Call)
            and isinstance(elt.func, ast.Attribute)
            and elt.func.attr == "param"
        ):
            target = ast.Tuple(elts=list(elt.args), ctx=ast.Load())
        try:
            value = ast.literal_eval(target)
        except ValueError:
            continue
        rows.append(value if isinstance(value, tuple) else (value,))
    return rows


def _parametrized_helper_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Card names flowing into a helper call through a ``parametrize`` column: when
    the test body calls ``test_card(name)`` with a bare variable and ``name`` is a
    parametrize argname, harvest exactly that column's string values — so a
    parametrized name table feeds the snapshot the same way a literal call does."""
    fed = {
        call.args[0].id
        for call in ast.walk(fn)
        if isinstance(call, ast.Call)
        and _helper_call_name(call)
        and call.args
        and isinstance(call.args[0], ast.Name)
    }
    if not fed:
        return set()
    names: set[str] = set()
    for dec in fn.decorator_list:
        if not (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "parametrize"
            and len(dec.args) >= 2
        ):
            continue
        argnames = _parametrize_argnames(dec.args[0])
        rows = _parametrize_rows(dec.args[1])
        for var in fed.intersection(argnames):
            col = argnames.index(var)
            names.update(
                row[col] for row in rows if col < len(row) and isinstance(row[col], str)
            )
    return names


def _scan_module(text: str) -> set[str]:
    """Every card name a test module asks the testkit for: direct helper-call
    literals, parametrize columns feeding a helper call, and ``_REAL_CASES``
    key→name table values."""
    names: set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _helper_call_name(node) and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.add(arg.value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(t, ast.Name) and t.id == "_REAL_CASES" for t in targets
            ) and isinstance(node.value, ast.Dict):
                names.update(
                    v.value
                    for v in node.value.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.update(_parametrized_helper_names(node))
    return names


def _minimal(card: dict) -> dict:
    out = {k: card[k] for k in _SCRY_FIELDS if k in card}
    if "card_faces" in out:
        out["card_faces"] = [
            {k: f[k] for k in _FACE_FIELDS if k in f} for f in out["card_faces"]
        ]
    return out


def _scan_names(test_dirs: list[Path]) -> set[str]:
    """Usage-derived names: direct ``test_card(...)`` literals, parametrize
    columns feeding a helper call, and every value in a ``_REAL_CASES`` key→name
    table. So adding a parametrize row (and re-running) grows the snapshot with
    no external name list."""
    names: set[str] = set()
    for d in test_dirs:
        if not d.exists():
            continue
        for py in d.rglob("test_*.py"):
            names.update(_scan_module(py.read_text(encoding="utf-8")))
    return names


def _index_by_name(bulk: list[dict], ir: dict) -> dict[str, dict]:
    """normalized name → the GAMEPLAY printing (oracle_id in the sidecar; DFC front
    faces keyed too; art_series / reversible dups are skipped because their oracle_id
    is absent from the sidecar)."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    for c in bulk:
        nm = c.get("name")
        if not nm:
            continue
        by_name[normalize_card_name(nm)].append(c)
        if " // " in nm:
            by_name[normalize_card_name(nm.split(" // ")[0])].append(c)
    resolved: dict[str, dict] = {}
    for key, printings in by_name.items():
        pick = next((c for c in printings if c.get("oracle_id") in ir), None)
        if pick is not None:
            resolved[key] = pick
    return resolved


def build_snapshot(names: set[str], out_path: Path | None = None) -> tuple[Path, dict]:
    ir = load_card_ir()
    bulk_path = default_bulk_path()
    if bulk_path is None:
        raise SystemExit(
            "No Scryfall bulk found. Run `download-bulk` first (this gated script "
            "needs the local bulk + a built Card IR sidecar)."
        )
    bulk = load_bulk_cards(bulk_path)
    index = _index_by_name(bulk, ir)

    cards: dict[str, dict] = {}
    snapshot_ir: dict = {}  # oid -> Card, for the snapshot field-coverage metric
    unresolved: list[str] = []
    no_ir: list[str] = []
    lossy: list[str] = []
    for name in sorted(names):
        rec = index.get(normalize_card_name(name))
        if rec is None:
            unresolved.append(name)
            continue
        oid = rec.get("oracle_id")
        card_ir = ir.get(oid)
        if card_ir is None:  # pragma: no cover — index already gates on sidecar
            no_ir.append(name)
            continue
        ir_dict = card_ir.to_dict()
        minimal = _minimal(rec)
        # Field-completeness guard: the slice must lose no signal vs the full record.
        full_sigs = {
            (s.key, s.scope, s.subject) for s in extract_signals_hybrid(rec, card_ir)
        }
        mini_sigs = {
            (s.key, s.scope, s.subject)
            for s in extract_signals_hybrid(minimal, card_ir)
        }
        if full_sigs != mini_sigs:
            lossy.append(
                f"{name}: only-full={full_sigs - mini_sigs} "
                f"only-mini={mini_sigs - full_sigs}"
            )
            continue
        cards[name] = {"scryfall": minimal, "ir": ir_dict}
        snapshot_ir[oid] = card_ir

    if lossy:
        raise SystemExit(
            "Minimal Scryfall slice dropped signals — expand _SCRY_FIELDS:\n  "
            + "\n  ".join(lossy)
        )

    out = out_path or snapshot_path()
    payload = {
        "schema": SCHEMA_VERSION,
        "sidecar_version": SIDECAR_VERSION,
        "phase_tag": PHASE_TAG,
        "cards": cards,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # ADR-0032 parse-completeness metric: the committed full-corpus drift-watch
    # (regenerated in this same gated step) + the snapshot field-coverage the CI
    # assertion (test_parse_metrics) recomputes offline from card_snapshot.json.
    metrics_path = out.parent / "parse_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA_VERSION,
                "sidecar_version": SIDECAR_VERSION,
                "phase_tag": PHASE_TAG,
                "full_corpus": compute_parse_metrics(ir),
                "snapshot": compute_parse_metrics(snapshot_ir),
            },
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    stats = {
        "cards": len(cards),
        "requested": len(names),
        "unresolved": unresolved,
        "no_ir": no_ir,
        "bytes": out.stat().st_size,
        "metrics_path": str(metrics_path),
    }
    return out, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the committed test card snapshot (Scryfall + real IR)."
    )
    parser.add_argument(
        "--names", default="", help="Comma-separated card names (additive to the scan)."
    )
    parser.add_argument(
        "--names-file", default=None, help="File with one card name per line."
    )
    parser.add_argument(
        "--no-scan", action="store_true", help="Skip the test-tree usage scan."
    )
    parser.add_argument(
        "--out", default=None, help="Output path (default: the fixture)."
    )
    args = parser.parse_args(argv)

    out_path = Path(args.out) if args.out else snapshot_path()
    # Repo root = the parent of tests/ (snapshot lives at tests/fixtures/<file>).
    repo_root = out_path.resolve().parents[2]

    names: set[str] = set()
    if not args.no_scan:
        names |= _scan_names(
            [repo_root / "tests" / "deck-forge", repo_root / "tests" / "mtg-utils"]
        )
    if args.names:
        names |= {n.strip() for n in args.names.split(",") if n.strip()}
    if args.names_file:
        names |= {
            ln.strip()
            for ln in Path(args.names_file).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        }
    if not names:
        print("No card names found (scan empty and no --names). Nothing to do.")
        return 1

    out, stats = build_snapshot(names, out_path)
    kb = stats["bytes"] / 1024
    print(
        f"Wrote {stats['cards']}/{stats['requested']} cards to {out} "
        f"({kb:.0f} KB, sidecar v{SIDECAR_VERSION}, phase {PHASE_TAG})."
    )
    if stats["unresolved"]:
        print(f"  unresolved (no gameplay printing): {stats['unresolved']}")
    if stats["no_ir"]:
        print(f"  resolved but no IR: {stats['no_ir']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
