"""oracle_id -> signal-ident sidecar over the FULL bulk pool (task #90).

``extract_signals_hybrid`` (``signals.py``) is deterministic per card — its
output depends only on the card's own record + the source code of the
crosswalk lane stack, never on process state. That means every fresh CLI /
server process re-pays the same ~2-4 minute whole-pool pass the moment a
consumer scans the entire bulk (``card_search`` with a ``--preset`` filter,
deck-forge's commander-discovery novelty sweep, a cube's balance/archetype
audit). This module persists ``oracle_id -> sorted tuple of "key|scope|
subject" idents`` ONE TIME per (bulk, signal-source-code) pair so every
later load is a pickle deserialize, not a crosswalk re-run.

Sidecar lives at ``<bulk_path>.signals.pkl`` — same physical-placement
convention as ``_mtgjson.rulings_index`` (``<AllPrintings.json>.rulings.pkl``),
which is the freshest precedent this module mirrors: its own atomic
tmp-file-then-rename write, its own inline version-tagged read/write pair
(rather than routing through ``_sidecar.py``'s ``$TMPDIR``-keyed JSON
helpers, which back a different family of caches — the tuner's per-query
scratch dumps and ``engine``'s lane-density sweep — not a card-data sidecar
that lives beside the bulk file itself).

# Invalidation (the load-bearing part)

A hand-bumped version constant is NOT the invalidation key (the
``creature_recursion`` v0.20 lesson: a cache nobody's version gate watched
kept serving stale output past a lane fix). Instead every load computes a
content hash over:

  * every ``.py`` file transitively reachable from
    ``mtg_utils._deck_forge.signals`` by following ``mtg_utils``-internal
    imports — module-level AND lazy (inside a function body) — via
    :func:`signal_source_files`. This is a live AST walk, not a
    hand-maintained list: adding a new lane helper, threading a new
    corrections pass, or editing any file already in the graph changes the
    hash on its own, with no second place to remember to update.
  * ``_phase.PHASE_TAG`` (a phase-rs bump changes the Card IR the crosswalk
    reads even when no ``mtg_utils`` file changes).
  * ``SIGNALS_SIDECAR_VERSION`` (bumped only for an on-disk payload SHAPE
    change, e.g. adding a new field to the stored record — never used as a
    substitute for the content hash above).

A payload whose stored hash doesn't match a freshly-computed one, or whose
bulk-file identity (path + mtime_ns + size) doesn't match the current bulk
file, is treated as absent — silently rebuilt, never served stale.

# Configuration (the trap)

``extract_signals_hybrid`` takes ``vocab`` / ``include_membership`` /
``resolve_object`` knobs; a sidecar entry is only valid for the SAME
effective config a caller runs live. Every whole-pool production call site
(``theme_presets._signal_keys_for``, ``engine._signal_freq``) calls it at
its DEFAULTS (``vocab=CREATURE_SUBTYPES``, ``include_membership=True``,
``resolve_object=None`` — the latter is accepted-but-unused by the
crosswalk path regardless, per ``extract_signals_hybrid``'s own docstring,
so it never causes divergence). :func:`build_signals_index` calls it at
those same defaults, so this is the ONE config the sidecar is valid for.
The one production call site that passes ``include_membership=False``
(``engine._commander_lanes``, scoped to a single owned commander at a
time — never a pool scan) stays on live compute; it is cheap at that
scale and wiring it would require storing a second, differently-configured
index for no measured benefit.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import pickle
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtg_utils._deck_forge.signals import Signal

SIGNALS_SIDECAR_VERSION = 1
_SIGNALS_SIDECAR_SUFFIX = ".signals.pkl"

# oracle_id -> sorted tuple of "key|scope|subject" idents (empty tuple for a
# card with zero signals — a real, cacheable answer, not "unknown").
SignalsIndex = dict[str, tuple[str, ...]]

_ROOT_MODULE = "mtg_utils._deck_forge.signals"


def _sidecar_path(bulk_path: Path) -> Path:
    return bulk_path.with_name(bulk_path.name + _SIGNALS_SIDECAR_SUFFIX)


def _ident(sig: Signal) -> str:
    """``Signal(key, scope, subject, ...)`` -> its ``"key|scope|subject"`` id,
    the same identity tuple every producer/consumer dedups signals by."""
    return f"{sig.key}|{sig.scope}|{sig.subject}"


def build_signals_index(records: Iterable[dict]) -> SignalsIndex:
    """oracle_id -> sorted idents, over EVERY record carrying an ``oracle_id``.

    One entry per distinct ``oracle_id`` — the first record seen wins; later
    printings of the same card share the oracle_id and produce byte-identical
    signals (their oracle text / type line / keywords are the same card), so
    which printing gets processed never changes the stored result. Calls
    ``extract_signals_hybrid`` at its DEFAULTS (see the module docstring's
    "Configuration" section) — the ONE config every wired consumer relies on.

    Public + importable so a corpus-verification harness can build the exact
    same artifact this module persists, over any record list it likes."""
    from mtg_utils._deck_forge.signals import extract_signals_hybrid

    index: SignalsIndex = {}
    for rec in records:
        oid = rec.get("oracle_id")
        if not oid or oid in index:
            continue
        sigs = extract_signals_hybrid(rec)
        index[oid] = tuple(sorted(_ident(s) for s in sigs))
    return index


# ── Version gate: an AST-audited import closure, not a hand-kept list ───────


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


def _imported_mtg_modules(path: Path) -> set[str]:
    """Every ``mtg_utils...`` dotted module name *path* imports, found via a
    FULL ``ast.walk`` (module-level statements AND ones nested inside a
    function body — several signal-facing modules, e.g. ``theme_presets`` /
    ``_ir_lookup`` / ``engine``, import their heaviest dependency lazily to
    dodge an import cycle, so a top-level-only scan would silently miss
    them). ``from pkg import name`` is ambiguous between "import the
    submodule ``pkg.name``" and "import the symbol ``name`` from ``pkg``'s
    ``__init__``" — both ``pkg`` and ``pkg.name`` are added as candidates;
    :func:`_module_file` resolves whichever is real and the caller silently
    drops whichever isn't a module at all (e.g. a plain function/constant
    name)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
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
    return names


