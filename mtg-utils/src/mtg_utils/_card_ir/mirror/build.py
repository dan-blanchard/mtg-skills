"""Gated dev build of the phase-mirror substrate (ADR-0035, Stage 1).

NEVER CI. Like ``build-card-snapshot`` / ``build-card-ir``, this is a manual
step run once per phase tag bump. It:

1. infers the typed-mirror :class:`MirrorSchema` from the pinned card-data,
2. audits discriminator-uniqueness (no ambiguous tagged/struct collision),
3. strict-loads the full corpus (the schema must accept every real record),
4. computes the per-``Effect``-variant population baseline,
5. writes the (gitignored) substrate-cache to the card-ir cache dir, and
6. writes three committed fixtures the additive Stage-1 gate tests read:
   ``phase_mirror_schema.json`` (the generated mirror),
   ``phase_variant_population.json`` (the baseline), and
   ``phase_mirror_samples.json`` (a diverse real-card slice
   for the losslessness round-trip + injected-drift tests).

Nothing in production reads any of this yet — Stage 1 is purely additive; the
sole shipped behaviour is the loud-on-bump drift detector.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from mtg_utils import _phase
from mtg_utils._card_ir.load import card_ir_dir
from mtg_utils._card_ir.metrics import compute_phase_variant_population
from mtg_utils._card_ir.mirror.infer import infer_schema
from mtg_utils._card_ir.mirror.loader import (
    MirrorDriftError,
    find_ambiguous_fields,
    strict_load_card,
)
from mtg_utils._card_ir.mirror.schema import MirrorSchema
from mtg_utils._sidecar import atomic_write_json

MIRROR_CACHE_VERSION = "mirror_v1"

# Committed-fixture file names (under tests/fixtures/).
SCHEMA_FIXTURE = "phase_mirror_schema.json"
POPULATION_FIXTURE = "phase_variant_population.json"
SAMPLES_FIXTURE = "phase_mirror_samples.json"


def substrate_cache_path() -> Path:
    """The gitignored substrate-cache path, keyed by PHASE_TAG (a tag bump
    auto-invalidates it; old tags stay cached)."""
    return card_ir_dir() / f"substrate-mirror-{_phase.PHASE_TAG}.json"


def fixtures_dir() -> Path:
    """The committed ``tests/fixtures`` dir (repo-relative to this module)."""
    # .../mtg-utils/src/mtg_utils/_card_ir/mirror/build.py -> repo root
    return Path(__file__).resolve().parents[5] / "tests" / "fixtures"


def _write_fixture(path: Path, data: object) -> None:
    """Atomically write a committed JSON fixture WITH a trailing newline.

    Matches the repo's other committed fixtures (``parse_metrics.json`` etc.) so
    the ``end-of-file-fixer`` commit hook leaves it untouched and a rebuild is
    byte-stable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _select_samples(records: list[dict], cap: int = 16) -> list[dict]:
    """Greedily pick a small, diverse, deterministic real-card slice.

    Covers the structural features the loader must round-trip: triggers,
    abilities, static abilities, replacements, tagged power/toughness, a
    planeswalker (loyalty), a ``modal`` struct, a ``layout`` (DFC/adventure),
    ``additional_cost``, ``parse_warnings``, and an empty-``{}`` legalities.
    """

    def features(r: dict) -> set[str]:
        feats: set[str] = set()
        if r.get("triggers"):
            feats.add("triggers")
        if r.get("abilities"):
            feats.add("abilities")
        if r.get("static_abilities"):
            feats.add("static_abilities")
        if r.get("replacements"):
            feats.add("replacements")
        if isinstance(r.get("power"), dict):
            feats.add("pt")
        if r.get("loyalty") is not None:
            feats.add("loyalty")
        if r.get("modal"):
            feats.add("modal")
        if r.get("layout"):
            feats.add("layout")
        if r.get("additional_cost"):
            feats.add("additional_cost")
        if r.get("parse_warnings"):
            feats.add("parse_warnings")
        if r.get("keywords"):
            feats.add("keywords")
        if r.get("legalities") == {}:
            feats.add("empty_legalities")
        return feats

    # Deterministic order by card name.
    ordered = sorted(records, key=lambda r: r.get("name") or "")
    covered: set[str] = set()
    picked: list[dict] = []
    for r in ordered:
        f = features(r)
        if f - covered:
            picked.append(r)
            covered |= f
            if len(picked) >= cap:
                break
    return picked


