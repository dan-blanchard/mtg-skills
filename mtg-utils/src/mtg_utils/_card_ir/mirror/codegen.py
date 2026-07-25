"""Full typed-class codegen for the phase-mirror substrate (ADR-0035, Stage 2).

Reads the inferred :class:`MirrorSchema` and emits a committed Python
**package** of frozen typed dataclasses — **one per distinct shape, complete
coverage**: a class for every ``(content_key, tag)`` tagged shape and every
``content_key`` struct shape the schema describes, plus a discriminated-union
type alias per tagged ``content_key`` and the two dispatch tables the loader
builds typed instances from. NO real card shape falls back to a generic
interpreted node.

This is a gated dev step (never CI), like the schema JSON it consumes; the
COMMITTED ``generated/`` package is what consumers import. Regenerate it with
``build-card-ir-substrate`` (or :func:`emit_typed_codegen` directly) whenever
the committed schema changes.

The emitted field *types* are advisory for static consumers (the loader's
losslessness is value-kind driven, not type driven); they are derived from the
schema by the rule "the child of a field recurses at ``content_key == field
name``", so a ``tagged`` field at name ``effect`` is typed as the union of
every ``effect`` tagged class, a ``struct`` field at name ``filter`` as the
``filter`` struct class, and so on.

**Package layout** (task: split the single 15k-line monolith): every class is
named ``S_<ckey>`` / ``T_<ckey>__<tag>`` / ``U_<ckey>`` exactly as before, but
the *definitions* are spread across ``generated/gNN_<slug>.py`` modules, one
per **content-key group** — a contiguous, alphabetically-ordered run of content
keys, sized by a greedy line-count bin-pack (:func:`_group_ckeys`) so a normal
schema lands ~10-30 modules of a few hundred to ~1500 lines rather than 1,743
one-class files. A content key's struct shape and ALL of its tagged shapes
always land in the same module (a discriminated-union alias needs its member
classes in scope), so the "prefix" a module covers is exactly the ckey range
named in its filename. Cross-module field-type references are resolved under
``TYPE_CHECKING`` (never executed) rather than real top-level imports, because
the schema's field graph is not a DAG — two ckeys can each reference the
other's content key — and a real import would risk a circular-import failure;
annotations are never evaluated at runtime (``from __future__ import
annotations``), so this costs nothing. ``generated/_dispatch.py`` holds the
two real (non-lazy) dispatch tables the loader reads, importing the concrete
classes for real since it needs live class objects as dict values.
``generated/__init__.py`` re-exports every symbol from every module (plus the
dispatch tables) so ``from mtg_utils._card_ir.mirror.generated import X``
behaves exactly like the single-file import it replaces.
"""

from __future__ import annotations

import keyword
import re
import textwrap
from dataclasses import dataclass
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

# Greedy line-count bin-pack targets for content-key-group modules (see the
# module docstring). Not a hard cap: a single oversized content key (e.g. the
# ~1.5k-line "effect" ckey, which alone has 200+ tagged variants) still gets
# its own module rather than being split — splitting it would separate a
# discriminated-union alias from its member classes. Empirically (v0.35.2
# schema) this yields ~14 modules ranging ~550-1560 lines.
_TARGET_MODULE_LINES = 800
_MIN_MODULE_LINES = 300

_GENERATED_PKG = "mtg_utils._card_ir.mirror.generated"


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


def _module_slug(ckey: str) -> str:
    """A lowercase, filename-safe fragment identifying *ckey* in a module name."""
    base = "root" if ckey == ROOT else ckey
    slug = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").lower()
    # Capped so `from mtg_utils._card_ir.mirror.generated.gNN_<slug> import (`
    # stays under the line-length limit even at the deepest (4-space TYPE_
    # CHECKING-block) indent — see the codegen's own E501 self-check.
    return (slug or "x")[:20]


def _module_basename(index: int, first_ckey: str) -> str:
    """The importable module name (no ``.py``) for group *index*, 1-based."""
    return f"g{index:02d}_{_module_slug(first_ckey)}"


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


