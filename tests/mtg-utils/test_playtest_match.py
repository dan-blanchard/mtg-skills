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
