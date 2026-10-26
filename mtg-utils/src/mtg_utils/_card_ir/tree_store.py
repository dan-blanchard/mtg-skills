"""The corrected trees, persisted per oracle_id beside phase's card-data.

Building a card's trees (strict load, overlay, corrections: ``trees.build_trees``)
takes about 1 ms; unpickling them about 0.02 ms (backlog (l), 2026-10-25). The store
keeps each oracle_id's trees, with the names of its phase face records, in SQLite
beside the card-data they were built from (``<card-data>.trees.sqlite``), so a
process reads a card's trees without building them, and without loading the mirror
schema or the phase records index to build them.

A row is keyed by the oracle_id and the store key (:func:`store_key`), which covers
everything a tree depends on: the code that builds it (every module the import
closure of ``_card_ir.trees`` reaches, ``_import_closure``), ``PHASE_TAG``, the
card-data file, the committed mirror schema, the known-tokens file, the Python
version and :data:`STORE_VERSION`. A process running other code never reads a row
this one wrote. Worktrees share one phase cache, so the rows of the
:data:`KEEP_KEYS` most recently written keys are kept and older ones dropped.

What a row holds is exactly what ``trees_for(card)`` builds (``trees`` stores only
those: never a card's text-only faces read off its bulk record, which depend on the
order a process reads the card in — ``trees.reads_bulk_faces``). Writes are
batched: a process keeps what it built and writes it at exit, or every
:data:`FLUSH_EVERY` cards (a ``multiprocessing`` worker never runs ``atexit``).
Every failure degrades to building: a store that can't be opened, read or written
serves nothing.
"""

from __future__ import annotations

import atexit
import contextlib
import hashlib
import io
import json
import os
import pickle
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from mtg_utils import _gc
from mtg_utils._card_ir.crosswalk.reads import MEMO_ATTR_PREFIX

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import ConceptTree

#: Bumped for a change in what a row holds.
STORE_VERSION = 1
#: Built cards a process holds before it writes them.
FLUSH_EVERY = 256
#: Store keys whose rows are kept (one per code a worktree runs).
KEEP_KEYS = 4

_SCHEMA = (
    (
        "CREATE TABLE IF NOT EXISTS trees (key TEXT NOT NULL, oid TEXT NOT NULL, "
        "names TEXT NOT NULL, blob BLOB NOT NULL, PRIMARY KEY (key, oid)) "
        "WITHOUT ROWID"
    ),
    "CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, written REAL NOT NULL)",
)


class _TreePickler(pickle.Pickler):
    """Pickles trees without the memos reads left on their nodes
    (``crosswalk.reads.MEMO_ATTR_PREFIX``): a memo is a pure function of its
    object, recomputed on demand, and some are keyed by the ``id()`` of the nodes
    they index (``crosswalk.reads._owner_index``), which a loaded copy's nodes
    don't share."""

    def reducer_override(self, obj: object) -> Any:  # noqa: ANN401 — pickle's reduce shape, or NotImplemented
        state = getattr(obj, "__dict__", None)
        if not isinstance(state, dict) or not any(
            k.startswith(MEMO_ATTR_PREFIX) for k in state
        ):
            return NotImplemented
        func, args, *_rest = obj.__reduce_ex__(pickle.HIGHEST_PROTOCOL)
        return (
            func,
            args,
            {k: v for k, v in state.items() if not k.startswith(MEMO_ATTR_PREFIX)},
        )


def _dumps(trees: tuple[ConceptTree, ...]) -> bytes:
    buffer = io.BytesIO()
    _TreePickler(buffer, protocol=pickle.HIGHEST_PROTOCOL).dump(trees)
    return buffer.getvalue()


#: Connections a forked child inherited, kept unclosed: closing one there would
#: touch the parent's file locks.
_INHERITED: list[sqlite3.Connection] = []


class StoredTrees(NamedTuple):
    """One oracle_id's row: the casefolded names of its phase face records (empty
    when phase has none) and its corrected trees."""

    face_names: frozenset[str]
    trees: tuple[ConceptTree, ...]


def store_key(card_data: Path, schema: Path, known_tokens: Path) -> str:
    """What every tree in the store was built from (the module docstring)."""
    from mtg_utils import _phase
    from mtg_utils._import_closure import hash_files, source_files

    package = Path(__file__).resolve().parents[1]
    hasher = hashlib.sha256(f"tree_store:{STORE_VERSION}".encode())
    hasher.update(f"|py{sys.version_info[0]}.{sys.version_info[1]}".encode())
    hasher.update(f"|phase_tag:{_phase.PHASE_TAG}".encode())
    hash_files(hasher, source_files("mtg_utils._card_ir.trees"), relative_to=package)
    # card-data and known-tokens are per-tag downloads, replaced whole: their
    # identity is their stat; the schema fixture is a checked-in file.
    for label, path in (("card_data", card_data), ("known_tokens", known_tokens)):
        st = path.stat()
        hasher.update(f"|{label}:{path.name}:{st.st_mtime_ns}:{st.st_size}".encode())
    hasher.update(b"|schema:")
    hasher.update(schema.read_bytes())
    return hasher.hexdigest()