# ---------------------------------------------------------------------------
# content-key grouping (one module per group; see module docstring)
# ---------------------------------------------------------------------------


@dataclass
class _Group:
    basename: str
    ckeys: list[str]
    local_names: list[str]  # every S_/T_/U_ name this group's module defines


def _tags_by_ckey(schema: MirrorSchema) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for ckey, tag in schema.tagged:
        out.setdefault(ckey, []).append(tag)
    return out


def _all_class_lines(
    schema: MirrorSchema, names: _Names
) -> dict[tuple[str, str | None], list[str]]:
    """Every emitted class's source lines, keyed by ``(ckey, tag)`` (``tag`` is
    ``None`` for the struct shape) — computed exactly once and reused for both
    the line-count bin-pack and the final per-module render, so costing and
    rendering can never drift apart."""
    out: dict[tuple[str, str | None], list[str]] = {}
    for ckey, grp in schema.structs.items():
        out[(ckey, None)] = _emit_class(names, grp, _struct_cls(ckey), None)
    for (ckey, tag), grp in schema.tagged.items():
        out[(ckey, tag)] = _emit_class(names, grp, _tagged_cls(ckey, tag), tag)
    return out


def _group_ckeys(
    all_ckeys: list[str],
    tags_by_ckey: dict[str, list[str]],
    class_lines: dict[tuple[str, str | None], list[str]],
) -> list[list[str]]:
    """Greedily bin-pack *all_ckeys* (already alpha-sorted) into contiguous
    runs targeting ``_TARGET_MODULE_LINES`` lines, never closing a run below
    ``_MIN_MODULE_LINES`` (so a run of small ckeys keeps absorbing neighbors
    until it's substantial) and never splitting a single ckey's struct+tagged
    classes across two runs."""

    def cost(ckey: str) -> int:
        c = len(class_lines.get((ckey, None), ()))
        for tag in tags_by_ckey.get(ckey, ()):
            c += len(class_lines[(ckey, tag)])
        return c

    groups: list[list[str]] = []
    cur: list[str] = []
    cur_cost = 0
    for ckey in all_ckeys:
        c = cost(ckey)
        if (
            cur
            and cur_cost >= _MIN_MODULE_LINES
            and cur_cost + c > _TARGET_MODULE_LINES
        ):
            groups.append(cur)
            cur = []
            cur_cost = 0
        cur.append(ckey)
        cur_cost += c
    if cur:
        groups.append(cur)
    # A trailing run smaller than the floor (schema-dependent, not guaranteed
    # by the loop above since there's no "next" ckey to trigger a flush) folds
    # into its predecessor rather than shipping as its own tiny module.
    if len(groups) > 1 and sum(cost(k) for k in groups[-1]) < _MIN_MODULE_LINES:
        groups[-2].extend(groups.pop())
    return groups


def _build_groups(
    schema: MirrorSchema, names: _Names
) -> tuple[
    list[_Group],
    dict[tuple[str, str | None], list[str]],
    dict[str, list[str]],
    dict[str, str],
]:
    """Partition the schema into modules; return the groups plus the shared
    lookups needed to render them (class-source cache, ckey->tags, and the
    global name -> owning-module registry used for cross-module refs)."""
    tags_by_ckey = _tags_by_ckey(schema)
    class_lines = _all_class_lines(schema, names)
    all_ckeys = sorted(set(schema.structs) | set(tags_by_ckey))
    ckey_groups = _group_ckeys(all_ckeys, tags_by_ckey, class_lines)

    groups: list[_Group] = []
    name_to_module: dict[str, str] = {}
    for i, ckeys in enumerate(ckey_groups, start=1):
        basename = _module_basename(i, ckeys[0])
        local_names: list[str] = []
        for ckey in ckeys:
            if ckey in schema.structs:
                local_names.append(_struct_cls(ckey))
            tags = tags_by_ckey.get(ckey)
            if tags:
                local_names.append(_union_alias(ckey))
                local_names.extend(_tagged_cls(ckey, t) for t in sorted(tags))
        for name in local_names:
            name_to_module[name] = basename
        groups.append(_Group(basename=basename, ckeys=ckeys, local_names=local_names))
    return groups, class_lines, tags_by_ckey, name_to_module


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

