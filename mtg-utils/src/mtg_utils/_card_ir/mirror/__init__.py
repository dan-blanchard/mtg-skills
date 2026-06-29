"""Lossless phase-mirror substrate — Layer 1 (ADR-0035, Stage 1).

The codegen'd typed mirror of phase's emitted ``card-data.json`` plus the strict
loader (the loud-on-bump drift detector). Inferred from the data, never from
phase's Rust source. **Additive:** nothing in production reads this yet — it is
the de-risking first step of the lossless-IR migration.

Stays self-contained within ``_card_ir`` (no ``_deck_forge.signals`` import).
"""

from __future__ import annotations

from mtg_utils._card_ir.mirror.infer import infer_schema
from mtg_utils._card_ir.mirror.loader import (
    MirrorDriftError,
    MirrorNode,
    MirrorVariant,
    find_ambiguous_fields,
    strict_load_card,
)
from mtg_utils._card_ir.mirror.schema import MirrorSchema, value_kind
from mtg_utils._card_ir.mirror.variants import (
    EFFECT_VARIANTS,
    ZERO_INSTANCE_EFFECTS,
)

__all__ = [
    "EFFECT_VARIANTS",
    "ZERO_INSTANCE_EFFECTS",
    "MirrorDriftError",
    "MirrorNode",
    "MirrorSchema",
    "MirrorVariant",
    "find_ambiguous_fields",
    "infer_schema",
    "strict_load_card",
    "value_kind",
]
