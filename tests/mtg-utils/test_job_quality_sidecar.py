"""The job reads' write-back sidecar (``job_quality.attach_job_read_sidecar``):
a process attached to a bulk persists each read's deck-free card values, and the
next one serves them without re-reading the card — real cards (ADR-0056)."""

import dataclasses

from mtg_utils._analysis import job_quality
from mtg_utils._analysis.job_quality import _common, card_draw
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _fresh_process(monkeypatch) -> None:
    """Nothing attached, nothing memoized."""
    _common.JOB_READS.detach()
    monkeypatch.setattr(job_quality, "_SCORE_MEMO", {})
    monkeypatch.setattr(card_draw, "_FUEL_MEMO", {})


def test_the_job_read_sidecar_serves_what_a_process_wrote_back(monkeypatch, tmp_path):
    """Wrath of God's board-wipe score and Skullclamp's draw fuel are written back
    at the first process's flush and served to the next as the live read's values;
    another bulk (its identity is the key) serves nothing."""
    bulk = tmp_path / "AllPrintings.json"
    bulk.write_text("[]")
    wrath, clamp = _real("Wrath of God"), _real("Skullclamp")

    _fresh_process(monkeypatch)
    assert job_quality.attach_job_read_sidecar(bulk)
    live_score = job_quality.job_score(wrath, "board_wipe")
    live_fuel = card_draw.draw_fuel(clamp)
    assert live_score is not None
    assert live_fuel is not None
    _common.JOB_READS.flush()
    assert (tmp_path / "AllPrintings.json.job-reads.pkl").is_file()

    _fresh_process(monkeypatch)
    assert job_quality.attach_job_read_sidecar(bulk)

    def no_read(*_a, **_k):
        raise AssertionError("served from the sidecar, never re-read")

    wipe = job_quality.READS["board_wipe"]
    monkeypatch.setitem(
        job_quality.READS, "board_wipe", dataclasses.replace(wipe, features=no_read)
    )
    monkeypatch.setattr(card_draw, "_sources", no_read)
    assert job_quality.job_score(wrath, "board_wipe") == live_score
    assert card_draw.draw_fuel(clamp) == live_fuel

    bulk.write_text("[ ]")  # another bulk: another key
    assert job_quality.attach_job_read_sidecar(bulk)
    assert _common.JOB_READS.persisted == {}
