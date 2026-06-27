"""Tests for the phase-rs subprocess wrapper."""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mtg_utils import _phase


def _fake_server_tarball(
    payload: bytes, *, member: str = "data/card-data.json"
) -> bytes:
    """Build an in-memory .tar.gz carrying a single ``member`` of ``payload``."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(member)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


class _FakeUrlopen:
    """Stand-in for ``urllib.request.urlopen`` that serves bytes and counts hits."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.calls: list[str] = []

    def __call__(self, request, *_a, **_kw):
        # ``request`` is a urllib.request.Request — record the URL it targets.
        self.calls.append(getattr(request, "full_url", str(request)))
        return io.BytesIO(self._body)


class TestPhaseTag:
    def test_phase_tag_is_pinned(self):
        assert _phase.PHASE_TAG == "v0.8.0"


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
    def test_install_runs_clone_then_cargo_binaries_only(self, monkeypatch, tmp_path):
        # Binaries-only now: no card-data-gen (setup.sh) step — card-data comes
        # from ensure_card_data, not from this cargo build.
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
        build_idx = next(
            i for i, c in enumerate(joined) if "cargo build" in c and "ai-duel" in c
        )
        assert clone_idx < build_idx, f"clone must precede cargo build: {joined}"
        # No card-data-gen step in the binaries-only flow.
        assert not any("setup.sh" in c for c in joined), (
            f"install_phase must not run the card-data-gen setup.sh: {joined}"
        )

        version_file = _phase.cache_dir() / "version.txt"
        assert version_file.exists(), "install_phase must write version.txt"
        assert version_file.read_text().strip() == "abc1234def5678"


class TestCoverageGate:
    @pytest.fixture
    def phase_card_data(self, monkeypatch, tmp_path):
        """Stand up a cached card-data.json at the tag-versioned cache path.

        Pre-seeding the cache path means ``ensure_card_data`` returns it with no
        download.
        """
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        path = _phase._card_data_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
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
        return path

    def test_loads_supported_set(self, phase_card_data):
        names = _phase.load_supported_card_names()
        # Supported names are lowercased for case-insensitive matching.
        assert "mountain" in names
        assert "lightning bolt" in names
        assert "goblin guide" in names

    def test_loads_flat_schema(self, monkeypatch, tmp_path):
        # phase v0.1.19 ships card-data.json as a flat {lowercased-name: record}
        # dict, NOT {"cards": [...]}. Reading data.get("cards", []) against it
        # returned an empty set, marking every card unsupported.
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        path = _phase._card_data_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "sol ring": {"name": "Sol Ring"},
                    "lightning bolt": {"name": "Lightning Bolt"},
                }
            )
        )
        _phase.load_supported_card_names.cache_clear()
        names = _phase.load_supported_card_names()
        assert "sol ring" in names
        assert "lightning bolt" in names
        # Proper-case deck input still resolves against the lowercased set.
        report = _phase.coverage_report(["Sol Ring", "Lightning Bolt"])
        assert report["status"] == "full"
        assert report["supported_pct"] == 1.0
        _phase.load_supported_card_names.cache_clear()

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


class TestDeckConversionPassthrough:
    def test_passes_through_phase_native_input(self):
        phase_deck = {
            "name": "Affinity",
            "format": "modern",
            "main": [{"name": "Mountain", "count": 4}],
        }
        out = _phase.to_phase_deck(phase_deck, label="X")
        assert out["name"] == "X"  # relabeled
        assert out["format"] == "modern"
        assert out["main"] == [{"name": "Mountain", "count": 4}]
        # No commander field if not in input.
        assert "commander" not in out

    def test_passes_through_commander_field_when_present(self):
        phase_deck = {
            "name": "Krenko",
            "format": "commander",
            "main": [{"name": "Mountain", "count": 99}],
            "commander": ["Krenko, Mob Boss"],
        }
        out = _phase.to_phase_deck(phase_deck, label="Y")
        assert out["name"] == "Y"
        assert out["commander"] == ["Krenko, Mob Boss"]

    def test_non_phase_native_still_converts(self):
        deck = {
            "format": "modern",
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
        }
        out = _phase.to_phase_deck(deck, label="Burn")
        assert {"name": "Lightning Bolt", "count": 4} in out["main"]


