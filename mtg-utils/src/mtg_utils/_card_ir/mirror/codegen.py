"""Full typed-class codegen for the phase-mirror substrate (ADR-0035, Stage 2).

Reads the inferred :class:`MirrorSchema` and emits a committed Python module of
frozen typed dataclasses — **one per distinct shape, complete coverage**: a class
for every ``(content_key, tag)`` tagged shape and every ``content_key`` struct
shape the schema describes, plus a discriminated-union type alias per tagged
``content_key`` and the two dispatch tables the loader builds typed instances
from. NO real card shape falls back to a generic interpreted node.

This is a gated dev step (never CI), like the schema JSON it consumes; the
COMMITTED ``generated_types.py`` is what consumers import. Regenerate it with
``build-card-ir-substrate`` (or :func:`emit_typed_codegen` directly) whenever the
committed schema changes.

The emitted field *types* are advisory for static consumers (the loader's
losslessness is value-kind driven, not type driven); they are derived from the
schema by the rule "the child of a field recurses at ``content_key == field
name``", so a ``tagged`` field at name ``effect`` is typed as the union of every
``effect`` tagged class, a ``struct`` field at name ``filter`` as the ``filter``
struct class, and so on.
"""

from __future__ import annotations

import keyword
import re
from pathlib import Path

from mtg_utils._card_ir.mirror.schema import (
    EMPTY,
    LIST,
    ROOT,
    STRUCT,
    TAGGED,
    VARIANT,
    GroupSchema,
    MirrorSchema,
)

# value-kind -> scalar python type (containers handled separately)
_SCALAR_TYPES = {
    "null": "None",
    "bool": "bool",
    "int": "int",
    "float": "float",
    "str": "str",
}


def _san(s: str) -> str:
    """Sanitize a content_key / tag into an identifier fragment.

    ckeys and tags are already valid identifiers in the v0.9.0 schema except the
    ``<root>`` sentinel; the regex is a defensive guard against future drift.
    """
    if s == ROOT:
        return "Root"
    return re.sub(r"\W", "_", s)


def _struct_cls(ckey: str) -> str:
    return "S_" + _san(ckey)


def _tagged_cls(ckey: str, tag: str) -> str:
    return "T_" + _san(ckey) + "__" + _san(tag)


def _union_alias(ckey: str) -> str:
    return "U_" + _san(ckey)


def _py_field(name: str) -> str:
    """The python attribute name for a JSON field key (keyword-safe)."""
    return name + "_" if keyword.iskeyword(name) else name


class _Names:
    """Precomputed ckey membership sets for type-string resolution."""

    def __init__(self, schema: MirrorSchema) -> None:
        self.tagged_ckeys = {ckey for (ckey, _t) in schema.tagged}
        self.struct_ckeys = set(schema.structs)
        self.variant_ckeys = set(schema.variants)

    def list_elem(self, fk: str) -> str:
        elems: list[str] = []
        if fk in self.tagged_ckeys:
            elems.append(_union_alias(fk))
        if fk in self.struct_ckeys:
            elems.append(_struct_cls(fk))
        if fk in self.variant_ckeys:
            elems.append("MirrorVariant")
        return " | ".join(elems) if elems else "object"

    def field_type(self, fk: str, kinds: set[str]) -> str:
        parts: list[str] = []
        for vk in ("null", "bool", "int", "float", "str"):
            if vk in kinds:
                parts.append(_SCALAR_TYPES[vk])
        if TAGGED in kinds:
            parts.append(_union_alias(fk))
        if STRUCT in kinds or EMPTY in kinds:
            parts.append(_struct_cls(fk))
        if VARIANT in kinds:
            parts.append("MirrorVariant")
        if LIST in kinds:
            parts.append(f"list[{self.list_elem(fk)}]")
        out: list[str] = []
        for p in parts:
            if p not in out:
                out.append(p)
        return " | ".join(out) if out else "object"


def _field_line(names: _Names, grp: GroupSchema, fname: str) -> str:
    """One dataclass field line for JSON field ``fname`` of group ``grp``."""
    spec = grp.fields[fname]
    pyname = _py_field(fname)
    type_str = names.field_type(fname, spec.kinds)
    required = spec.seen == grp.count
    renamed = pyname != fname
    if required and not renamed:
        return f"    {pyname}: {type_str}"
    if required and renamed:
        return f'    {pyname}: {type_str} = field(metadata={{"json": "{fname}"}})'
    if renamed:
        return (
            f"    {pyname}: {type_str} = field("
            f'default=MISSING, metadata={{"json": "{fname}"}})'
        )
    return f"    {pyname}: {type_str} = MISSING"


def _emit_class(
    names: _Names, grp: GroupSchema, clsname: str, tag: str | None
) -> list[str]:
    """Emit the source lines for one frozen dataclass."""
    lines = [
        "@dataclass(frozen=True)",
        f"class {clsname}(TypedMirrorNode):",
    ]
    body: list[str] = []
    if tag is not None:
        body.append(f'    _tag: ClassVar[str | None] = "{tag}"')
    # Required fields first (no default), then optional (MISSING default), each
    # sorted by python attribute name for deterministic output.
    req: list[str] = []
    opt: list[str] = []
    for fname in sorted(grp.fields, key=_py_field):
        line = _field_line(names, grp, fname)
        (req if grp.fields[fname].seen == grp.count else opt).append(line)
    body.extend(req)
    body.extend(opt)
    if not body:
        body.append("    pass")
    lines.extend(body)
    lines.append("")
    lines.append("")
    return lines


