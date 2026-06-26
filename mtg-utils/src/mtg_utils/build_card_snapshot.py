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
  * default — scan the test tree for ``test_card("…")`` / ``test_card_ir("…")`` /
    ``test_signals("…")`` literals (usage-derived; the snapshot only holds cards a
    test actually asks for).
  * ``--names "A,B"`` / ``--names-file PATH`` — an explicit name list (additive to the
    scan unless ``--no-scan``).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from mtg_utils._card_ir.load import SIDECAR_VERSION, load_card_ir
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

# Direct literal calls: ``test_card("Sol Ring")`` / ``test_card_ir(...)`` /
# ``test_signals(...)`` plus the per-suite real-card wrapper family that forwards a
# name into those helpers (``_ks_real("Atraxa, …")``, ``_keys_real_regex(…)``,
# ``_by_key_real(…)`` — the name literal sits on the wrapper, not on ``test_signals``).
# Two string alternates so a name's internal apostrophe (``Atraxa, Praetors' Voice``,
# ``Be'lakor``) inside a double-quoted literal isn't truncated at that apostrophe.
_USAGE_RE = re.compile(
    r"""\b(?:test_(?:card|card_ir|signals)"""
    r"""|_(?:keys|ks|ksub|by_key)_real(?:_regex)?"""
    r"""|_real_full|_real)"""  # test_signals.py wrappers (longer alt first)
    r"""\(\s*(?:"([^"]+)"|'([^']+)')"""
)
# The parametrized convention: a ``_REAL_CASES: dict[str, str] = { "key": "Name", … }``
# name table (mapping migrated key → representative card NAME). Capture each value.
_REAL_CASES_BLOCK_RE = re.compile(r"_REAL_CASES\b[^=]*=\s*\{(.*?)\n\}", re.DOTALL)
_NAME_TABLE_VALUE_RE = re.compile(r'^\s*"[^"]+":\s*"([^"]+)",?\s*$', re.MULTILINE)


def _minimal(card: dict) -> dict:
    out = {k: card[k] for k in _SCRY_FIELDS if k in card}
    if "card_faces" in out:
        out["card_faces"] = [
            {k: f[k] for k in _FACE_FIELDS if k in f} for f in out["card_faces"]
        ]
    return out


def _scan_names(test_dirs: list[Path]) -> set[str]:
    """Usage-derived names: direct ``test_card(...)`` literals + every value in a
    ``_REAL_CASES`` key→name table. So adding a row to that table (and re-running)
    grows the snapshot with no external name list."""
    names: set[str] = set()
    for d in test_dirs:
        if not d.exists():
            continue
        for py in d.rglob("test_*.py"):
            text = py.read_text(encoding="utf-8")
            # Each match is a (double-quoted, single-quoted) group pair; one is empty.
            names.update(g for m in _USAGE_RE.findall(text) for g in m if g)
            for block in _REAL_CASES_BLOCK_RE.findall(text):
                names.update(_NAME_TABLE_VALUE_RE.findall(block))
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
    unresolved: list[str] = []
    no_ir: list[str] = []
    lossy: list[str] = []
    for name in sorted(names):
        rec = index.get(normalize_card_name(name))
        if rec is None:
            unresolved.append(name)
            continue
        card_ir = ir.get(rec.get("oracle_id"))
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
    stats = {
        "cards": len(cards),
        "requested": len(names),
        "unresolved": unresolved,
        "no_ir": no_ir,
        "bytes": out.stat().st_size,
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