_GENERATOR_LINE = (
    "Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by\n"
    "``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``)."
)

_NAMING_NOTE = (
    "Class naming: ``S_<ckey>`` for a struct shape, ``T_<ckey>__<tag>`` for a\n"
    "tagged shape, ``U_<ckey>`` for the union of all tagged shapes at one\n"
    "content_key."
)

_NAME_RE = re.compile(r"\b(?:S_|T_|U_)[A-Za-z0-9_]+")


def _external_refs(
    type_strs: list[str],
    local_names: set[str],
    name_to_module: dict[str, str],
    own_basename: str,
) -> dict[str, list[str]]:
    """module -> sorted class/alias names *type_strs* reference outside this
    group. Scoped to the rendered field-type strings only (never docstrings or
    string-literal JSON keys), so there is no risk of a stray string literal
    masquerading as a cross-module reference."""
    by_module: dict[str, set[str]] = {}
    for type_str in type_strs:
        for m in _NAME_RE.finditer(type_str):
            name = m.group(0)
            if name in local_names:
                continue
            mod = name_to_module.get(name)
            if mod is None or mod == own_basename:
                continue
            by_module.setdefault(mod, set()).add(name)
    return {mod: sorted(names) for mod, names in sorted(by_module.items())}


def _field_type_strs(names: _Names, grp: GroupSchema) -> list[str]:
    return [names.field_type(fname, spec.kinds) for fname, spec in grp.fields.items()]


def _module_docstring(extra: list[str], *, wrap: bool = False) -> str:
    lines = ['"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).', ""]
    lines.append(_GENERATOR_LINE)
    lines.append("")
    if wrap:
        for line in extra:
            lines.extend(textwrap.wrap(line, width=79) if line else [""])
    else:
        lines.extend(extra)
    lines.append('"""')
    return "\n".join(lines)


def _render_group_module(
    schema: MirrorSchema,
    names: _Names,
    group: _Group,
    class_lines: dict[tuple[str, str | None], list[str]],
    tags_by_ckey: dict[str, list[str]],
    name_to_module: dict[str, str],
) -> str:
    ckeys = group.ckeys
    struct_ckeys = [c for c in ckeys if c in schema.structs]
    tagged_ckeys = [c for c in ckeys if tags_by_ckey.get(c)]
    local_names = set(group.local_names)

    body: list[str] = []
    type_strs: list[str] = []

    if struct_ckeys:
        body.append("# --- struct shapes (untagged records, one per content_key) ---")
        body.append("")
        body.append("")
        for ckey in struct_ckeys:
            body.extend(class_lines[(ckey, None)])
            type_strs.extend(_field_type_strs(names, schema.structs[ckey]))

    if tagged_ckeys:
        body.append("# --- tagged shapes (discriminated enum nodes) ---")
        body.append("")
        body.append("")
        for ckey in tagged_ckeys:
            for tag in sorted(tags_by_ckey[ckey]):
                body.extend(class_lines[(ckey, tag)])
                type_strs.extend(_field_type_strs(names, schema.tagged[(ckey, tag)]))

        body.append(
            "# --- discriminated-union aliases (one per tagged content_key) ---"
        )
        body.append("")
        for ckey in tagged_ckeys:
            tags = sorted(tags_by_ckey[ckey])
            member_names = [_tagged_cls(ckey, t) for t in tags]
            alias = _union_alias(ckey)
            one_liner = f"type {alias} = {' | '.join(member_names)}"
            if len(one_liner) <= 88:
                body.append(one_liner)
            else:
                # ruff format doesn't auto-wrap a PEP 695 ``type`` statement's
                # RHS the way it splits dict/call literals, so a union with
                # enough members to blow the line limit needs manual wrapping.
                body.append(f"type {alias} = (")
                body.append(f"    {member_names[0]}")
                for n in member_names[1:]:
                    body.append(f"    | {n}")
                body.append(")")
        body.append("")

    external = _external_refs(type_strs, local_names, name_to_module, group.basename)

    if len(ckeys) == 1:
        scope = f"content key ``{ckeys[0]}``."
    else:
        scope = f"content keys ``{ckeys[0]}`` .. ``{ckeys[-1]}`` ({len(ckeys)} keys)."
    header = _module_docstring(
        [
            "Part of the generated typed-mirror package (see this directory's",
            "``__init__.py``). This module holds " + scope,
            "",
            _NAMING_NOTE,
        ],
        wrap=True,
    )

    out: list[str] = [header, "", "from __future__ import annotations", ""]
    out.append("from dataclasses import dataclass, field")
    out.append("from typing import TYPE_CHECKING, ClassVar")
    out.append("")
    out.append("from mtg_utils._card_ir.mirror.runtime import (")
    out.append("    MISSING,")
    out.append("    MirrorVariant,")
    out.append("    TypedMirrorNode,")
    out.append(")")
    if external:
        out.append("")
        out.append("if TYPE_CHECKING:")
        for mod, mod_names in external.items():
            out.append(f"    from {_GENERATED_PKG}.{mod} import (")
            for n in mod_names:
                out.append(f"        {n},")
            out.append("    )")
    out.append("")
    out.append("")
    out.extend(body)
    return "\n".join(out).rstrip("\n") + "\n"


