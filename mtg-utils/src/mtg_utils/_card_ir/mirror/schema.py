"""The inferred typed-mirror schema (ADR-0035, Stage 1 — Layer 1 substrate).

This is the *data-inference* product: a structural schema of phase's emitted
``card-data.json``, inferred from the bytes (never from phase's Rust source /
schemars). It is a **shape-faithful** mirror — polymorphic positions are
dispatched on the data-visible discriminator keyed by ``(content_key, tag)`` —
**not** a claim to phase's nominal type graph.

Every concrete value falls into exactly one *value-kind* (``value_kind``):

* scalars — ``null`` / ``bool`` / ``int`` / ``float`` / ``str``
* ``list`` — a homogeneous-position list (its items recurse at the same ckey)
* ``tagged`` — a dict carrying a string ``"type"`` (a discriminated enum node);
  the ``type`` value is the variant tag
* ``variant1`` — a single-key dict with **no** ``"type"`` (an untagged
  single-key enum, e.g. ``{"UntilNextTurnOf": {...}}``); the key is the variant
* ``struct`` — a multi-key dict with no ``"type"`` (a plain record)
* ``empty_dict`` — ``{}`` (folded into ``struct`` for schema purposes)

These three dict-shapes are **mutually exclusive and decidable per concrete
instance**, so dispatch is never ambiguous at load time. The schema records,
per group, which fields appear and with which value-kinds; a field present in
every occurrence of its group is *required*.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

# value-kind tags
NULL = "null"
BOOL = "bool"
INT = "int"
FLOAT = "float"
STR = "str"
LIST = "list"
EMPTY = "empty_dict"
TAGGED = "tagged"
VARIANT = "variant1"
STRUCT = "struct"

CONTAINER_KINDS: frozenset[str] = frozenset({TAGGED, VARIANT, STRUCT})

# Sentinel ckey for the top-level card record (a struct with no parent field).
ROOT = "<root>"

SCHEMA_VERSION = 1


def value_kind(v: object) -> str:
    """Classify a concrete JSON value into its value-kind (see module docstring)."""
    if v is None:
        return NULL
    if isinstance(v, bool):
        return BOOL
    if isinstance(v, int):
        return INT
    if isinstance(v, float):
        return FLOAT
    if isinstance(v, str):
        return STR
    if isinstance(v, list):
        return LIST
    if isinstance(v, dict):
        if not v:
            return EMPTY
        if isinstance(v.get("type"), str):
            return TAGGED
        if len(v) == 1:
            return VARIANT
        return STRUCT
    raise TypeError(f"non-JSON value of type {type(v).__name__!r}")


@dataclass
class FieldSpec:
    """Observed value-kinds of one field within one group, plus a presence count.

    ``seen`` counts the occurrences (of the owning group) in which this field
    was present; a field with ``seen == group.count`` is *required*.
    """

    kinds: set[str] = field(default_factory=set)
    seen: int = 0


@dataclass
class GroupSchema:
    """The inferred schema of one structural position.

    For a tagged node it is keyed by ``(ckey, tag)``; for a struct position it
    is keyed by ``ckey`` with ``tag is None``. ``count`` is the number of nodes
    that landed in this group across the corpus.
    """

    ckey: str | None
    tag: str | None
    fields: dict[str, FieldSpec] = field(default_factory=dict)
    count: int = 0

    def required_fields(self) -> frozenset[str]:
        """Fields present in *every* occurrence of this group."""
        return frozenset(
            name for name, spec in self.fields.items() if spec.seen == self.count
        )


@dataclass
class MirrorSchema:
    """The whole inferred mirror: tagged groups + struct groups + variant keys."""

    tagged: dict[tuple[str, str], GroupSchema] = field(default_factory=dict)
    structs: dict[str, GroupSchema] = field(default_factory=dict)
    variants: dict[str, set[str]] = field(default_factory=dict)
    phase_tag: str = ""
    schema_version: int = SCHEMA_VERSION

    # ---- serialization (the committed "generated mirror" artifact) ----

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict (tuple keys flattened to a list)."""
        return {
            "schema_version": self.schema_version,
            "phase_tag": self.phase_tag,
            "tagged": [
                {
                    "ckey": g.ckey,
                    "tag": g.tag,
                    "count": g.count,
                    "fields": {
                        n: {"kinds": sorted(s.kinds), "seen": s.seen}
                        for n, s in sorted(g.fields.items())
                    },
                }
                for g in _sorted_groups(self.tagged.values())
            ],
            "structs": [
                {
                    "ckey": g.ckey,
                    "count": g.count,
                    "fields": {
                        n: {"kinds": sorted(s.kinds), "seen": s.seen}
                        for n, s in sorted(g.fields.items())
                    },
                }
                for g in sorted(self.structs.values(), key=lambda g: g.ckey or "")
            ],
            "variants": {k: sorted(v) for k, v in sorted(self.variants.items())},
        }

    @classmethod
    def from_json(cls, data: dict) -> MirrorSchema:
        tagged: dict[tuple[str, str], GroupSchema] = {}
        for g in data.get("tagged", []):
            ckey, tag = str(g["ckey"]), str(g["tag"])
            tagged[(ckey, tag)] = GroupSchema(
                ckey=ckey,
                tag=tag,
                count=g["count"],
                fields={
                    n: FieldSpec(kinds=set(s["kinds"]), seen=s["seen"])
                    for n, s in g["fields"].items()
                },
            )
        structs: dict[str, GroupSchema] = {}
        for g in data.get("structs", []):
            ckey = str(g["ckey"])
            structs[ckey] = GroupSchema(
                ckey=ckey,
                tag=None,
                count=g["count"],
                fields={
                    n: FieldSpec(kinds=set(s["kinds"]), seen=s["seen"])
                    for n, s in g["fields"].items()
                },
            )
        variants = {k: set(v) for k, v in data.get("variants", {}).items()}
        return cls(
            tagged=tagged,
            structs=structs,
            variants=variants,
            phase_tag=data.get("phase_tag", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
        )


def _sorted_groups(groups: Iterable[GroupSchema]) -> list[GroupSchema]:
    return sorted(groups, key=lambda g: (g.ckey or "", g.tag or ""))
