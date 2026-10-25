"""A write-back sidecar: per-card memos persisted beside the bulk.

Some per-card reads on the signal path are deterministic but too slow to run
over the whole pool up front, and a tune asks them for a thousand cards or more
(the ranking's per-unit ident attribution, ``ident_provenance``; the job reads'
card values, ``job_quality``). Each owner keeps a :class:`WriteBackSidecar` and
one :class:`WriteBackMemo` per kind of value (its namespace). Attached to a bulk,
the sidecar serves what earlier processes computed (``<bulk><suffix>``) and, at
process exit, writes back what this one computed, merged under the sidecar's
lock with what other processes wrote meanwhile. An entry holds only for the same
code (the owner's content key), the same payload shape
(:data:`WRITE_BACK_VERSION`) and the same bulk (its identity), so an edit to any
of them starts the cache over. Nothing attached, the memos are in-process only.
"""

from __future__ import annotations

import atexit
import pickle
import threading
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable

#: Bumped for an on-disk payload SHAPE change (``{"key", "entries": {namespace:
#: {key: value}}}``); part of every sidecar's key.
WRITE_BACK_VERSION = 2
#: What :meth:`WriteBackMemo.get` returns for a key nothing holds.
MISSING = object()
#: Every sidecar made, so a test harness can detach them all (:func:`detach_all`).
_ALL: list[WriteBackSidecar] = []

_Key = tuple[str, tuple[str, int, int], int]


class _Attached(NamedTuple):
    path: Path
    key: _Key


class WriteBackSidecar:
    """One owner's persisted memos. ``content_key`` is the owner's code identity
    (a content hash of what its values are computed by), read once per attach."""

    def __init__(self, suffix: str, content_key: Callable[[], str]) -> None:
        self._suffix = suffix
        self._content_key = content_key
        self._attached: list[_Attached] = []
        #: namespace -> the entries the attached sidecar served.
        self._persisted: dict[str, dict[Hashable, object]] = {}
        #: namespace -> the entries this process computed since (:meth:`flush`).
        self._fresh: dict[str, dict[Hashable, object]] = {}
        self._memos: list[WriteBackMemo] = []
        self._lock = threading.Lock()
        _ALL.append(self)
        atexit.register(self.flush)  # a no-op while nothing is attached

    def memo(self, namespace: str) -> WriteBackMemo:
        """The in-process memo for one kind of value, backed by this sidecar."""
        memo = WriteBackMemo(self, namespace)
        self._memos.append(memo)
        return memo

    def served(self, namespace: str, key: Hashable) -> object:
        """The attached sidecar's value for ``key``, else :data:`MISSING`."""
        return self._persisted.get(namespace, {}).get(key, MISSING)

    def note(self, namespace: str, key: Hashable, value: object) -> None:
        """Note a value this process computed, for the write-back (attached only)."""
        if self._attached:
            self._fresh.setdefault(namespace, {})[key] = value

    def attach(self, bulk_path: Path | None) -> bool:
        """Serve from ``<bulk_path><suffix>`` and write back to it at exit.
        Idempotent for one bulk; attaching another writes back what the first
        one's process computed, then re-keys to the new one. ``False`` (no bulk)
        leaves the memos in-process only."""
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
            key = (self._content_key(), identity, WRITE_BACK_VERSION)
            sidecar = path.with_name(path.name + self._suffix)
            self._persisted.update(_read(sidecar, key))
            self._attached.append(_Attached(sidecar, key))
        return True

    def flush(self) -> None:
        """Write this process's fresh entries into the attached sidecar, merged
        with what is on disk now (another process may have added its own). Best
        effort: a failure leaves them for the next process to recompute."""
        from mtg_utils._sidecar import atomic_write_bytes, exclusive_lock

        fresh = {ns: dict(entries) for ns, entries in self._fresh.items() if entries}
        if not self._attached or not fresh:
            return
        sidecar, key = self._attached[0]
        with exclusive_lock(sidecar.with_name(sidecar.name + ".lock")):
            entries = _read(sidecar, key)
            for ns, values in fresh.items():
                entries.setdefault(ns, {}).update(values)
            payload = {"key": key, "entries": entries}
            try:
                atomic_write_bytes(
                    sidecar, pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
                )
            except OSError:
                return
        for ns, values in fresh.items():
            for k in values:
                self._fresh[ns].pop(k, None)

    def detach(self) -> None:
        """Forget the attached sidecar, what it served and every memo's values,
        writing nothing back."""
        self._attached.clear()
        self._persisted.clear()
        self._fresh.clear()
        for memo in self._memos:
            memo.local.clear()


class WriteBackMemo:
    """One namespace of a :class:`WriteBackSidecar`: an in-process memo (``local``)
    that falls back to what the attached sidecar served and records what this
    process computes for the write-back."""

    def __init__(self, sidecar: WriteBackSidecar, namespace: str) -> None:
        self._sidecar = sidecar
        self._namespace = namespace
        self.local: dict[Hashable, object] = {}

    def persisted(self, key: Hashable) -> object:
        """The attached sidecar's value for ``key``, else :data:`MISSING`."""
        return self._sidecar.served(self._namespace, key)

    def record(self, key: Hashable, value: object) -> None:
        """Note a value this process computed, for the write-back (attached only)."""
        self._sidecar.note(self._namespace, key, value)

    def get(self, key: Hashable) -> object:
        """``local``'s value for ``key``, else the sidecar's (kept in ``local``
        from then on), else :data:`MISSING`."""
        if key in self.local:
            return self.local[key]
        value = self.persisted(key)
        if value is not MISSING:
            self.local[key] = value
        return value

    def put(self, key: Hashable, value: object) -> None:
        """Memoize ``value`` and record it for the write-back."""
        self.local[key] = value
        self.record(key, value)


def _read(path: Path, key: object) -> dict[str, dict[Hashable, object]]:
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
