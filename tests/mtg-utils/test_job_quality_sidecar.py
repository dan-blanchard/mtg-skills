"""The job reads' write-back sidecar (``job_quality.attach_job_read_sidecar``):
a process attached to a bulk persists each read's deck-free card values, and the
next one serves them without re-reading the card — real cards (ADR-0056)."""

import dataclasses

import pytest

from mtg_utils._analysis import job_quality
from mtg_utils._analysis.job_quality import _common, card_draw
from mtg_utils._analysis.write_back import MISSING
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _fresh_process() -> None:
    """Nothing attached, nothing memoized: detaching clears the reads' memos."""
    _common.JOB_READS.detach()
    assert not job_quality._SCORES.local
    assert not card_draw._FUELS.local


def test_the_job_read_sidecar_serves_what_a_process_wrote_back(monkeypatch, tmp_path):
    """Wrath of God's board-wipe score and Skullclamp's draw fuel are written back
    at the first process's flush and served to the next as the live read's values;
    another bulk (its identity is the key) serves nothing."""
    bulk = tmp_path / "AllPrintings.json"
    bulk.write_text("[]")
    wrath, clamp = _real("Wrath of God"), _real("Skullclamp")

    _fresh_process()
    assert job_quality.attach_job_read_sidecar(bulk)
    live_score = job_quality.job_score(wrath, "board_wipe")
    live_fuel = card_draw.draw_fuel(clamp)
    assert live_score is not None
    assert live_fuel is not None
    _common.JOB_READS.flush()
    assert (tmp_path / "AllPrintings.json.job-reads.pkl").is_file()

    _fresh_process()
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
    assert job_quality._SCORES.persisted(("board_wipe", wrath["oracle_id"])) is MISSING


def test_a_read_outside_reads_is_scored_live():
    """Only the job's own read in ``READS`` is memoized: another read of the
    same job, with its own weights, scores the card by those weights."""
    wrath = _real("Wrath of God")
    wipe = job_quality.READS["board_wipe"]
    assert wipe.score(wrath) is not None
    doubled = dataclasses.replace(
        wipe, weights={k: 2 * v for k, v in wipe.weights.items()}
    )
    assert doubled.score(wrath) == pytest.approx(2 * wipe.score(wrath), abs=0.002)