class TestRunDuelError:
    def test_called_process_error_raises_phase_runtime(self, monkeypatch, tmp_path):
        bin_path = tmp_path / "ai-duel"
        bin_path.write_text("#!/bin/sh\n")
        bin_path.chmod(0o755)
        monkeypatch.setenv("MTG_SKILLS_PHASE_BIN", str(bin_path))

        def fake_run(cmd, **_kwargs):
            raise subprocess.CalledProcessError(
                returncode=2,
                cmd=cmd,
                stderr="card 'Foo' not implemented",
            )

        monkeypatch.setattr("subprocess.run", fake_run)

        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text("{}")
        b.write_text("{}")

        with pytest.raises(_phase.PhaseRuntimeError) as excinfo:
            _phase.run_duel(a, b, games=10, seed=0, format_="modern", timeout_s=60)
        assert excinfo.value.stderr == "card 'Foo' not implemented"
        assert "code 2" in str(excinfo.value)


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


class TestEnsureCardData:
    def test_returns_cached_path_without_downloading(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        dest = _phase._card_data_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text('{"sol ring": {"name": "Sol Ring"}}')

        fake = _FakeUrlopen(b"unused")
        monkeypatch.setattr("urllib.request.urlopen", fake)

        out = _phase.ensure_card_data()
        assert out == dest
        assert fake.calls == [], "must NOT download when the cache exists"

    def test_downloads_and_extracts_to_tag_versioned_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        payload = b'{"lightning bolt": {"name": "Lightning Bolt"}}'
        fake = _FakeUrlopen(_fake_server_tarball(payload))
        monkeypatch.setattr("urllib.request.urlopen", fake)

        out = _phase.ensure_card_data()

        expected = (
            tmp_path / "phase" / "card-data" / f"card-data-{_phase.PHASE_TAG}.json"
        )
        assert out == expected
        assert out.read_bytes() == payload
        # Downloaded the LINUX server asset for the pinned tag.
        assert len(fake.calls) == 1
        assert _phase.PHASE_SERVER_ASSET in fake.calls[0]
        assert _phase.PHASE_TAG in fake.calls[0]

    def test_keyed_by_phase_tag_refetches_on_bump(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))

        # Seed the cache for the current tag → no download.
        first = _FakeUrlopen(_fake_server_tarball(b'{"a": {"name": "A"}}'))
        monkeypatch.setattr("urllib.request.urlopen", first)
        path_v1 = _phase.ensure_card_data()
        assert len(first.calls) == 1
        # Idempotent: second call for the SAME tag does not re-download.
        again = _phase.ensure_card_data()
        assert again == path_v1
        assert len(first.calls) == 1

        # A tag bump points at a different path and refetches.
        monkeypatch.setattr(_phase, "PHASE_TAG", "v9.9.9")
        second = _FakeUrlopen(_fake_server_tarball(b'{"b": {"name": "B"}}'))
        monkeypatch.setattr("urllib.request.urlopen", second)
        path_v2 = _phase.ensure_card_data()
        assert path_v2 != path_v1
        assert "v9.9.9" in path_v2.name
        assert len(second.calls) == 1
        # Old tag's cache file is untouched.
        assert path_v1.exists()

    def test_fails_loud_on_bad_asset(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        # Tarball is missing the data/card-data.json member.
        bad = _fake_server_tarball(b"x", member="data/other.json")
        fake = _FakeUrlopen(bad)
        monkeypatch.setattr("urllib.request.urlopen", fake)

        with pytest.raises(RuntimeError) as excinfo:
            _phase.ensure_card_data()
        msg = str(excinfo.value)
        assert "card-data.json" in msg
        assert _phase.PHASE_TAG in msg
        # No partial cache file left behind on failure.
        assert not _phase._card_data_path().exists()


class TestBuildAndCoverageUseEnsure:
    def test_build_sidecar_calls_ensure_card_data(self, monkeypatch, tmp_path):
        from mtg_utils._card_ir import build as build_mod

        called = {"n": 0}
        cdp = tmp_path / "card-data.json"
        cdp.write_text("{}")

        def fake_ensure():
            called["n"] += 1
            return cdp

        monkeypatch.setattr(_phase, "ensure_card_data", fake_ensure)
        out = tmp_path / "sidecar.json"
        _path, stats = build_mod.build_sidecar(out_path=out)
        assert called["n"] == 1
        assert out.exists()
        assert stats["phase_tag"] == _phase.PHASE_TAG

    def test_coverage_uses_ensure_card_data(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        payload = json.dumps({"sol ring": {"name": "Sol Ring"}}).encode()
        fake = _FakeUrlopen(_fake_server_tarball(payload))
        monkeypatch.setattr("urllib.request.urlopen", fake)
        _phase.load_supported_card_names.cache_clear()

        names = _phase.load_supported_card_names()
        assert "sol ring" in names
        assert len(fake.calls) == 1
        _phase.load_supported_card_names.cache_clear()
