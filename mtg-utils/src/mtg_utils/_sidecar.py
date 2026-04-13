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
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _hash_part(hasher: hashlib._Hash, part: Any) -> None:
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


def sha_keyed_path(prefix: str, *parts: Any) -> Path:
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


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON to *path* via a temp file plus atomic rename.

    Ensures concurrent readers never observe a half-written file. Creates
    the parent directory if missing. ``data`` is serialized with
    ``indent=2`` for human readability.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
