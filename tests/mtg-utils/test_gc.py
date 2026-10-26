"""The cyclic collector's pace around the build-only work (``mtg_utils._gc``)."""

import gc
import threading

from mtg_utils import _gc


def test_paused_restores_the_collector_as_it_found_it():
    assert gc.isenabled()
    with _gc.paused():
        assert not gc.isenabled()
        with _gc.paused():
            assert not gc.isenabled()
        assert not gc.isenabled()  # the outer pause still holds
    assert gc.isenabled()
    gc.disable()
    try:
        with _gc.paused():
            pass
        assert not gc.isenabled()  # a caller's own pause is left alone
    finally:
        gc.enable()


def test_freeze_at_exit_registers_one_freeze(monkeypatch):
    registered: list[object] = []
    monkeypatch.setattr(_gc.atexit, "register", registered.append)
    monkeypatch.setattr(_gc, "_freezing_at_exit", [])
    _gc.freeze_at_exit()
    _gc.freeze_at_exit()
    assert registered == [gc.freeze]


def test_relaxed_raises_the_threshold_until_the_last_block_leaves():
    before = gc.get_threshold()
    with _gc.relaxed():
        assert gc.get_threshold()[0] == _gc.RELAXED_THRESHOLD
        with _gc.relaxed():
            assert gc.get_threshold()[0] == _gc.RELAXED_THRESHOLD
        assert gc.get_threshold()[0] == _gc.RELAXED_THRESHOLD
    assert gc.get_threshold() == before


def test_relaxed_blocks_in_two_threads_restore_the_pace_once_both_leave():
    """The second thread's block, entered while the first holds, never captures
    the raised threshold as the one to restore."""
    before = gc.get_threshold()
    inside, release = threading.Event(), threading.Event()

    def hold():
        with _gc.relaxed():
            inside.set()
            release.wait()

    worker = threading.Thread(target=hold)
    worker.start()
    inside.wait()
    with _gc.relaxed():
        release.set()
        worker.join()
        assert gc.get_threshold()[0] == _gc.RELAXED_THRESHOLD
    assert gc.get_threshold() == before
