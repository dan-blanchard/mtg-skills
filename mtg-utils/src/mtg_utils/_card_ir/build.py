"""Build the Card IR cache sidecar from phase-rs's ``card-data.json``.

Cache-only distribution (the grilled decision): each user builds phase locally,
this step projects its parse once into a sidecar keyed by ``oracle_id``, and the
runtime then does field lookups (no Rust/mypyc at runtime). The sidecar carries
the phase tag so a phase upgrade invalidates it.

phase keys ``card-data.json`` by lowercased face name (each face a separate
entry); DFC faces share a ``scryfall_oracle_id``, so we group all records by it
and project each group into one multi-face :class:`~mtg_utils.card_ir.Card`.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from mtg_utils import _phase
from mtg_utils._card_ir.load import SIDECAR_VERSION, sidecar_path
from mtg_utils._card_ir.project import project_card
from mtg_utils._sidecar import atomic_write_json


def _group_by_oracle_id(data: object) -> dict[str, list[dict]]:
    """Group phase face-records by ``scryfall_oracle_id`` (insertion order kept,
    so a DFC's front face precedes its back face as listed in card-data.json)."""
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
        if isinstance(oid, str) and oid:
            groups.setdefault(oid, []).append(rec)
    return groups


def build_sidecar(
    card_data_path: str | Path | None = None,
    out_path: str | Path | None = None,
) -> tuple[Path, dict]:
    """Project phase's card-data.json into the sidecar; return (path, stats)."""
    cdp = Path(card_data_path) if card_data_path else _phase._card_data_path()  # noqa: SLF001 — canonical phase card-data path
    if not cdp.exists():
        raise FileNotFoundError(
            f"phase card-data.json not found at {cdp}. "
            "Run `playtest-install-phase` to generate it."
        )
    data = json.loads(cdp.read_text())
    groups = _group_by_oracle_id(data)

    cards: dict[str, dict] = {}
    confidence: Counter[str] = Counter()
    for oid, records in groups.items():
        card = project_card(records)
        cards[oid] = card.to_dict()
        confidence[card.parse_confidence] += 1

    out = Path(out_path) if out_path else sidecar_path()
    atomic_write_json(
        out,
        {"version": SIDECAR_VERSION, "phase_tag": _phase.PHASE_TAG, "cards": cards},
    )
    stats = {
        "cards": len(cards),
        "phase_tag": _phase.PHASE_TAG,
        "confidence": dict(confidence),
    }
    return out, stats


def main(argv: list[str] | None = None) -> int:
    """CLI: ``build-card-ir [--card-data PATH] [--out PATH]``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build the Card IR cache sidecar from phase's card-data.json."
    )
    parser.add_argument(
        "--card-data",
        default=None,
        help="Path to phase card-data.json (default: the playtest-install location).",
    )
    parser.add_argument(
        "--out", default=None, help="Sidecar output path (default: the cache dir)."
    )
    args = parser.parse_args(argv)

    try:
        out, stats = build_sidecar(args.card_data, args.out)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    total = stats["cards"]
    conf = stats["confidence"]
    print(f"Wrote {total} cards to {out} (phase {stats['phase_tag']}).")
    for level in ("full", "partial", "unparsed"):
        n = conf.get(level, 0)
        pct = (n / total * 100) if total else 0.0
        print(f"  {level:>8}: {n:>6} ({pct:4.1f}%)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
