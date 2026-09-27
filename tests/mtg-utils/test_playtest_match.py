"""Tests for playtest-match (phase-driven AI vs AI batch)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from mtg_utils.playtest import match_main


@pytest.fixture
def two_decks(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    deck = {
        "format": "modern",
        "commanders": [],
        "cards": [{"name": "Mountain", "quantity": 60}],
        "sideboard": [],
    }
    a.write_text(json.dumps(deck))
    b.write_text(json.dumps(deck))
    return a, b


class TestMatchCLI:
    def test_runs_match_with_full_coverage(self, tmp_path, two_decks, monkeypatch):
        a, b = two_decks
        monkeypatch.setattr(
            "mtg_utils._phase.coverage_report",
            lambda _names, **_kw: {
                "status": "full",
                "supported_pct": 1.0,
                "missing": [],
                "requested": 60,
                "supported": 60,
            },
        )
        monkeypatch.setattr(
            "mtg_utils._phase.run_duel",
            lambda *_a, **_kw: {
                "status": "ok",
                "wins_p0": 30,
                "wins_p1": 18,
                "draws": 2,
                "games": 50,
                "games_completed": 50,
                "games_requested": 50,
                "timed_out": False,
                "avg_turns": 7.0,
                "avg_duration_ms": 1500,
            },
        )
        out = tmp_path / "out.json"
        runner = CliRunner()
        result = runner.invoke(
            match_main,
            [
                str(a),
                str(b),
                "--games",
                "50",
                "--seed",
                "1",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        env = json.loads(out.read_text())
        assert env["mode"] == "match"
        assert env["engine"] == "phase"
        assert env["results"]["wins_p0"] == 30
        assert env["results"]["draws"] == 2

    def test_blocks_on_low_coverage(self, tmp_path, two_decks, monkeypatch):
        a, b = two_decks
        monkeypatch.setattr(
            "mtg_utils._phase.coverage_report",
            lambda _names, **_kw: {
                "status": "blocked",
                "supported_pct": 0.5,
                "missing": ["X", "Y"],
                "requested": 60,
                "supported": 30,
            },
        )
        runner = CliRunner()
        result = runner.invoke(match_main, [str(a), str(b)])
        assert result.exit_code != 0
        assert "coverage" in result.output.lower()


def _full_coverage(_names, **_kw):
    return {
        "status": "full",
        "supported_pct": 1.0,
        "missing": [],
        "requested": 60,
        "supported": 60,
    }


def _timed_out(completed: int, requested: int) -> dict:
    return {
        "status": "timeout",
        "wins_p0": completed // 2,
        "wins_p1": completed - completed // 2,
        "draws": 0,
        "games": completed,
        "games_completed": completed,
        "games_requested": requested,
        "timed_out": True,
        "avg_turns": 7.0 if completed else 0.0,
        "avg_duration_ms": 1500 if completed else 0,
    }


class TestMatchTimeout:
    def test_partial_run_reports_the_games_that_finished(self, two_decks, monkeypatch):
        a, b = two_decks
        monkeypatch.setattr("mtg_utils._phase.coverage_report", _full_coverage)
        monkeypatch.setattr(
            "mtg_utils._phase.run_duel", lambda *_a, **_kw: _timed_out(118, 200)
        )
        result = CliRunner().invoke(match_main, [str(a), str(b), "--games", "200"])
        assert result.exit_code == 0, result.output
        assert "118 of 200 games completed — timed out" in result.output
        assert "**59** (50.0%)" in result.output  # rated over the 118 that finished
        assert "118 of 200 games completed - the results cover those games" in (
            result.output
        )

    def test_nothing_finished_is_not_a_tie(self, two_decks, monkeypatch):
        a, b = two_decks
        monkeypatch.setattr("mtg_utils._phase.coverage_report", _full_coverage)
        monkeypatch.setattr(
            "mtg_utils._phase.run_duel", lambda *_a, **_kw: _timed_out(0, 50)
        )
        result = CliRunner().invoke(match_main, [str(a), str(b), "--games", "50"])
        assert result.exit_code == 0, result.output
        assert "0 of 50 games completed — timed out" in result.output
        assert "not a tie" in result.output

    def test_default_budget_scales_with_the_games(self, two_decks, monkeypatch):
        a, b = two_decks
        seen: dict = {}
        monkeypatch.setattr("mtg_utils._phase.coverage_report", _full_coverage)

        def fake_run_duel(*_a, **kw):
            seen["timeout_s"] = kw["timeout_s"]
            return _timed_out(kw["games"], kw["games"]) | {
                "timed_out": False,
                "status": "ok",
            }

        monkeypatch.setattr("mtg_utils._phase.run_duel", fake_run_duel)
        runner = CliRunner()
        runner.invoke(match_main, [str(a), str(b), "--games", "200"])
        assert seen["timeout_s"] == 2000  # 10 s per game
        runner.invoke(match_main, [str(a), str(b), "--games", "20"])
        assert seen["timeout_s"] == 600  # the floor
        runner.invoke(match_main, [str(a), str(b), "--timeout-s", "45"])
        assert seen["timeout_s"] == 45  # an explicit budget wins
