"""The cyclic garbage collector around the work that mostly builds.

A tune holds the card pool, its indexes and the trees it reads: millions of
containers, almost none of them garbage. A collection walks them, so at the
interpreter's default pace (a young collection every 2,000 net allocations) the
collector costs a tune about as much as any one of its reads (backlog (l),
2026-10-25, a warm Blood Rites tune: 0.4 s collecting while it seeded the
signals index, 0.5 s more during the tune, and 1 s on the final collection at
exit). Collecting less often changes no value any code computes; it only frees
the reference cycles the work makes later.
"""

from __future__ import annotations

import contextlib
import gc
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

#: The young-generation threshold while :func:`relaxed` holds: about 50 times
#: fewer collections than the default. A tune at this pace runs as fast as one
#: with the collector off (measured, 2026-10-25), yet a whole-pool pass the tune
#: may start (the signals index's ~2 min build, whose per-card reads make cyclic
#: garbage: about 50 objects a card) still frees what it makes.
RELAXED_THRESHOLD = 100_000

_relaxed_lock = threading.Lock()
_relaxed_depth = 0
_relaxed_saved: tuple[int, ...] = ()


@contextlib.contextmanager
def paused() -> Generator[None]:
    """Run the block with the cyclic collector off, restoring its state after
    (so a nested pause, or a caller that turned it off, is left as it was). For
    a load that makes no reference cycles (decoded JSON, the seeded indexes)."""
    collecting = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if collecting:
            gc.enable()


@contextlib.contextmanager
def relaxed() -> Generator[None]:
    """Run the block collecting at :data:`RELAXED_THRESHOLD`, for work that
    makes some garbage but mostly builds (a tune). Re-entrant and thread-safe:
    the first block in raises the threshold, the last one out restores it."""
    global _relaxed_depth, _relaxed_saved  # noqa: PLW0603 — the one shared pace
    with _relaxed_lock:
        if _relaxed_depth == 0:
            _relaxed_saved = gc.get_threshold()
            gc.set_threshold(RELAXED_THRESHOLD, *_relaxed_saved[1:])
        _relaxed_depth += 1
    try:
        yield
    finally:
        with _relaxed_lock:
            _relaxed_depth -= 1
            if _relaxed_depth == 0:
                gc.set_threshold(*_relaxed_saved)


def skip_exit_collection() -> None:
    """Freeze every object alive now, so the interpreter's final collection at
    exit skips them. For a CLI about to exit: the heap dies with the process, and
    the collection would only walk it (``gc.freeze``)."""
    gc.freeze()