def build_substrate(
    card_data_path: str | Path | None = None,
    *,
    write_fixtures: bool = True,
) -> tuple[Path, dict]:
    """Infer + strict-load + baseline the substrate; return (cache_path, stats)."""
    if card_data_path:
        cdp = Path(card_data_path)
        if not cdp.exists():
            raise FileNotFoundError(f"phase card-data.json not found at {cdp}.")
    else:
        cdp = _phase.ensure_card_data()
    data = json.loads(cdp.read_text())
    records = cast(
        "list[dict]",
        list(data.values()) if isinstance(data, dict) else list(data),
    )

    schema = infer_schema(records, phase_tag=_phase.PHASE_TAG)

    ambiguous = find_ambiguous_fields(schema)
    if ambiguous:
        raise MirrorDriftError(
            "discriminator-uniqueness violation — ambiguous tagged/struct "
            f"collisions: {ambiguous[:10]}"
        )

    # Strict-load the whole corpus (validation only — no tree materialization).
    loaded = 0
    for rec in records:
        strict_load_card(rec, schema, build=False)
        loaded += 1

    population = compute_phase_variant_population(records)
    samples = _select_samples(records)

    cache_path = substrate_cache_path()
    atomic_write_json(
        cache_path,
        {
            "version": MIRROR_CACHE_VERSION,
            "phase_tag": _phase.PHASE_TAG,
            "schema": schema.to_json(),
            "variant_population": population,
            "strict_load": {"cards": loaded, "ambiguous_fields": ambiguous},
        },
    )

    if write_fixtures:
        fx = fixtures_dir()
        _write_fixture(fx / SCHEMA_FIXTURE, schema.to_json())
        _write_fixture(
            fx / POPULATION_FIXTURE,
            {"phase_tag": _phase.PHASE_TAG, **population},
        )
        _write_fixture(
            fx / SAMPLES_FIXTURE,
            {
                "phase_tag": _phase.PHASE_TAG,
                "schema_version": schema.schema_version,
                "cards": {
                    (r.get("name") or f"card{i}"): r for i, r in enumerate(samples)
                },
            },
        )

    stats = {
        "cards": loaded,
        "phase_tag": _phase.PHASE_TAG,
        "tagged_groups": len(schema.tagged),
        "struct_positions": len(schema.structs),
        "variant_positions": len(schema.variants),
        "ambiguous_fields": len(ambiguous),
        "distinct_effect_variants_observed": population["distinct_variants_observed"],
        "zero_instance_variants": population["zero_instance_variants"],
        "total_effect_nodes": population["total_effect_nodes"],
        "samples": len(samples),
    }
    return cache_path, stats


def load_committed_schema() -> MirrorSchema:
    """Load the committed generated-mirror schema fixture (CI-usable, no corpus)."""
    path = fixtures_dir() / SCHEMA_FIXTURE
    return MirrorSchema.from_json(json.loads(path.read_text()))


def main(argv: list[str] | None = None) -> int:
    """CLI: ``build-card-ir-substrate [--card-data PATH] [--no-fixtures]``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build the lossless phase-mirror substrate (ADR-0035, "
        "Stage 1) — gated dev step, never CI."
    )
    parser.add_argument(
        "--card-data",
        default=None,
        help="Path to phase card-data.json (default: download+cache the "
        "release tarball's copy for the pinned PHASE_TAG).",
    )
    parser.add_argument(
        "--no-fixtures",
        action="store_true",
        help="Skip writing the committed tests/fixtures artifacts.",
    )
    args = parser.parse_args(argv)

    try:
        cache_path, stats = build_substrate(
            args.card_data, write_fixtures=not args.no_fixtures
        )
    except (FileNotFoundError, MirrorDriftError, RuntimeError) as exc:
        print(str(exc))
        return 1

    print(f"Mirror substrate built for phase {stats['phase_tag']}: {cache_path}")
    print(f"  cards strict-loaded:   {stats['cards']}")
    print(f"  tagged groups:         {stats['tagged_groups']}")
    print(f"  struct positions:      {stats['struct_positions']}")
    print(f"  variant positions:     {stats['variant_positions']}")
    print(f"  ambiguous fields:      {stats['ambiguous_fields']}")
    print(
        f"  effect variants:       "
        f"{stats['distinct_effect_variants_observed']} observed / "
        f"{stats['zero_instance_variants']} zero-instance"
    )
    print(f"  effect nodes:          {stats['total_effect_nodes']}")
    print(f"  samples:               {stats['samples']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