def signal_source_files() -> tuple[Path, ...]:
    """Every ``.py`` file transitively reachable from ``_deck_forge.signals``
    by following ``mtg_utils``-internal imports (module-level + lazy) — the
    exact file set whose content can change ``extract_signals_hybrid``'s
    output. Recomputed via a fresh AST walk every call (never a cached/
    hand-written list), so a newly-added lane module or corrections pass is
    picked up automatically the next time this runs — the "audit the actual
    import graph" the sidecar's invalidation depends on. Deliberately
    conservative: a module reachable here but NOT actually read by
    ``extract_signals_hybrid`` at runtime (e.g. ``theme_presets``, pulled in
    because ``_signals_regex`` imports ``get_preset`` for its now-dead
    ``producible_static_keys`` probe) still counts — over-invalidating on an
    unrelated edit costs one wasted rebuild; under-invalidating serves stale
    signals silently, which is the one failure mode this sidecar must never
    have."""
    seen: set[str] = set()
    queue: list[str] = [_ROOT_MODULE]
    files: set[Path] = set()
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = _module_file(name)
        if path is None:
            continue
        files.add(path)
        for dep in _imported_mtg_modules(path):
            if dep not in seen:
                queue.append(dep)
    return tuple(sorted(files))


def _content_hash() -> str:
    """SHA-256 over every signal-source file's bytes + ``PHASE_TAG`` +
    ``SIGNALS_SIDECAR_VERSION`` — the sidecar's actual version key. ANY byte
    change anywhere in the reachable source graph, a phase-rs bump, or a
    sidecar-shape bump changes this hash and silently invalidates every
    existing sidecar on its next load."""
    from mtg_utils import _phase

    hasher = hashlib.sha256()
    for path in signal_source_files():
        hasher.update(str(path).encode())
        with contextlib.suppress(OSError):
            hasher.update(path.read_bytes())
    hasher.update(f"|phase_tag:{_phase.PHASE_TAG}".encode())
    hasher.update(f"|sidecar_version:{SIGNALS_SIDECAR_VERSION}".encode())
    return hasher.hexdigest()


def _bulk_identity(bulk_path: Path) -> tuple[str, int, int]:
    st = bulk_path.stat()
    return (str(bulk_path), st.st_mtime_ns, st.st_size)


def _read_sidecar(
    sidecar: Path, bulk_path: Path, content_hash: str
) -> SignalsIndex | None:
    if not sidecar.exists():
        return None
    try:
        with sidecar.open("rb") as f:
            payload = pickle.load(f)
    except (pickle.PickleError, EOFError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != SIGNALS_SIDECAR_VERSION:
        return None
    if payload.get("content_hash") != content_hash:
        return None
    if payload.get("bulk_identity") != _bulk_identity(bulk_path):
        return None
    index = payload.get("index")
    if not isinstance(index, dict):
        return None
    return index


def _write_sidecar(
    sidecar: Path, index: SignalsIndex, content_hash: str, bulk_path: Path
) -> None:
    """Best-effort atomic write; a failure just means the next call rebuilds."""
    payload = {
        "version": SIGNALS_SIDECAR_VERSION,
        "content_hash": content_hash,
        "bulk_identity": _bulk_identity(bulk_path),
        "index": index,
    }
    tmp = sidecar.with_name(sidecar.name + ".tmp")
    try:
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(sidecar)
    except OSError:
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()


def load_signals_index(
    bulk_path: Path | None, records: list[dict] | None = None
) -> SignalsIndex | None:
    """Return the oracle_id -> signal-ident index for *bulk_path*.

    ``None`` means "nothing to serve" — no bulk path, or the file isn't
    present — the caller's existing no-sidecar behavior (per-card live
    compute) is the correct, graceful fallback; this function never raises
    to force a consumer onto the sidecar.

    Builds the sidecar on first touch (a one-time whole-pool
    ``extract_signals_hybrid`` pass — ~2-4 min over the full bulk — logged to
    stderr so a caller mid-request isn't left wondering why it's slow) and
    persists it; every subsequent call for the same bulk + source code is a
    pickle deserialize. Pass *records* when the caller already holds the
    loaded bulk list (``bulk_loader.load_bulk_cards`` is itself cached, so
    omitting it just adds one cheap cache hit, never a re-parse)."""
    if bulk_path is None:
        return None
    bulk_path = Path(bulk_path)
    if not bulk_path.is_file():
        return None

    content_hash = _content_hash()
    sidecar = _sidecar_path(bulk_path)
    cached = _read_sidecar(sidecar, bulk_path, content_hash)
    if cached is not None:
        return cached

    if records is None:
        from mtg_utils.bulk_loader import load_bulk_cards

        records = load_bulk_cards(bulk_path)

    print(
        f"mtg-utils: building signals index over {len(records)} cards "
        f"(one-time ~2-4 min pass; cached at {sidecar})...",
        file=sys.stderr,
    )
    index = build_signals_index(records)
    _write_sidecar(sidecar, index, content_hash, bulk_path)
    return index
