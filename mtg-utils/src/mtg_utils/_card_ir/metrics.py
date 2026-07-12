"""Substrate-level parse metrics over phase's raw ``card-data.json``.

ADR-0039 step 7: the ADR-0032 parse-completeness metric
(``compute_parse_metrics`` + the committed ``parse_metrics.json``) was retired
with the legacy ``project.py`` builder — its subject (the old projection's
``parse_confidence`` / ``(recovered)`` recovery footprint and the bucket-A/B
masking classification) was intrinsic to that builder's own bookkeeping and has
no truthful crosswalk-level equivalent. The substrate-level drift-watch lives
on: :func:`compute_phase_variant_population` reads phase's RAW discriminator
tags (no projection at all) and backs the committed
``phase_variant_population.json`` fixture.
"""

from __future__ import annotations

from collections import Counter
from typing import cast

from mtg_utils._card_ir.mirror.variants import EFFECT_SLOT, EFFECT_VARIANTS


def compute_phase_variant_population(records: list[dict]) -> dict:
    """Per-phase-``Effect``-variant node count over raw ``card-data.json``.

    ADR-0035 Stage 1, deliverable 4 — the one residual the strict loader can't
    see: a node relocating between two *both-valid* ``Effect`` variants (schema
    unchanged, count shifts). This baseline pins the count of each variant at
    the canonical effect slot (``ckey == "effect"``); a phase bump that moves
    nodes between valid variants trips a committed-fixture diff here even though
    strict-load stays green.

    Unlike the retired ADR-0032 ``compute_parse_metrics`` (which read the old
    *projected* Card IR, where phase's variant names were already collapsed into
    ~80 IR categories), this reads phase's **raw** discriminator tags, so it
    takes the unprojected ``records`` (the ``card-data.json`` value list)
    directly.

    The result seeds every one of the 207 enum variants — including the 18
    zero-instance closed-union arms at ``0`` — so a first emission shows as a
    0→N jump.
    """
    counts: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    known = set(EFFECT_VARIANTS)

    def walk(v: object, ckey: str) -> None:
        if isinstance(v, dict):
            d = cast("dict[str, object]", v)
            tag = d.get("type")
            if isinstance(tag, str):
                if ckey == EFFECT_SLOT:
                    (counts if tag in known else unknown)[tag] += 1
                for fk, fv in d.items():
                    if fk != "type":
                        walk(fv, fk)
            elif len(d) == 1:
                (only,) = d.keys()
                walk(d[only], only)
            else:
                for fk, fv in d.items():
                    walk(fv, fk)
        elif isinstance(v, list):
            for item in cast("list[object]", v):
                walk(item, ckey)

    for rec in records:
        for fk, fv in rec.items():
            walk(fv, fk)

    population = {name: counts.get(name, 0) for name in EFFECT_VARIANTS}
    observed = sum(1 for n in EFFECT_VARIANTS if counts.get(n, 0) > 0)
    return {
        "effect_slot": EFFECT_SLOT,
        "total_effect_nodes": sum(counts.values()),
        "distinct_variants_observed": observed,
        "zero_instance_variants": len(EFFECT_VARIANTS) - observed,
        # An effect-slot tag NOT in phase's known Effect roster — would mean the
        # name grep drifted from the enum; must stay empty.
        "unknown_effect_slot_tags": dict(sorted(unknown.items())),
        "population": dict(sorted(population.items())),
    }
