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
from typing import TYPE_CHECKING

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
