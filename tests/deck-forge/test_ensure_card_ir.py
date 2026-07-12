"""Tests for ``production.ensure_card_ir`` — the launch-time Card IR sidecar
guarantee (ADR-0027; ADR-0039 task #80 step 4).

ADR-0027 deleted 31 keys' oracle-regex detectors; production serves them from the
Card IR sidecar. Without a sidecar the hybrid degrades to regex, silently losing
those lanes. ``ensure_card_ir`` mirrors the ``download-bulk`` ensure: build the
sidecar once at launch (common case → zero loss) and warn loudly + non-blocking
when phase isn't installed so the sidecar can't be built (degraded case → loud).

ADR-0039 task #80 step 4 made ``ensure_card_ir`` FLAG-AWARE: with the crosswalk
flag ON (the Stage-4 default), it ensures the crosswalk-backed sidecar
(``ensure_crosswalk_card_ir``); with the flag explicitly OFF (the
``MTG_SKILLS_CROSSWALK_SIGNALS=0`` revert path) it ensures the legacy
(project.py) sidecar (``ensure_legacy_card_ir``), byte-identical to before the
flip. The two sidecars live at distinct on-disk paths and are never conflated.

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
    sidecar_path,
)
from mtg_utils._card_ir.mirror.build import fixtures_dir
from mtg_utils._deck_forge import production
from mtg_utils._deck_forge.signals import MIGRATED_KEYS

FLAG = "MTG_SKILLS_CROSSWALK_SIGNALS"

# One minimal phase face-record for the LEGACY (project.py) builder — it is
# lenient about shape (no ``extra=forbid`` / required-field enforcement), so a
# hand-rolled stub is enough to key the sidecar by oracle_id. Only exercised
# under the explicit ``MTG_SKILLS_CROSSWALK_SIGNALS=0`` revert since Stage-4.
_LEGACY_CARD_DATA = {
    "sol ring": {
        "name": "Sol Ring",
        "scryfall_oracle_id": "sol-ring-oracle-id",
        "card_type": {},
        "keywords": [],
    }
}

# Llanowar Elves' real oracle_id, borrowed from the committed crosswalk fixture.
_CROSSWALK_OID = "68954295-54e3-4303-a6bc-fc4547a4e3a3"


@lru_cache(maxsize=1)
def _crosswalk_card_data() -> dict:
    """A real, schema-valid phase record (Llanowar Elves, borrowed verbatim
    from the committed crosswalk fixture) for the CROSSWALK builder. Unlike
    the legacy builder, ``strict_load_card`` enforces ``extra=forbid`` plus
    required-field checks, so a hand-rolled minimal stub (like
    ``_LEGACY_CARD_DATA``) drifts and is silently dropped — this ensure test
    needs a real record, not a synthetic one."""
    path = fixtures_dir() / "crosswalk_fixture_cards.json"
    cards = json.loads(path.read_text())["cards"]
    return {"llanowar elves": cards["Llanowar Elves"]}


def _phase_card_data_path(cache_root):  # noqa: ARG001 — env-derived, kept for call symmetry
    """The path ensure_card_ir / build_sidecar resolve to for phase's parse.

    Since the v0.8.0 bump, card-data ships in the release tarball and lives at the
    tag-versioned ``_phase._card_data_path()`` (under ``$MTG_SKILLS_CACHE_DIR``,
    set by ``_isolated_cache``). The conftest ``_block_card_data_download`` guard
    serves this path "cached-or-raise", so writing the fixture here makes the
    phase-present path hermetic and leaving it absent drives the phase-absent path.
    """
    return _phase._card_data_path()


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    # Force the deterministic "unset ⇒ ON" Stage-4 default regardless of
    # whatever MTG_SKILLS_CROSSWALK_SIGNALS happens to be set to in the
    # AMBIENT shell environment (the ADR-0039 step 4 gate runs this whole
    # suite with the flag unset/"0"/"1" — a test relying on ambient absence
    # would silently flip behavior under that matrix). Tests that want the
    # explicit revert path still call ``monkeypatch.setenv(FLAG, "0")``
    # themselves, which simply overrides this for their own body.
    monkeypatch.delenv(FLAG, raising=False)
    clear_memory_cache()
    yield
    clear_memory_cache()


def _write_phase_card_data(tmp_path, data: dict | None = None):
    cdp = _phase_card_data_path(tmp_path)
    cdp.parent.mkdir(parents=True, exist_ok=True)
    cdp.write_text(json.dumps(data if data is not None else _LEGACY_CARD_DATA))
    return cdp


# ── flag ON (Stage-4 default, unset) — the CROSSWALK sidecar ─────────────────


def test_builds_crosswalk_sidecar_by_default(tmp_path, capsys):
    """Phase installed, no sidecar yet, flag unset (default ON) → the launch
    ensure builds the CROSSWALK sidecar, not the legacy one (ADR-0039 step 4)."""
    _write_phase_card_data(tmp_path, _crosswalk_card_data())
    assert not crosswalk_sidecar_path().exists()

    assert production.ensure_card_ir() is True

    assert crosswalk_sidecar_path().exists()
    assert not sidecar_path().exists()  # the legacy sidecar is never touched
    payload = json.loads(crosswalk_sidecar_path().read_text())
    assert _CROSSWALK_OID in payload["cards"]
    assert "built crosswalk Card IR sidecar" in capsys.readouterr().err


def test_idempotent_no_rebuild_when_crosswalk_sidecar_fresh(tmp_path):
    """A fresh crosswalk sidecar → ensure is a single load, never a rebuild."""
    _write_phase_card_data(tmp_path, _crosswalk_card_data())
    production.ensure_card_ir()  # first call writes the sidecar
    assert crosswalk_sidecar_path().exists()

    # Second call must NOT rebuild — assert build_crosswalk_sidecar is unreached.
    with mock.patch(
        "mtg_utils._card_ir.build.build_crosswalk_sidecar",
        side_effect=AssertionError("rebuilt a fresh crosswalk sidecar"),
    ) as builder:
        assert production.ensure_card_ir() is True
    builder.assert_not_called()


def test_rebuilds_when_crosswalk_sidecar_stale_version(tmp_path, capsys):
    """A present-but-wrong-version crosswalk sidecar is rebuilt (not served,
    not crashed)."""
    _write_phase_card_data(tmp_path, _crosswalk_card_data())
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
    assert f"{len(MIGRATED_KEYS)} migrated signal lanes" in err
    # Post-bump, card-data is fetched (release tarball), not cargo-built — the
    # actionable fix is re-running build-card-ir-crosswalk with network, not
    # `playtest-install-phase`.
    assert "build-card-ir-crosswalk" in err


def test_default_state_warns_but_does_not_crash_without_phase(capsys):
    """default_state calls ensure_card_ir at launch; phase-absent must not block
    the hub from starting (it still returns a usable ForgeState)."""
    state = production.default_state("commander")
    assert state is not None
    assert "WARNING" in capsys.readouterr().err


# ── the explicit MTG_SKILLS_CROSSWALK_SIGNALS=0 revert path — the LEGACY sidecar ──


def test_builds_legacy_sidecar_when_flag_off(tmp_path, monkeypatch, capsys):
    """Flag explicitly OFF: the launch ensure builds the LEGACY (project.py)
    sidecar — byte-identical to the pre-Stage-4 default."""
    monkeypatch.setenv(FLAG, "0")
    _write_phase_card_data(tmp_path)
    assert not sidecar_path().exists()

    assert production.ensure_card_ir() is True

    assert sidecar_path().exists()
    assert not crosswalk_sidecar_path().exists()  # the crosswalk build never runs
    payload = json.loads(sidecar_path().read_text())
    assert "sol-ring-oracle-id" in payload["cards"]
    assert "built Card IR sidecar" in capsys.readouterr().err


def test_legacy_idempotent_no_rebuild_when_sidecar_fresh(tmp_path, monkeypatch):
    """A fresh legacy sidecar → ensure is a single load, never a rebuild."""
    monkeypatch.setenv(FLAG, "0")
    _write_phase_card_data(tmp_path)
    production.ensure_card_ir()  # first call writes the sidecar
    assert sidecar_path().exists()

    with mock.patch(
        "mtg_utils._card_ir.build.build_sidecar",
        side_effect=AssertionError("rebuilt a fresh sidecar"),
    ) as builder:
        assert production.ensure_card_ir() is True
    builder.assert_not_called()


def test_legacy_warns_non_blocking_when_phase_absent(tmp_path, monkeypatch, capsys):
    """Flag OFF, no sidecar, no phase card-data.json → loud, actionable,
    non-blocking, and the actionable fix names the legacy builder."""
    monkeypatch.setenv(FLAG, "0")
    assert not _phase_card_data_path(tmp_path).exists()
    assert not sidecar_path().exists()

    assert production.ensure_card_ir() is False
    assert not sidecar_path().exists()

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert f"{len(MIGRATED_KEYS)} migrated signal lanes" in err
    assert "build-card-ir" in err
    assert "build-card-ir-crosswalk" not in err
