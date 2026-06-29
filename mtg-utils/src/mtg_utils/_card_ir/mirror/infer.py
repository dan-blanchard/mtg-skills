"""Data-inference codegen (ADR-0035, Stage 1).

``infer_schema`` walks the full ``card-data.json`` once and groups every node by
its data-visible discriminator — ``(content_key, tag)`` for tagged enum nodes,
``content_key`` for struct/variant positions — recording the field set and
value-kinds observed at each. The product is a :class:`MirrorSchema`: the typed
structural mirror the strict loader validates against. This is *tag-dispatch
over the emitted bytes*, never a reimplementation of phase's serde semantics.

``records`` is the value list of phase's oracle-keyed ``card-data.json`` (each a
flat face record). The walk recurses to the data's full depth (observed 24).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from mtg_utils._card_ir.mirror.schema import (
    EMPTY,
    LIST,
    ROOT,
    STRUCT,
    TAGGED,
    VARIANT,
    FieldSpec,
    GroupSchema,
    MirrorSchema,
    value_kind,
)


def infer_schema(records: Iterable[dict], *, phase_tag: str = "") -> MirrorSchema:
    """Infer the typed-mirror schema from the emitted card-data records."""
    schema = MirrorSchema(phase_tag=phase_tag)

    def note(grp: GroupSchema, name: str, val: object) -> None:
        spec = grp.fields.get(name)
        if spec is None:
            spec = FieldSpec()
            grp.fields[name] = spec
        spec.kinds.add(value_kind(val))
        spec.seen += 1

    def tagged_group(ckey: str, tag: str) -> GroupSchema:
        key = (ckey, tag)
        grp = schema.tagged.get(key)
        if grp is None:
            grp = GroupSchema(ckey=ckey, tag=tag)
            schema.tagged[key] = grp
        return grp

    def struct_group(ckey: str) -> GroupSchema:
        grp = schema.structs.get(ckey)
        if grp is None:
            grp = GroupSchema(ckey=ckey, tag=None)
            schema.structs[ckey] = grp
        return grp

    def walk(v: object, ckey: str) -> None:
        kind = value_kind(v)
        if kind == TAGGED:
            d = cast("dict[str, object]", v)
            grp = tagged_group(ckey, cast("str", d["type"]))
            grp.count += 1
            for fk, fv in d.items():
                if fk == "type":
                    continue
                note(grp, fk, fv)
                walk(fv, fk)
        elif kind == VARIANT:
            d = cast("dict[str, object]", v)
            (only,) = d.keys()
            schema.variants.setdefault(ckey, set()).add(only)
            walk(d[only], only)
        elif kind in (STRUCT, EMPTY):
            d = cast("dict[str, object]", v)
            grp = struct_group(ckey)
            grp.count += 1
            for fk, fv in d.items():
                note(grp, fk, fv)
                walk(fv, fk)
        elif kind == LIST:
            for item in cast("list[object]", v):
                walk(item, ckey)
        # scalars carry no sub-structure

    for rec in records:
        root = struct_group(ROOT)
        root.count += 1
        for fk, fv in rec.items():
            note(root, fk, fv)
            walk(fv, fk)

    return schema
