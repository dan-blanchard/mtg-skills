"""Parse-completeness metrics over the Card IR (ADR-0032).

Two cuts of the fidelity ladder, both written to the committed
``tests/fixtures/parse_metrics.json`` in the same gated step that builds the IR
sidecar / ``card_snapshot.json``:

- **Synergy-completeness** (primary, regression-tripping): ``parse_confidence``
  full-% plus field-coverage — triggers stuck at ``event="other"``, effects at
  ``category="other"`` (the partial-driving gaps). *Any* structure counts; a
  regex-recovered node IS parsed for synergy.
- **Feed-phase-readiness** (secondary, direction-tracking): the raw-regex recovery
  footprint (nodes whose ``raw`` ends ``(recovered)``), split bucket-A (a recovery
  *masking* a node phase actually has → DEBT) vs bucket-B (a genuine phase gap →
  combinator-ize later). bucket-A is the tripwire: it is recovered nodes in an
  UNRECOGNIZED category (every known surviving recovery is a curated bucket-B gap;
  a new category means someone added a masking recovery instead of a native read).

A ``(projected)``-suffixed node is a NATIVE read placeholder (metadata carrier),
not a recovery — excluded from the recovery footprint.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, cast

from mtg_utils._card_ir.mirror.variants import EFFECT_SLOT, EFFECT_VARIANTS

if TYPE_CHECKING:
    from mtg_utils.card_ir import Card

# Curated bucket-B recovery categories — the genuine phase gaps the IR-fanout work
# left as raw-regex recoveries (phase Unimplements / has no node), per the ledger at
# ~/.cache/mtg-skills/ir-fanout/. A recovered node in ANY OTHER category is bucket-A
# (masking) until promoted here with justification.
_BUCKET_B_CATEGORIES: frozenset[str] = frozenset(
    {
        "facedown_ref",  # FaceDown morph/manifest marker (no clean phase node)
        "discard",  # discard_unless / group-hug variable-amount folds (kept backstop)
        "other",  # Unimplemented / nodeless residue recovered from raw
    }
)

_RECOVERED = "(recovered)"  # a recovery; "(projected)" is a native-read placeholder


def compute_parse_metrics(cards: dict[str, Card]) -> dict:
    """Compute the two-metric block over an oracle_id -> Card mapping."""
    conf: Counter[str] = Counter()
    triggers_total = triggers_event_other = 0
    effects_total = effects_category_other = 0
    recovered_nodes = cards_with_recovered = 0
    recovered_by_cat: Counter[str] = Counter()

    for card in cards.values():
        conf[card.parse_confidence] += 1
        has_recovered = False
        for ab in card.all_abilities():
            if ab.trigger is not None:
                triggers_total += 1
                if ab.trigger.event == "other":
                    triggers_event_other += 1
            for e in ab.effects:
                effects_total += 1
                if e.category == "other":
                    effects_category_other += 1
                raw = e.raw or ""
                if raw.endswith(_RECOVERED):
                    recovered_nodes += 1
                    recovered_by_cat[e.category] += 1
                    has_recovered = True
        if has_recovered:
            cards_with_recovered += 1

    total = sum(conf.values())
    bucket_b = sum(n for c, n in recovered_by_cat.items() if c in _BUCKET_B_CATEGORIES)
    bucket_a = recovered_nodes - bucket_b

    return {
        "cards": total,
        "synergy_completeness": {
            "parse_confidence": dict(sorted(conf.items())),
            "full_pct": round(conf.get("full", 0) / total * 100, 2) if total else 0.0,
            "triggers_total": triggers_total,
            "triggers_event_other": triggers_event_other,
            "effects_total": effects_total,
            "effects_category_other": effects_category_other,
        },
        "feed_phase_readiness": {
            "cards_with_recovered_node": cards_with_recovered,
            "recovered_nodes": recovered_nodes,
            "bucket_a_masking": bucket_a,
            "bucket_b_genuine_gap": bucket_b,
            "recovered_by_category": dict(sorted(recovered_by_cat.items())),
        },
    }


def compute_phase_variant_population(records: list[dict]) -> dict:
    """Per-phase-``Effect``-variant node count over raw ``card-data.json``.

    ADR-0035 Stage 1, deliverable 4 — the one residual the strict loader can't
    see: a node relocating between two *both-valid* ``Effect`` variants (schema
    unchanged, count shifts). This baseline pins the count of each variant at
    the canonical effect slot (``ckey == "effect"``); a phase bump that moves
    nodes between valid variants trips a committed-fixture diff here even though
    strict-load stays green.

    Unlike :func:`compute_parse_metrics` (which reads the *projected* Card IR,
    where phase's variant names are already collapsed into ~80 IR categories),
    this reads phase's **raw** discriminator tags, so it takes the unprojected
    ``records`` (the ``card-data.json`` value list) directly.

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
