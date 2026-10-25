"""A write-back sidecar: a per-card memo persisted beside the bulk.

Some per-card reads on the signal path are deterministic but too slow to run
over the whole pool up front, and a tune asks them for a thousand cards or more
(the ranking's per-unit ident attribution, ``ident_provenance``; the job reads'
card scores, ``job_quality``). Each keeps a :class:`WriteBackSidecar`: attached
to a bulk, it serves what earlier processes computed (``<bulk><suffix>``) and,
at process exit, writes back what this one computed, merged under the
sidecar's lock with what other processes wrote meanwhile. An entry holds only
for the same code (the owner's content hash) and the same bulk (its identity),
so an edit to either starts the cache over. Nothing attached, the owner's reads
stay live-only.
"""

from __future__ import annotations

import atexit
import pickle
import threading
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable

#: Every sidecar made, so a test harness can detach them all (:func:`detach_all`).
_ALL: list[WriteBackSidecar] = []


class _Attached(NamedTuple):
    path: Path
    key: tuple[str, tuple[str, int, int]]


class WriteBackSidecar:
    """One owner's persisted memo. ``content_key`` is the owner's code identity
    (a content hash of what its values are computed by), read once per attach."""

    def __init__(self, suffix: str, content_key: Callable[[], str]) -> None:
        self._suffix = suffix
        self._content_key = content_key
        self._attached: list[_Attached] = []
        #: The entries the attached sidecar served.
        self.persisted: dict[Hashable, object] = {}
        #: The entries this process computed since (written back by :meth:`flush`).
        self._fresh: dict[Hashable, object] = {}
        self._lock = threading.Lock()
        _ALL.append(self)
        atexit.register(self.flush)  # a no-op while nothing is attached

    @property
    def attached(self) -> bool:
        return bool(self._attached)

    def record(self, key: Hashable, value: object) -> None:
        """Note a value this process computed, for the write-back (attached only)."""
        if self._attached:
            self._fresh[key] = value

    def attach(self, bulk_path: Path | None) -> bool:
        """Serve from ``<bulk_path><suffix>`` and write back to it at exit.
        Idempotent for one bulk; attaching another writes back what the first
        one's process computed, then re-keys to the new one. ``False`` (no bulk)
        leaves the owner live-only."""
        if bulk_path is None:
            return False
        path = Path(bulk_path)
        if not path.is_file():
            return False
        from mtg_utils._analysis.signals_index import bulk_identity

        identity = bulk_identity(path)
        with self._lock:
            if self._attached and self._attached[0].key[1] == identity:
                return True
            self.flush()
            self.detach()
            key = (self._content_key(), identity)
            sidecar = path.with_name(path.name + self._suffix)
            self.persisted.update(_read(sidecar, key))
            self._attached.append(_Attached(sidecar, key))
        return True

    def flush(self) -> None:
        """Write this process's fresh entries into the attached sidecar, merged
        with what is on disk now (another process may have added its own). Best
        effort: a failure leaves them for the next process to recompute."""
        from mtg_utils._sidecar import atomic_write_bytes, exclusive_lock

        fresh = dict(self._fresh)
        if not self._attached or not fresh:
            return
        sidecar, key = self._attached[0]
        with exclusive_lock(sidecar.with_name(sidecar.name + ".lock")):
            entries = _read(sidecar, key)
            entries.update(fresh)
            payload = {"key": key, "entries": entries}
            try:
                atomic_write_bytes(
                    sidecar, pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
                )
            except OSError:
                return
        for k in fresh:
            self._fresh.pop(k, None)

    def detach(self) -> None:
        """Forget the attached sidecar and what it served, writing nothing back."""
        self._attached.clear()
        self.persisted.clear()
        self._fresh.clear()


def _read(path: Path, key: object) -> dict:
    try:
        with path.open("rb") as fh:
            payload = pickle.load(fh)
    except (pickle.PickleError, EOFError, OSError, AttributeError, ImportError):
        return {}
    if not isinstance(payload, dict) or payload.get("key") != key:
        return {}
    entries = payload.get("entries")
    return entries if isinstance(entries, dict) else {}


def detach_all() -> None:
    """Detach every sidecar, writing nothing back (test hygiene)."""
    for sidecar in _ALL:
        sidecar.detach()