def _render_dispatch_module(
    schema: MirrorSchema, name_to_module: dict[str, str]
) -> str:
    by_module: dict[str, list[str]] = {}
    for ckey, tag in sorted(schema.tagged):
        cls = _tagged_cls(ckey, tag)
        by_module.setdefault(name_to_module[cls], []).append(cls)
    for ckey in sorted(schema.structs):
        cls = _struct_cls(ckey)
        by_module.setdefault(name_to_module[cls], []).append(cls)

    header = _module_docstring(
        [
            "The two dispatch tables (``(content_key, tag) -> class`` and",
            "``content_key -> class``) plus the JSON-field-name -> python-attr",
            "rename table, over every class defined across this package's",
            "content-key-group modules. Real (non-lazy) imports throughout: this",
            "module needs live class objects as dict values, not just annotation",
            "strings, and it only ever imports *from* the leaf group modules (never",
            "the reverse), so there is no circular-import risk.",
        ]
    )

    out: list[str] = [header, "", "from __future__ import annotations", ""]
    for mod in sorted(by_module):
        out.append(f"from {_GENERATED_PKG}.{mod} import (")
        for n in sorted(set(by_module[mod])):
            out.append(f"    {n},")
        out.append(")")
    out.append("")
    out.append("from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode")
    out.append("")
    out.append("__all__ = [")
    out.append('    "GENERATED_BY_CKEY",')
    out.append('    "GENERATED_BY_KEY",')
    out.append('    "JSON_TO_PY",')
    out.append("]")
    out.append("")
    out.append("")
    out.append("# --- dispatch tables (full schema coverage) ---")
    out.append("")
    out.append("GENERATED_BY_KEY: dict[tuple[str, str], type[TypedMirrorNode]] = {")
    for ckey, tag in sorted(schema.tagged):
        out.append(f"    ({ckey!r}, {tag!r}): {_tagged_cls(ckey, tag)},")
    out.append("}")
    out.append("")
    out.append("GENERATED_BY_CKEY: dict[str, type[TypedMirrorNode]] = {")
    for ckey in sorted(schema.structs):
        out.append(f"    {ckey!r}: {_struct_cls(ckey)},")
    out.append("}")
    out.append("")
    renames = sorted(
        {
            fname
            for grp in list(schema.tagged.values()) + list(schema.structs.values())
            for fname in grp.fields
            if _py_field(fname) != fname
        }
    )
    out.append("JSON_TO_PY: dict[str, str] = {")
    for fname in renames:
        out.append(f"    {fname!r}: {_py_field(fname)!r},")
    out.append("}")
    return "\n".join(out).rstrip("\n") + "\n"


