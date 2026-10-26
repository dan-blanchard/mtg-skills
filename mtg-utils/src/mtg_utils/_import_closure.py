"""The ``mtg_utils`` import closure of a set of modules: every ``.py`` file their
``mtg_utils``-internal imports reach, module-level and lazy, found by parsing each
file (never importing it). A cache keyed by code hashes the closure's bytes: the
signals index (``_analysis.signals_index``) and the trees store
(``_card_ir.tree_store``). Neutral, so a low layer can key by it without its
closure taking in the signal path.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path


def _find_spec(modname: str):  # noqa: ANN202 — importlib's own private return shape
    try:
        return importlib.util.find_spec(modname)
    except (ModuleNotFoundError, ImportError, ValueError, AttributeError, TypeError):
        return None


def _module_file(modname: str) -> Path | None:
    """The ``.py`` file backing *modname*, without executing it (``find_spec``
    locates; it doesn't import)."""
    spec = _find_spec(modname)
    if spec is None or spec.origin is None:
        return None
    path = Path(spec.origin)
    return path if path.suffix == ".py" else None


def _parse_mtg_imports(source: bytes, filename: str) -> tuple[str, ...]:
    """Every ``mtg_utils...`` dotted module name *source* imports, found via a
    FULL ``ast.walk`` (module-level statements AND ones nested inside a
    function body — several signal-facing modules, e.g. ``theme_presets`` /
    ``_ir_lookup`` / ``engine``, import their heaviest dependency lazily to
    dodge an import cycle, so a top-level-only scan would silently miss
    them). ``from pkg import name`` is ambiguous between "import the
    submodule ``pkg.name``" and "import the symbol ``name`` from ``pkg``'s
    ``__init__``" — both ``pkg`` and ``pkg.name`` are added as candidates;
    :func:`_module_file` resolves whichever is real and the caller silently
    drops whichever isn't a module at all (e.g. a plain function/constant
    name). A pure function of the bytes (and the Python version parsing them),
    which is what lets :func:`_imported_mtg_modules` memoize it by content."""
    try:
        tree = ast.parse(source.decode("utf-8"), filename=filename)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return ()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("mtg_utils"):
                    names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and (
            node.module and node.module.startswith("mtg_utils")
        ):
            names.add(node.module)
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return tuple(sorted(names))


# ── The import read's memo: content-addressed, in-process and on disk ───────
#
# Parsing the closure's ~100 modules is most of what keying a code-keyed cache
# costs (about 0.3 s a walk; a tune walks for the signals index, the provenance,
# job-read and card-read sidecars and the trees store). The parse is a pure
# function of a file's bytes, so its memo is keyed by the sha256 of those bytes:
# a cached answer is exactly what a fresh parse would return, with no mtime
# trusted anywhere. The walk itself (and every ``find_spec`` resolution in it)
# still runs on every call, so a new import edge, a new module file or a deleted
# one is seen at once.

_IMPORTS_CACHE_VERSION = 1
_IMPORTS_CACHE_PREFIX = "signals-imports"  # its name before the walk moved here
#: sha256(file bytes) -> the ``mtg_utils`` names that file imports. Filled from
#: the on-disk cache on first use (:data:`_IMPORTS_LOADED`), then by each parse.
_IMPORTS_BY_DIGEST: dict[str, tuple[str, ...]] = {}
_IMPORTS_LOADED: list[bool] = [False]


def _imports_cache_path() -> Path:
    """The persisted memo, one per package checkout (so worktrees don't prune each
    other's entries) and Python version (the parser that produced it)."""
    return sha_keyed_path(
        _IMPORTS_CACHE_PREFIX,
        str(Path(__file__).resolve().parent),
        f"py{sys.version_info[0]}.{sys.version_info[1]}",
        _IMPORTS_CACHE_VERSION,
    )


def _imports_memo() -> dict[str, tuple[str, ...]]:
    if not _IMPORTS_LOADED[0]:
        _IMPORTS_LOADED[0] = True
        with contextlib.suppress(OSError, ValueError):
            payload = json.loads(_imports_cache_path().read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("version") == _IMPORTS_CACHE_VERSION
                and isinstance(payload.get("imports"), dict)
            ):
                _IMPORTS_BY_DIGEST.update(
                    (digest, tuple(names))
                    for digest, names in payload["imports"].items()
                    if isinstance(names, list)
                )
    return _IMPORTS_BY_DIGEST


def _imported_mtg_modules(path: Path) -> tuple[str, tuple[str, ...]] | None:
    """*path*'s content digest and the ``mtg_utils`` names it imports
    (:func:`_parse_mtg_imports`), parsed only when no memo holds those exact
    bytes; ``None`` when the file can't be read."""
    try:
        source = path.read_bytes()
    except OSError:
        return None
    digest = hashlib.sha256(source).hexdigest()
    memo = _imports_memo()
    names = memo.get(digest)
    if names is None:
        names = memo[digest] = _parse_mtg_imports(source, str(path))
    return digest, names


def source_files(*roots: str, persist: bool = False) -> tuple[Path, ...]:
    """Every ``.py`` file transitively reachable from ``roots`` by
    ``mtg_utils``-internal imports, module-level and lazy: the walk
    ``signals_index.signal_source_files`` runs from the signal path's roots,
    recomputed every call so a new import edge or module is seen at once. Only
    each file's import read is memoized, by the sha256 of its bytes. ``persist``
    writes the walk's import reads to the on-disk memo, which only a walk over
    the signal path's whole closure may do: a narrower one (the trees store's
    key, ``_card_ir.tree_store``) would drop the reads it never needed."""
    known = set(_imports_memo())
    seen: set[str] = set()
    queue: list[str] = list(roots)
    files: set[Path] = set()
    used: dict[str, tuple[str, ...]] = {}
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = _module_file(name)
        if path is None:
            continue
        files.add(path)
        read = _imported_mtg_modules(path)
        if read is None:
            continue
        digest, deps = read
        used[digest] = deps
        for dep in deps:
            if dep not in seen:
                queue.append(dep)
    if persist and not used.keys() <= known:
        # Persist this walk's reads — only these, so edited files' old entries
        # drop out. Best-effort: a failed write just means the next process parses.
        with contextlib.suppress(OSError):
            atomic_write_json(
                _imports_cache_path(),
                {
                    "version": _IMPORTS_CACHE_VERSION,
                    "imports": {d: list(n) for d, n in sorted(used.items())},
                },
            )
    return tuple(sorted(files))


def hash_files(
    hasher: hashlib._Hash, files: Iterable[Path], *, relative_to: Path | None = None
) -> None:
    """Fold each file's name (relative to ``relative_to`` when given) and bytes into
    ``hasher``: the code identity of a cache keyed by a closure's source
    (:func:`source_files`). A file that vanished mid-walk adds its name alone."""
    for path in files:
        name = path.resolve().relative_to(relative_to) if relative_to else path
        hasher.update(str(name).encode())
        with contextlib.suppress(OSError):
            hasher.update(path.read_bytes())
