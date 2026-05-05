"""Tests for sidecar I/O.

The sidecar is a write-only audit record of one orchestrator run. There
is no resume path; if a run fails mid-build, the user fixes the
underlying issue and re-runs from scratch. So the only behavior under
test here is the atomic-write contract.
"""

from __future__ import annotations

import json

from mtg_utils.lgs_search import SIDECAR_VERSION, Sidecar, write_sidecar


def test_round_trip(tmp_path):
    sc: Sidecar = {
        "version": SIDECAR_VERSION,
        "generated_at": "2026-05-04T15:30:00Z",
        "allocation": [],
        "online_optimizer_results": None,
        "unfindable": [],
        "basic_lands_needed": {},
    }
    path = tmp_path / "sc.json"
    write_sidecar(path, sc)
    loaded = json.loads(path.read_text())
    assert loaded["version"] == SIDECAR_VERSION
    assert loaded["allocation"] == []


def test_write_creates_parent_dirs(tmp_path):
    """write_sidecar should create the output dir if missing."""
    path = tmp_path / "deep" / "nested" / "sc.json"
    sc: Sidecar = {
        "version": SIDECAR_VERSION,
        "generated_at": "2026-05-04T15:30:00Z",
        "allocation": [],
        "online_optimizer_results": None,
        "unfindable": [],
        "basic_lands_needed": {},
    }
    write_sidecar(path, sc)
    assert path.exists()
    assert json.loads(path.read_text())["version"] == SIDECAR_VERSION


def test_atomic_write_does_not_leave_tmp_on_success(tmp_path):
    """The atomic-write helper uses a per-call NamedTemporaryFile; on
    success the .tmp file should be renamed in place, not lingering.
    """
    path = tmp_path / "sc.json"
    sc: Sidecar = {
        "version": SIDECAR_VERSION,
        "generated_at": "2026-05-04T15:30:00Z",
        "allocation": [],
        "online_optimizer_results": None,
        "unfindable": [],
        "basic_lands_needed": {},
    }
    write_sidecar(path, sc)
    siblings = [p.name for p in tmp_path.iterdir()]
    assert "sc.json" in siblings
    assert not any(name.endswith(".tmp") for name in siblings)
