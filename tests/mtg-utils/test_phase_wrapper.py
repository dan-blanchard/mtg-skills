"""Tests for the phase-rs subprocess wrapper."""

from __future__ import annotations

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


class TestInstall:
    def test_install_runs_clone_setup_and_cargo(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        calls: list[list[str]] = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        monkeypatch.setattr("subprocess.run", fake_run)
        # Skip prereq checks
        monkeypatch.setattr(_phase, "_ensure_prereqs", lambda: None)

        _phase.install_phase()

        # Expect: git clone, ./scripts/setup.sh, cargo build
        joined = [" ".join(c) if isinstance(c, list) else c for c in calls]
        assert any("git clone" in c for c in joined)
        assert any("setup.sh" in c for c in joined)
        assert any("cargo build" in c and "ai-duel" in c for c in joined)
