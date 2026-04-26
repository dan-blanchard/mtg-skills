"""Tests for the phase-rs subprocess wrapper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mtg_utils import _phase


class TestPhaseTag:
    def test_phase_tag_is_pinned(self):
        assert _phase.PHASE_TAG.startswith("v0.1.")
        assert _phase.PHASE_TAG == "v0.1.19"


class TestCacheLayout:
    def test_default_cache_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MTG_SKILLS_CACHE_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        cache = _phase.cache_dir()
        assert cache == tmp_path / ".cache" / "mtg-skills" / "phase"

    def test_cache_dir_overridable(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path / "x"))
        cache = _phase.cache_dir()
        assert cache == tmp_path / "x" / "phase"


class TestBinaryLookup:
    def test_uses_env_override_when_set(self, monkeypatch, tmp_path):
        bin_path = tmp_path / "ai-duel"
        bin_path.write_text("#!/bin/sh\n")
        bin_path.chmod(0o755)
        monkeypatch.setenv("MTG_SKILLS_PHASE_BIN", str(bin_path))
        assert _phase.find_binary("ai-duel") == bin_path

    def test_uses_cache_when_built(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MTG_SKILLS_PHASE_BIN", raising=False)
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        target = tmp_path / "phase" / "phase.git" / "target" / "release"
        target.mkdir(parents=True)
        bin_path = target / "ai-duel"
        bin_path.write_text("#!/bin/sh\n")
        bin_path.chmod(0o755)
        assert _phase.find_binary("ai-duel") == bin_path

    def test_raises_clear_error_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MTG_SKILLS_PHASE_BIN", raising=False)
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        with pytest.raises(_phase.PhaseNotInstalledError) as excinfo:
            _phase.find_binary("ai-duel")
        assert "playtest-install-phase" in str(excinfo.value)

    def test_env_override_set_but_binary_missing_raises(self, monkeypatch, tmp_path):
        # Env var points to a directory that doesn't contain the requested binary.
        monkeypatch.setenv("MTG_SKILLS_PHASE_BIN", str(tmp_path))
        with pytest.raises(_phase.PhaseNotInstalledError) as excinfo:
            _phase.find_binary("ai-duel")
        msg = str(excinfo.value)
        assert "MTG_SKILLS_PHASE_BIN" in msg
        assert str(tmp_path) in msg


class TestInstall:
    def test_install_runs_clone_setup_and_cargo(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        calls: list[list[str]] = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            r = MagicMock()
            r.returncode = 0
            joined = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            r.stdout = "abc1234def5678\n" if "rev-parse" in joined else ""
            r.stderr = ""
            return r

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr(_phase, "_ensure_prereqs", lambda: None)

        _phase.install_phase()

        joined = [" ".join(c) if isinstance(c, list) else c for c in calls]
        clone_idx = next(i for i, c in enumerate(joined) if "git clone" in c)
        setup_idx = next(i for i, c in enumerate(joined) if "setup.sh" in c)
        build_idx = next(
            i for i, c in enumerate(joined) if "cargo build" in c and "ai-duel" in c
        )
        assert clone_idx < setup_idx < build_idx, (
            f"clone/setup/cargo must run in order: {joined}"
        )

        version_file = _phase.cache_dir() / "version.txt"
        assert version_file.exists(), "install_phase must write version.txt"
        assert version_file.read_text().strip() == "abc1234def5678"


class TestCoverageGate:
    @pytest.fixture
    def phase_card_data(self, monkeypatch, tmp_path):
        """Stand up a fake phase install with a card-data.json file."""
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        public = tmp_path / "phase" / "phase.git" / "client" / "public"
        public.mkdir(parents=True)
        public.joinpath("card-data.json").write_text(
            json.dumps(
                {
                    "cards": [
                        {"name": "Mountain"},
                        {"name": "Lightning Bolt"},
                        {"name": "Goblin Guide"},
                    ],
                }
            )
        )
        # Clear any cached supported-name set from earlier tests.
        _phase.load_supported_card_names.cache_clear()
        return public / "card-data.json"

    def test_loads_supported_set(self, phase_card_data):
        names = _phase.load_supported_card_names()
        assert "Mountain" in names
        assert "Lightning Bolt" in names
        assert "Goblin Guide" in names

    def test_coverage_full(self, phase_card_data):
        report = _phase.coverage_report(["Mountain", "Lightning Bolt"])
        assert report["status"] == "full"
        assert report["supported_pct"] == 1.0

    def test_coverage_warn(self, phase_card_data):
        # 2 of 3 = 66% — below default 90% threshold => "blocked"
        # but with threshold=0.5 should be "warn"
        report = _phase.coverage_report(
            ["Mountain", "Lightning Bolt", "Foo Bar"],
            threshold=0.5,
        )
        assert report["status"] == "warn"
        assert "Foo Bar" in report["missing"]

    def test_coverage_blocked(self, phase_card_data):
        # 1 of 3 = 33% supported, default threshold 0.9 => blocked
        report = _phase.coverage_report(
            ["Mountain", "Foo", "Bar"],
        )
        assert report["status"] == "blocked"
        assert sorted(report["missing"]) == ["Bar", "Foo"]


class TestDeckConversion:
    def test_to_phase_deck_drops_set_codes_and_extras(self):
        deck = {
            "format": "modern",
            "commanders": [],
            "cards": [
                {"name": "Mountain", "quantity": 20, "set": "FDN"},
                {"name": "Lightning Bolt", "quantity": 4},
            ],
        }
        out = _phase.to_phase_deck(deck, label="Aggro")
        assert out["name"] == "Aggro"
        assert out["format"] == "modern"
        assert {"name": "Mountain", "count": 20} in out["main"]
        assert {"name": "Lightning Bolt", "count": 4} in out["main"]
        # Extra fields stripped
        assert all(set(e.keys()) == {"name", "count"} for e in out["main"])

    def test_to_phase_deck_includes_commander(self):
        deck = {
            "format": "commander",
            "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
            "cards": [{"name": "Mountain", "quantity": 99}],
        }
        out = _phase.to_phase_deck(deck, label="Krenko")
        assert out["commander"] == ["Krenko, Mob Boss"]
        # Commander in main too (phase requires it).
        names = [e["name"] for e in out["main"]]
        assert "Krenko, Mob Boss" in names


class TestRunDuel:
    def test_run_duel_invokes_binary_with_args(self, monkeypatch, tmp_path):
        bin_path = tmp_path / "ai-duel"
        bin_path.write_text("#!/bin/sh\n")
        bin_path.chmod(0o755)
        monkeypatch.setenv("MTG_SKILLS_PHASE_BIN", str(bin_path))

        captured = {}

        def fake_run(cmd, **_kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = _kwargs
            output_path = Path([a for a in cmd if a.startswith("/")][-1])
            output_path.write_text(
                json.dumps(
                    {
                        "matchup": "deckA-vs-deckB",
                        "games": 50,
                        "p0_wins": 28,
                        "p1_wins": 18,
                        "draws": 4,
                        "avg_turns": 7.2,
                        "avg_duration_ms": 2100,
                    }
                )
            )
            r = MagicMock()
            r.returncode = 0
            return r

        monkeypatch.setattr("subprocess.run", fake_run)

        deck_a = tmp_path / "a.json"
        deck_b = tmp_path / "b.json"
        deck_a.write_text(json.dumps({"name": "A", "format": "modern", "main": []}))
        deck_b.write_text(json.dumps({"name": "B", "format": "modern", "main": []}))

        result = _phase.run_duel(
            deck_a,
            deck_b,
            games=50,
            seed=42,
            format_="modern",
            timeout_s=300,
        )

        assert result["wins_p0"] == 28
        assert result["wins_p1"] == 18
        assert result["draws"] == 4
        assert "--batch" in captured["cmd"]
        assert "50" in captured["cmd"]
        assert "--seed" in captured["cmd"]
        assert "42" in captured["cmd"]


class TestRunCommander:
    def test_runs_4_player_commander(self, monkeypatch, tmp_path):
        bin_path = tmp_path / "ai-commander"
        bin_path.write_text("#!/bin/sh\n")
        bin_path.chmod(0o755)
        monkeypatch.setenv("MTG_SKILLS_PHASE_BIN", str(bin_path.parent))

        def fake_run(cmd, **_kwargs):
            output_path = Path([a for a in cmd if a.endswith(".json")][-1])
            output_path.write_text(
                json.dumps(
                    {
                        "winners_by_seat": [12, 8, 6, 4],
                        "games": 30,
                        "draws": 0,
                        "avg_turns": 14.5,
                    }
                )
            )
            r = MagicMock()
            r.returncode = 0
            return r

        monkeypatch.setattr("subprocess.run", fake_run)

        decks = [tmp_path / f"d{i}.json" for i in range(4)]
        for d in decks:
            d.write_text(
                json.dumps(
                    {
                        "name": d.stem,
                        "format": "commander",
                        "main": [],
                        "commander": ["X"],
                    }
                )
            )

        result = _phase.run_commander(decks, games=30, seed=1, timeout_s=600)
        assert result["status"] == "ok"
        assert result["winners_by_seat"] == [12, 8, 6, 4]
        assert result["games"] == 30