def _emit_union_aliases(schema: MirrorSchema) -> list[str]:
    """One discriminated-union alias per tagged content_key."""
    by_ckey: dict[str, list[str]] = {}
    for ckey, tag in schema.tagged:
        by_ckey.setdefault(ckey, []).append(tag)
    lines = ["# --- discriminated-union aliases (one per tagged content_key) ---", ""]
    for ckey in sorted(by_ckey):
        tags = sorted(by_ckey[ckey])
        members = " | ".join(_tagged_cls(ckey, t) for t in tags)
        lines.append(f"type {_union_alias(ckey)} = {members}")
    lines.append("")
    return lines


def _emit_dispatch(schema: MirrorSchema) -> list[str]:
    lines = ["# --- dispatch tables (full schema coverage) ---", ""]
    lines.append("GENERATED_BY_KEY: dict[tuple[str, str], type[TypedMirrorNode]] = {")
    for ckey, tag in sorted(schema.tagged):
        lines.append(f"    ({ckey!r}, {tag!r}): {_tagged_cls(ckey, tag)},")
    lines.append("}")
    lines.append("")
    lines.append("GENERATED_BY_CKEY: dict[str, type[TypedMirrorNode]] = {")
    for ckey in sorted(schema.structs):
        lines.append(f"    {ckey!r}: {_struct_cls(ckey)},")
    lines.append("}")
    lines.append("")
    # JSON-key -> python-attr renames (keyword-clashing field names).
    renames = sorted(
        {
            fname
            for grp in list(schema.tagged.values()) + list(schema.structs.values())
            for fname in grp.fields
            if _py_field(fname) != fname
        }
    )
    lines.append("JSON_TO_PY: dict[str, str] = {")
    for fname in renames:
        lines.append(f"    {fname!r}: {_py_field(fname)!r},")
    lines.append("}")
    lines.append("")
    return lines


_HEADER = '''\
"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).
One frozen typed dataclass per distinct mirror shape — complete coverage, no
generic fallback — plus a discriminated-union alias per tagged content_key and
the two dispatch tables the strict loader builds typed instances from.

Class naming: ``S_<ckey>`` for a struct shape, ``T_<ckey>__<tag>`` for a tagged
shape, ``U_<ckey>`` for the union of all tagged shapes at one content_key. The
``<root>`` card record is :class:`S_Root`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

__all__ = [
    "GENERATED_BY_CKEY",
    "GENERATED_BY_KEY",
    "JSON_TO_PY",
]

'''


def _collision_check(schema: MirrorSchema) -> None:
    """Fail loud if sanitization collapses two shapes onto one class name."""
    seen: dict[str, str] = {}

    def claim(name: str, what: str) -> None:
        if name in seen and seen[name] != what:
            raise ValueError(
                f"codegen name collision: {name!r} for both {seen[name]!r} and {what!r}"
            )
        seen[name] = what

    for ckey, tag in schema.tagged:
        claim(_tagged_cls(ckey, tag), f"tagged({ckey},{tag})")
    for ckey in schema.structs:
        claim(_struct_cls(ckey), f"struct({ckey})")
    for ckey in {c for (c, _t) in schema.tagged}:
        claim(_union_alias(ckey), f"union({ckey})")


def generate_module(schema: MirrorSchema) -> str:
    """Render the full generated_types.py source from the schema."""
    _collision_check(schema)
    names = _Names(schema)
    out: list[str] = [_HEADER]

    # Struct shapes first, then tagged shapes (both name-sorted, deterministic).
    out.append("# --- struct shapes (untagged records, one per content_key) ---")
    out.append("")
    out.append("")
    for ckey in sorted(schema.structs):
        out.extend(_emit_class(names, schema.structs[ckey], _struct_cls(ckey), None))

    out.append("# --- tagged shapes (discriminated enum nodes) ---")
    out.append("")
    out.append("")
    for ckey, tag in sorted(schema.tagged):
        grp = schema.tagged[(ckey, tag)]
        out.extend(_emit_class(names, grp, _tagged_cls(ckey, tag), tag))

    out.extend(_emit_union_aliases(schema))
    out.append("")
    out.extend(_emit_dispatch(schema))

    return "\n".join(out).rstrip("\n") + "\n"


def generated_module_path() -> Path:
    """The committed generated module path (next to this codegen module)."""
    return Path(__file__).resolve().parent / "generated_types.py"


def emit_typed_codegen(schema: MirrorSchema, output_path: Path | None = None) -> Path:
    """Generate the typed-dataclass module and write it (ruff-format applied)."""
    path = output_path or generated_module_path()
    path.write_text(generate_module(schema), encoding="utf-8")
    _ruff_format(path)
    return path


def _ruff_format(path: Path) -> None:
    """Best-effort ``ruff format`` of the emitted file (no-op if ruff absent)."""
    import shutil
    import subprocess

    ruff = shutil.which("ruff")
    if ruff is None:
        return
    subprocess.run([ruff, "format", str(path)], check=False)
