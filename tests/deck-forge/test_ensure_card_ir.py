"""Tests for ``production.ensure_card_ir`` — the launch-time Card IR sidecar
guarantee (ADR-0027).

ADR-0027 deleted 31 keys' oracle-regex detectors; production serves them from the
Card IR sidecar. Without a sidecar the hybrid degrades to regex, silently losing
those lanes. ``ensure_card_ir`` mirrors the ``download-bulk`` ensure: build the
sidecar once at launch (common case → zero loss) and warn loudly + non-blocking
when phase isn't installed so the sidecar can't be built (degraded case → loud).

These are hermetic: ``MTG_SKILLS_CACHE_DIR`` points at a tmp dir, so the real
phase install / user cache are never touched. The in-memory IR cache is cleared
each test so a previous test's load can't leak.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest

from mtg_utils._card_ir.load import (
    card_ir_dir,
    clear_memory_cache,
    sidecar_path,
)
from mtg_utils._deck_forge import production
from mtg_utils._deck_forge.signals import MIGRATED_KEYS

# One minimal phase face-record — enough to project + key the sidecar by oracle_id.
_CARD_DATA = {
    "sol ring": {
        "name": "Sol Ring",
        "scryfall_oracle_id": "sol-ring-oracle-id",
        "card_type": {},
        "keywords": [],
    }
}


def _phase_card_data_path(cache_root):
    """The path ensure_card_ir / build_sidecar resolve to for phase's parse."""
    return cache_root / "phase" / "phase.git" / "client" / "public" / "card-data.json"


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    clear_memory_cache()
    yield
    clear_memory_cache()


def _write_phase_card_data(tmp_path):
    cdp = _phase_card_data_path(tmp_path)
    cdp.parent.mkdir(parents=True, exist_ok=True)
    cdp.write_text(json.dumps(_CARD_DATA))
    return cdp


def test_builds_sidecar_when_missing_and_phase_present(tmp_path, capsys):
    """Phase installed (card-data.json present), no sidecar yet → build it."""
    _write_phase_card_data(tmp_path)
    assert not sidecar_path().exists()

    assert production.ensure_card_ir() is True

    assert sidecar_path().exists()
    payload = json.loads(sidecar_path().read_text())
    assert "sol-ring-oracle-id" in payload["cards"]
    assert "built Card IR sidecar" in capsys.readouterr().err


def test_idempotent_no_rebuild_when_sidecar_fresh(tmp_path):
    """A fresh sidecar → ensure is a single load, never a rebuild (idempotent)."""
    _write_phase_card_data(tmp_path)
    production.ensure_card_ir()  # first call writes the sidecar
    assert sidecar_path().exists()

    # Second call must NOT rebuild — assert build_sidecar is never reached.
    with mock.patch(
        "mtg_utils._card_ir.build.build_sidecar",
        side_effect=AssertionError("rebuilt a fresh sidecar"),
    ) as builder:
        assert production.ensure_card_ir() is True
    builder.assert_not_called()


def test_rebuilds_when_sidecar_stale_version(tmp_path, capsys):
    """A present-but-wrong-version sidecar is rebuilt (not served, not crashed)."""
    _write_phase_card_data(tmp_path)
    card_ir_dir().mkdir(parents=True, exist_ok=True)
    sidecar_path().write_text(
        json.dumps({"version": -1, "phase_tag": "old", "cards": {}})
    )

    assert production.ensure_card_ir() is True

    payload = json.loads(sidecar_path().read_text())
    assert payload["version"] != -1  # rebuilt to the current version
    assert "sol-ring-oracle-id" in payload["cards"]
    assert "built Card IR sidecar" in capsys.readouterr().err


def test_warns_non_blocking_when_phase_absent(tmp_path, capsys):
    """No sidecar AND no phase card-data.json → loud, actionable, non-blocking."""
    assert not _phase_card_data_path(tmp_path).exists()
    assert not sidecar_path().exists()

    # Returns False (degraded) instead of raising — building must continue.
    assert production.ensure_card_ir() is False
    assert not sidecar_path().exists()

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert f"{len(MIGRATED_KEYS)} migrated signal lanes" in err
    assert "playtest-install-phase" in err
    assert "build-card-ir" in err


def test_default_state_warns_but_does_not_crash_without_phase(capsys):
    """default_state calls ensure_card_ir at launch; phase-absent must not block
    the hub from starting (it still returns a usable ForgeState)."""
    state = production.default_state("commander")
    assert state is not None
    assert "WARNING" in capsys.readouterr().err
