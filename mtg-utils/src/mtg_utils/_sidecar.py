"""Shared helpers for scripts that write a sha-keyed JSON sidecar file.

Every script in the tuner that emits a human-readable text report to stdout
also always writes its full structured JSON to a deterministic path so that
downstream scripts and Step 7 self-grill subagents can `Read` it selectively
instead of receiving pasted content. This module centralizes the path
computation and the atomic-write pattern so all scripts stay consistent
and so adding a new filter argument to a script's cache key is a one-line
change.

``sha_keyed_path`` computes ``$TMPDIR/{prefix}-{sha16}.json`` where ``sha16``
is a SHA-256 of the supplied parts truncated to 16 hex chars. Parts are
treated as follows:

* ``Path`` that exists → hashed as ``path:{mtime_ns}:{size}`` so large files
  (e.g. the ~500MB Scryfall bulk JSON) don't need to be content-hashed on
  every call. An absent path hashes to a sentinel so deleting the file
  busts the cache.
* ``bytes`` / ``bytearray`` → hashed by content.
* Anything else → ``str(part)`` hashed by content. This handles strings,
  numbers, ``None``, booleans, tuples of primitives, etc.

``atomic_write_json`` writes to a temporary file alongside the destination
and renames, so a reader that observes the destination file always sees
fully-formed JSON even if a concurrent writer crashes mid-write.

``load_pickle_sidecar`` / ``write_pickle_sidecar`` are the pickled-cache
counterpart: a parsed/derived value that's expensive to rebuild (a parsed
bulk-data list, a parsed Comprehensive Rules doc) gets cached next to its
source file, keyed on mtime + a version tag, with atomic-rename writes.
``bulk_loader`` and ``rules_lookup`` are the two callers; both hand-rolled
this before it was extracted, so the staleness/version/atomic-write rules
here are exactly what those two already did — this only removes the
duplication, it doesn't change either one's on-disk format or invalidation
behavior.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def _hash_part(hasher: hashlib._Hash, part: object) -> None:
    """Feed a single part into the running hasher with a typed separator."""
    if isinstance(part, Path):
        try:
            stat = part.stat()
        except OSError:
            hasher.update(f"|path-missing:{part}".encode())
            return
        hasher.update(f"|path:{stat.st_mtime_ns}:{stat.st_size}".encode())
    elif isinstance(part, (bytes, bytearray)):
        hasher.update(b"|bytes:")
        hasher.update(bytes(part))
    elif isinstance(part, (list, tuple)):
        hasher.update(b"|seq:[")
        for sub in part:
            _hash_part(hasher, sub)
        hasher.update(b"]")
    else:
        hasher.update(f"|{part}".encode())


def sha_keyed_path(prefix: str, *parts: object) -> Path:
    """Return a deterministic path for a sidecar JSON file under $TMPDIR.

    Args:
        prefix: Short file-name prefix, e.g. ``"find-commanders"``.
        parts: Any number of path/content parts that together identify the
            result. See the module docstring for how each type is hashed.

    The resulting path is absolute and its parent directory is guaranteed
    to exist after the first successful ``atomic_write_json`` call.
    """
    hasher = hashlib.sha256()
    for part in parts:
        _hash_part(hasher, part)
    digest = hasher.hexdigest()[:16]
    tmpdir_str = os.environ.get("TMPDIR") or tempfile.gettempdir()
    tmpdir = Path(tmpdir_str)
    return (tmpdir / f"{prefix}-{digest}.json").resolve()


def atomic_write_json(path: Path, data: object) -> None:
    """Write JSON to *path* via a temp file plus atomic rename.

    Ensures concurrent readers never observe a half-written file. Creates
    the parent directory if missing. ``data`` is serialized with
    ``indent=2`` for human readability.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 — closed by the with below
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        with tmp:
            json.dump(data, tmp, indent=2)
        tmp_path.replace(path)
    except Exception:
        # json.dump on non-serializable data (or a failed rename) would otherwise
        # orphan the .tmp file, since delete=False. Remove it and re-raise.
        tmp_path.unlink(missing_ok=True)
        raise


def write_pickle_sidecar[T](
    sidecar_path: Path,
    *,
    version_tag: int,
    value_key: str,
    value: T,
) -> None:
    """Atomically write ``{"version": version_tag, value_key: value}`` as a pickle.

    Writes go through a temp file plus rename so a reader can never observe a
    partially-written sidecar. A write failure is non-fatal (best-effort cache):
    the caller already has ``value`` in hand, and the next successful write simply
    overwrites whatever ``.tmp`` was left behind.
    """
    payload = {"version": version_tag, value_key: value}
    tmp = sidecar_path.with_name(sidecar_path.name + ".tmp")
    try:
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(sidecar_path)
    except OSError:
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()


def load_pickle_sidecar[T](
    source_path: Path,
    sidecar_path: Path,
    *,
    version_tag: int,
    value_key: str,
    build_fn: Callable[[], T],
    source_mtime: float | None = None,
    validate: Callable[[T], bool] | None = None,
) -> T:
    """Load a cached value from *sidecar_path*, rebuilding via *build_fn* on a miss.

    Mirrors what ``bulk_loader`` and ``rules_lookup`` each hand-rolled: the sidecar
    is trusted only when it exists, its mtime is at least as new as the source's
    (staleness check), its ``"version"`` key matches *version_tag*, and (if
    *validate* is given) the cached value under *value_key* passes it — mirrors
    ``bulk_loader``'s ``isinstance(cards, list)`` / ``rules_lookup``'s
    ``isinstance(parsed, dict)`` shape checks. Any of those failing, including an
    unpickle error, falls through to calling *build_fn* and atomically rewriting
    the sidecar via :func:`write_pickle_sidecar`.

    *source_mtime* lets a caller supply a freshness value derived from more than
    one file (``bulk_loader``'s MTGJSON case watches the ``AllPricesToday``
    sibling too); it defaults to ``source_path.stat().st_mtime``.
    """
    mtime = source_path.stat().st_mtime if source_mtime is None else source_mtime
    if sidecar_path.exists() and sidecar_path.stat().st_mtime >= mtime:
        try:
            with sidecar_path.open("rb") as f:
                payload = pickle.load(f)
            if isinstance(payload, dict) and payload.get("version") == version_tag:
                value = payload.get(value_key)
                if validate is None or validate(value):
                    return value
        except (pickle.PickleError, EOFError, OSError):
            pass  # fall through to rebuild

    value = build_fn()
    write_pickle_sidecar(
        sidecar_path, version_tag=version_tag, value_key=value_key, value=value
    )
    return value
