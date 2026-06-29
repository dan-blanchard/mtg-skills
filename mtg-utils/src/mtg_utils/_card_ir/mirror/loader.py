"""Strict loader for the phase-mirror substrate (ADR-0035).

The drift detector. ``strict_load_card`` walks a real card record against an
inferred :class:`MirrorSchema` with ``extra=forbid`` semantics: an **unknown
field**, a **missing required field**, an **unknown tag**, or an **unknown
single-key variant** raises :class:`MirrorDriftError` — it never silently
degrades to ``None`` (the v0.8.0 failure mode). A tag that is a name-known but
zero-instance phase ``Effect`` variant raises a *specific* closed-union message
on its first emission.

Stage 2 (full codegen): the loader builds **typed instances of the generated
classes** (``generated_types.py``) — one concrete frozen dataclass per shape,
dispatched on ``(content_key, tag)`` for tagged nodes and ``content_key`` for
structs, with **no generic-interpreter fallback** for any real card shape. The
``variant1`` single-key positions wrap their (already typed) inner value in the
thin typed :class:`MirrorVariant`. The tree is **lossless**: every concrete
node's ``to_dict`` reconstructs its source dict, so
``strict_load_card(rec, schema).to_dict() == rec`` for any in-schema record.

For the full-corpus gate pass we validate without materializing the tree
(``build=False``) to stay fast and low-memory; losslessness round-trips a
sample with ``build=True``.
"""

from __future__ import annotations

from typing import cast

from mtg_utils._card_ir.mirror.generated_types import (
    GENERATED_BY_CKEY,
    GENERATED_BY_KEY,
    JSON_TO_PY,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant, TypedMirrorNode
from mtg_utils._card_ir.mirror.schema import (
    EMPTY,
    LIST,
    ROOT,
    STRUCT,
    TAGGED,
    VARIANT,
    MirrorSchema,
    value_kind,
)
from mtg_utils._card_ir.mirror.variants import (
    EFFECT_SLOT,
    ZERO_INSTANCE_EFFECTS,
)


class MirrorDriftError(ValueError):
    """Raised when a card node diverges from the inferred mirror schema.

    Signals phase schema drift (a renamed/relocated tag, a new field, a dropped
    required field) or a first emission of a zero-instance closed-union variant.
    """


def strict_load_card(
    record: dict,
    schema: MirrorSchema,
    *,
    name: str | None = None,
    build: bool = True,
) -> TypedMirrorNode | None:
    """Strict-load one card record; raise :class:`MirrorDriftError` on drift.

    With ``build=True`` returns the typed-instance tree (root is an
    ``S_Root``); with ``build=False`` the record is only validated.
    """
    where = name or record.get("name") or "<card>"
    return cast(
        "TypedMirrorNode | None",
        _walk(record, ROOT, schema, build=build, where=str(where)),
    )


def _walk(
    v: object, ckey: str, schema: MirrorSchema, *, build: bool, where: str
) -> object:
    kind = value_kind(v)
    if kind == TAGGED:
        d = cast("dict[str, object]", v)
        return _walk_tagged(d, ckey, schema, build=build, where=where)
    if kind == VARIANT:
        d = cast("dict[str, object]", v)
        (only,) = d.keys()
        allowed = schema.variants.get(ckey)
        if allowed is None or only not in allowed:
            raise MirrorDriftError(
                f"{where}: unknown single-key variant {only!r} under "
                f"content_key {ckey!r} — phase schema drift"
            )
        inner = _walk(d[only], only, schema, build=build, where=where)
        return MirrorVariant(only, ckey, inner) if build else None
    if kind in (STRUCT, EMPTY):
        d = cast("dict[str, object]", v)
        return _walk_struct(d, ckey, schema, build=build, where=where)
    if kind == LIST:
        items = [
            _walk(it, ckey, schema, build=build, where=where)
            for it in cast("list[object]", v)
        ]
        return items if build else None
    return v  # scalar — passes through verbatim


def _walk_tagged(
    v: dict, ckey: str, schema: MirrorSchema, *, build: bool, where: str
) -> object:
    tag = cast("str", v["type"])
    grp = schema.tagged.get((ckey, tag))
    if grp is None:
        if ckey == EFFECT_SLOT and tag in ZERO_INSTANCE_EFFECTS:
            raise MirrorDriftError(
                f"{where}: zero-instance phase Effect variant {tag!r} emitted "
                f"for the first time (closed-union arm — no v0.9.0 shape; "
                f"regenerate the mirror)"
            )
        raise MirrorDriftError(
            f"{where}: unknown tagged node (content_key={ckey!r}, "
            f"type={tag!r}) — phase schema drift"
        )
    field_values: dict[str, object] = {}
    for fk, fv in v.items():
        if fk == "type":
            continue
        if fk not in grp.fields:
            raise MirrorDriftError(
                f"{where}: unknown field {fk!r} on tagged node "
                f"({ckey!r}, {tag!r}) — phase schema drift"
            )
        child = _walk(fv, fk, schema, build=build, where=where)
        if build:
            field_values[JSON_TO_PY.get(fk, fk)] = child
    _check_required(grp.required_fields(), v, ckey, tag, where)
    if not build:
        return None
    return GENERATED_BY_KEY[(ckey, tag)](**field_values)


def _walk_struct(
    v: dict, ckey: str, schema: MirrorSchema, *, build: bool, where: str
) -> object:
    grp = schema.structs.get(ckey)
    if grp is None:
        raise MirrorDriftError(
            f"{where}: unknown struct position {ckey!r} — phase schema drift"
        )
    field_values: dict[str, object] = {}
    for fk, fv in v.items():
        if fk not in grp.fields:
            raise MirrorDriftError(
                f"{where}: unknown field {fk!r} on struct {ckey!r} — phase schema drift"
            )
        child = _walk(fv, fk, schema, build=build, where=where)
        if build:
            field_values[JSON_TO_PY.get(fk, fk)] = child
    _check_required(grp.required_fields(), v, ckey, None, where)
    if not build:
        return None
    return GENERATED_BY_CKEY[ckey](**field_values)


def _check_required(
    required: frozenset[str],
    v: dict,
    ckey: str,
    tag: str | None,
    where: str,
) -> None:
    missing = required - v.keys()
    if missing:
        what = f"({ckey!r}, {tag!r})" if tag else f"struct {ckey!r}"
        raise MirrorDriftError(
            f"{where}: missing required field(s) {sorted(missing)} on {what} — "
            f"phase schema drift"
        )


def find_ambiguous_fields(schema: MirrorSchema) -> list[str]:
    """Discriminator-uniqueness audit: positions whose dispatch is undecidable.

    Each ``(content_key, tag)`` group must resolve to ONE payload schema. The
    three dict-shapes (tagged / variant1 / struct) are decidable per concrete
    instance, so the only genuine ambiguity is a field that mixes ``tagged``
    with another container kind — i.e. a value that is *sometimes* a
    discriminated enum node and *sometimes* a plain struct/variant, which the
    loader could not dispatch deterministically. Returns a human-readable list
    of any such collisions (empty == clean).
    """
    bad: list[str] = []
    groups = list(schema.tagged.values()) + list(schema.structs.values())
    for grp in groups:
        for name, spec in grp.fields.items():
            containers = spec.kinds & {TAGGED, VARIANT, STRUCT}
            if TAGGED in containers and len(containers) > 1:
                key = f"({grp.ckey!r}, {grp.tag!r})" if grp.tag else f"{grp.ckey!r}"
                bad.append(f"{key}.{name}: {sorted(spec.kinds)}")
    return bad