class TreeStore:
    """One SQLite store of trees, read and written under one store key."""

    def __init__(self, path: Path, key: str) -> None:
        self._path = path
        self._key = key
        self._lock = threading.Lock()
        self._con: sqlite3.Connection | None = None
        self._pid = 0
        self._broken = False
        #: oid -> (names JSON, pickled trees) built since the last write.
        self._fresh: dict[str, tuple[str, bytes]] = {}
        atexit.register(self.flush)

    def _connection(self) -> sqlite3.Connection | None:
        """The connection, opened on first use and again in a forked child (a
        connection never crosses a fork); ``None`` once the store has failed."""
        if self._broken:
            return None
        if self._con is None or self._pid != os.getpid():
            if self._con is not None:
                # A forked child's inherited connection: never used or closed there.
                _INHERITED.append(self._con)
            try:
                con = sqlite3.connect(
                    self._path,
                    timeout=30,
                    isolation_level=None,
                    check_same_thread=False,
                )
                con.execute("PRAGMA journal_mode=WAL")
                con.execute("PRAGMA synchronous=NORMAL")
                for statement in _SCHEMA:
                    con.execute(statement)
            except sqlite3.Error:
                self._broken = True
                return None
            self._con, self._pid = con, os.getpid()
        return self._con

    def _row(self, columns: str, oid: str) -> tuple | None:
        with self._lock:
            con = self._connection()
            if con is None:
                return None
            try:
                return con.execute(
                    f"SELECT {columns} FROM trees WHERE key = ? AND oid = ?",
                    (self._key, oid),
                ).fetchone()
            except sqlite3.Error:
                return None

    def face_names(self, oid: str) -> frozenset[str] | None:
        """``oid``'s row's face names alone (no trees unpickled), else ``None``."""
        row = self._row("names", oid)
        return frozenset(json.loads(row[0])) if row is not None else None

    def get(self, oid: str) -> StoredTrees | None:
        """``oid``'s row under this store's key, else ``None``."""
        row = self._row("names, blob", oid)
        if row is None:
            return None
        try:
            # Unpickling a card's trees allocates a few hundred objects and no
            # garbage; at the collector's pace that is a collection walking the
            # pool every few cards (four fifths of a read's cost, measured).
            with _gc.paused():
                names, trees = json.loads(row[0]), pickle.loads(row[1])
        except Exception:  # noqa: BLE001 — an unreadable row is a miss
            return None
        return StoredTrees(frozenset(names), trees)

    def put(
        self, oid: str, face_names: frozenset[str], trees: tuple[ConceptTree, ...]
    ) -> None:
        """Hold ``oid``'s freshly built trees for the next write."""
        blob = _dumps(trees)
        with self._lock:
            self._fresh[oid] = (json.dumps(sorted(face_names)), blob)
            full = len(self._fresh) >= FLUSH_EVERY
        if full:
            self.flush()

    def flush(self) -> None:
        """Write the held trees, keeping the rows of the :data:`KEEP_KEYS` most
        recently written keys. Best effort: a failure drops them, for a later
        process to build again."""
        with self._lock:
            if not self._fresh:
                return
            con = self._connection()
            rows = [(self._key, oid, n, b) for oid, (n, b) in self._fresh.items()]
            self._fresh.clear()
            if con is None:
                return
            try:
                con.execute("BEGIN IMMEDIATE")
                con.executemany("INSERT OR IGNORE INTO trees VALUES (?, ?, ?, ?)", rows)
                con.execute(
                    "INSERT OR REPLACE INTO keys VALUES (?, ?)",
                    (self._key, time.time()),
                )
                stale = con.execute(
                    "SELECT key FROM keys ORDER BY written DESC LIMIT -1 OFFSET ?",
                    (KEEP_KEYS,),
                ).fetchall()
                for (key,) in stale:
                    con.execute("DELETE FROM trees WHERE key = ?", (key,))
                    con.execute("DELETE FROM keys WHERE key = ?", (key,))
                con.execute("COMMIT")
            except sqlite3.Error:
                with contextlib.suppress(sqlite3.Error):
                    con.execute("ROLLBACK")
