"""Lossless phase-mirror substrate — Layer 1 (ADR-0035, Stage 1).

The codegen'd typed mirror of phase's emitted ``card-data.json`` plus the strict
loader (the loud-on-bump drift detector). Inferred from the data, never from
phase's Rust source. **Additive:** nothing in production reads this yet — it is
the de-risking first step of the lossless-IR migration.

Stays self-contained within ``_card_ir`` (no ``_analysis.signals`` import).

The strict loader is imported from ``mirror.loader``, never re-exported here: it
imports the generated classes (about 1,900 frozen dataclasses, 0.28 s), which a
process importing only ``runtime`` — every lane, read and crosswalk module —
needs only when it builds a tree or unpickles a stored one (pickle imports their
modules itself). A CLI thus pays them after it has asked Commander Spellbook.
"""

from __future__ import annotations

from mtg_utils._card_ir.mirror.infer import infer_schema
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.mirror.schema import MirrorSchema, value_kind
from mtg_utils._card_ir.mirror.variants import (
    EFFECT_VARIANTS,
    ZERO_INSTANCE_EFFECTS,
)

__all__ = [
    "EFFECT_VARIANTS",
    "MISSING",
    "ZERO_INSTANCE_EFFECTS",
    "MirrorSchema",
    "MirrorVariant",
    "TypedMirrorNode",
    "infer_schema",
    "value_kind",
]
