"""Tests for ``production.ensure_card_ir`` — the launch-time Card IR sidecar
guarantee (ADR-0027; ADR-0039 task #80 step 6).

ADR-0027 deleted 31 keys' oracle-regex detectors; production serves them (and
every other crosswalk-served key) from the crosswalk-backed Card IR sidecar.
Without a sidecar the hybrid degrades to an empty signal set for those lanes
(ADR-0039 task #80 step 6: there is no more regex/legacy-IR fallback to degrade
INTO). ``ensure_card_ir`` mirrors the ``download-bulk`` ensure: build the
sidecar once at launch (common case → zero loss) and warn loudly + non-blocking
when phase isn't installed so the sidecar can't be built (degraded case →
loud).

``ensure_card_ir`` is a thin alias for ``ensure_crosswalk_card_ir`` — the
``MTG_SKILLS_CROSSWALK_SIGNALS`` cutover flag and the legacy (project.py)
sidecar revert path it used to select between are gone (task #80 step 6), and
step 7 deleted the legacy sidecar loader/builder outright, so the crosswalk
sidecar is the only Card IR on disk.

These are hermetic: ``MTG_SKILLS_CACHE_DIR`` points at a tmp dir, so the real
phase install / user cache are never touched. The in-memory IR cache is cleared
each test so a previous test's load can't leak.
"""

from __future__ import annotations

import json
from functools import lru_cache
from unittest import mock

import pytest

from mtg_utils import _phase
from mtg_utils._card_ir.load import (
    card_ir_dir,
    clear_memory_cache,
    crosswalk_sidecar_path,
)
from mtg_utils._card_ir.mirror.build import fixtures_dir
from mtg_utils._deck_forge import production
from mtg_utils._deck_forge.crosswalk_signals import PORTED_KEYS

# Llanowar Elves' real oracle_id, borrowed from the committed crosswalk fixture.
_CROSSWALK_OID = "68954295-54e3-4303-a6bc-fc4547a4e3a3"


@lru_cache(maxsize=1)
def _crosswalk_card_data() -> dict:
    """A real, schema-valid phase record (Llanowar Elves, borrowed verbatim
    from the committed crosswalk fixture). ``strict_load_card`` enforces
    ``extra=forbid`` plus required-field checks, so a hand-rolled minimal stub
    drifts and is silently dropped — this ensure test needs a real record, not
    a synthetic one."""
    path = fixtures_dir() / "crosswalk_fixture_cards.json"
    cards = json.loads(path.read_text())["cards"]
    return {"llanowar elves": cards["Llanowar Elves"]}


def _phase_card_data_path(cache_root):  # noqa: ARG001 — env-derived, kept for call symmetry
    """The path ensure_card_ir / build_crosswalk_sidecar resolve to for phase's
    parse.

    Card-data ships in the release tarball and lives at the tag-versioned
    ``_phase._card_data_path()`` (under ``$MTG_SKILLS_CACHE_DIR``, set by
    ``_isolated_cache``). The conftest ``_block_card_data_download`` guard
    serves this path "cached-or-raise", so writing the fixture here makes the
    phase-present path hermetic and leaving it absent drives the phase-absent
    path.
    """
    return _phase._card_data_path()


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    clear_memory_cache()
    yield
    clear_memory_cache()


def _write_phase_card_data(tmp_path):
    cdp = _phase_card_data_path(tmp_path)
    cdp.parent.mkdir(parents=True, exist_ok=True)
    cdp.write_text(json.dumps(_crosswalk_card_data()))
    return cdp


def test_builds_crosswalk_sidecar(tmp_path, capsys):
    """Phase installed, no sidecar yet → the launch ensure builds the
    crosswalk sidecar."""
    _write_phase_card_data(tmp_path)
    assert not crosswalk_sidecar_path().exists()

    assert production.ensure_card_ir() is True

    assert crosswalk_sidecar_path().exists()
    payload = json.loads(crosswalk_sidecar_path().read_text())
    assert _CROSSWALK_OID in payload["cards"]
    assert "built crosswalk Card IR sidecar" in capsys.readouterr().err


def test_idempotent_no_rebuild_when_sidecar_fresh(tmp_path):
    """A fresh crosswalk sidecar → ensure is a single load, never a rebuild."""
    _write_phase_card_data(tmp_path)
    production.ensure_card_ir()  # first call writes the sidecar
    assert crosswalk_sidecar_path().exists()

    # Second call must NOT rebuild — assert build_crosswalk_sidecar is unreached.
    with mock.patch(
        "mtg_utils._card_ir.build.build_crosswalk_sidecar",
        side_effect=AssertionError("rebuilt a fresh crosswalk sidecar"),
    ) as builder:
        assert production.ensure_card_ir() is True
    builder.assert_not_called()


def test_rebuilds_when_sidecar_stale_version(tmp_path, capsys):
    """A present-but-wrong-version crosswalk sidecar is rebuilt (not served,
    not crashed)."""
    _write_phase_card_data(tmp_path)
    card_ir_dir().mkdir(parents=True, exist_ok=True)
    crosswalk_sidecar_path().write_text(
        json.dumps({"version": -1, "phase_tag": "old", "cards": {}})
    )

    assert production.ensure_card_ir() is True

    payload = json.loads(crosswalk_sidecar_path().read_text())
    assert payload["version"] != -1  # rebuilt to the current version
    assert _CROSSWALK_OID in payload["cards"]
    assert "built crosswalk Card IR sidecar" in capsys.readouterr().err


def test_warns_non_blocking_when_phase_absent(tmp_path, capsys):
    """No sidecar AND no phase card-data.json → loud, actionable, non-blocking."""
    assert not _phase_card_data_path(tmp_path).exists()
    assert not crosswalk_sidecar_path().exists()

    # Returns False (degraded) instead of raising — building must continue.
    assert production.ensure_card_ir() is False
    assert not crosswalk_sidecar_path().exists()

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert f"{len(PORTED_KEYS)} crosswalk signal lanes" in err
    # Card-data is fetched (release tarball), not cargo-built — the
    # actionable fix is re-running build-card-ir-crosswalk with network, not
    # `playtest-install-phase`.
    assert "build-card-ir-crosswalk" in err


def test_default_state_warns_but_does_not_crash_without_phase(capsys):
    """default_state calls ensure_card_ir at launch; phase-absent must not block
    the hub from starting (it still returns a usable ForgeState)."""
    state = production.default_state("commander")
    assert state is not None
    assert "WARNING" in capsys.readouterr().err