def _render_init_module(groups: list[_Group]) -> str:
    header = _module_docstring(
        [
            "Aggregates the content-key-group modules (``gNN_<slug>.py``) plus the",
            "dispatch tables (``_dispatch.py``) into one flat namespace, so",
            "``from mtg_utils._card_ir.mirror.generated import X`` behaves exactly",
            "like it did against the single-file ``generated_types.py`` this",
            "package replaced.",
            "",
            _NAMING_NOTE,
            "The ``<root>`` card record is :class:`S_Root`.",
        ]
    )

    out: list[str] = [header, "", "from __future__ import annotations", ""]
    out.append(f"from {_GENERATED_PKG}._dispatch import (")
    out.append("    GENERATED_BY_CKEY,")
    out.append("    GENERATED_BY_KEY,")
    out.append("    JSON_TO_PY,")
    out.append(")")
    all_names = ["GENERATED_BY_CKEY", "GENERATED_BY_KEY", "JSON_TO_PY"]
    for group in groups:
        out.append(f"from {_GENERATED_PKG}.{group.basename} import (")
        for n in sorted(group.local_names):
            out.append(f"    {n},")
        out.append(")")
        all_names.extend(group.local_names)
    out.append("")
    out.append("__all__ = [")
    for n in sorted(all_names):
        out.append(f'    "{n}",')
    out.append("]")
    return "\n".join(out).rstrip("\n") + "\n"


def generate_modules(schema: MirrorSchema) -> dict[str, str]:
    """Render every file of the ``generated/`` package: ``{filename: source}``."""
    _collision_check(schema)
    names = _Names(schema)
    groups, class_lines, tags_by_ckey, name_to_module = _build_groups(schema, names)

    out: dict[str, str] = {}
    for group in groups:
        out[f"{group.basename}.py"] = _render_group_module(
            schema, names, group, class_lines, tags_by_ckey, name_to_module
        )
    out["_dispatch.py"] = _render_dispatch_module(schema, name_to_module)
    out["__init__.py"] = _render_init_module(groups)
    return out


def generated_package_dir() -> Path:
    """The committed generated package dir (next to this codegen module)."""
    return Path(__file__).resolve().parent / "generated"


def emit_typed_codegen(schema: MirrorSchema, output_dir: Path | None = None) -> Path:
    """Generate the typed-dataclass package and write it (ruff-formatted).

    Wipes every existing ``*.py`` file in *output_dir* first: the number and
    boundaries of content-key-group modules are schema-dependent (a phase bump
    can shift them), so a stale file from a previous shape must never survive
    a regeneration — that's exactly what the "second run produces zero diff"
    determinism check would otherwise fail to catch.
    """
    out_dir = output_dir or generated_package_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.py"):
        stale.unlink()
    for filename, source in generate_modules(schema).items():
        (out_dir / filename).write_text(source, encoding="utf-8")
    _ruff_postprocess(out_dir)
    return out_dir


def _ruff_postprocess(path: Path) -> None:
    """Best-effort ``ruff check --fix`` + ``ruff format`` (no-op if ruff absent).

    ``check --fix`` resolves import ordering (I001) deterministically given a
    fixed ruff version and fixed input; ``format`` then normalizes whitespace,
    matching the single-file monolith's previous best-effort formatting pass.
    """
    import shutil
    import subprocess

    ruff = shutil.which("ruff")
    if ruff is None:
        return
    # capture_output: `check --fix` reports (to stdout) any diagnostic it can't
    # itself fix — e.g. E501 on a dict entry `format` will still wrap below —
    # so surfacing it here would print a scary false alarm on every clean run.
    subprocess.run(
        [ruff, "check", "--fix", "--quiet", str(path)], check=False, capture_output=True
    )
    subprocess.run(
        [ruff, "format", "--quiet", str(path)], check=False, capture_output=True
    )
