"""The write-back sidecar's merge at a flush (``_analysis.write_back``): two
processes' fresh entries both land, and a flush re-reads the file only when
another process has written it since this one read it."""

from mtg_utils._analysis import write_back
from mtg_utils._analysis.write_back import MISSING, WriteBackSidecar


def _process(bulk) -> tuple[WriteBackSidecar, write_back.WriteBackMemo]:
    sidecar = WriteBackSidecar(".test-reads.pkl", lambda: "test-key")
    assert sidecar.attach(bulk)
    return sidecar, sidecar.memo("reads")


def test_two_processes_flushes_keep_both_entries(tmp_path):
    bulk = tmp_path / "AllPrintings.json"
    bulk.write_text("[]")
    first, first_memo = _process(bulk)
    second, second_memo = _process(bulk)
    first_memo.put("a", 1)
    first.flush()
    second_memo.put("b", 2)
    second.flush()  # the file changed since it read it: merged with the first's

    third, third_memo = _process(bulk)
    assert (third_memo.get("a"), third_memo.get("b")) == (1, 2)
    for sidecar in (first, second, third):
        sidecar.detach()


def test_a_flush_merges_into_what_it_read_when_no_one_wrote_since(
    tmp_path, monkeypatch
):
    bulk = tmp_path / "AllPrintings.json"
    bulk.write_text("[]")
    first, first_memo = _process(bulk)
    first_memo.put("a", 1)
    first.flush()

    second, second_memo = _process(bulk)
    assert second_memo.get("a") == 1

    def no_read(*_a, **_k):
        raise AssertionError("the file is as this process read it")

    monkeypatch.setattr(write_back, "_read", no_read)
    second_memo.put("b", 2)
    second.flush()
    second_memo.put("c", 3)
    second.flush()  # its own write: still no read
    monkeypatch.undo()

    third, third_memo = _process(bulk)
    assert [third_memo.get(k) for k in "abc"] == [1, 2, 3]
    assert third_memo.get("d") is MISSING
    for sidecar in (first, second, third):
        sidecar.detach()
